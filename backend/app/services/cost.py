"""费用计算与配额累计：按 DeepSeek 价目表折算，traceId 关联每次调用。

配额检查与占用合并为单条 UPDATE ... WHERE total < limit，避免并发 check-then-act 竞态。
"""
import logging
import uuid
from datetime import datetime

from sqlalchemy import select, text
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


async def ensure_quota_row(db: AsyncSession, user_id: uuid.UUID) -> None:
    """幂等创建当月配额行（不存在则插入，limit 取配置默认值）。"""
    settings = get_settings()
    period = current_period()
    existing = (
        await db.execute(
            select(Quota).where(Quota.user_id == user_id, Quota.period == period)
        )
    ).scalar_one_or_none()
    if existing is None:
        quota = Quota(user_id=user_id, period=period, limit_tokens=settings.quota_monthly_tokens)
        db.add(quota)
        try:
            await db.flush()
        except Exception:
            # 并发首请求竞态：唯一约束冲突，回滚后重新查询
            await db.rollback()
        return


async def try_consume_quota(
    db: AsyncSession, user_id: uuid.UUID, prompt_tokens: int, completion_tokens: int
) -> tuple[bool, Quota | None]:
    """原子地占用配额：检查未超限 + 累加。

    postgresql 模式用单条 UPDATE ... WHERE total+new <= limit RETURNING（行锁保证并发安全）；
    sqlite 模式（本地演示）退化为读-判-写——并发场景弱，但本地单用户演示可接受。
    返回 (ok, quota)：ok=False 表示已达上限拒绝占用。
    """
    settings = get_settings()
    await ensure_quota_row(db, user_id)
    period = current_period()
    cost_cny = compute_cost_cny(prompt_tokens, completion_tokens)

    if settings.db_backend == "sqlite":
        # sqlite 模式：读-判-写（演示场景，低并发）
        quota = (
            await db.execute(
                select(Quota).where(Quota.user_id == user_id, Quota.period == period)
            )
        ).scalar_one()
        if quota.prompt_tokens + quota.completion_tokens + prompt_tokens + completion_tokens > (
            quota.limit_tokens or settings.quota_monthly_tokens
        ):
            return False, None
        quota.prompt_tokens += prompt_tokens
        quota.completion_tokens += completion_tokens
        quota.cost_cny = round(quota.cost_cny + cost_cny, 6)
        await db.flush()
    else:
        # postgresql 模式：原子 UPDATE
        result = await db.execute(
            text(
                """
                UPDATE quotas
                SET prompt_tokens = prompt_tokens + :p,
                    completion_tokens = completion_tokens + :c,
                    cost_cny = round(cost_cny + :cost, 6),
                    updated_at = now()
                WHERE user_id = :uid
                  AND period = :period
                  AND (prompt_tokens + completion_tokens + :p + :c) <= limit_tokens
                RETURNING *
                """
            ),
            {
                "uid": str(user_id),
                "period": period,
                "p": prompt_tokens,
                "c": completion_tokens,
                "cost": cost_cny,
            },
        )
        if result.first() is None:
            return False, None
    quota = (
        await db.execute(
            select(Quota).where(Quota.user_id == user_id, Quota.period == period)
        )
    ).scalar_one()
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
    return True, quota


async def accumulate_usage(
    db: AsyncSession, user_id: uuid.UUID, prompt_tokens: int, completion_tokens: int
) -> Quota | None:
    """兼容旧调用：尝试占用配额，超限时静默不累计（已在流式中途，无法回滚已消耗的 token）。

    推荐改用 try_consume_quota 做预占；本函数用于流末尾补登——
    若并发导致超出 limit，记录超额但不再加（避免无限累加），
    实际超额量由配额角标展示并触发下次提问被拒。
    """
    ok, quota = await try_consume_quota(db, user_id, prompt_tokens, completion_tokens)
    if not ok:
        logger.warning(
            "quota exceeded during accumulation, usage not recorded",
            extra={"event": "quota_overflow", "user_id": str(user_id),
                   "extra": {"prompt": prompt_tokens, "completion": completion_tokens}},
        )
    return quota


async def quota_exhausted(db: AsyncSession, user_id: uuid.UUID) -> bool:
    """快查：当月是否已达上限。仅用于请求入口的快速拒绝；
    真正的占用以 try_consume_quota 的原子 UPDATE 为准。"""
    settings = get_settings()
    await ensure_quota_row(db, user_id)
    quota = (
        await db.execute(
            select(Quota).where(Quota.user_id == user_id, Quota.period == current_period())
        )
    ).scalar_one()
    return quota.prompt_tokens + quota.completion_tokens >= (
        quota.limit_tokens or settings.quota_monthly_tokens
    )
