import hashlib
import logging
import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
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
from app.services.storage import delete_object, get_object, put_object

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20MB


def _media_type(filename: str) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        return "application/pdf"
    if name.endswith(".markdown"):
        return "text/markdown; charset=utf-8"
    if name.endswith(".md"):
        return "text/markdown; charset=utf-8"
    return "text/plain; charset=utf-8"

# 文件名规则：取 basename；禁控制字符与 <>:"/\|?*；去首尾空白与点；长度 1..255（库列 String(256)）
_FORBIDDEN_FILENAME_CHARS = set('<>:"/\\|?*')


def _normalize_filename(raw: str) -> str:
    name = (raw or "").replace("\\", "/").split("/")[-1]
    if any(ord(c) < 32 or ord(c) == 127 for c in name):
        raise AppError("INVALID_FILENAME", "文件名包含非法控制字符", 400)
    if _FORBIDDEN_FILENAME_CHARS.intersection(name):
        raise AppError("INVALID_FILENAME", '文件名包含非法字符：<>:"/\\|?*', 400)
    name = name.strip().strip(" .")
    if not 1 <= len(name) <= 255:
        raise AppError("INVALID_FILENAME", "文件名长度需在 1-255 之间", 400)
    return name


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
    filename = _normalize_filename(file.filename)
    if not filename.lower().endswith((".txt", ".md", ".markdown", ".pdf")):
        raise AppError("BAD_FILE_TYPE", "仅支持 .txt/.md/.pdf")

    content_hash = hashlib.sha256(data).hexdigest()
    dup = (
        await db.execute(
            select(Document.filename)
            .where(Document.user_id == user.id, Document.content_hash == content_hash)
            .limit(1)
        )
    ).scalar_one_or_none()
    if dup is not None:
        raise AppError("DUPLICATE_DOCUMENT", f"内容已存在，原文件：{dup}", 409)

    # 纯图片 PDF（无文字层）：保留原文件但不投递切分任务，进入 no_text 终态供预览/将来 OCR
    status = "uploaded"
    if filename.lower().endswith(".pdf"):
        from app.services.chunking import extract_text  # 懒加载

        try:
            no_text = not extract_text(filename, data)
        except Exception:
            # 加密/损坏的 PDF 无法提取文本：在请求内明确 4xx 拒绝，避免落入 worker 才 failed
            raise AppError("BAD_FILE_TYPE", "PDF 无法解析（文件损坏或已加密），未保存", 400)
        if no_text:
            status = "no_text"

    settings = get_settings()
    document = Document(
        user_id=user.id,
        filename=filename,
        content_hash=content_hash,
        object_key="",
        status=status,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )
    db.add(document)
    await db.flush()
    document.object_key = f"{user.id}/{document.id}/{filename}"
    await put_object(document.object_key, data)

    if status == "uploaded":
        # 入队切分任务，traceId 从上传请求贯穿到 worker
        task = Task(
            type="ingest_document",
            payload={"document_id": str(document.id)},
            user_id=user.id,
            trace_id=get_trace_id(),
            max_retries=settings.task_max_retries,
        )
        db.add(task)

    try:
        await db.commit()
    except IntegrityError:
        # 并发双传兜底：部分唯一索引 (user_id, content_hash) 拦下，翻译为用户可读错误
        await db.rollback()
        raise AppError("DUPLICATE_DOCUMENT", f"内容已存在，原文件：{filename}", 409)
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


@router.get("/documents/{document_id}/file")
async def get_document_file(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """取本人文档原始字节（预览用）：鉴权内联返回，不生成预签名 URL。"""
    document = (
        await db.execute(
            select(Document).where(Document.id == document_id, Document.user_id == user.id)
        )
    ).scalar_one_or_none()
    if document is None or not document.object_key:
        raise not_found("文档")
    try:
        data = await get_object(document.object_key)
    except Exception:
        # 对象缺失/取数失败（如已删除）视为不可预览
        logger.warning("读取文档对象失败: object_key=%s", document.object_key, exc_info=True)
        raise not_found("文档")
    filename = quote(document.filename)
    return Response(
        content=data,
        media_type=_media_type(document.filename),
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{filename}"},
    )


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """删除文档：连库删除切块（含 embedding），并清理 MinIO 中的原始文件。"""
    document = (
        await db.execute(
            select(Document).where(Document.id == document_id, Document.user_id == user.id)
        )
    ).scalar_one_or_none()
    if document is None:
        raise not_found("文档")

    # 取消该文档尚未完成的入库任务（best-effort：当前仓库尚无消费者，通常为空）
    stale_tasks = (
        await db.execute(
            select(Task).where(
                Task.type == "ingest_document",
                Task.user_id == user.id,
                Task.status.in_(("pending", "running", "failed", "dead")),
            )
        )
    ).scalars().all()
    for task in stale_tasks:
        if (task.payload or {}).get("document_id") == str(document.id):
            await db.delete(task)

    # chunks 依赖 FK ondelete=CASCADE，随 document 删除一并连库清理（含 pgvector 向量）
    object_key = document.object_key
    await db.delete(document)
    await db.commit()

    if object_key:
        try:
            await delete_object(object_key)
        except Exception:
            logger.warning("删除文档对象失败: object_key=%s", object_key, exc_info=True)


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
