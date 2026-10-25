"""导入 ORM 模型，使其注册到同一份表结构元数据。"""

from backend.app.infrastructure.db.models.base import Base
from backend.app.infrastructure.db.models.user import UserModel

__all__ = ["Base", "UserModel"]
