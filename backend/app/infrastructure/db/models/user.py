"""MySQL users 表的 SQLAlchemy 映射定义，仅声明结构，不自动建表。"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, String, UniqueConstraint, text
from sqlalchemy.dialects.mysql import BIGINT, DATETIME
from sqlalchemy.orm import Mapped, mapped_column, validates

from backend.app.domain.user import (
    PASSWORD_HASH_MAX_LENGTH,
    USERNAME_MAX_LENGTH,
    USERNAME_MIN_LENGTH,
    UserRole,
    normalize_username,
    validate_password_hash,
)
from backend.app.infrastructure.db.models.base import Base


def utc_now() -> datetime:
    """MySQL DATETIME 不携带时区，本项目约定统一写入 UTC 时间。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class UserModel(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username"),
        CheckConstraint(
            f"CHAR_LENGTH(username) BETWEEN {USERNAME_MIN_LENGTH} AND {USERNAME_MAX_LENGTH} "
            "AND NOT REGEXP_LIKE(username, '[^a-z0-9_]', 'c')",
            name="username_format",
        ),
        CheckConstraint("CHAR_LENGTH(TRIM(password_hash)) > 0", name="password_hash"),
        CheckConstraint("role IN ('user', 'admin')", name="role"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_0900_ai_ci",
        },
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(
        String(USERNAME_MAX_LENGTH, collation="utf8mb4_bin"), nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String(PASSWORD_HASH_MAX_LENGTH), nullable=False)
    role: Mapped[str] = mapped_column(
        String(16), default=UserRole.USER.value, server_default=text("'user'"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean(create_constraint=True, name="is_active"),
        default=True,
        server_default=text("1"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), default=utc_now, onupdate=utc_now, nullable=False
    )

    @validates("username")
    def validate_username(self, key: str, value: str) -> str:
        return normalize_username(value)

    @validates("password_hash")
    def validate_hash(self, key: str, value: str) -> str:
        return validate_password_hash(value)

    @validates("role")
    def validate_role(self, key: str, value: str | UserRole) -> str:
        return UserRole(value).value
