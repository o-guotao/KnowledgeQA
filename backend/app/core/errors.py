"""统一业务错误与异常处理。"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def not_found(resource: str) -> AppError:
    return AppError("NOT_FOUND", f"{resource}不存在", 404)


def forbidden(message: str = "无权访问该资源") -> AppError:
    return AppError("FORBIDDEN", message, 403)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": {"code": exc.code, "message": exc.message}},
        )
