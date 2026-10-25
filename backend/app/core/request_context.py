"""保存当前请求的上下文，不依赖 Web 框架。"""

from contextvars import ContextVar

request_id_context: ContextVar[str] = ContextVar("request_id", default="-")
