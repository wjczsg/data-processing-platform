"""原始文件内容的存储约定，与文件信息仓储分开。"""

from typing import BinaryIO, ContextManager, Protocol


class FileStorageError(Exception):
    """文件存储失败。"""


class FileStorage(Protocol):
    def open_read(self, storage_key: str) -> ContextManager[BinaryIO]:
        """只读打开已有对象，离开上下文时关闭，读取异常转为 FileStorageError。"""
        ...

    def save(self, storage_key: str, source: BinaryIO) -> None:
        """从头保存原始字节，不覆盖已有对象，不关闭调用方的 source。"""
        ...

    def delete(self, storage_key: str) -> None:
        """清理指定对象，不存在时无需报错。"""
        ...
