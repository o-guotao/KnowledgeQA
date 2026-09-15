from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.config import get_settings
from app.core.errors import register_error_handlers
from app.core.tracing import TraceMiddleware
from app.logging_config import configure_logging
from app.version import get_version

configure_logging()

settings = get_settings()

app = FastAPI(
    title="Web Agent - 内部知识问答",
    version=get_version(),  # 单一来源：根 VERSION 文件
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
    """启动校验：embedding 后端真实可用、维度匹配、生产禁止非语义降级。

    production 环境校验失败必须 fail fast（raise），避免以随机召回对外服务；
    development 降级到 hash 时仅记警告（链路可演示，召回无语义）。
    """
    import logging

    # sqlite 本地模式：直接 create_all 建表（跳过 alembic）+ seed 演示账号
    if settings.db_backend == "sqlite":
        from app.db import create_all_tables
        from scripts.seed import seed

        await create_all_tables()
        await seed()
        logging.getLogger(__name__).info("sqlite mode: tables created + seeded")

    from app.services.embeddings import verify_embedding_ready

    ok, message = await verify_embedding_ready()
    if not ok:
        if settings.environment == "production":
            # 生产 fail fast：宁可起不来也不以错误状态对外服务
            raise RuntimeError(f"embedding 生产启动校验失败：{message}")
        logging.getLogger(__name__).warning(
            "embedding startup check failed (dev, continuing): %s",
            message, extra={"event": "embedding_verify_failed"},
        )
    else:
        logging.getLogger(__name__).info("startup check: %s", message)


@app.get("/api/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
