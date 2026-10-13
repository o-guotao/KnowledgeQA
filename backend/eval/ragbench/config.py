"""实验配置：单变量实验数据类 + env 注入/恢复 + 硬编码变量 monkey-patch。

变量注入方式（已逐个核实代码入口）：
- env + get_settings.cache_clear()：top_k(RAG_TOP_K)/candidate 倍数/hybrid/bm25/rerank/chunk 三件套
- monkey-patch：RRF k 值（rag._rrf_fuse 硬编码 k=60）
- runner 行为参数：top_k_mode（fixed/auto/router）、context_chunks、prompt_variant、gen_model
"""
from __future__ import annotations

import functools
import os
from dataclasses import asdict, dataclass

# apply/restore 时覆盖的全部 env 键（每个实验都显式设置，保证基线不受 .env 污染）
ENV_KEYS = (
    "RAG_TOP_K",
    "RERANK_CANDIDATE_MULTIPLIER",
    "HYBRID_SEARCH_ENABLED",
    "BM25_ENABLED",
    "RERANK_ENABLED",
    "CHUNK_SIZE",
    "CHUNK_OVERLAP",
    "CHUNK_STRATEGY",
)

TOP_K_MODES = ("fixed", "auto", "router")
PROMPT_VARIANTS = ("default", "concise")


@dataclass(frozen=True)
class ExperimentConfig:
    """一轮实验的完整配置快照。默认值 = 系统当前默认配置（基线）。"""

    tag: str = "baseline"
    desc: str = ""
    # 检索参数
    top_k: int = 5
    top_k_mode: str = "fixed"  # fixed=固定 top_k / auto=L2 启发式 / router=L4 LLM 分类
    candidate_multiplier: int = 4  # 仅 rerank 开启时生效（rag.py 行为）
    hybrid: bool = True
    bm25: bool = True
    rrf_k: int = 60
    rerank: bool = False
    # 索引/切分参数
    chunk_size: int = 512
    chunk_overlap: int = 64
    chunk_strategy: str = "window"  # window | semantic
    # 生成参数
    context_chunks: int = 5  # 注入 prompt 的块数上限
    prompt_variant: str = "default"  # default | concise
    gen_model: str | None = None  # None=settings.deepseek_model
    # L4 Router top_k 映射覆盖（None=用 router.py 默认映射 3/10/10/8）；
    # 映射硬编码且无 Settings 字段，经 apply_config monkey-patch 注入
    router_factual: int | None = None
    router_list: int | None = None
    router_comparison: int | None = None
    router_summary: int | None = None

    def kb_key(self) -> tuple[str, int, int]:
        """知识库缓存键：切分三要素相同的实验共享一份建库。"""
        return (self.chunk_strategy, self.chunk_size, self.chunk_overlap)

    def to_snapshot(self) -> dict:
        return asdict(self)

    def diff_vs(self, other: "ExperimentConfig") -> dict[str, tuple]:
        """与另一配置的差异字段 {field: (other, self)}，用于单变量校验与报告。"""
        a, b = asdict(other), asdict(self)
        return {k: (a[k], b[k]) for k in a if a[k] != b[k] and k not in ("tag", "desc")}


class apply_config:
    """实验配置生效上下文：env 覆盖 + Settings 缓存清理 + 单例重置 + RRF monkey-patch。

    退出时恢复全部 env 与原函数，保证实验间隔离（参照 eval_runner._group_env 先例）。
    """

    def __init__(self, cfg: ExperimentConfig):
        self.cfg = cfg
        self._saved_env: dict[str, str | None] = {}
        self._orig_rrf = None
        self._orig_router_map = None

    def __enter__(self) -> ExperimentConfig:
        from app.config import get_settings

        cfg = self.cfg
        self._saved_env = {k: os.environ.get(k) for k in ENV_KEYS}
        os.environ["RAG_TOP_K"] = str(cfg.top_k)
        os.environ["RERANK_CANDIDATE_MULTIPLIER"] = str(cfg.candidate_multiplier)
        os.environ["HYBRID_SEARCH_ENABLED"] = "true" if cfg.hybrid else "false"
        os.environ["BM25_ENABLED"] = "true" if cfg.bm25 else "false"
        os.environ["RERANK_ENABLED"] = "true" if cfg.rerank else "false"
        os.environ["CHUNK_SIZE"] = str(cfg.chunk_size)
        os.environ["CHUNK_OVERLAP"] = str(cfg.chunk_overlap)
        os.environ["CHUNK_STRATEGY"] = cfg.chunk_strategy
        get_settings.cache_clear()

        # 单例重置：reranker 跨实验复用会带错配置；BM25 索引需按新库重建
        import app.services.rerank as rk
        from app.services import bm25_index

        rk._reranker = None
        bm25_index._state = None

        # RRF k 值硬编码（rag.py:248），monkey-patch 注入
        if cfg.rrf_k != 60:
            from app.services import rag

            self._orig_rrf = rag._rrf_fuse
            rag._rrf_fuse = functools.partial(self._orig_rrf, k=cfg.rrf_k)

        # L4 Router：分类结果缓存按进程驻留，跨实验必须重置（避免旧档位决策泄漏）；
        # top_k 映射硬编码（router.py:46 _CATEGORY_TOP_K），按配置覆盖 monkey-patch
        from app.services.agents import router as _router

        _router.reset_cache()
        overrides = {
            "factual": cfg.router_factual,
            "list": cfg.router_list,
            "comparison": cfg.router_comparison,
            "summary": cfg.router_summary,
        }
        overrides = {k: v for k, v in overrides.items() if v is not None}
        if overrides:
            self._orig_router_map = _router._CATEGORY_TOP_K
            _router._CATEGORY_TOP_K = {**self._orig_router_map, **overrides}
        return self.cfg

    def __exit__(self, *exc) -> bool:
        from app.config import get_settings

        if self._orig_rrf is not None:
            from app.services import rag

            rag._rrf_fuse = self._orig_rrf
        if self._orig_router_map is not None:
            from app.services.agents import router as _router

            _router._CATEGORY_TOP_K = self._orig_router_map
            _router.reset_cache()
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        get_settings.cache_clear()
        return False
