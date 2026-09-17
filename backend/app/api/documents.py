import hashlib
import logging
import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.errors import AppError, not_found
from app.core.pagination import (
    LIKE_ESCAPE,
    PageParams,
    json_text_search,
    like_pattern,
    make_page,
    normalize_q,
    paginate,
)
from app.core.security import get_current_user
from app.db import get_db
from app.logging_config import get_trace_id
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.task import Task
from app.models.user import User
from app.schemas.common import DocumentStats, Page
from app.schemas.document import (
    BatchDeleteRequest,
    BatchDeleteResponse,
    ChunkOut,
    ContentUpdateResult,
    DocumentOut,
    DocumentUpdate,
)
from app.services.doc_sync import stale_reasons
from app.services.storage import delete_object, get_object, put_object

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20MB

# 上传白名单与分类：图片仅预览不切分；pdf/docx/xlsx 在请求内做可解析探测
ALLOWED_EXTENSIONS = (
    ".txt", ".md", ".markdown", ".pdf",
    ".png", ".jpg", ".jpeg", ".webp",
    ".docx", ".xlsx",
)
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
PROBE_EXTENSIONS = (".pdf", ".docx", ".xlsx")


def _media_type(filename: str) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        return "application/pdf"
    if name.endswith((".markdown", ".md")):
        return "text/markdown; charset=utf-8"
    if name.endswith(".png"):
        return "image/png"
    if name.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if name.endswith(".webp"):
        return "image/webp"
    if name.endswith(".docx"):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if name.endswith(".xlsx"):
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return "text/plain; charset=utf-8"


def _detect_status(filename: str, data: bytes) -> str:
    """上传探测：图片与无文字层/无文本内容文档 → no_text（仅预览不切分），其余 uploaded 入队。

    pdf/docx/xlsx 损坏或加密时在请求内明确 4xx 拒绝，避免落入 worker 才 failed。
    PDF 用轻量探测（只看前几页有无文字层），避免 pdfplumber 全量解析拖慢上传请求。
    """
    name = filename.lower()
    if name.endswith(IMAGE_EXTENSIONS):
        return "no_text"
    if name.endswith(".pdf"):
        from app.services.chunking import pdf_has_text  # 懒加载

        try:
            no_text = not pdf_has_text(data)
        except Exception:
            raise AppError("BAD_FILE_TYPE", "PDF 无法解析（文件损坏或已加密），未保存", 400)
        return "no_text" if no_text else "uploaded"
    if name.endswith((".docx", ".xlsx")):
        from app.services.chunking import extract_text  # 懒加载

        try:
            no_text = not extract_text(filename, data)
        except Exception:
            raise AppError("BAD_FILE_TYPE", "文件无法解析（文件损坏或已加密），未保存", 400)
        return "no_text" if no_text else "uploaded"
    return "uploaded"

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


def _to_out(document: Document) -> DocumentOut:
    """序列化文档并计算失效检测字段（stale = 入库签名 vs 当前 settings 的纯函数）。"""
    out = DocumentOut.model_validate(document)
    reasons = stale_reasons(document, get_settings())
    out.stale = bool(reasons)
    out.stale_reasons = reasons
    return out


async def _get_owned_document(document_id: uuid.UUID, user: User, db: AsyncSession) -> Document:
    document = (
        await db.execute(
            select(Document).where(Document.id == document_id, Document.user_id == user.id)
        )
    ).scalar_one_or_none()
    if document is None:
        raise not_found("文档")
    return document


def _can_read(document: Document, user: User) -> bool:
    """读授权：owner / admin / 团队空间文档（全部登录用户可检索与预览）。"""
    return document.user_id == user.id or user.role == "admin" or document.visibility == "team"


def _can_write(document: Document, user: User) -> bool:
    """写授权：owner；admin 仅可管理团队空间文档（取消共享/删除），他人私有文档不碰。"""
    return document.user_id == user.id or (user.role == "admin" and document.visibility == "team")


def _enqueue_ingest(document: Document, user: User, db: AsyncSession) -> None:
    """置 uploaded 并入队切分任务（worker 重放幂等：先清旧块再写新块）。"""
    settings = get_settings()
    document.status = "uploaded"
    document.error = None
    db.add(
        Task(
            type="ingest_document",
            payload={"document_id": str(document.id)},
            user_id=user.id,
            trace_id=get_trace_id(),
            max_retries=settings.task_max_retries,
        )
    )


