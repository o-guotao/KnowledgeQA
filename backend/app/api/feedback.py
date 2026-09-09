"""答案反馈：用户对 assistant 答案点赞/点踩，以及质量看板统计。"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import not_found
from app.core.security import get_current_user
from app.db import get_db
from app.models.message import Message
from app.models.session import Session
from app.models.user import User
from app.schemas.feedback import FeedbackStats, MessageFeedbackRequest, MessageFeedbackResponse

router = APIRouter()


@router.post("/messages/{message_id}/feedback", response_model=MessageFeedbackResponse)
async def set_feedback(
    message_id: uuid.UUID,
    body: MessageFeedbackRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MessageFeedbackResponse:
    # 仅允许对自己会话中的 assistant 消息反馈
    message = (
        await db.execute(
            select(Message)
            .join(Session, Message.session_id == Session.id)
            .where(Message.id == message_id, Session.user_id == user.id)
        )
    ).scalar_one_or_none()
    if message is None:
        raise not_found("消息")
    if message.role != "assistant":
        raise not_found("仅 assistant 答案可反馈")
    message.feedback = body.feedback
    await db.commit()
    return MessageFeedbackResponse(message_id=message.id, feedback=message.feedback)


@router.get("/feedback/stats", response_model=FeedbackStats)
async def feedback_stats(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> FeedbackStats:
    base = (
        select(func.count())
        .select_from(Message)
        .join(Session, Message.session_id == Session.id)
        .where(Session.user_id == user.id, Message.role == "assistant", Message.status == "complete")
    )
    total_answered = (await db.execute(base)).scalar_one()
    up_count = (
        await db.execute(
            select(func.count()).select_from(Message).join(Session, Message.session_id == Session.id)
            .where(Session.user_id == user.id, Message.feedback == "up")
        )
    ).scalar_one()
    down_count = (
        await db.execute(
            select(func.count()).select_from(Message).join(Session, Message.session_id == Session.id)
            .where(Session.user_id == user.id, Message.feedback == "down")
        )
    ).scalar_one()
    feedback_total = up_count + down_count
    return FeedbackStats(
        total_answered=total_answered,
        up_count=up_count,
        down_count=down_count,
        feedback_total=feedback_total,
        down_rate=round(down_count / feedback_total, 4) if feedback_total else 0.0,
    )
