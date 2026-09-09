from fastapi import APIRouter

from app.api import admin, auth, chat, documents, feedback, model_configs, quotas, sessions, tools

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(sessions.router, tags=["sessions"])
api_router.include_router(chat.router, tags=["chat"])
api_router.include_router(documents.router, tags=["documents"])
api_router.include_router(feedback.router, tags=["feedback"])
api_router.include_router(quotas.router, tags=["quotas"])
api_router.include_router(tools.router, tags=["tools"])
api_router.include_router(model_configs.router, tags=["model-configs"])
api_router.include_router(admin.router, tags=["admin"])
