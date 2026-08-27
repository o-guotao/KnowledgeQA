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
        # INSERT ... ON CONFLICT DO NOTHING：并发首请求时只有一行胜出
        await db.execute(
            text(
                """
                INSERT INTO quotas (id, user_id, period, limit_tokens)
                VALUES (:id, :uid, :period, :lim)
                ON CONFLICT (user_id, period) DO NOTHING
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "uid": str(user_id),
                "period": period,
                "lim": settings.quota_monthly_tokens,
            },
        )
        await db.flush()


async def try_consume_quota(
    db: AsyncSession, user_id: uuid.UUID, prompt_tokens: int, completion_tokens: int
) -> tuple[bool, Quota | None]:
    """原子地占用配额：单条 UPDATE 同时做"检查未超限 + 累加"。

    返回 (ok, quota)：ok=False 表示已达上限拒绝占用；ok=True 时 quota 为更新后的行。
    保证并发安全——多请求同时调用，只有未超限的能 UPDATE 到行。
    """
    settings = get_settings()
    await ensure_quota_row(db, user_id)
    cost_cny = compute_cost_cny(prompt_tokens, completion_tokens)
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
            "period": current_period(),
            "p": prompt_tokens,
            "c": completion_tokens,
            "cost": cost_cny,
        },
    )
    row = result.first()
    if row is None:
        return False, None
    quota = (
        await db.execute(
            select(Quota).where(Quota.user_id == user_id, Quota.period == current_period())
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
