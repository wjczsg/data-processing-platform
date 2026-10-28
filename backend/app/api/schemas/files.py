"""上传预览响应、表头确认请求及保存结果。"""

from typing import Literal
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator


class FileReceiveResponse(BaseModel):
    file_id: str
    created_at: datetime
    filename: str | None
    content_type: str | None
    size_bytes: int
    owner_id: int
    preview_rows: list[list[str]] = Field(
        description="前 5 条原始 CSV 记录，包含首条记录，不认定表头；最多展示 50 列，每格 200 字符",
    )
    preview_truncated: bool = Field(
        description="预览是否因记录数、列数或单元格长度上限而截断；不影响原始文件或完整语法校验",
    )
    persisted: Literal[True] = True
    message: str = "文件已保存，文件信息已写入数据库；尚未创建处理任务"

    @field_validator("created_at")
    @classmethod
    def include_utc_timezone(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class ConfirmFileHeaderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    has_header: StrictBool = Field(description="true：第一条 CSV 记录是表头；false：文件没有表头")


class FileColumnResponse(BaseModel):
    index: int = Field(description="从 0 开始的原始列序号")
    name: str


class FileHeaderResponse(BaseModel):
    file_id: str
    has_header: bool
    columns: list[FileColumnResponse]
    message: str = "表头设置已保存"
