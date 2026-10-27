"""文件信息的数据访问约定，不负责提交事务。"""

from typing import Protocol

from backend.app.domain.uploaded_file import UploadedFile


class FileRepository(Protocol):
    def add(self, file: UploadedFile) -> UploadedFile:
        """写入文件信息并返回，最终提交由业务决定。"""
        ...
