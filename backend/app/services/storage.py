"""MinIO 对象存储客户端（懒加载）。"""
import asyncio
import io

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

    def _delete():
        _get_client().remove_object(settings.minio_bucket, object_key)

    await asyncio.to_thread(_delete)
