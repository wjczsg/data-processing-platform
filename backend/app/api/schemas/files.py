"""上传入口的接收结果；当前不创建持久化文件记录。"""

from typing import Literal

from pydantic import BaseModel, Field


class FileReceiveResponse(BaseModel):
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
    persisted: Literal[False] = False
    message: str = "文件已临时接收，尚未保存或创建处理任务"
