"""检查文件归属，生成任务并提交到数据库；后台执行后续接入。"""

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.application.ports.file_repository import UploadedFileNotFoundError
from backend.app.infrastructure.db.models import ProcessingTaskModel, UploadedFileModel


def create_processing_task(
    session: Session, *, file_id: str, owner_id: int,
) -> dict[str, str]:
    """为当前用户的文件创建 pending 任务，异常回滚由外部 session_scope 负责。"""
    existing_file_id = session.scalar(select(UploadedFileModel.id).where(
        UploadedFileModel.id == file_id,
        UploadedFileModel.owner_id == owner_id,
    ))
    if existing_file_id is None:
        # 不区分文件不存在和归属不符，避免泄露其他用户的文件信息。
        raise UploadedFileNotFoundError("文件不存在")

    task = ProcessingTaskModel(
        id=uuid4().hex, file_id=file_id, owner_id=owner_id, status="pending",
    )
    # 在提交前整理返回值，避免 commit 使 ORM 对象过期后再次查询数据库。
    result = {"task_id": task.id, "file_id": task.file_id, "status": task.status}
    session.add(task)
    # commit 自动执行 flush，并填充模型中定义的创建和更新时间。
    session.commit()
    return result
