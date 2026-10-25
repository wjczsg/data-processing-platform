"""为请求分配编号，并记录请求结果及耗时。"""

import logging
from time import perf_counter
from uuid import uuid4

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from backend.app.core.logging import mark_exception_logged
from backend.app.core.request_context import request_id_context

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        context_token = request_id_context.set(request_id)
        started_at = perf_counter()
        status_code = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        def request_fields() -> dict[str, object]:
            return {
                "method": scope["method"],
                "path": scope["path"],
                "status_code": status_code,
                "duration_ms": round((perf_counter() - started_at) * 1000, 2),
            }

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception as exception:
            fields = request_fields()
            fields["exception_type"] = type(exception).__name__
            logger.exception("请求执行失败", extra=fields)
            mark_exception_logged(exception)
            raise
        else:
            level = logging.ERROR if status_code >= 500 else logging.INFO
            logger.log(level, "请求完成", extra=request_fields())
        finally:
            request_id_context.reset(context_token)
