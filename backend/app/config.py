"""应用配置：全部经环境变量注入，密钥仅存在于服务端。"""
from functools import lru_cache

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

    # DeepSeek
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    deepseek_timeout_seconds: float = 60.0
    deepseek_price_input_per_million: float = 2.0
    deepseek_price_output_per_million: float = 8.0

    # Embedding
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_dim: int = 512

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
