"""工具人工确认闭环：模型发起的 tool_call 落库为 pending_confirm，确认后才执行。"""
import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, not_found
from app.core.security import get_current_user
from app.db import get_db
from app.logging_config import get_trace_id
from app.models.message import Message
from app.models.session import Session
from app.models.user import User
from app.schemas.tool import ToolConfirmRequest, ToolConfirmResponse
from app.services.tools import execute_tool

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/tools/confirm", response_model=ToolConfirmResponse)
async def confirm_tool(
    body: ToolConfirmRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ToolConfirmResponse:
    message = (
        await db.execute(
            select(Message)
            .join(Session, Message.session_id == Session.id)
            .where(Message.id == body.message_id, Session.user_id == user.id)
        )
    ).scalar_one_or_none()
    if message is None:
        raise not_found("待确认消息")
    if message.status != "pending_confirm" or not message.tool_call:
        raise AppError("NOT_PENDING", "该消息没有待确认的工具调用", 409)

    tool_call = message.tool_call
    name = tool_call.get("name", "")
    args = tool_call.get("args") or {}

    if not body.approved:
        message.status = "complete"
        message.error = "用户拒绝了工具调用"
        result = f"用户拒绝了 {name} 的执行请求，未做任何变更。"
        logger.info("tool call rejected", extra={"event": "tool_rejected", "user_id": str(user.id)})
    else:
        result = await execute_tool(db, user.id, name, args)
        message.status = "complete"

    # 工具结果落库为 role=tool 的消息，完整留痕
    db.add(
        Message(
            session_id=message.session_id,
            role="tool",
            content=result,
            status="complete",
            trace_id=get_trace_id(),
            tool_call={"name": name, "args": args, "approved": body.approved},
        )
    )
    await db.commit()
    return ToolConfirmResponse(
        message_id=message.id, tool_name=name, approved=body.approved, result=result
    )
