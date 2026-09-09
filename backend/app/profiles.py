"""部署 Profile：一个 ``DEPLOY_PROFILE`` 开关切换整套后端基础设施。

把「本地 / 线上」两套差异配置收敛为两个命名集合，避免逐一修改 ``DB_BACKEND``、
``STORAGE_BACKEND``、``EMBEDDING_BACKEND`` 等多个键值。

优先级（高 → 低）::

    显式环境变量 / .env 配置项  >  PROFILE_DEFAULTS[deploy_profile]  >  config.py 字段默认值

即：profile 只为「你没有显式配置」的字段提供默认值；一旦某字段被显式设置
（出现在环境变量或 .env 中），永远以显式值为准，profile 不覆盖它。
"""
from typing import Any, Literal

DeployProfile = Literal["local", "production"]

PROFILE_DEFAULTS: dict[str, dict[str, Any]] = {
    # 本地：无 Docker 也能跑通演示。
    # SQLite 文件库 + 本地文件夹存储 + fastembed 本地向量；允许 hash 降级兜底。
    "local": {
        "environment": "development",
        "db_backend": "sqlite",
        "database_url": "sqlite:///./webagent.db",
        "storage_backend": "local",
        "local_storage_dir": "./.local_storage",
        "embedding_backend": "fastembed",
        "allow_hash_embedding": True,
        "rerank_enabled": False,
        "hybrid_search_enabled": True,
    },
    # 线上：Docker 全套生产依赖。
    # Postgres+pgvector + MinIO + fastembed 本地向量 + 重排；禁止无语义 hash 降级（启动校验 fail fast）。
    "production": {
        "environment": "production",
        "db_backend": "postgresql",
        "database_url": "postgresql+asyncpg://webagent:webagent_secret@localhost:5432/webagent",
        "storage_backend": "minio",
        "embedding_backend": "fastembed",
        "allow_hash_embedding": False,
        "rerank_enabled": True,
        "hybrid_search_enabled": True,
    },
}
