"""已保存文件的信息；不包含文件内容，也不依赖数据库或本地路径。"""

import re
from dataclasses import dataclass
from datetime import datetime, timezone


class FileMetadataError(ValueError):
    """文件信息不符合保存要求。"""


@dataclass(frozen=True, kw_only=True)
class UploadedFile:
    id: str
    owner_id: int
    original_filename: str
    storage_key: str
    size_bytes: int
    created_at: datetime

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9a-f]{32}", self.id):
            raise FileMetadataError("文件编号格式不正确")
        if type(self.owner_id) is not int or self.owner_id <= 0:
            raise FileMetadataError("文件所属用户无效")
        if not self.original_filename.strip() or len(self.original_filename) > 255 or "\0" in self.original_filename:
            raise FileMetadataError("文件名不能为空、不能包含空字符，且不能超过 255 个字符")
        if not self.storage_key or len(self.storage_key) > 255:
            raise FileMetadataError("文件存储标识无效")
        if type(self.size_bytes) is not int or self.size_bytes <= 0:
            raise FileMetadataError("文件大小必须为正整数")
        if self.created_at.tzinfo is not None:
            object.__setattr__(self, "created_at", self.created_at.astimezone(timezone.utc).replace(tzinfo=None))
