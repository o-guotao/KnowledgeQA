"""工具定义与执行：敏感操作（删除文档）必须经前端人工确认后才执行。"""
import json
import logging
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.chunk import Chunk
from app.models.document import Document
from app.services.storage import delete_object

logger = logging.getLogger(__name__)

# 暴露给模型的工具清单（OpenAI tools 格式）
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "list_documents",
            "description": "列出当前用户已上传到知识库的全部文档（文件名与状态）",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_document",
            "description": "从知识库中删除指定文档及其全部分块（不可恢复，需用户人工确认）",
            "parameters": {
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "文档 UUID"},
                    "reason": {"type": "string", "description": "删除原因"},
                },
                "required": ["document_id"],
            },
        },
    },
]

# 需要人工确认的工具白名单（其余只读工具可直接执行）
REQUIRE_CONFIRM = {"delete_document"}


def parse_tool_args(arguments: str) -> dict:
    try:
        return json.loads(arguments) if arguments else {}
    except json.JSONDecodeError:
        return {}


async def execute_tool(
    db: AsyncSession, user_id: uuid.UUID, name: str, args: dict
) -> str:
    """执行已确认的工具，返回给模型/用户的文本结果。"""
    if name == "list_documents":
        rows = (
            await db.execute(
                select(Document).where(Document.user_id == user_id).order_by(Document.created_at.desc())
            )
        ).scalars().all()
        if not rows:
            return "知识库为空，还没有上传任何文档。"
        lines = [f"- {d.filename}（状态 {d.status}，{d.chunk_count} 块，id={d.id}）" for d in rows]
        return "当前知识库文档：\n" + "\n".join(lines)

    if name == "delete_document":
        document_id = args.get("document_id")
        try:
            doc_uuid = uuid.UUID(str(document_id))
        except ValueError:
            raise AppError("BAD_ARGS", "document_id 不是合法 UUID") from None
        document = (
            await db.execute(
                select(Document).where(Document.id == doc_uuid, Document.user_id == user_id)
            )
        ).scalar_one_or_none()
        if document is None:
            raise AppError("NOT_FOUND", "文档不存在或不属于当前用户", 404)
        filename = document.filename
        object_key = document.object_key
        await db.execute(delete(Chunk).where(Chunk.document_id == document.id))
        await db.delete(document)
        try:
            await delete_object(object_key)
        except Exception as exc:
            # DB 已删但对象存储失败：记录孤儿对象 key，便于定期清理。
            # 不回滚 DB——文档已从知识库消失，存储泄漏是可接受的最终一致态。
            from app.services.orphans import record_orphan
            await record_orphan(db, object_key, str(exc)[:200])
            logger.warning(
                "minio delete failed, recorded as orphan: %s", object_key,
                extra={"event": "storage_orphan", "extra": {"key": object_key}},
            )
        await db.flush()
        logger.info(
            "document deleted via confirmed tool",
            extra={"event": "tool_executed", "user_id": str(user_id), "document_id": str(doc_uuid)},
        )
        return f"已删除文档《{filename}》及其全部分块。"

    raise AppError("UNKNOWN_TOOL", f"未知工具：{name}")
