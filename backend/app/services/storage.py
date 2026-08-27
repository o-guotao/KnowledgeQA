"""对象存储抽象：minio 或本地文件夹，按 STORAGE_BACKEND 切换。

本地模式：文档原文存到 LOCAL_STORAGE_DIR 下的对应路径，无任何外部服务依赖。
生产环境用 minio 模式。
"""
import asyncio
from pathlib import Path

from app.config import get_settings


async def put_object(object_key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
    settings = get_settings()
    if settings.storage_backend == "local":
        path = Path(settings.local_storage_dir) / object_key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return
    # minio 模式
    await _minio_put(object_key, data, content_type)


async def get_object(object_key: str) -> bytes:
    settings = get_settings()
    if settings.storage_backend == "local":
        path = Path(settings.local_storage_dir) / object_key
        return path.read_bytes()
    return await _minio_get(object_key)


async def delete_object(object_key: str) -> None:
    settings = get_settings()
    if settings.storage_backend == "local":
        path = Path(settings.local_storage_dir) / object_key
        if path.exists():
            path.unlink()
        return
    await _minio_delete(object_key)


# ---- MinIO 实现（懒加载，仅 minio 模式才真正导入 SDK） ----
async def _minio_put(object_key: str, data: bytes, content_type: str) -> None:
    import io

    settings = get_settings()

    def _put():
        client = _get_minio_client()
        if not client.bucket_exists(settings.minio_bucket):
            client.make_bucket(settings.minio_bucket)
        client.put_object(
            settings.minio_bucket, object_key, io.BytesIO(data), length=len(data), content_type=content_type
        )

    await asyncio.to_thread(_put)


async def _minio_get(object_key: str) -> bytes:
    settings = get_settings()

    def _get() -> bytes:
        response = _get_minio_client().get_object(settings.minio_bucket, object_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    return await asyncio.to_thread(_get)


async def _minio_delete(object_key: str) -> None:
    settings = get_settings()

    def _delete():
        _get_minio_client().remove_object(settings.minio_bucket, object_key)

    await asyncio.to_thread(_delete)


_minio_client = None


def _get_minio_client():
    global _minio_client
    if _minio_client is None:
        from minio import Minio

        settings = get_settings()
        _minio_client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_root_user,
            secret_key=settings.minio_root_password,
            secure=settings.minio_secure,
        )
    return _minio_client
