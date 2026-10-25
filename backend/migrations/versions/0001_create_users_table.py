"""创建 users 用户表。

Revision ID: 0001
Revises: None
Create Date: 2026-10-25 13:55:27.510627
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建表结构，具体数据由后续业务代码写入。"""
    op.create_table(
        "users",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=32, collation="utf8mb4_bin"), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=16), server_default=sa.text("'user'"), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(create_constraint=True, name="is_active"),
            server_default=sa.text("1"),
            nullable=False,
        ),
        # UTC 时间由 ORM 的 default / onupdate 维护，不是数据库自动更新时间。
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "CHAR_LENGTH(username) BETWEEN 3 AND 32 "
            "AND NOT REGEXP_LIKE(username, '[^a-z0-9_]', 'c')",
            name=op.f("ck_users_username_format"),
        ),
        sa.CheckConstraint("role IN ('user', 'admin')", name=op.f("ck_users_role")),
        sa.CheckConstraint(
            "CHAR_LENGTH(TRIM(password_hash)) > 0", name=op.f("ck_users_password_hash")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("username", name=op.f("uq_users_username")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
        mysql_engine="InnoDB",
    )


def downgrade() -> None:
    """撤销这次建表：删除 users 表及其数据，不能当作普通事务回滚。"""
    op.drop_table("users")
