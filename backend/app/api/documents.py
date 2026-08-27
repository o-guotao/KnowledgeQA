import uuid

from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.errors import AppError, not_found
from app.core.security import get_current_user
from app.db import get_db
from app.logging_config import get_trace_id
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.task import Task
from app.models.user import User
from app.schemas.document import ChunkOut, DocumentOut
from app.services.storage import put_object

router = APIRouter()

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20MB


@router.post("/documents", response_model=DocumentOut, status_code=201)
async def upload_document(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentOut:
    data = await file.read()
    if not data:
        raise AppError("EMPTY_FILE", "文件内容为空")
    if len(data) > MAX_UPLOAD_BYTES:
        raise AppError("FILE_TOO_LARGE", "文件超过 20MB 限制", 413)
    filename = file.filename or "unnamed"
    if not filename.lower().endswith((".txt", ".md", ".markdown", ".pdf")):
        raise AppError("BAD_FILE_TYPE", "仅支持 .txt/.md/.pdf")

    document = Document(user_id=user.id, filename=filename, object_key="", status="uploaded")
    db.add(document)
    await db.flush()

    settings = get_settings()
    document.object_key = f"{user.id}/{document.id}/{filename}"
    document.chunk_size = settings.chunk_size
    document.chunk_overlap = settings.chunk_overlap
    await put_object(document.object_key, data)

    # 入队切分任务，traceId 从上传请求贯穿到 worker
    task = Task(
        type="ingest_document",
        payload={"document_id": str(document.id)},
        user_id=user.id,
        trace_id=get_trace_id(),
        max_retries=settings.task_max_retries,
    )
    db.add(task)
    await db.commit()
    await db.refresh(document)
    return DocumentOut.model_validate(document)


@router.get("/documents", response_model=list[DocumentOut])
async def list_documents(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> list[DocumentOut]:
    rows = (
        await db.execute(
            select(Document).where(Document.user_id == user.id).order_by(Document.created_at.desc())
        )
    ).scalars().all()
    return [DocumentOut.model_validate(d) for d in rows]


@router.get("/documents/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentOut:
    document = (
        await db.execute(
            select(Document).where(Document.id == document_id, Document.user_id == user.id)
        )
    ).scalar_one_or_none()
    if document is None:
        raise not_found("文档")
    return DocumentOut.model_validate(document)


@router.get("/chunks/{chunk_id}", response_model=ChunkOut)
async def get_chunk(
    chunk_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChunkOut:
    """引用回跳：按 chunk_id 返回原文块、所属文档与总块数（前端高亮定位用）。"""
    row = (
        await db.execute(
            select(Chunk, Document.filename)
            .join(Document, Chunk.document_id == Document.id)
            .where(Chunk.id == chunk_id, Chunk.user_id == user.id)
        )
    ).one_or_none()
    if row is None:
        raise not_found("引用内容")
    chunk, filename = row
    return ChunkOut(
        id=chunk.id,
        document_id=chunk.document_id,
        document_name=filename,
        chunk_index=chunk.chunk_index,
        content=chunk.content,
        start_offset=chunk.start_offset,
        end_offset=chunk.end_offset,
        total_chunks=(await db.scalar(
            select(Document.chunk_count).where(Document.id == chunk.document_id)
        )) or 0,
    )
