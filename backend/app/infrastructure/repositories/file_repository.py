"""通过 SQLAlchemy 保存 MySQL 文件记录，不隐式提交。"""

from sqlalchemy.orm import Session

from backend.app.application.ports.file_repository import FileRepository
from backend.app.domain.uploaded_file import UploadedFile
from backend.app.infrastructure.db.models.uploaded_file import UploadedFileModel


class MySQLFileRepository(FileRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, file: UploadedFile) -> UploadedFile:
        model = UploadedFileModel(
            id=file.id, owner_id=file.owner_id, original_filename=file.original_filename,
            storage_key=file.storage_key, size_bytes=file.size_bytes, created_at=file.created_at,
        )
        self._session.add(model)
        self._session.flush()
        return file
