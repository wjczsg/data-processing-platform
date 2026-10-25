"""用户数据及字段规则，不依赖 FastAPI 或 SQLAlchemy。"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 32
PASSWORD_HASH_MAX_LENGTH = 255


class UserRole(StrEnum):
    USER = "user"
    ADMIN = "admin"


def normalize_username(value: str) -> str:
    """账号清理首尾空格、统一小写，仅允许 ASCII 字母、数字和下划线。"""
    if not isinstance(value, str):
        raise ValueError("账号必须是字符串")
    stripped = value.strip()
    normalized = stripped.lower()
    if not stripped.isascii() or not re.fullmatch(
        rf"[a-z0-9_]{{{USERNAME_MIN_LENGTH},{USERNAME_MAX_LENGTH}}}", normalized
    ):
        raise ValueError("账号必须为 3～32 位字母、数字或下划线")
    return normalized


def validate_password_hash(value: str) -> str:
    """校验哈希字段的基本形状；生成和验证密码的算法在认证模块实现。"""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("密码哈希不能为空")
    if len(value) > PASSWORD_HASH_MAX_LENGTH:
        raise ValueError("密码哈希长度不能超过 255 个字符")
    return value


@dataclass(frozen=True, kw_only=True)
class User:
    """业务层的用户数据；尚未持久化时 ID 和时间可以为空。"""

    username: str
    password_hash: str = field(repr=False)
    id: int | None = None
    role: UserRole = UserRole.USER
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "username", normalize_username(self.username))
        validate_password_hash(self.password_hash)
        object.__setattr__(self, "role", UserRole(self.role))
        if not isinstance(self.is_active, bool):
            raise ValueError("启用状态必须为布尔值")
        if self.id is not None and (type(self.id) is not int or self.id <= 0):
            raise ValueError("已保存用户的 ID 必须为正整数")
