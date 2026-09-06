"""用户模型配置的密钥保护、URL 校验和运行时解析。"""
import asyncio
import ipaddress
import socket
import uuid
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.errors import AppError, not_found
from app.models.model_config import ModelConfig


@dataclass(frozen=True)
class ProviderConfig:
    base_url: str
    model_name: str
    api_key: str
    timeout_seconds: float
    price_input_per_million: float
    price_output_per_million: float


def _cipher() -> Fernet:
    key = get_settings().provider_config_encryption_key.strip()
    if not key:
        raise AppError("CONFIG_ENCRYPTION_UNAVAILABLE", "服务尚未配置模型密钥加密能力", 503)
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise AppError("CONFIG_ENCRYPTION_UNAVAILABLE", "服务模型密钥配置无效", 503) from exc


def encrypt_api_key(api_key: str) -> str:
    return _cipher().encrypt(api_key.encode()).decode()


def decrypt_api_key(ciphertext: str) -> str:
    try:
        return _cipher().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise AppError("CONFIG_DECRYPT_FAILED", "模型密钥无法解密，请重新保存配置", 503) from exc


def api_key_hint(api_key: str) -> str:
    if len(api_key) <= 4:
        return "*" * len(api_key)
    return f"{api_key[:2]}{'*' * max(4, len(api_key) - 6)}{api_key[-4:]}"


def _is_public_ip(value: str) -> bool:
    ip = ipaddress.ip_address(value)
    return ip.is_global


async def normalize_public_base_url(raw: str) -> str:
    parsed = urlparse(raw.strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise AppError("INVALID_PROVIDER_URL", "模型服务地址必须是无凭据的 HTTPS 地址")
    if parsed.params or parsed.query or parsed.fragment:
        raise AppError("INVALID_PROVIDER_URL", "模型服务地址不能包含查询参数或片段")
    try:
        addresses = await asyncio.get_running_loop().run_in_executor(
            None, lambda: socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
        )
        if not addresses or any(not _is_public_ip(item[4][0]) for item in addresses):
            raise AppError("INVALID_PROVIDER_URL", "模型服务地址必须解析为公网地址")
    except socket.gaierror as exc:
        raise AppError("INVALID_PROVIDER_URL", "模型服务地址无法解析") from exc
    path = parsed.path.rstrip("/")
    return urlunparse(("https", parsed.netloc, path, "", "", ""))


async def get_owned_config(db: AsyncSession, user_id: uuid.UUID, config_id: uuid.UUID) -> ModelConfig:
    config = (
        await db.execute(
            select(ModelConfig).where(ModelConfig.id == config_id, ModelConfig.user_id == user_id)
        )
    ).scalar_one_or_none()
    if config is None:
        raise not_found("模型配置")
    return config


async def activate_config(db: AsyncSession, user_id: uuid.UUID, config_id: uuid.UUID) -> ModelConfig:
    config = await get_owned_config(db, user_id, config_id)
    await db.execute(update(ModelConfig).where(ModelConfig.user_id == user_id).values(is_active=False))
    config.is_active = True
    await db.commit()
    await db.refresh(config)
    return config


async def resolve_provider_config(db: AsyncSession, user_id: uuid.UUID) -> ProviderConfig:
    config = (
        await db.execute(select(ModelConfig).where(ModelConfig.user_id == user_id, ModelConfig.is_active.is_(True)))
    ).scalar_one_or_none()
    if config is not None:
        settings = get_settings()
        return ProviderConfig(
            base_url=config.base_url,
            model_name=config.model_name,
            api_key=decrypt_api_key(config.api_key_encrypted),
            timeout_seconds=config.timeout_seconds,
            price_input_per_million=(config.price_input_per_million if config.price_input_per_million is not None else settings.deepseek_price_input_per_million),
            price_output_per_million=(config.price_output_per_million if config.price_output_per_million is not None else settings.deepseek_price_output_per_million),
        )
    settings = get_settings()
    if not settings.deepseek_api_key:
        raise AppError("MODEL_NOT_CONFIGURED", "请先在模型配置中添加并启用一个模型", 422)
    return ProviderConfig(
        base_url=settings.deepseek_base_url.rstrip("/"), model_name=settings.deepseek_model,
        api_key=settings.deepseek_api_key, timeout_seconds=settings.deepseek_timeout_seconds,
        price_input_per_million=settings.deepseek_price_input_per_million,
        price_output_per_million=settings.deepseek_price_output_per_million,
    )
