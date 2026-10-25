"""FastAPI 应用入口，组装配置、日志与接口路由。"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.api.exception_handlers import unhandled_exception_handler
from backend.app.api.health import router as health_router
from backend.app.api.middleware.request_logging import RequestLoggingMiddleware
from backend.app.core.config import get_settings
from backend.app.core.logging import setup_logging

settings = get_settings()
setup_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    logger.info("应用启动，环境=%s，版本=%s", settings.app_env, settings.app_version)
    try:
        yield
    finally:
        logger.info("应用停止")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
)

app.add_middleware(RequestLoggingMiddleware)
app.add_exception_handler(Exception, unhandled_exception_handler)
app.include_router(health_router)
