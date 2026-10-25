"""检查接口服务是否能够响应请求。"""

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["健康检查"])


@router.get("/health")
def health_check() -> dict[str, str]:
    """仅检查接口响应，不检查数据库等外部依赖。"""
    return {"status": "ok"}
