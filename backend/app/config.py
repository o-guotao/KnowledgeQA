"""应用配置：全部经环境变量注入，密钥仅存在于服务端。"""
from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.profiles import DeployProfile, PROFILE_DEFAULTS

# 项目根 .env（backend/app/config.py -> 上两级 = 项目根）。无论 cwd 在哪都能读到，本地直跑与 docker 共享密钥。
_ROOT_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ROOT_ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    # 部署 Profile：一个开关切换整套后端基础设施（默认值见 app/profiles.py）。
    # local=本地无 Docker 演示（sqlite + 本地文件夹存储）；production=Docker 生产（postgres + minio）。
    # 显式设置的具体配置项（env/.env）永远优先于 profile 默认值。
    deploy_profile: DeployProfile = "production"

    # 数据库（postgresql 生产 / sqlite 本地开发演示）
    db_backend: str = "postgresql"  # postgresql | sqlite
    database_url: str = "postgresql+asyncpg://webagent:webagent_secret@localhost:5432/webagent"

    # 对象存储（minio 生产 / local 本地文件夹开发演示）
    storage_backend: str = "minio"  # minio | local
    local_storage_dir: str = "./.local_storage"
    minio_endpoint: str = "localhost:9000"
    minio_root_user: str = "minioadmin"
    minio_root_password: str = "minioadmin123"
    minio_bucket: str = "web-agent-docs"
    minio_secure: bool = False

    # 鉴权
    jwt_secret: str = "dev-only-secret"
    jwt_expire_minutes: int = 720

    # CORS（虚机部署改为实际前端域名，逗号分隔）
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # DeepSeek
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    deepseek_timeout_seconds: float = 60.0
    deepseek_price_input_per_million: float = 2.0
    deepseek_price_output_per_million: float = 8.0

    # 用户自定义模型配置：Fernet 32-byte URL-safe base64 key，由部署环境注入。
    # 留空时旧 DEEPSEEK_* 配置仍可使用，但不能创建用户配置。
    provider_config_encryption_key: str = Field(default="", validation_alias="MODEL_CONFIG_ENCRYPTION_KEY")

    # 运行环境：production 时 embedding 必须真实可用，hash 降级会被启动校验拒绝
    environment: str = "development"  # development | production

    # Embedding（后端可切：fastembed 本地 / openai 兼容 API / sentence_transformers / hash 开发降级）
    embedding_backend: str = "fastembed"  # fastembed | openai | sentence_transformers | hash
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_dim: int = 512
    # openai 兼容 embedding 后端（DeepSeek 无 embedding API，可用 OpenAI/通义等）
    openai_embedding_base_url: str = "https://api.openai.com"
    openai_embedding_api_key: str = ""
    openai_embedding_model: str = "text-embedding-3-small"
    # 是否允许 hash 降级（无语义，仅开发演示跑通链路）。生产必须 false。
    allow_hash_embedding: bool = True

    # 重排序（cross-encoder rerank，依赖 fastembed；生产 Docker 可开启）
    rerank_enabled: bool = False
    rerank_model: str = "BAAI/bge-reranker-base"
    # 召回候选倍数：先召回 top_k*multiplier 再重排取 top_k
    rerank_candidate_multiplier: int = 4

    # 切分与召回
    chunk_size: int = 512
    chunk_overlap: int = 64
    rag_top_k: int = 5
    # 混合检索：向量 + 关键词 RRF 融合
    hybrid_search_enabled: bool = True
    # 关键词召回引擎：true=BM25（jieba+rank_bm25 内存索引，推荐）；
    # false=数据库回退（Postgres tsvector / SQLite LIKE）
    bm25_enabled: bool = True
    # 切分策略：window 滑动窗口 / semantic 语义分块（按 Markdown 标题层级，父子块）
    chunk_strategy: str = "window"  # window | semantic

    # Langfuse 追踪（可观测性：LLM 调用/召回/重排追踪）。无 key 时自动禁用（no-op）
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # 任务与配额
    task_timeout_seconds: float = 300.0
    task_max_retries: int = 3
    task_retry_base_seconds: float = 5.0
    quota_monthly_tokens: int = 1_000_000

    # seed
    seed_admin_username: str = "demo"
    seed_admin_password: str = "demo1234"

    @model_validator(mode="after")
    def _apply_profile_defaults(self) -> "Settings":
        """用 deploy_profile 的默认值补全「未显式设置」的字段；显式配置（env/.env）永远优先。"""
        for field, value in PROFILE_DEFAULTS[self.deploy_profile].items():
            if field not in self.model_fields_set:
                setattr(self, field, value)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
