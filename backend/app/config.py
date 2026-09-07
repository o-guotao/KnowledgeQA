"""应用配置：全部经环境变量注入，密钥仅存在于服务端。"""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 数据库
    database_url: str = "postgresql+asyncpg://webagent:webagent_secret@localhost:5432/webagent"

    # 对象存储
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

    # 任务与配额
    task_timeout_seconds: float = 300.0
    task_max_retries: int = 3
    task_retry_base_seconds: float = 5.0
    quota_monthly_tokens: int = 1_000_000

    # seed
    seed_admin_username: str = "demo"
    seed_admin_password: str = "demo1234"


@lru_cache
def get_settings() -> Settings:
    return Settings()
