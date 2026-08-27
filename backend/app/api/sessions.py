import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import not_found
from app.core.security import get_current_user
from app.db import get_db
from app.models.message import Message
from app.models.session import Session
from app.models.user import User
from app.schemas.session import MessageOut, SessionCreate, SessionOut, SessionUpdate

router = APIRouter()


async def _owned_session(db: AsyncSession, session_id: uuid.UUID, user_id: uuid.UUID) -> Session:
    session = (
        await db.execute(select(Session).where(Session.id == session_id, Session.user_id == user_id))
    ).scalar_one_or_none()
    if session is None:
        raise not_found("会话")
    return session


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> list[SessionOut]:
    rows = (
        await db.execute(
            select(Session).where(Session.user_id == user.id).order_by(Session.updated_at.desc())
        )
    ).scalars().all()
    return [SessionOut.model_validate(s) for s in rows]


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


@router.get("/sessions/{session_id}/messages", response_model=list[MessageOut])
async def list_messages(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[MessageOut]:
    await _owned_session(db, session_id, user.id)
    rows = (
        await db.execute(
            select(Message).where(Message.session_id == session_id).order_by(Message.created_at.asc())
        )
    ).scalars().all()
    # 清理流式中断残留的 streaming 状态
    changed = False
    for m in rows:
        if m.status == "streaming":
            m.status = "aborted"
            changed = True
    if changed:
        await db.commit()
    return [MessageOut.model_validate(m) for m in rows]
