import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import not_found
from app.core.pagination import (
    LIKE_ESCAPE,
    MessagePageParams,
    PageParams,
    like_pattern,
    make_page,
    normalize_q,
    paginate,
)
from app.core.security import get_current_user
from app.db import get_db
from app.models.message import Message
from app.models.session import Session
from app.models.user import User
from app.schemas.common import Page
from app.schemas.session import MessageOut, SessionCreate, SessionOut, SessionUpdate

router = APIRouter()


async def _owned_session(db: AsyncSession, session_id: uuid.UUID, user_id: uuid.UUID) -> Session:
    session = (
        await db.execute(select(Session).where(Session.id == session_id, Session.user_id == user_id))
    ).scalar_one_or_none()
    if session is None:
        raise not_found("会话")
    return session


@router.get("/sessions", response_model=Page[SessionOut])
async def list_sessions(
    q: str | None = None,
    params: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Page[SessionOut]:
    """会话列表：支持 q（标题子串）+ 分页；侧栏用「加载更多」累加而非页码。"""
    stmt = select(Session).where(Session.user_id == user.id)
    term = normalize_q(q)
    if term is not None:
        stmt = stmt.where(Session.title.ilike(like_pattern(term), escape=LIKE_ESCAPE))
    stmt = stmt.order_by(Session.updated_at.desc(), Session.id.desc())
    rows, total = await paginate(db, stmt, params)
    return make_page([SessionOut.model_validate(row[0]) for row in rows], total, params)


@router.post("/sessions", response_model=SessionOut, status_code=201)
async def create_session(
    body: SessionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SessionOut:
    session = Session(user_id=user.id, title=body.title)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return SessionOut.model_validate(session)


@router.patch("/sessions/{session_id}", response_model=SessionOut)
async def rename_session(
    session_id: uuid.UUID,
    body: SessionUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SessionOut:
    session = await _owned_session(db, session_id, user.id)
    session.title = body.title
    await db.commit()
    await db.refresh(session)
    return SessionOut.model_validate(session)


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    session = await _owned_session(db, session_id, user.id)
    await db.delete(session)
    await db.commit()


@router.get("/sessions/{session_id}/messages", response_model=Page[MessageOut])
async def list_messages(
    session_id: uuid.UUID,
    params: MessagePageParams = Depends(),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Page[MessageOut]:
    """历史消息倒序分页：page=1 为最新一页（前端反转后渲染，「加载更早」取 page+1）。

    倒序而非正序：会话很长时优先拿到最近的上下文，避免首屏等待最老的消息。
    """
    await _owned_session(db, session_id, user.id)
    stmt = (
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.desc(), Message.id.desc())
    )
    rows, total = await paginate(db, stmt, params)
    # 清理流式中断残留的 streaming 状态（仅本次返回的页；语义同改造前，范围随分页收窄）
    changed = False
    for row in rows:
        if row[0].status == "streaming":
            row[0].status = "aborted"
            changed = True
    if changed:
        await db.commit()
    return make_page([MessageOut.model_validate(row[0]) for row in rows], total, params)
