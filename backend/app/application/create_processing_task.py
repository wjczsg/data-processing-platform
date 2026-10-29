"""检查文件归属及表头配置，保存输入快照并创建待执行任务。"""

from copy import deepcopy
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.application.ports.file_repository import UploadedFileNotFoundError
from backend.app.infrastructure.db.models import ProcessingTaskModel, UploadedFileModel


class FileConfigurationNotReadyError(ValueError):
    """文件尚未确认表头，或保存的列配置不可用。"""


def _snapshot_input_config(uploaded_file: UploadedFileModel) -> dict[str, object]:
    if uploaded_file.has_header is None:
        raise FileConfigurationNotReadyError("请先确认文件表头")

    columns = uploaded_file.columns
    if not isinstance(columns, list) or not columns:
        raise FileConfigurationNotReadyError("文件列配置不可用，请重新确认表头")
    seen_names = set()
    for index, column in enumerate(columns):
        if not isinstance(column, dict):
            raise FileConfigurationNotReadyError("文件列配置不可用，请重新确认表头")
        name = column.get("name")
        if (type(column.get("index")) is not int or column["index"] != index
                or not isinstance(name, str) or not name.strip() or name in seen_names):
            raise FileConfigurationNotReadyError("文件列配置不可用，请重新确认表头")
        seen_names.add(name)

    # 深拷贝嵌套列结构，任务不与文件配置共用可变对象。
    return {"version": 1, "has_header": uploaded_file.has_header, "columns": deepcopy(columns)}


def create_processing_task(
    session: Session, *, file_id: str, owner_id: int,
) -> dict[str, str]:
    """为当前用户的文件创建 pending 任务，异常回滚由外部 session_scope 负责。"""
    uploaded_file = session.scalar(select(UploadedFileModel).where(
        UploadedFileModel.id == file_id,
        UploadedFileModel.owner_id == owner_id,
    ))
    if uploaded_file is None:
        # 不区分文件不存在和归属不符，避免泄露其他用户的文件信息。
        raise UploadedFileNotFoundError("文件不存在")

    input_config = _snapshot_input_config(uploaded_file)
    task = ProcessingTaskModel(
        id=uuid4().hex, file_id=file_id, owner_id=owner_id, status="pending",
        input_config=input_config,
    )
    # 在提交前整理返回值，避免 commit 使 ORM 对象过期后再次查询数据库。
    result = {"task_id": task.id, "file_id": task.file_id, "status": task.status}
    session.add(task)
    # commit 自动执行 flush，并填充模型中定义的创建和更新时间。
    session.commit()
    return result
