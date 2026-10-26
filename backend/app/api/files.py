"""文件上传入口：验证登录并临时接收单个文件。"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from starlette.datastructures import UploadFile as FormUploadFile

from backend.app.api.dependencies import get_current_user
from backend.app.api.schemas.files import FileReceiveResponse
from backend.app.core.config import Settings, get_settings
from backend.app.domain.file_rules import FileTooLargeError, validate_csv_filename, validate_file_size
from backend.app.domain.user import User

router = APIRouter(prefix="/api/files", tags=["文件"])


@router.post(
    "",
    response_model=FileReceiveResponse,
    summary="临时接收单个文件",
    description="验证登录，仅接收 .csv 文件（扩展名不区分大小写）。CSV 内容解析、正式存储、数据库记录和后台任务尚未接入。",
    responses={413: {"description": "文件内容大小超过 UPLOAD_MAX_BYTES 配置上限，默认 50 MiB"}},
)
async def receive_file(
    request: Request,
    file: Annotated[UploadFile, File(
        description="待接收的 .csv 文件，扩展名不区分大小写，表单字段名为 file",
        json_schema_extra={"format": "binary"},
    )],
    user: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> FileReceiveResponse:
    # FastAPI 已解析并缓存表单；检查全部文件项，避免重复字段被静默取最后一个。
    form = await request.form()
    if sum(isinstance(value, FormUploadFile) for _, value in form.multi_items()) != 1:
        raise HTTPException(status_code=422, detail="每次只能上传一个文件")

    try:
        validate_csv_filename(file.filename)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    # 分块读取以确认实际内容大小，避免一次性把整个文件读入内存。
    size_bytes = 0
    try:
        while chunk := await file.read(1024 * 1024):
            size_bytes += len(chunk)
            validate_file_size(size_bytes, settings.upload_max_bytes)
    except FileTooLargeError as error:
        raise HTTPException(status_code=413, detail=str(error)) from error

    # 临时文件由 FastAPI 在请求结束时关闭；正式存储后续通过存储接口接入。
    return FileReceiveResponse(
        filename=file.filename, content_type=file.content_type,
        size_bytes=size_bytes, owner_id=user.id,
    )
