"""使用真实文件读取和业务流程验证确认接口，数据库仓库以 Mock 替代。"""

import io
import threading
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from backend.app.api.dependencies import get_authentication_service, get_file_storage, get_file_unit_of_work
from backend.app.api.exception_handlers import request_validation_exception_handler
from backend.app.api.files import router
from backend.app.application.ports.token_service import InvalidAccessTokenError
from backend.app.domain.file_header import InvalidFileHeaderError
from backend.app.domain.user import User
from backend.app.domain.uploaded_file import UploadedFile
from backend.app.infrastructure.files.csv_format import read_file_columns
from backend.app.infrastructure.files.local_storage import LocalFileStorage
from backend.tests.asgi_client import request_json


class FileHeaderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.storage = LocalFileStorage(self.root)
        self.record = UploadedFile(id="a" * 32, owner_id=7, original_filename="students.csv",
            storage_key="uploads/7/test.csv", size_bytes=21, created_at=datetime(2026, 10, 27))
        self.source_path = self.root / self.record.storage_key
        self.source_path.parent.mkdir(parents=True)
        self.source_path.write_bytes(b"code,name\n001,Alice\n")
        self.uow = Mock()
        self.uow.files.get_by_id_for_owner.side_effect = lambda file_id, owner_id: (
            self.record if (file_id, owner_id) == (self.record.id, self.record.owner_id) else None)
        self.auth = Mock()
        self.auth.current_user.return_value = User(id=7, username="student_07", password_hash="test-only")
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.add_exception_handler(RequestValidationError, request_validation_exception_handler)
        self.app.dependency_overrides[get_authentication_service] = lambda: self.auth
        self.app.dependency_overrides[get_file_unit_of_work] = lambda: self.uow
        self.app.dependency_overrides[get_file_storage] = lambda: self.storage

    async def confirm(self, payload, *, file_id=None, token="access"):
        return await request_json(self.app, f"/api/files/{file_id or self.record.id}/header", "PUT", payload,
            headers={"Authorization": f"Bearer {token}"} if token is not None else None)

    async def test_quoted_bom_headers_are_normalized_saved_and_returned(self):
        original = '\ufeff 学号 ,"姓,名","说明\n备注"\r\n001,Alice,ok\r\n'.encode("utf-8")
        self.source_path.write_bytes(original)
        status, body = await self.confirm({"has_header": True})
        self.assertEqual(status, 200)
        self.assertEqual(body["columns"], [
            {"index": 0, "name": "学号"}, {"index": 1, "name": "姓,名"}, {"index": 2, "name": "说明\n备注"},
        ])
        self.assertTrue(body["has_header"])
        self.assertEqual(body["file_id"], self.record.id)
        configuration, owner_id = self.uow.files.update_header.call_args.args
        self.assertEqual(owner_id, 7)
        self.assertEqual([column.name for column in configuration.columns], ["学号", "姓,名", "说明\n备注"])
        self.uow.commit.assert_called_once_with()
        self.assertEqual(self.source_path.read_bytes(), original)
        self.assertNotIn("storage_key", body)

    async def test_without_header_uses_first_record_with_fields_and_preserves_original(self):
        original = b"\n\n001,Alice\n002,Bob,extra\n"
        self.source_path.write_bytes(original)
        status, body = await self.confirm({"has_header": False})
        self.assertEqual(status, 200)
        self.assertFalse(body["has_header"])
        self.assertEqual(body["columns"], [{"index": 0, "name": "column_1"}, {"index": 1, "name": "column_2"}])
        self.assertEqual(self.source_path.read_bytes(), original)

    async def test_empty_and_duplicate_header_names_are_rejected_without_writing(self):
        for content in (b"a,,c\n", b"a, a \n", b" \n", b"\na,b\n"):
            with self.subTest(content=content):
                self.source_path.write_bytes(content)
                status, _ = await self.confirm({"has_header": True})
                self.assertEqual(status, 422)
        self.uow.files.update_header.assert_not_called()
        self.uow.commit.assert_not_called()

    async def test_empty_bom_only_invalid_encoding_and_csv_syntax_do_not_write(self):
        for content in (b"", b"\xef\xbb\xbf", b'"unfinished', b"a,\xff"):
            with self.subTest(content=content):
                self.source_path.write_bytes(content)
                self.assertEqual((await self.confirm({"has_header": True}))[0], 422)
        self.uow.files.update_header.assert_not_called()
        self.uow.commit.assert_not_called()

    async def test_other_users_and_missing_files_are_indistinguishable_and_never_read_disk(self):
        with patch.object(self.storage, "open_read", side_effect=AssertionError("must not read")):
            missing = await self.confirm({"has_header": True}, file_id="b" * 32)
            self.auth.current_user.return_value = User(id=8, username="other_user", password_hash="test-only")
            foreign = await self.confirm({"has_header": True})
        self.assertEqual(missing, (404, {"detail": "文件不存在"}))
        self.assertEqual(foreign, missing)
        self.uow.files.update_header.assert_not_called()

    async def test_missing_and_invalid_credentials_are_rejected(self):
        self.assertEqual((await self.confirm({"has_header": True}, token=None))[0], 401)
        self.auth.current_user.side_effect = InvalidAccessTokenError("expired")
        self.assertEqual((await self.confirm({"has_header": True}))[0], 401)
        self.uow.files.get_by_id_for_owner.assert_not_called()

    async def test_only_explicit_boolean_and_file_id_are_accepted(self):
        payloads = [{}, *({"has_header": value} for value in (None, "true", 1, 0, [])),
                    {"has_header": True, "owner_id": 999}, {"has_header": True, "columns": []}]
        for payload in payloads:
            with self.subTest(payload=payload):
                self.assertEqual((await self.confirm(payload))[0], 422)
        self.assertEqual((await self.confirm({"has_header": True}, file_id="invalid-id"))[0], 422)
        self.uow.files.get_by_id_for_owner.assert_not_called()
        self.uow.commit.assert_not_called()

    async def test_missing_original_returns_503_without_updating_configuration(self):
        self.source_path.unlink()
        status, body = await self.confirm({"has_header": True})
        self.assertEqual(status, 503)
        self.assertNotIn(str(self.root), str(body))
        self.uow.files.update_header.assert_not_called()
        self.uow.commit.assert_not_called()

    async def test_confirmation_runs_outside_the_event_loop_thread(self):
        request_thread = threading.get_ident()
        observed = []

        def read_in_worker(source, has_header):
            observed.append(threading.get_ident())
            return read_file_columns(source, has_header)

        with patch("backend.app.api.dependencies.read_file_columns", side_effect=read_in_worker):
            self.assertEqual((await self.confirm({"has_header": True}))[0], 200)
        self.assertEqual(len(observed), 1)
        self.assertNotEqual(observed[0], request_thread)


class FileColumnReaderTests(unittest.TestCase):
    def test_full_names_and_columns_exceeding_preview_limits_are_retained(self):
        names = ["x" * (128 * 1024 + 1), *[f"列{index}" for index in range(1, 55)]]
        source = io.BytesIO((",".join(names) + "\n").encode("utf-8"))
        columns = read_file_columns(source, True)
        self.assertEqual([column.name for column in columns], names)
        self.assertEqual([column.index for column in columns], list(range(55)))
        self.assertFalse(source.closed)

    def test_duplicate_check_is_case_sensitive_and_parser_errors_do_not_close_owned_stream(self):
        source = io.BytesIO(b"Name,name\n")
        self.assertEqual([column.name for column in read_file_columns(source, True)], ["Name", "name"])
        invalid = io.BytesIO(b"a, a\n")
        with self.assertRaises(InvalidFileHeaderError):
            read_file_columns(invalid, True)
        self.assertFalse(invalid.closed)


if __name__ == "__main__":
    unittest.main()
