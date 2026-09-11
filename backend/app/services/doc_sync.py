"""文档失效检测：stale 是「文档入库配置快照 vs 当前 settings」的纯函数，不落库。

ingest_signature 格式：{chunk_strategy}|{chunk_size}|{chunk_overlap}|{embedding_backend}|{embedding_model}
由 worker 在每次 ingest 成功时写入；空串表示历史文档（迁移前）未记录，不参与 stale 判定。
"""
from app.config import Settings
from app.models.document import Document

_SEP = "|"


def current_ingest_signature(
    settings: Settings, chunk_size: int | None = None, chunk_overlap: int | None = None
) -> str:
    """当前配置的入库签名。chunk 参数默认取全局 settings，可按文档快照覆盖。"""
    size = settings.chunk_size if chunk_size is None else chunk_size
    overlap = settings.chunk_overlap if chunk_overlap is None else chunk_overlap
    return _SEP.join(
        [
            settings.chunk_strategy,
            str(size),
            str(overlap),
            settings.embedding_backend.lower(),
            settings.embedding_model,
        ]
    )


def stale_reasons(document: Document, settings: Settings) -> list[str]:
    """列出文档过期原因；仅 ready 且已记录签名的文档参与判定。"""
    if document.status != "ready" or not document.ingest_signature:
        return []
    stored = document.ingest_signature.split(_SEP)
    if len(stored) != 5:
        return ["入库配置快照格式过期，建议重新切分"]
    reasons: list[str] = []
    if stored[0] != settings.chunk_strategy:
        reasons.append(f"切分策略已变更（{stored[0]} → {settings.chunk_strategy}）")
    if stored[1] != str(settings.chunk_size) or stored[2] != str(settings.chunk_overlap):
        reasons.append(
            f"切块参数已变更（{stored[1]}/{stored[2]} → {settings.chunk_size}/{settings.chunk_overlap}）"
        )
    if stored[3] != settings.embedding_backend.lower() or stored[4] != settings.embedding_model:
        reasons.append(
            f"Embedding 已变更（{stored[3]}/{stored[4]} → "
            f"{settings.embedding_backend.lower()}/{settings.embedding_model}）"
        )
    return reasons


def is_stale(document: Document, settings: Settings) -> bool:
    return bool(stale_reasons(document, settings))
