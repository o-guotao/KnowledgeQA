"""跨数据库类型抽象：UUID 与向量列类型按 db_backend 切换。

- UUID：postgresql 用原生 uuid；sqlite 用 String(36) + TypeDecorator 自动 str/UUID 转换
  （sqlite3 驱动不认 uuid.UUID 对象，且 SQLAlchemy 隐式 Uuid 读回会调 .hex 报 AttributeError）
- 向量：postgresql 用 pgvector.Vector；sqlite 用 JSON 存 list[float]（召回改 Python 端余弦）
"""
import uuid

from sqlalchemy import JSON, String
from sqlalchemy.types import TypeDecorator, Uuid as PgUuid

from app.config import get_settings


class SQLiteUUID(TypeDecorator):
    """sqlite 兼容 UUID：存储为 36 字符字符串，Python 端仍用 uuid.UUID。"""
    impl = String(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


def UUIDType():
    """返回当前后端适用的 UUID 列类型。"""
    if get_settings().db_backend == "sqlite":
        return SQLiteUUID()
    return PgUuid()


def get_vector_type(dim: int):
    """返回当前后端适用的向量列类型。"""
    if get_settings().db_backend == "sqlite":
        return JSON()
    from pgvector.sqlalchemy import Vector  # 仅 postgresql 模式导入

    return Vector(dim)
