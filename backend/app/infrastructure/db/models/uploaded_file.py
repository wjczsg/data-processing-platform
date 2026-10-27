"""uploaded_files 只存元信息，CSV 原始内容由文件存储实现负责。"""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.dialects.mysql import BIGINT, DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.infrastructure.db.models.base import Base


class UploadedFileModel(Base):
    __tablename__ = "uploaded_files"
    __table_args__ = (
        UniqueConstraint("storage_key"),
        CheckConstraint("size_bytes > 0", name="size_bytes"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"},
    )

    id: Mapped[str] = mapped_column(String(32, collation="utf8mb4_bin"), primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255, collation="utf8mb4_bin"), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    # None 表示尚未确认；False 明确表示没有表头，不能用 False 作为默认值。
    has_header: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # 按原始列顺序保存，例如 [{"index": 0, "name": "学号"}]；index 从 0 开始。
    # none_as_null=True 让未确认状态保存为 SQL NULL，而不是 JSON 的 null。
    columns: Mapped[list[dict[str, int | str]] | None] = mapped_column(JSON(none_as_null=True), nullable=True)
