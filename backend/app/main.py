"""FastAPI 应用入口，后续在这里注册各个模块的路由。"""

from fastapi import FastAPI

from backend.app.api.health import router as health_router
from backend.app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
)

app.include_router(health_router)
