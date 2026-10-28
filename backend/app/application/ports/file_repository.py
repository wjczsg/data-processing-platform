"""文件信息的数据访问约定，不负责提交事务。"""

from typing import Protocol

from backend.app.domain.uploaded_file import UploadedFile
from backend.app.domain.file_header import FileHeaderConfiguration


class UploadedFileNotFoundError(Exception):
    """文件不存在或不属于当前用户，对外不区分两种情况。"""


class FileRepository(Protocol):
    def add(self, file: UploadedFile) -> UploadedFile:
        """写入文件信息并返回，最终提交由业务决定。"""
        ...

    def get_by_id_for_owner(self, file_id: str, owner_id: int) -> UploadedFile | None:
        """按文件编号和用户编号联合查询，不返回其他用户的文件。"""
        ...

    def update_header(self, configuration: FileHeaderConfiguration, owner_id: int) -> None:
        """按文件归属更新两项设置，不自行提交；文件不存在时抛出异常。"""
        ...
