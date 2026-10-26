"""验证真实 multipart 请求、公共身份校验及单文件接收，不访问磁盘存储或 MySQL。"""

import unittest
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from backend.app.api.dependencies import get_authentication_service
from backend.app.api.exception_handlers import request_validation_exception_handler
from backend.app.api.files import router
from backend.app.application.ports.token_service import InvalidAccessTokenError
from backend.app.domain.user import User
from backend.tests.asgi_client import request_json


class FileUploadTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.user = User(id=7, username="student_07", password_hash="test-only-hash")
        self.service = Mock()
        self.service.current_user.return_value = self.user
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.add_exception_handler(RequestValidationError, request_validation_exception_handler)
        self.app.dependency_overrides[get_authentication_service] = lambda: self.service

    async def upload(self, files, token="test-access", owner_id=None):
        boundary = "test-upload-boundary"
        parts = []
        for field, filename, content in files:
            parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; '
                          f'filename="{filename}"\r\nContent-Type: text/csv\r\n\r\n').encode()
                         + content + b"\r\n")
        if owner_id is not None:
            parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="owner_id"'
                          f'\r\n\r\n{owner_id}\r\n').encode())
        parts.append(f"--{boundary}--\r\n".encode())
        headers = {"Authorization": f"Bearer {token}"} if token is not None else None
        return await request_json(self.app, "/api/files", "POST", headers=headers,
            raw_body=b"".join(parts), content_type=f"multipart/form-data; boundary={boundary}")

    async def test_receives_file_with_authenticated_owner_and_reports_no_persistence(self):
        content = "order_id,product,amount,order_date\nORD1,键盘,199,2026-10-26\n".encode()
        status, body = await self.upload([("file", "订单.csv", content)], owner_id=999)
        self.assertEqual(status, 200)
        self.assertEqual((body["filename"], body["size_bytes"]), ("订单.csv", len(content)))
        self.assertEqual(body["content_type"], "text/csv")
        self.assertEqual(body["owner_id"], 7)
        self.assertIs(body["persisted"], False)
        self.assertNotIn("password_hash", body)
        self.service.current_user.assert_called_once_with("test-access")

    async def test_missing_credentials_are_rejected(self):
        status, _ = await self.upload([("file", "orders.csv", b"data")], token=None)
        self.assertEqual(status, 401)
        self.service.current_user.assert_not_called()

    async def test_invalid_login_state_is_rejected(self):
        self.service.current_user.side_effect = InvalidAccessTokenError("expired")
        self.assertEqual((await self.upload([("file", "orders.csv", b"data")]))[0], 401)

    async def test_missing_file_is_rejected(self):
        self.assertEqual((await self.upload([]))[0], 422)

    async def test_multiple_files_are_rejected_even_with_different_field_names(self):
        for other_field in ("file", "another_file"):
            with self.subTest(other_field=other_field):
                status, body = await self.upload([
                    ("file", "one.csv", b"one"), (other_field, "two.csv", b"two"),
                ])
                self.assertEqual((status, body), (422, {"detail": "每次只能上传一个文件"}))


if __name__ == "__main__":
    unittest.main()
