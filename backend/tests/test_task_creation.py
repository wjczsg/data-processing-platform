"""创建任务接口的认证、参数检查和异常响应，不连接 MySQL。"""

import unittest
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_authentication_service, get_database_session
from backend.app.api.exception_handlers import (
    request_validation_exception_handler, unhandled_exception_handler,
)
from backend.app.api.tasks import router
from backend.app.application.create_processing_task import FileConfigurationNotReadyError
from backend.app.application.ports.file_repository import UploadedFileNotFoundError
from backend.app.application.ports.token_service import InvalidAccessTokenError
from backend.app.domain.user import User
from backend.tests.asgi_client import request_json


class TaskCreationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.add_exception_handler(RequestValidationError, request_validation_exception_handler)
        self.app.add_exception_handler(Exception, unhandled_exception_handler)
        self.session = Mock(spec=Session)
        self.auth = Mock()
        self.auth.current_user.return_value = User(id=7, username="task_user", password_hash="test-only-hash")
        self.app.dependency_overrides[get_authentication_service] = lambda: self.auth
        self.app.dependency_overrides[get_database_session] = lambda: self.session
        self.file_id = "a" * 32
        self.result = {"task_id": "b" * 32, "file_id": self.file_id, "status": "pending"}
        self.create = self.enterContext(patch(
            "backend.app.api.tasks.create_processing_task", return_value=self.result,
        ))

    async def create_task(self, payload=None, *, headers=None):
        return await request_json(
            self.app, "/api/tasks", "POST", {"file_id": self.file_id} if payload is None else payload,
            headers={"Authorization": "Bearer test-token"} if headers is None else headers,
        )

    async def test_success_uses_authenticated_owner_and_returns_task_information(self):
        status, body = await self.create_task()
        self.assertEqual(status, 201)
        self.assertEqual(body, self.result)
        self.create.assert_called_once_with(self.session, file_id=self.file_id, owner_id=7)

    async def test_missing_or_invalid_login_prevents_creation(self):
        self.assertEqual((await self.create_task(headers={}))[0], 401)
        self.auth.current_user.side_effect = InvalidAccessTokenError("登录已失效")
        self.assertEqual((await self.create_task())[0], 401)
        self.create.assert_not_called()

    async def test_invalid_requests_and_client_controlled_fields_are_rejected(self):
        payloads = [{}, {"file_id": None}, {"file_id": 123}, {"file_id": "invalid"},
                    {"file_id": "A" * 32}, {"file_id": "a" * 33}]
        payloads.extend({"file_id": self.file_id, key: value} for key, value in (
            ("owner_id", 999), ("status", "succeeded"), ("task_id", "c" * 32),
            ("input_config", {"has_header": True, "columns": []}),
        ))
        for payload in payloads:
            with self.subTest(payload=payload):
                self.assertEqual((await self.create_task(payload))[0], 422)
        self.create.assert_not_called()

    async def test_unavailable_file_returns_not_found(self):
        self.create.side_effect = UploadedFileNotFoundError("内部文件归属信息")
        self.assertEqual(await self.create_task(), (404, {"detail": "文件不存在"}))

    async def test_unready_configuration_returns_conflict_with_actionable_message(self):
        for message in ("请先确认文件表头", "文件列配置不可用，请重新确认表头"):
            with self.subTest(message=message):
                self.create.side_effect = FileConfigurationNotReadyError(message)
                self.assertEqual(await self.create_task(), (409, {"detail": message}))

    async def test_database_failure_is_not_reported_as_success_or_exposed(self):
        self.create.side_effect = RuntimeError("private database failure details")
        status, body = await self.create_task()
        self.assertEqual(status, 500)
        self.assertEqual(body["detail"], "Internal Server Error")
        self.assertNotIn("private", str(body))


if __name__ == "__main__":
    unittest.main()
