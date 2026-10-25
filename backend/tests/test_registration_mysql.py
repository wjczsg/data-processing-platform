"""显式开启的真实注册链路检查，结束后删除本次创建的唯一测试账号。"""

import asyncio
import os
import unittest
from uuid import uuid4

from sqlalchemy import delete, select

from backend.app.api.dependencies import get_user_unit_of_work
from backend.app.infrastructure.db.models.user import UserModel
from backend.app.infrastructure.db.session import session_scope
from backend.app.infrastructure.db.unit_of_work import MySQLUserUnitOfWork
from backend.app.infrastructure.security.password_hasher import Argon2PasswordHasher
from backend.tests.asgi_client import post_json


@unittest.skipUnless(os.environ.get("RUN_MYSQL_TESTS") == "1", "需要显式开启 MySQL 集成测试")
class MySQLRegistrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from backend.app.main import app

        self.app = app
        self.lifecycle = app.router.lifespan_context(app)
        await self.lifecycle.__aenter__()
        self.engine = app.state.database_engine
        self.username = "it_register_" + uuid4().hex[:16]
        self.payload = {
            "username": self.username,
            "password": "  IntegrationPassword42!  ",
            "password_confirmation": "  IntegrationPassword42!  ",
        }

    async def asyncTearDown(self):
        self.app.dependency_overrides.pop(get_user_unit_of_work, None)
        try:
            with self.engine.begin() as connection:
                connection.execute(delete(UserModel).where(UserModel.username == self.username))
        finally:
            await self.lifecycle.__aexit__(None, None, None)

    async def test_http_registration_is_committed_and_duplicate_returns_409(self):
        status, response = await post_json(self.app, {**self.payload, "username": " " + self.username.upper() + " "})
        self.assertEqual(status, 201, response)
        # 独立连接能读到记录，证明 HTTP 请求完成前已经真正提交。
        with self.engine.connect() as connection:
            rows = connection.execute(select(UserModel.__table__).where(UserModel.username == self.username)).mappings().all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], response["id"])
        self.assertEqual(rows[0]["role"], "user")
        self.assertTrue(Argon2PasswordHasher().verify_password(self.payload["password"], rows[0]["password_hash"]))
        self.assertNotIn("password_hash", response)
        status, _ = await post_json(self.app, self.payload)
        self.assertEqual(status, 409)

    async def test_concurrent_registration_creates_one_user(self):
        responses = await asyncio.gather(post_json(self.app, self.payload), post_json(self.app, self.payload))
        self.assertEqual(sorted(status for status, _ in responses), [201, 409])
        with self.engine.connect() as connection:
            rows = connection.execute(select(UserModel.id).where(UserModel.username == self.username)).all()
        self.assertEqual(len(rows), 1)

    async def test_failed_commit_rolls_back_insert_and_releases_connection(self):
        class FailingCommitUnitOfWork(MySQLUserUnitOfWork):
            def commit(self):
                raise RuntimeError("simulated commit failure")

        def failing_unit_of_work():
            with session_scope(self.app.state.session_factory) as session:
                yield FailingCommitUnitOfWork(session)

        self.app.dependency_overrides[get_user_unit_of_work] = failing_unit_of_work
        with self.assertLogs("backend.app.api.middleware.request_logging", level="ERROR") as captured:
            status, response = await post_json(self.app, self.payload)
        self.assertEqual(status, 500)
        self.assertEqual(response["detail"], "Internal Server Error")
        self.assertNotIn(self.payload["password"], "\n".join(captured.output))
        with self.engine.connect() as connection:
            row = connection.execute(select(UserModel.id).where(UserModel.username == self.username)).first()
        self.assertIsNone(row)
        self.assertEqual(self.engine.pool.checkedout(), 0)


if __name__ == "__main__":
    unittest.main()
