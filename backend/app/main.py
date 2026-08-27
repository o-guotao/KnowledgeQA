from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.core.errors import register_error_handlers
from app.core.tracing import TraceMiddleware
from app.logging_config import configure_logging

configure_logging()

app = FastAPI(
    title="Web Agent - 内部知识问答",
    version="0.1.0",
    description="带权限的内部知识问答 Agent：JWT 鉴权、SSE 流式、RAG、任务表、配额与费用。",
)

app.add_middleware(TraceMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)
app.include_router(api_router)


@app.get("/api/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
