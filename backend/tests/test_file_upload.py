"""验证真实 multipart 请求、公共身份校验及单文件接收，使用隔离临时目录和内存仓库，不访问 MySQL。"""

import unittest
import threading
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from backend.app.api.dependencies import get_authentication_service, get_file_unit_of_work
from backend.app.api.exception_handlers import request_validation_exception_handler
from backend.app.api.files import router
from backend.app.application.ports.token_service import InvalidAccessTokenError
from backend.app.core.config import Settings, get_settings
from backend.app.domain.user import User
from backend.app.infrastructure.files.csv_format import validate_csv_format
from backend.app.infrastructure.files.encoding import Utf8FileValidator
from backend.tests.asgi_client import request_json
from backend.tests.test_file_persistence import MemoryFileUnitOfWork


class FileUploadTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.user = User(id=7, username="student_07", password_hash="test-only-hash")
        self.service = Mock()
        self.service.current_user.return_value = self.user
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.add_exception_handler(RequestValidationError, request_validation_exception_handler)
        self.app.dependency_overrides[get_authentication_service] = lambda: self.service
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.uow = MemoryFileUnitOfWork()
        self.app.dependency_overrides[get_file_unit_of_work] = lambda: self.uow
        self.settings = Settings(_env_file=None, mysql_user="test_user", mysql_password="test-only-password",
                                 upload_max_bytes=50 * 1024 * 1024, upload_storage_dir=Path(self.directory.name))
        self.app.dependency_overrides[get_settings] = lambda: self.settings

    async def upload(self, files, token="test-access", owner_id=None, *, file_content_type="text/csv"):
        boundary = "test-upload-boundary"
        parts = []
        for field, filename, content in files:
            parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; '
                          f'filename="{filename}"\r\nContent-Type: {file_content_type}\r\n\r\n').encode()
                         + content + b"\r\n")
        if owner_id is not None:
            parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="owner_id"'
                          f'\r\n\r\n{owner_id}\r\n').encode())
        parts.append(f"--{boundary}--\r\n".encode())
        headers = {"Authorization": f"Bearer {token}"} if token is not None else None
        return await request_json(self.app, "/api/files", "POST", headers=headers,
            raw_body=b"".join(parts), content_type=f"multipart/form-data; boundary={boundary}")

    async def test_receives_file_with_authenticated_owner_and_persists_original_bytes(self):
        content = "order_id,product,amount,order_date\nORD1,键盘,199,2026-10-26\n".encode()
        status, body = await self.upload([("file", "订单.csv", content)], owner_id=999)
        self.assertEqual(status, 201)
        self.assertEqual((body["filename"], body["size_bytes"]), ("订单.csv", len(content)))
        self.assertEqual(body["content_type"], "text/csv")
        self.assertEqual(body["owner_id"], 7)
        self.assertIs(body["persisted"], True)
        record = self.uow.records[body["file_id"]]
        self.assertEqual(record.owner_id, 7)
        self.assertEqual((Path(self.directory.name) / record.storage_key).read_bytes(), content)
        self.assertTrue(body["created_at"].endswith("Z"))
        self.assertEqual(body["preview_rows"], [
            ["order_id", "product", "amount", "order_date"], ["ORD1", "键盘", "199", "2026-10-26"],
        ])
        self.assertFalse(body["preview_truncated"])
        self.assertNotIn("password_hash", body)
        self.service.current_user.assert_called_once_with("test-access")

    async def test_missing_credentials_are_rejected(self):
        status, _ = await self.upload([("file", "orders.csv", b"data")], token=None)
        self.assertEqual(status, 401)
        self.service.current_user.assert_not_called()

    async def test_filename_metadata_limit_is_checked_before_persistence(self):
        accepted = "x" * 251 + ".csv"
        self.assertEqual((await self.upload([("file", accepted, b"a\n1\n")]))[0], 201)
        status, _ = await self.upload([("file", "x" * 252 + ".csv", b"a\n1\n")])
        self.assertEqual(status, 422)
        self.assertEqual(len(self.uow.records), 1)
        self.assertEqual(len(list(Path(self.directory.name).rglob("*.csv"))), 1)

    async def test_invalid_login_state_is_rejected(self):
        self.service.current_user.side_effect = InvalidAccessTokenError("expired")
        self.assertEqual((await self.upload([("file", "orders.csv", b"data")]))[0], 401)

    async def test_missing_file_is_rejected(self):
        self.assertEqual((await self.upload([]))[0], 422)

    async def test_configured_file_size_limit_allows_boundary_and_rejects_one_extra_byte(self):
        self.settings = self.settings.model_copy(update={"upload_max_bytes": 8})
        for size, expected_status in ((7, 201), (8, 201), (9, 413)):
            with self.subTest(size=size):
                status, body = await self.upload([("file", "orders.csv", b"x" * size)])
                self.assertEqual(status, expected_status)
                if status == 201:
                    self.assertEqual(body["size_bytes"], size)
                else:
                    self.assertEqual(body, {"detail": "文件大小不能超过 8 字节"})

    async def test_size_limit_counts_all_read_chunks(self):
        limit = 1024 * 1024 + 1
        self.settings = self.settings.model_copy(update={"upload_max_bytes": limit})
        status, body = await self.upload([("file", "orders.csv", b"x" * (limit + 1))])
        self.assertEqual((status, body), (413, {"detail": f"文件大小不能超过 {limit} 字节"}))

    async def test_zero_byte_file_is_rejected(self):
        status, body = await self.upload([("file", "orders.csv", b"")])
        self.assertEqual((status, body), (422, {"detail": "不能上传空文件"}))
        self.assertEqual(self.uow.records, {})
        self.assertEqual(list(Path(self.directory.name).rglob("*.csv")), [])

    async def test_nonzero_content_is_not_treated_as_zero_byte_file(self):
        for content in (b"x", b" ", b"\n", b"\xef\xbb\xbf", b"order_id,product,amount,order_date\n"):
            with self.subTest(content=content):
                status, body = await self.upload([("file", "orders.csv", content)])
                self.assertEqual(status, 201)
                self.assertEqual(body["size_bytes"], len(content))

    async def test_utf8_chinese_and_optional_bom_preserve_original_byte_count(self):
        data = "order_id,product,amount,order_date\n订单1,键盘,199,2026-10-27\n".encode("utf-8")
        for content in (data, b"\xef\xbb\xbf" + data):
            with self.subTest(has_bom=content.startswith(b"\xef\xbb\xbf")):
                status, body = await self.upload([("file", "orders.csv", content)])
                self.assertEqual((status, body["size_bytes"]), (201, len(content)))

    async def test_multibyte_characters_split_between_read_chunks_are_accepted(self):
        for character in ("中", "🙂"):
            with self.subTest(character=character):
                content = b"a" * (1024 * 1024 - 1) + character.encode("utf-8") + b"\n"
                status, body = await self.upload([("file", "orders.csv", content)])
                self.assertEqual((status, body["size_bytes"]), (201, len(content)))
                self.assertEqual(body["preview_rows"], [["a" * 200]])
                self.assertTrue(body["preview_truncated"])

    async def test_preview_keeps_first_data_record_and_reports_record_limit(self):
        content = b"001,Alice,85\n002,Bob,90\n003,Carol,80\n004,Dan,75\n005,Eve,95\n006,Frank,88\n"
        status, body = await self.upload([("file", "students.csv", content)])
        self.assertEqual(status, 201)
        self.assertEqual(body["preview_rows"], [
            ["001", "Alice", "85"], ["002", "Bob", "90"], ["003", "Carol", "80"],
            ["004", "Dan", "75"], ["005", "Eve", "95"],
        ])
        self.assertTrue(body["preview_truncated"])
        self.assertNotIn("headers", body)
        self.assertNotIn("has_header", body)

    async def test_invalid_utf8_is_rejected_including_errors_after_first_read_chunk(self):
        for content in (b"secret-order\xff", "中文".encode("gbk"), "orders".encode("utf-16"),
                        b"a" * (1024 * 1024) + b"\xff"):
            with self.subTest(size=len(content)):
                status, body = await self.upload([("file", "orders.csv", content)])
                self.assertEqual((status, body), (422, {
                    "detail": "文件无法按 UTF-8 解码，请另存为 UTF-8 编码后重新上传",
                }))

    async def test_incomplete_characters_and_partial_bom_at_eof_are_rejected(self):
        for content in (b"\xe4", b"\xe4\xb8", b"\xef", b"\xef\xbb", b"orders\n\xf0\x9f\x99"):
            with self.subTest(content=content):
                status, body = await self.upload([("file", "orders.csv", content)])
                self.assertEqual((status, body), (422, {
                    "detail": "文件无法按 UTF-8 解码，请另存为 UTF-8 编码后重新上传",
                }))

    async def test_failed_upload_does_not_leave_decoder_state_for_next_request(self):
        self.assertEqual((await self.upload([("file", "broken.csv", b"\xe4")]))[0], 422)
        self.assertEqual((await self.upload([("file", "orders.csv", b"order_id\nORD1\n")]))[0], 201)

    async def test_csv_quoted_commas_double_quotes_and_multiline_fields_are_accepted(self):
        data = ('order_id,product,amount\r\n'
                'ORD1,"键盘,黑色",199\r\n'
                'ORD2,"他说""你好""",89\r\n'
                'ORD3,"第一行\r\n第二行",99\r\n').encode("utf-8")
        for content in (data, b"\xef\xbb\xbf" + data):
            with self.subTest(has_bom=content.startswith(b"\xef\xbb\xbf")):
                status, body = await self.upload([("file", "orders.csv", content)])
                self.assertEqual((status, body["size_bytes"]), (201, len(content)))

    async def test_csv_syntax_errors_return_422_with_physical_line_location(self):
        for content, line in ((b'a,b\n1,"unfinished\n', 2), (b'a,b\n1,"ok"x\n', 2),
                              (b'a,b\n1,"line1\nline2"\n2,"unfinished', 4),
                              (b'a,b\n' + b'1,2\n' * 5 + b'2,"unfinished', 7)):
            with self.subTest(line=line, size=len(content)):
                status, body = await self.upload([("file", "orders.csv", content)])
                self.assertEqual((status, body), (422, {
                    "detail": f"CSV 格式错误，解析在第 {line} 个物理行附近失败",
                }))

    async def test_csv_syntax_check_does_not_enforce_template_columns_or_business_rules(self):
        for content in (b"custom\none,two,three\n", b"order_id,amount\nORD1,abc\n",
                        b"order_id;product;amount\nORD1;keyboard;abc\n"):
            with self.subTest(content=content):
                self.assertEqual((await self.upload([("file", "orders.csv", content)]))[0], 201)

    async def test_csv_parsing_runs_in_worker_and_framework_closes_temporary_file(self):
        request_thread = threading.get_ident()
        for content, expected_status in ((b"a,b\n1,2\n", 201), (b'a,b\n1,"unfinished', 422)):
            observed = {}

            def validate_in_worker(stream):
                observed.update(thread=threading.get_ident(), stream=stream)
                return validate_csv_format(stream)

            with self.subTest(status=expected_status), patch(
                "backend.app.api.files.validate_csv_format", side_effect=validate_in_worker,
            ):
                self.assertEqual((await self.upload([("file", "orders.csv", content)]))[0], expected_status)
                self.assertNotEqual(observed["thread"], request_thread)
                self.assertTrue(observed["stream"].closed)

    async def test_csv_extension_is_case_insensitive(self):
        for filename in ("orders.csv", "orders.CSV", "orders.CsV"):
            with self.subTest(filename=filename):
                status, body = await self.upload([("file", filename, b"order_id\nORD1\n")])
                self.assertEqual(status, 201)
                self.assertEqual(body["filename"], filename)

    async def test_invalid_or_missing_extensions_are_rejected_despite_csv_content_type(self):
        for filename in ("orders.xlsx", "orders.txt", "orders.csv.exe", "orders", "", ".csv"):
            with self.subTest(filename=filename):
                status, body = await self.upload([("file", filename, b"order_id\nORD1\n")])
                self.assertEqual((status, body), (422, {"detail": "仅支持上传 CSV 文件（.csv）"}))

    async def test_csv_extension_does_not_require_browser_to_report_csv_content_type(self):
        for content_type in ("text/plain", "application/octet-stream"):
            with self.subTest(content_type=content_type):
                status, _ = await self.upload([("file", "orders.csv", b"order_id\nORD1\n")],
                    file_content_type=content_type)
                self.assertEqual(status, 201)

    async def test_multiple_files_are_rejected_even_with_different_field_names(self):
        for other_field in ("file", "another_file"):
            with self.subTest(other_field=other_field):
                status, body = await self.upload([
                    ("file", "one.csv", b"one"), (other_field, "two.csv", b"two"),
                ])
                self.assertEqual((status, body), (422, {"detail": "每次只能上传一个文件"}))


class Utf8FileValidatorTests(unittest.TestCase):
    def test_bom_and_multibyte_characters_can_be_split_at_every_byte(self):
        validator = Utf8FileValidator()
        for value in b"\xef\xbb\xbf" + "中文🙂".encode("utf-8"):
            validator.validate_chunk(bytes([value]))
        validator.finish()


if __name__ == "__main__":
    unittest.main()
