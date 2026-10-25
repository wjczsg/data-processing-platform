"""未处理异常的 HTTP 响应，堆栈由请求日志记录。"""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


async def request_validation_exception_handler(
    request: Request, exception: RequestValidationError
) -> JSONResponse:
    """只返回错误位置和描述，避免默认校验响应回显密码或整个请求体。"""
    details = [
        {"loc": error["loc"], "msg": error["msg"], "type": error["type"]}
        for error in exception.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": details})


async def unhandled_exception_handler(request: Request, exception: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "-")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "request_id": request_id},
        headers={"X-Request-ID": request_id},
    )
