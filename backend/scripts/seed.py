"""seed：创建演示账号与当月配额行（幂等）。"""
import asyncio

from sqlalchemy import select

from app.config import get_settings
from app.core.security import hash_password
from app.db import SessionLocal
from app.models.quota import Quota
from app.models.user import User
from app.services.cost import current_period


async def seed() -> None:
    settings = get_settings()
    async with SessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.username == settings.seed_admin_username))
        ).scalar_one_or_none()
        if user is None:
            user = User(
                username=settings.seed_admin_username,
                password_hash=hash_password(settings.seed_admin_password),
                display_name="演示账号",
                role="admin",
            )
            db.add(user)
            await db.flush()
            print(f"[seed] 创建演示账号 {settings.seed_admin_username}/{settings.seed_admin_password}")
        quota = (
            await db.execute(
                select(Quota).where(Quota.user_id == user.id, Quota.period == current_period())
            )
        ).scalar_one_or_none()
        if quota is None:
            db.add(Quota(user_id=user.id, period=current_period(), limit_tokens=settings.quota_monthly_tokens))
        await db.commit()
        print("[seed] done")


if __name__ == "__main__":
    asyncio.run(seed())
