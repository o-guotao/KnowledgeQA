"""异步数据库引擎与会话。postgresql 生产 / sqlite 本地开发演示。"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()

if settings.db_backend == "sqlite":
    # sqlite：aiosqlite 驱动，check_same_thread=False 允许跨线程
    url = settings.database_url
    if url.startswith("sqlite:///"):
        # 用户给的是同步驱动 URL，规范化为 aiosqlite
        url = url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    elif not url.startswith("sqlite"):
        url = "sqlite+aiosqlite:///./webagent.db"
    engine = create_async_engine(url, connect_args={"check_same_thread": False})
else:
    engine = create_async_engine(settings.database_url, pool_size=10, max_overflow=20)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def create_all_tables() -> None:
    """sqlite 模式：直接 metadata.create_all 建表（跳过 alembic）。postgresql 用 alembic。"""
    import app.models  # noqa: F401 确保全部模型已注册

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
