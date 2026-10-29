"""处理任务表结构，供创建任务业务保存记录。"""

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, ForeignKey, Index, JSON, String, Text, text
from sqlalchemy.dialects.mysql import BIGINT, DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.infrastructure.db.models.base import Base


def utc_now() -> datetime:
    """与项目约定一致，MySQL DATETIME(6) 保存不带时区的 UTC 时间。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ProcessingTaskModel(Base):
    __tablename__ = "processing_tasks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed')", name="status",
        ),
        Index("ix_processing_tasks_status_created_at_id", "status", "created_at", "id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"},
    )

    # 编号由创建任务服务生成；同一文件允许创建多个独立任务。
    id: Mapped[str] = mapped_column(String(32, collation="utf8mb4_bin"), primary_key=True)
    file_id: Mapped[str] = mapped_column(
        String(32, collation="utf8mb4_bin"),
        ForeignKey("uploaded_files.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    # 创建任务服务同时校验该用户也是关联文件的所属用户。
    owner_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    status: Mapped[str] = mapped_column(
        String(16, collation="utf8mb4_bin"), default="pending",
        server_default=text("'pending'"), nullable=False,
    )
    # None 表示尚未保存输入配置；下一步创建任务时写入表头和完整列结构快照。
    input_config: Mapped[dict[str, object] | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    processed_rows: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), default=0, server_default=text("0"), nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 领取、执行逻辑接入后显式填写；创建任务不等于已经开始处理。
    started_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), default=utc_now, onupdate=utc_now, nullable=False,
    )
