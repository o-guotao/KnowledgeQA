"""对象存储抽象：minio（生产）或 local 本地文件夹（开发演示），按 STORAGE_BACKEND 切换。"""
import asyncio
import io
from pathlib import Path

from app.config import get_settings

_client = None


def _get_client():
    global _client
    if _client is None:
        from minio import Minio  # 懒加载

        settings = get_settings()
        _client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_root_user,
            secret_key=settings.minio_root_password,
            secure=settings.minio_secure,
        )
    return _client


async def put_object(object_key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
    settings = get_settings()
    if settings.storage_backend == "local":
        path = Path(settings.local_storage_dir) / object_key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return

    def _put():
        client = _get_client()
        if not client.bucket_exists(settings.minio_bucket):
            client.make_bucket(settings.minio_bucket)
        client.put_object(
            settings.minio_bucket, object_key, io.BytesIO(data), length=len(data), content_type=content_type
        )

    await asyncio.to_thread(_put)


async def get_object(object_key: str) -> bytes:
    settings = get_settings()
    if settings.storage_backend == "local":
        return (Path(settings.local_storage_dir) / object_key).read_bytes()

    def _get() -> bytes:
        response = _get_client().get_object(settings.minio_bucket, object_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    return await asyncio.to_thread(_get)


async def delete_object(object_key: str) -> None:
    settings = get_settings()
    if settings.storage_backend == "local":
        path = Path(settings.local_storage_dir) / object_key
        if path.exists():
            path.unlink()
        return

    def _delete():
        _get_client().remove_object(settings.minio_bucket, object_key)

    await asyncio.to_thread(_delete)
