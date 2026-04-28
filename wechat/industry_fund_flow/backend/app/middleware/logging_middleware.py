"""用途：请求日志 + 异常转统一 JSON。"""
import logging
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.responses import err
from app.core.exceptions import AppError

LOG = logging.getLogger("api")


class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = str(uuid.uuid4())[:8]
        start = time.time()
        try:
            response = await call_next(request)
            cost = (time.time() - start) * 1000
            LOG.info(
                "%s %s %s %sms",
                rid,
                request.method,
                request.url.path,
                f"{cost:.1f}",
            )
            response.headers["X-Request-Id"] = rid
            return response
        except AppError as e:
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=200,
                content=err(e.code, e.message),
            )


def register_exception_handlers(app):
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from fastapi.exceptions import RequestValidationError

    @app.exception_handler(AppError)
    async def app_error_handler(_, exc: AppError):
        return JSONResponse(status_code=200, content=err(exc.code, exc.message))

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_, exc: RequestValidationError):
        return JSONResponse(
            status_code=200,
            content=err(422, "参数错误", {"detail": exc.errors()}),
        )

    @app.exception_handler(Exception)
    async def generic_handler(_, exc: Exception):
        LOG.exception("unhandled: %s", exc)
        return JSONResponse(status_code=200, content=err(500, "服务器内部错误"))
