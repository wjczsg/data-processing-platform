"""处理任务表，仅声明结构；创建任务的业务流程后续接入。"""

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, ForeignKey, String, text
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
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"},
    )

    # 编号由后续创建任务服务生成；同一文件允许创建多个独立任务。
    id: Mapped[str] = mapped_column(String(32, collation="utf8mb4_bin"), primary_key=True)
    file_id: Mapped[str] = mapped_column(
        String(32, collation="utf8mb4_bin"),
        ForeignKey("uploaded_files.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    # 后续业务服务还需校验该用户也是关联文件的所属用户。
    owner_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    status: Mapped[str] = mapped_column(
        String(16, collation="utf8mb4_bin"), default="pending",
        server_default=text("'pending'"), nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), default=utc_now, onupdate=utc_now, nullable=False,
    )
