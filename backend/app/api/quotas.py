from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.security import get_current_user
from app.db import get_db
from app.models.quota import Quota
from app.models.user import User
from app.schemas.quota import QuotaOut
from app.services.cost import current_period

router = APIRouter()


@router.get("/quotas/me", response_model=QuotaOut)
async def my_quota(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> QuotaOut:
    settings = get_settings()
    quota = (
        await db.execute(
            select(Quota).where(Quota.user_id == user.id, Quota.period == current_period())
        )
    ).scalar_one_or_none()
    prompt = quota.prompt_tokens if quota else 0
    completion = quota.completion_tokens if quota else 0
    limit = (quota.limit_tokens if quota else 0) or settings.quota_monthly_tokens
    total = prompt + completion
    return QuotaOut(
        period=current_period(),
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total,
        cost_cny=quota.cost_cny if quota else 0.0,
        limit_tokens=limit,
        remaining_tokens=max(0, limit - total),
        exhausted=total >= limit,
    )
