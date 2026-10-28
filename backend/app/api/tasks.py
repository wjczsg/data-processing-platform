"""为当前用户的上传文件创建处理任务记录。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_current_user, get_database_session
from backend.app.api.schemas.tasks import CreateTaskRequest, CreateTaskResponse
from backend.app.application.create_processing_task import create_processing_task
from backend.app.application.ports.file_repository import UploadedFileNotFoundError
from backend.app.domain.user import User

router = APIRouter(prefix="/api/tasks", tags=["任务"])


@router.post(
    "", response_model=CreateTaskResponse, status_code=201, summary="创建处理任务记录",
    description=(
        "为当前用户自己的上传文件创建一条 pending 任务并提交到数据库。"
        "当前仅保存记录，不要求先确认表头，不启动后台处理。"
        "每次调用创建独立任务，重复提交去重尚未实现。"
    ),
    responses={401: {"description": "未登录或登录已失效"},
               404: {"description": "文件不存在或不属于当前用户"}},
)
def create_task(
    payload: CreateTaskRequest,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_database_session)],
) -> CreateTaskResponse:
    # 同步数据库操作由 FastAPI 在线程池执行；与认证复用请求级 Session。
    if user.id is None:
        raise RuntimeError("当前登录用户缺少编号")
    try:
        result = create_processing_task(session, file_id=payload.file_id, owner_id=user.id)
    except UploadedFileNotFoundError as error:
        raise HTTPException(status_code=404, detail="文件不存在") from error
    return CreateTaskResponse(**result)
