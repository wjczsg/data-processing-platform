"""保存原始文件，再提交对应的数据库记录。"""

import logging
from datetime import datetime, timezone
from typing import BinaryIO
from uuid import uuid4

from backend.app.application.ports.file_storage import FileStorage
from backend.app.application.ports.unit_of_work import FileUnitOfWork
from backend.app.domain.uploaded_file import UploadedFile

logger = logging.getLogger(__name__)


class StoreUploadedFileService:
    def __init__(self, unit_of_work: FileUnitOfWork, storage: FileStorage) -> None:
        self._uow = unit_of_work
        self._storage = storage

    def store(self, *, owner_id: int, filename: str, size_bytes: int, source: BinaryIO) -> UploadedFile:
        file_id = uuid4().hex
        record = UploadedFile(
            id=file_id, owner_id=owner_id, original_filename=filename,
            storage_key=f"uploads/{owner_id}/{file_id}.csv", size_bytes=size_bytes,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        self._storage.save(record.storage_key, source)
        try:
            record = self._uow.files.add(record)
        except BaseException:
            # add 不会提交，写入失败时可清理本次生成的文件。
            try:
                self._storage.delete(record.storage_key)
            except Exception:
                logger.exception("文件记录写入失败后的清理未完成，file_id=%s", record.id)
            raise
        try:
            self._uow.commit()
        except BaseException:
            # 连接中断可能发生在服务端提交之后；不能盲目删掉已提交记录引用的文件。
            logger.warning("文件记录提交结果未确认，保留原文件待核对，file_id=%s", record.id)
            raise
        return record
