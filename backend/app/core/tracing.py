"""traceId 中间件：每个请求生成/透传 traceId，贯穿日志、SSE 事件、任务与费用记录。"""
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.logging_config import set_trace_id

TRACE_HEADER = "X-Trace-Id"


def new_trace_id() -> str:
    return uuid.uuid4().hex[:16]


class TraceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        trace_id = request.headers.get(TRACE_HEADER) or new_trace_id()
        set_trace_id(trace_id)
        response = await call_next(request)
        response.headers[TRACE_HEADER] = trace_id
        return response
