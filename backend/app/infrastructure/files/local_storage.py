"""将原始文件保存到配置的本地根目录，以相对键定位。"""

import logging
import shutil
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from backend.app.application.ports.file_storage import FileStorage, FileStorageError

logger = logging.getLogger(__name__)


class LocalFileStorage(FileStorage):
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def _path(self, storage_key: str) -> Path:
        key = PurePosixPath(storage_key)
        if not storage_key or "\\" in storage_key or ":" in storage_key or key.is_absolute() or ".." in key.parts:
            raise FileStorageError("文件存储标识无效")
        target = self._root.joinpath(*key.parts).resolve()
        if target == self._root or not target.is_relative_to(self._root):
            raise FileStorageError("文件存储位置无效")
        return target

    def save(self, storage_key: str, source: BinaryIO) -> None:
        target = self._path(storage_key)
        created = False
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as output:
                created = True
                source.seek(0)
                shutil.copyfileobj(source, output, length=1024 * 1024)
        except BaseException as error:
            if created:
                try:
                    target.unlink(missing_ok=True)
                except OSError:
                    logger.exception("上传文件中断后的清理未完成，storage_key=%s", storage_key)
            if isinstance(error, OSError):
                raise FileStorageError("文件保存失败") from error
            raise

    def delete(self, storage_key: str) -> None:
        try:
            self._path(storage_key).unlink(missing_ok=True)
        except OSError as error:
            raise FileStorageError("文件清理失败") from error
