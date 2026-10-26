"""上传入口的接收结果；当前不创建持久化文件记录。"""

from typing import Literal

from pydantic import BaseModel


class FileReceiveResponse(BaseModel):
    filename: str | None
    content_type: str | None
    size_bytes: int
    owner_id: int
    persisted: Literal[False] = False
    message: str = "文件已临时接收，尚未保存或创建处理任务"
