"""配置统一的终端日志格式与级别。"""

import json
import logging
from datetime import datetime, timezone
from logging.config import dictConfig

from backend.app.core.request_context import request_id_context

_LOGGED_ATTRIBUTE = "_xingxu_exception_logged"


def mark_exception_logged(exception: Exception) -> None:
    """标记已经记录的异常，避免 Uvicorn 再次打印相同堆栈。"""
    setattr(exception, _LOGGED_ATTRIBUTE, True)


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.name == "uvicorn.error" and record.exc_info:
            if getattr(record.exc_info[1], _LOGGED_ATTRIBUTE, False):
                return False
        record.request_id = request_id_context.get()
        return True


class TextFormatter(logging.Formatter):
    """公共字段固定，请求字段按事件添加；异常堆栈跟随该条记录。"""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).astimezone()
        parts = [
            timestamp.isoformat(timespec="milliseconds"),
            record.levelname,
            record.name,
            f"request_id={getattr(record, 'request_id', '-')}",
        ]
        for field in ("method", "path", "status_code", "duration_ms", "exception_type"):
            if hasattr(record, field):
                value = json.dumps(getattr(record, field), ensure_ascii=False)
                parts.append(f"{field}={value}")
        message = json.dumps(record.getMessage(), ensure_ascii=False)
        parts.append(f"message={message}")
        result = " ".join(parts)
        if record.exc_info:
            result += "\n" + self.formatException(record.exc_info)
        if record.stack_info:
            result += "\n" + self.formatStack(record.stack_info)
        return result


def setup_logging(level: str = "INFO") -> None:
    """初始化一次即可；重复调用会替换配置，不会累加输出处理器。"""
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {"request_context": {"()": RequestContextFilter}},
            "formatters": {"text": {"()": TextFormatter}},
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stderr",
                    "formatter": "text",
                    "filters": ["request_context"],
                    "level": level,
                }
            },
            "root": {"handlers": ["console"], "level": level},
            "loggers": {
                "uvicorn": {"handlers": ["console"], "level": level, "propagate": False},
                "uvicorn.error": {"handlers": [], "level": level, "propagate": True},
                "uvicorn.access": {"handlers": [], "level": level, "propagate": False},
            },
        }
    )
    # 请求完成日志由应用中间件负责，避免同一个请求再打印一条 access 日志。
    logging.getLogger("uvicorn.access").disabled = True
