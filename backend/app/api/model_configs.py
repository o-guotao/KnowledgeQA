"""用户自管 OpenAI 兼容模型配置。"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import get_current_user
from app.db import get_db
from app.models.model_config import ModelConfig
from app.models.user import User
from app.schemas.model_config import ModelConfigCreate, ModelConfigOut, ModelConfigTestResult, ModelConfigUpdate
from app.services.model_configs import (
    activate_config,
    api_key_hint,
    encrypt_api_key,
    get_owned_config,
    normalize_public_base_url,
    resolve_provider_config,
)
from app.services.openai_compatible import test_provider_connection

router = APIRouter()


def to_out(config: ModelConfig) -> ModelConfigOut:
    return ModelConfigOut(
        id=config.id, name=config.name, base_url=config.base_url, model_name=config.model_name,
        api_key_masked=config.api_key_hint, timeout_seconds=config.timeout_seconds,
        price_input_per_million=config.price_input_per_million,
        price_output_per_million=config.price_output_per_million,
        is_active=config.is_active, created_at=config.created_at, updated_at=config.updated_at,
    )


@router.get("/model-configs", response_model=list[ModelConfigOut])
async def list_model_configs(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> list[ModelConfigOut]:
    rows = (
        await db.execute(select(ModelConfig).where(ModelConfig.user_id == user.id).order_by(ModelConfig.created_at.desc()))
    ).scalars().all()
    return [to_out(row) for row in rows]


@router.post("/model-configs", response_model=ModelConfigOut, status_code=201)
async def create_model_config(
    body: ModelConfigCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> ModelConfigOut:
    base_url = await normalize_public_base_url(body.base_url)
    has_config = (await db.execute(select(ModelConfig.id).where(ModelConfig.user_id == user.id).limit(1))).scalar_one_or_none()
    config = ModelConfig(
        user_id=user.id, name=body.name, base_url=base_url, model_name=body.model_name,
        api_key_encrypted=encrypt_api_key(body.api_key), api_key_hint=api_key_hint(body.api_key),
        timeout_seconds=body.timeout_seconds, price_input_per_million=body.price_input_per_million,
        price_output_per_million=body.price_output_per_million, is_active=has_config is None,
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return to_out(config)


@router.patch("/model-configs/{config_id}", response_model=ModelConfigOut)
async def update_model_config(
    config_id: uuid.UUID, body: ModelConfigUpdate,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
) -> ModelConfigOut:
    config = await get_owned_config(db, user.id, config_id)
    values = body.model_dump(exclude_unset=True)
    if "base_url" in values:
        config.base_url = await normalize_public_base_url(values.pop("base_url"))
    if "api_key" in values:
        api_key = values.pop("api_key")
        config.api_key_encrypted = encrypt_api_key(api_key)
        config.api_key_hint = api_key_hint(api_key)
    for field, value in values.items():
        setattr(config, field, value)
    await db.commit()
    await db.refresh(config)
    return to_out(config)


@router.delete("/model-configs/{config_id}", status_code=204)
async def delete_model_config(
    config_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> None:
    config = await get_owned_config(db, user.id, config_id)
    was_active = config.is_active
    await db.delete(config)
    await db.flush()
    if was_active:
        replacement = (
            await db.execute(select(ModelConfig).where(ModelConfig.user_id == user.id).order_by(ModelConfig.created_at.desc()).limit(1))
        ).scalar_one_or_none()
        if replacement is not None:
            replacement.is_active = True
    await db.commit()


@router.post("/model-configs/{config_id}/activate", response_model=ModelConfigOut)
async def set_active_model_config(
    config_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> ModelConfigOut:
    return to_out(await activate_config(db, user.id, config_id))


@router.post("/model-configs/{config_id}/test", response_model=ModelConfigTestResult)
async def test_model_config(
    config_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> ModelConfigTestResult:
    config = await get_owned_config(db, user.id, config_id)
    try:
        provider = await resolve_provider_config(db, user.id) if config.is_active else None
        if provider is None:
            from app.services.model_configs import ProviderConfig, decrypt_api_key
            provider = ProviderConfig(
                base_url=config.base_url, model_name=config.model_name, api_key=decrypt_api_key(config.api_key_encrypted),
                timeout_seconds=config.timeout_seconds, price_input_per_million=0, price_output_per_million=0,
            )
        await test_provider_connection(provider)
        return ModelConfigTestResult(ok=True, message="连接成功")
    except AppError:
        raise
    except Exception:
        return ModelConfigTestResult(ok=False, message="连接失败，请检查服务地址、模型名称和 API Key")
