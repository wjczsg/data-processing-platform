"""验证文件与数据库记录之间的失败边界，所有文件写入隔离临时目录。"""

import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

from backend.app.application.ports.file_storage import FileStorageError
from backend.app.application.store_uploaded_file import StoreUploadedFileService
from backend.app.infrastructure.files.local_storage import LocalFileStorage


class MemoryFileUnitOfWork:
    def __init__(self):
        self.records = {}
        self.pending = []
        self.files = self

    def add(self, record):
        self.pending.append(record)
        return record

    def commit(self):
        self.records.update((record.id, record) for record in self.pending)
        self.pending.clear()


class FilePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.storage = LocalFileStorage(self.root)
        self.uow = MemoryFileUnitOfWork()
        self.service = StoreUploadedFileService(self.uow, self.storage)

    def store(self):
        source = io.BytesIO(b"\xef\xbb\xbfa,b\r\n001,2\r\n")
        source.seek(5)  # 解析结束后仍必须从文件开头保存。
        record = self.service.store(owner_id=7, filename="同名.csv", size_bytes=len(source.getvalue()), source=source)
        self.assertFalse(source.closed)
        self.assertEqual((self.root / record.storage_key).read_bytes(), source.getvalue())
        return record

    def test_duplicate_names_keep_separate_original_files_and_committed_records(self):
        first, second = self.store(), self.store()
        self.assertNotEqual(first.id, second.id)
        self.assertNotEqual(first.storage_key, second.storage_key)
        self.assertEqual(first.original_filename, second.original_filename)
        self.assertEqual(len(self.uow.records), 2)

    def test_insert_failure_removes_own_file(self):
        self.uow.add = Mock(side_effect=RuntimeError("insert failed"))
        with self.assertRaisesRegex(RuntimeError, "insert failed"):
            self.store()
        self.assertEqual(list(self.root.rglob("*.csv")), [])
        self.assertEqual(self.uow.records, {})

    def test_uncertain_commit_keeps_file_for_reconciliation(self):
        self.uow.commit = Mock(side_effect=RuntimeError("commit result unknown"))
        with self.assertLogs("backend.app.application.store_uploaded_file", level="WARNING"):
            with self.assertRaisesRegex(RuntimeError, "commit result unknown"):
                self.store()
        self.assertEqual(len(list(self.root.rglob("*.csv"))), 1)
        self.assertEqual(self.uow.records, {})

    def test_storage_failure_does_not_insert_metadata(self):
        self.storage.save = Mock(side_effect=FileStorageError("disk full"))
        with self.assertRaises(FileStorageError):
            self.store()
        self.assertEqual(self.uow.pending, [])
        self.assertEqual(self.uow.records, {})

    def test_storage_never_overwrites_or_deletes_existing_file(self):
        self.storage.save("uploads/existing.csv", io.BytesIO(b"original"))
        with self.assertRaises(FileStorageError):
            self.storage.save("uploads/existing.csv", io.BytesIO(b"replacement"))
        self.assertEqual((self.root / "uploads/existing.csv").read_bytes(), b"original")

    def test_partial_copy_failure_cleans_partial_file(self):
        class BrokenSource(io.BytesIO):
            def read(self, size=-1):
                if self.tell():
                    raise OSError("source interrupted")
                return super().read(2)

        with self.assertRaises(FileStorageError):
            self.storage.save("uploads/partial.csv", BrokenSource(b"abcdef"))
        self.assertFalse((self.root / "uploads/partial.csv").exists())

    def test_path_traversal_and_absolute_storage_keys_are_rejected(self):
        for key in ("../outside.csv", "/absolute.csv", "C:/absolute.csv", "uploads\\file.csv", ""):
            with self.subTest(key=key), self.assertRaises(FileStorageError):
                self.storage.save(key, io.BytesIO(b"data"))


if __name__ == "__main__":
    unittest.main()
