"""验证 CSV，保存原始文件和 MySQL 文件记录，返回原始记录预览。"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile as FormUploadFile

from backend.app.api.dependencies import get_current_user, get_store_uploaded_file_service
from backend.app.api.schemas.files import FileReceiveResponse
from backend.app.application.store_uploaded_file import StoreUploadedFileService
from backend.app.core.config import Settings, get_settings
from backend.app.domain.file_rules import (
    EmptyFileError,
    FileTooLargeError,
    InvalidCsvFormatError,
    InvalidFileEncodingError,
    validate_csv_filename,
    validate_file_size,
    validate_non_empty_file,
)
from backend.app.domain.user import User
from backend.app.domain.uploaded_file import FileMetadataError
from backend.app.infrastructure.files.csv_format import validate_csv_format
from backend.app.infrastructure.files.encoding import Utf8FileValidator

router = APIRouter(prefix="/api/files", tags=["文件"])


@router.post(
    "",
    response_model=FileReceiveResponse,
    status_code=201,
    summary="保存单个 CSV 文件及文件信息",
    description=(
        "验证登录，仅接收非零字节、UTF-8 编码的 .csv 文件（兼容 UTF-8 BOM，扩展名不区分大小写），"
        "严格解析完整 CSV 后保存原始文件和数据库记录，返回文件编号及前 5 条记录预览。"
        "不自动识别表头；表头、列数、数据规则和后台任务尚未接入。"
    ),
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
    service: Annotated[StoreUploadedFileService, Depends(get_store_uploaded_file_service)],
) -> FileReceiveResponse:
    # FastAPI 已解析并缓存表单；检查全部文件项，避免重复字段被静默取最后一个。
    form = await request.form()
    if sum(isinstance(value, FormUploadFile) for _, value in form.multi_items()) != 1:
        raise HTTPException(status_code=422, detail="每次只能上传一个文件")

    try:
        validate_csv_filename(file.filename)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    # 同一轮分块读取累计大小、校验编码；每个文件独立保留解码状态。
    size_bytes = 0
    encoding_validator = Utf8FileValidator()
    try:
        while chunk := await file.read(1024 * 1024):
            size_bytes += len(chunk)
            validate_file_size(size_bytes, settings.upload_max_bytes)
            encoding_validator.validate_chunk(chunk)
        validate_non_empty_file(size_bytes)
        encoding_validator.finish()
        # 第二遍读取已有临时文件，逐条解析；同步解析放到线程池执行。
        preview = await run_in_threadpool(validate_csv_format, file.file)
    except FileTooLargeError as error:
        raise HTTPException(status_code=413, detail=str(error)) from error
    except (EmptyFileError, InvalidFileEncodingError, InvalidCsvFormatError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    try:
        record = await run_in_threadpool(
            service.store, owner_id=user.id, filename=file.filename,
            size_bytes=size_bytes, source=file.file,
        )
    except FileMetadataError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    # 请求临时文件由 FastAPI 关闭；正式原始文件及其数据库记录已经保存。
    return FileReceiveResponse(
        file_id=record.id, created_at=record.created_at,
        filename=record.original_filename, content_type=file.content_type,
        size_bytes=record.size_bytes, owner_id=record.owner_id,
        preview_rows=preview.rows, preview_truncated=preview.truncated,
    )
