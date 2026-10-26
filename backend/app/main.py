"""FastAPI 应用入口，组装配置、日志与接口路由。"""

import logging
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from backend.app.api.auth import router as auth_router
from backend.app.api.exception_handlers import (
    request_validation_exception_handler,
    unhandled_exception_handler,
)
from backend.app.api.health import router as health_router
from backend.app.api.middleware.cors import configure_cors
from backend.app.api.middleware.request_logging import RequestLoggingMiddleware
from backend.app.core.config import get_settings
from backend.app.core.logging import setup_logging
from backend.app.infrastructure.db.connection import create_database_engine
from backend.app.infrastructure.db.session import create_session_factory
from backend.app.infrastructure.security.password_hasher import Argon2PasswordHasher
from backend.app.infrastructure.security.token_service import JWTTokenService

settings = get_settings()
setup_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    if settings.jwt_secret_key is None:
        raise RuntimeError("请在本机 .env 中配置至少 32 字符的随机 JWT_SECRET_KEY")
    engine = create_database_engine(settings)
    try:
        application.state.database_engine = engine
        application.state.session_factory = create_session_factory(engine)
        application.state.password_hasher = Argon2PasswordHasher()
        application.state.token_service = JWTTokenService(
            settings.jwt_secret_key.get_secret_value(), settings.jwt_access_token_expire_minutes,
        )
        application.state.dummy_password_hash = application.state.password_hasher.hash_password(secrets.token_urlsafe(32))
        logger.info("应用启动，环境=%s，版本=%s", settings.app_env, settings.app_version)
        yield
    finally:
        engine.dispose()
        logger.info("应用停止")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
)

configure_cors(app, settings)
app.add_middleware(RequestLoggingMiddleware)
app.add_exception_handler(Exception, unhandled_exception_handler)
app.add_exception_handler(RequestValidationError, request_validation_exception_handler)
app.include_router(health_router)
app.include_router(auth_router)
