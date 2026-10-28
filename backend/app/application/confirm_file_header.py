"""确认文件归属，读取完整列信息，再提交表头设置。"""

from collections.abc import Callable
from typing import BinaryIO

from backend.app.application.ports.file_repository import UploadedFileNotFoundError
from backend.app.application.ports.file_storage import FileStorage
from backend.app.application.ports.unit_of_work import FileUnitOfWork
from backend.app.domain.file_header import FileColumn, FileHeaderConfiguration


class ConfirmFileHeaderService:
    def __init__(
        self, unit_of_work: FileUnitOfWork, storage: FileStorage,
        read_columns: Callable[[BinaryIO, bool], tuple[FileColumn, ...]],
    ) -> None:
        self._uow = unit_of_work
        self._storage = storage
        # 解析能力从外部组装传入，业务流程不依赖具体 CSV 解析实现。
        self._read_columns = read_columns

    def confirm(self, *, file_id: str, owner_id: int, has_header: bool) -> FileHeaderConfiguration:
        record = self._uow.files.get_by_id_for_owner(file_id, owner_id)
        if record is None:
            raise UploadedFileNotFoundError("文件不存在")
        with self._storage.open_read(record.storage_key) as source:
            columns = self._read_columns(source, has_header)
        configuration = FileHeaderConfiguration(file_id, has_header, columns)
        self._uow.files.update_header(configuration, owner_id)
        self._uow.commit()
        return configuration
