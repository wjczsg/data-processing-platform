"""通过 SQLAlchemy 保存 MySQL 文件记录，不隐式提交。"""

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.app.application.ports.file_repository import FileRepository, UploadedFileNotFoundError
from backend.app.domain.file_header import FileHeaderConfiguration
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

    def get_by_id_for_owner(self, file_id: str, owner_id: int) -> UploadedFile | None:
        model = self._session.scalar(select(UploadedFileModel).where(
            UploadedFileModel.id == file_id, UploadedFileModel.owner_id == owner_id,
        ))
        if model is None:
            return None
        return UploadedFile(
            id=model.id, owner_id=model.owner_id, original_filename=model.original_filename,
            storage_key=model.storage_key, size_bytes=model.size_bytes, created_at=model.created_at,
        )

    def update_header(self, configuration: FileHeaderConfiguration, owner_id: int) -> None:
        result = self._session.execute(update(UploadedFileModel).where(
            UploadedFileModel.id == configuration.file_id, UploadedFileModel.owner_id == owner_id,
        ).values(
            has_header=configuration.has_header,
            columns=[{"index": column.index, "name": column.name} for column in configuration.columns],
        ))
        if result.rowcount == 0:
            raise UploadedFileNotFoundError("文件不存在")
