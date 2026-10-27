"""原始文件内容的存储约定，与文件信息仓储分开。"""

from typing import BinaryIO, Protocol


class FileStorageError(Exception):
    """文件存储失败。"""


class FileStorage(Protocol):
    def save(self, storage_key: str, source: BinaryIO) -> None:
        """从头保存原始字节，不覆盖已有对象，不关闭调用方的 source。"""
        ...

    def delete(self, storage_key: str) -> None:
        """清理指定对象，不存在时无需报错。"""
        ...
