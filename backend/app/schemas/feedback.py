import uuid
from typing import Literal

from pydantic import BaseModel


class MessageFeedbackRequest(BaseModel):
    feedback: Literal["up", "down"] | None = None  # up | down | None（取消反馈）


class MessageFeedbackResponse(BaseModel):
    message_id: uuid.UUID
    feedback: str | None


class FeedbackStats(BaseModel):
    """答案质量看板统计。"""
    total_answered: int  # 完整回答的 assistant 消息数
    up_count: int
    down_count: int
    feedback_total: int  # up + down
    down_rate: float  # 点踩率 = down / feedback_total（无反馈时为 0）