@router.post("/documents", response_model=DocumentOut, status_code=201)
async def upload_document(
    file: UploadFile,
    folder: str = Form(""),
    tags: str = Form(""),
    visibility: str = Form("private"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentOut:
    if visibility not in ("private", "team"):
        raise AppError("BAD_VISIBILITY", "visibility 仅支持 private/team", 400)
    data = await file.read()
    if not data:
        raise AppError("EMPTY_FILE", "文件内容为空")
    if len(data) > MAX_UPLOAD_BYTES:
        raise AppError("FILE_TOO_LARGE", "文件超过 20MB 限制", 413)
    filename = _normalize_filename(file.filename)
    if not filename.lower().endswith(ALLOWED_EXTENSIONS):
        raise AppError("BAD_FILE_TYPE", "仅支持 .txt/.md/.pdf/.png/.jpg/.webp/.docx/.xlsx")

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

    # 图片与无文字层/无文本内容文档：保留原文件但不投递切分任务，进入 no_text 终态供预览
    status = _detect_status(filename, data)

    settings = get_settings()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()][:20]
    document = Document(
        user_id=user.id,
        filename=filename,
        content_hash=content_hash,
        folder=folder.strip()[:128],
        tags=tag_list,
        visibility=visibility,
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
    return _to_out(document)


@router.get("/documents", response_model=Page[DocumentOut])
async def list_documents(
    folder: str | None = None,
    q: str | None = None,
    params: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Page[DocumentOut]:
    """当前用户的文档列表：支持 folder 精确过滤 + q 关键词（文件名/标签）+ 分页。

    排序带 id 兜底：created_at 相同（同批上传）时保证分页不重复、不遗漏。
    """
    stmt = select(Document).where(Document.user_id == user.id)
    if folder is not None:
        stmt = stmt.where(Document.folder == folder)
    term = normalize_q(q)
    if term is not None:
        pattern = like_pattern(term)
        stmt = stmt.where(
            or_(
                Document.filename.ilike(pattern, escape=LIKE_ESCAPE),
                json_text_search(Document.tags, term),
            )
        )
    stmt = stmt.order_by(Document.folder.asc(), Document.created_at.desc(), Document.id.desc())
    rows, total = await paginate(db, stmt, params)
    return make_page([_to_out(row[0]) for row in rows], total, params)


@router.get("/documents/folders", response_model=list[str])
async def list_folders(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> list[str]:
    """当前用户用到过的全部文件夹（去重，含空字符串根目录）。"""
    rows = (
        await db.execute(
            select(Document.folder).where(Document.user_id == user.id).distinct()
        )
    ).scalars().all()
    return sorted(rows)


@router.get("/documents/stats", response_model=DocumentStats)
async def document_stats(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> DocumentStats:
    """当前用户文档的按状态计数（列表顶部 chips 数据源）。

    全局口径：不随 q/folder 变化（folder 过滤的结果条数以分页信封的 total 展示）。
    路由必须声明在 /documents/{document_id} 之前，否则 "stats" 会被当成 UUID 解析。
    """
    rows = (
        await db.execute(
            select(Document.status, func.count())
            .where(Document.user_id == user.id)
            .group_by(Document.status)
        )
    ).all()
    by_status = {status: count for status, count in rows}
    return DocumentStats(
        total=sum(by_status.values()),
        ready=by_status.get("ready", 0),
        processing=by_status.get("uploaded", 0) + by_status.get("processing", 0),
        failed=by_status.get("failed", 0),
        no_text=by_status.get("no_text", 0),
    )


@router.get("/documents/team", response_model=Page[DocumentOut])
async def list_team_documents(
    q: str | None = None,
    params: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Page[DocumentOut]:
    """团队空间：全员共享（visibility=team）文档列表，附 owner 显示名。任何登录用户可访问。

    q 额外匹配共享人显示名，便于"找某人共享的文档"。
    """
    stmt = (
        select(Document, User.display_name)
        .join(User, Document.user_id == User.id)
        .where(Document.visibility == "team")
    )
    term = normalize_q(q)
    if term is not None:
        pattern = like_pattern(term)
        stmt = stmt.where(
            or_(
                Document.filename.ilike(pattern, escape=LIKE_ESCAPE),
                json_text_search(Document.tags, term),
                User.display_name.ilike(pattern, escape=LIKE_ESCAPE),
            )
        )
    stmt = stmt.order_by(Document.created_at.desc(), Document.id.desc())
    rows, total = await paginate(db, stmt, params)
    result: list[DocumentOut] = []
    for doc, owner_name in rows:
        out = _to_out(doc)
        out.owner_name = owner_name or None
        result.append(out)
    return make_page(result, total, params)


@router.patch("/documents/{document_id}", response_model=DocumentOut)
async def update_document(
    document_id: uuid.UUID,
    body: DocumentUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentOut:
    """更新文档的文件夹/标签/可见性（不触发重新切分）。

    owner 可改全部字段；admin 对他人的 team 文档仅可改 visibility（取消共享）；
    他人私有文档一律 404（不泄露存在性）。
    """
    document = (
        await db.execute(select(Document).where(Document.id == document_id))
    ).scalar_one_or_none()
    if document is None:
        raise not_found("文档")
    if document.user_id != user.id:
        if not (user.role == "admin" and document.visibility == "team"):
            raise not_found("文档")
        if set(body.model_dump(exclude_unset=True)) - {"visibility"}:
            raise AppError("FORBIDDEN", "管理员仅可修改团队空间文档的 visibility", 403)
    if body.folder is not None:
        document.folder = body.folder.strip()[:128]
    if body.tags is not None:
        document.tags = [t.strip() for t in body.tags if t.strip()][:20]
    if body.visibility is not None:
        document.visibility = body.visibility
    await db.commit()
    await db.refresh(document)
    return _to_out(document)


@router.post("/documents/batch-delete", response_model=BatchDeleteResponse)
async def batch_delete_documents(
    body: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> BatchDeleteResponse:
    """批量删除文档：逐个级联删除 chunks 与对象存储，失败的收集返回。"""
    deleted = 0
    failed: list[uuid.UUID] = []
    for doc_id in body.document_ids:
        document = (
            await db.execute(
                select(Document).where(Document.id == doc_id, Document.user_id == user.id)
            )
        ).scalar_one_or_none()
        if document is None:
            failed.append(doc_id)
            continue
        object_key = document.object_key
        await db.delete(document)
        deleted += 1
        if object_key:
            try:
                await delete_object(object_key)
            except Exception:
                logger.warning("批量删除对象失败: %s", object_key, exc_info=True)
    await db.commit()
    return BatchDeleteResponse(deleted=deleted, failed=failed)


@router.get("/documents/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentOut:
    document = (
        await db.execute(select(Document).where(Document.id == document_id))
    ).scalar_one_or_none()
    if document is None or not _can_read(document, user):
        raise not_found("文档")
    return _to_out(document)


@router.post("/documents/{document_id}/content", response_model=ContentUpdateResult)
async def update_document_content(
    document_id: uuid.UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ContentUpdateResult:
    """就地更新文档内容：hash 比对后替换对象文件并重新切分，version+1，文档 id 不变。

    - 内容与本文档当前 hash 相同：幂等 no-op（updated=false，不入队）
    - 内容与其他文档相同：409 DUPLICATE_DOCUMENT（预查 + 唯一索引兜底）
    - 处理中（uploaded/processing）：409，避免与在途 ingest 竞争
    - 新内容为纯图片 PDF：no_text 终态，旧切块同事务内联清空
    """
    document = await _get_owned_document(document_id, user, db)
    if document.status in ("uploaded", "processing"):
        raise AppError("DOCUMENT_PROCESSING", "文档正在处理中，请稍后重试", 409)

    data = await file.read()
    if not data:
        raise AppError("EMPTY_FILE", "文件内容为空")
    if len(data) > MAX_UPLOAD_BYTES:
        raise AppError("FILE_TOO_LARGE", "文件超过 20MB 限制", 413)
    filename = _normalize_filename(file.filename)
    if not filename.lower().endswith(ALLOWED_EXTENSIONS):
        raise AppError("BAD_FILE_TYPE", "仅支持 .txt/.md/.pdf/.png/.jpg/.webp/.docx/.xlsx")

    content_hash = hashlib.sha256(data).hexdigest()
    if content_hash == document.content_hash:
        return ContentUpdateResult(updated=False, document=_to_out(document))
    dup = (
        await db.execute(
            select(Document.filename)
            .where(
                Document.user_id == user.id,
                Document.content_hash == content_hash,
                Document.id != document.id,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if dup is not None:
        raise AppError("DUPLICATE_DOCUMENT", f"内容已存在，原文件：{dup}", 409)

    # 文件探测（与上传一致）：不可解析 4xx 拒绝；图片/无文字层/无文本进 no_text
    status = _detect_status(filename, data)

    old_object_key = document.object_key
    document.object_key = f"{user.id}/{document.id}/{filename}"
    await put_object(document.object_key, data)

    document.filename = filename
    document.content_hash = content_hash
    document.version += 1

    if status == "no_text":
        # ready → no_text：旧切块立即失效，同事务内联清理（不入队）
        await db.execute(
            text("DELETE FROM chunks WHERE document_id = :did"), {"did": str(document.id)}
        )
        document.chunk_count = 0
        document.status = "no_text"
        document.error = None
    else:
        _enqueue_ingest(document, user, db)

    try:
        await db.commit()
    except IntegrityError:
        # 并发兜底：(user_id, content_hash) 部分唯一索引拦下
        await db.rollback()
        raise AppError("DUPLICATE_DOCUMENT", f"内容已存在，原文件：{filename}", 409)

    if old_object_key and old_object_key != document.object_key:
        try:
            await delete_object(old_object_key)
        except Exception:
            logger.warning("删除旧文档对象失败: %s", old_object_key, exc_info=True)

    await db.refresh(document)
    return ContentUpdateResult(updated=True, document=_to_out(document))


@router.post("/documents/{document_id}/reingest", response_model=DocumentOut)
async def reingest_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentOut:
    """用当前 settings 对已存储内容重新切分（stale 一键刷新 / failed 重试共用）。

    同步 chunk_size/chunk_overlap 为当前全局值，使重切后 ingest_signature 与当前
    配置一致、stale 消除；version 不变（内容未变）。

    no_text 逃生通道：上传探测只看 PDF 前几页，「前几页纯图、后续页有文字」的文档会
    被误判为 no_text，允许 pdf/docx/xlsx 重切（worker 全量提取，仍无文本则落 failed）；
    图片文件（png/jpg/webp）无文字层是确定的，仍拒绝。
    """
    document = await _get_owned_document(document_id, user, db)
    if document.status == "no_text" and document.filename.lower().endswith(IMAGE_EXTENSIONS):
        raise AppError("NOT_INGESTABLE", "图片文件无文字层，不可切分，无法检索", 400)
    if document.status in ("uploaded", "processing"):
        raise AppError("DOCUMENT_PROCESSING", "文档正在处理中，请稍后重试", 409)

    settings = get_settings()
    document.chunk_size = settings.chunk_size
    document.chunk_overlap = settings.chunk_overlap
    _enqueue_ingest(document, user, db)
    await db.commit()
    await db.refresh(document)
    return _to_out(document)


@router.get("/documents/{document_id}/file")
async def get_document_file(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """取文档原始字节（预览用）：owner/admin/团队空间可读，鉴权内联返回，不生成预签名 URL。"""
    document = (
        await db.execute(select(Document).where(Document.id == document_id))
    ).scalar_one_or_none()
    if document is None or not document.object_key or not _can_read(document, user):
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
    """删除文档：连库删除切块（含 embedding），并清理 MinIO 中的原始文件。

    owner 可删；admin 可删团队空间文档；他人私有文档 404。
    """
    document = (
        await db.execute(select(Document).where(Document.id == document_id))
    ).scalar_one_or_none()
    if document is None or not _can_write(document, user):
        raise not_found("文档")

    # 取消该文档尚未完成的入库任务（best-effort：按 payload 匹配，兼容 admin 删他人文档）
    stale_tasks = (
        await db.execute(
            select(Task).where(
                Task.type == "ingest_document",
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
    """引用回跳：按 chunk_id 返回原文块、所属文档与总块数（前端高亮定位用）。

    授权同文档读：owner/admin/团队空间文档（团队文档的引用需对非 owner 可用）。
    """
    row = (
        await db.execute(
            select(Chunk, Document)
            .join(Document, Chunk.document_id == Document.id)
            .where(Chunk.id == chunk_id)
        )
    ).one_or_none()
    if row is None or not _can_read(row[1], user):
        raise not_found("引用内容")
    chunk, document = row
    filename = document.filename
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
