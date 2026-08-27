"""费用计算与配额累计：按 DeepSeek 价目表折算，traceId 关联每次调用。"""
import logging
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.quota import Quota

logger = logging.getLogger(__name__)


def current_period() -> str:
    return datetime.now().strftime("%Y-%m")


def compute_cost_cny(prompt_tokens: int, completion_tokens: int) -> float:
    settings = get_settings()
    cost = (
        prompt_tokens * settings.deepseek_price_input_per_million
        + completion_tokens * settings.deepseek_price_output_per_million
    ) / 1_000_000
    return round(cost, 6)


async def accumulate_usage(
    db: AsyncSession, user_id: uuid.UUID, prompt_tokens: int, completion_tokens: int
) -> Quota:
    """累加本月用量与费用，返回最新配额行。"""
    settings = get_settings()
    period = current_period()
    quota = (
        await db.execute(select(Quota).where(Quota.user_id == user_id, Quota.period == period))
    ).scalar_one_or_none()
    if quota is None:
        quota = Quota(user_id=user_id, period=period, limit_tokens=settings.quota_monthly_tokens)
        db.add(quota)
    quota.prompt_tokens += prompt_tokens
    quota.completion_tokens += completion_tokens
    quota.cost_cny = round(quota.cost_cny + compute_cost_cny(prompt_tokens, completion_tokens), 6)
    await db.flush()
    logger.info(
        "usage accumulated",
        extra={
            "event": "usage",
            "user_id": str(user_id),
            "extra": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "period_total": quota.prompt_tokens + quota.completion_tokens,
                "cost_cny": quota.cost_cny,
            },
        },
    )
    return quota


async def quota_exhausted(db: AsyncSession, user_id: uuid.UUID) -> bool:
    settings = get_settings()
    quota = (
        await db.execute(
            select(Quota).where(Quota.user_id == user_id, Quota.period == current_period())
        )
    ).scalar_one_or_none()
    if quota is None:
        return False
    return quota.prompt_tokens + quota.completion_tokens >= (
        quota.limit_tokens or settings.quota_monthly_tokens
    )
