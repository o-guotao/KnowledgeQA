"""异步数据库引擎与会话。"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()

if settings.db_backend == "sqlite":
    engine = create_async_engine(
        "sqlite+aiosqlite:///" + settings.database_url.replace("sqlite:///", ""),
        connect_args={"check_same_thread": False},
    )
else:
    engine = create_async_engine(settings.database_url, pool_size=10, max_overflow=20)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session

