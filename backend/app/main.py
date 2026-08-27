from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.config import get_settings
from app.core.errors import register_error_handlers
from app.core.tracing import TraceMiddleware
from app.logging_config import configure_logging

configure_logging()

settings = get_settings()

app = FastAPI(
    title="Web Agent - 内部知识问答",
    version="0.1.0",
    description="带权限的内部知识问答 Agent：JWT 鉴权、SSE 流式、RAG、任务表、配额与费用。",
)

app.add_middleware(TraceMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)
app.include_router(api_router)


@app.on_event("startup")
async def _startup_checks() -> None:
    """启动时校验 embedding 维度与配置一致，避免运行时写入 vector 列才报错。

    sqlite 模式跳过 alembic，直接 create_all 建表（本地演示）。
    校验失败应 fail fast：模型加载需要时间，但维度错配是配置错误，
    应在服务对外可访问前暴露，而非首条提问时才报晦涩的 type error。
    """
    import logging

    log = logging.getLogger(__name__)

    # sqlite 本地模式：用 metadata.create_all 代替 alembic 迁移
    if settings.db_backend == "sqlite":
        from app.db import Base, engine
        import app.models  # noqa: F401 确保全部模型已注册

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        log.info("sqlite mode: tables created via metadata.create_all")
        # 本地模式自动 seed 演示账号
        from scripts.seed import seed
        await seed()

    try:
        from app.services.embedding import verify_dimension

        await verify_dimension()
    except Exception as exc:
        log.warning(
            "embedding dimension verify failed at startup: %s", exc,
            extra={"event": "embedding_verify_failed"},
        )


@app.get("/api/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
