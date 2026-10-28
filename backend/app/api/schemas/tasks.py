"""创建处理任务的请求和响应。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CreateTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_id: str = Field(
        pattern=r"^[0-9a-f]{32}$", description="上传成功后返回的 32 位文件编号",
    )


class CreateTaskResponse(BaseModel):
    task_id: str
    file_id: str
    status: Literal["pending"]
