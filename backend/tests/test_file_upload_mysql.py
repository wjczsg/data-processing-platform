"""真实登录、上传、MySQL 提交及磁盘保存；只清理本次创建的测试账号和文件。"""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from fastapi import Depends
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_database_session, get_file_storage, get_file_unit_of_work
from backend.app.infrastructure.db.models.uploaded_file import UploadedFileModel
from backend.app.infrastructure.db.models.user import UserModel
from backend.app.infrastructure.db.unit_of_work import MySQLFileUnitOfWork
from backend.app.infrastructure.files.local_storage import LocalFileStorage
from backend.tests.asgi_client import post_json, request_json


@unittest.skipUnless(os.environ.get("RUN_MYSQL_TESTS") == "1", "需要显式开启 MySQL 集成测试")
class MySQLFileUploadTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from backend.app.main import app

        self.app = app
        self.lifecycle = app.router.lifespan_context(app)
        await self.lifecycle.__aenter__()
        self.engine = app.state.database_engine
        self.directory = TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.app.dependency_overrides[get_file_storage] = lambda: LocalFileStorage(self.root)
        self.username = "it_file_" + uuid4().hex[:16]
        payload = {"username": self.username, "password": "FileIntegration42!",
                   "password_confirmation": "FileIntegration42!"}
        status, registered = await post_json(app, payload)
        self.assertEqual(status, 201)
        self.owner_id = registered["id"]
        status, login = await request_json(app, "/api/auth/login", "POST", {
            "username": self.username, "password": payload["password"],
        })
        self.assertEqual(status, 200)
        self.token = login["access_token"]

    async def asyncTearDown(self):
        self.app.dependency_overrides.pop(get_file_storage, None)
        self.app.dependency_overrides.pop(get_file_unit_of_work, None)
        try:
            with self.engine.begin() as connection:
                user_ids = select(UserModel.id).where(UserModel.username == self.username)
                connection.execute(delete(UploadedFileModel).where(UploadedFileModel.owner_id.in_(user_ids)))
                connection.execute(delete(UserModel).where(UserModel.username == self.username))
        finally:
            self.directory.cleanup()
            await self.lifecycle.__aexit__(None, None, None)

    async def upload(self, content=b"code,name\r\n001,Alice\r\n"):
        boundary = "mysql-upload-test"
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="same.csv"\r\n'
                'Content-Type: text/csv\r\n\r\n').encode() + content + (
                f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="owner_id"\r\n\r\n999999\r\n'
                f'--{boundary}--\r\n').encode()
        return await request_json(self.app, "/api/files", "POST", raw_body=body,
            content_type=f"multipart/form-data; boundary={boundary}",
            headers={"Authorization": f"Bearer {self.token}"})

    def stored_rows(self):
        with self.engine.connect() as connection:
            return connection.execute(select(UploadedFileModel.__table__).where(
                UploadedFileModel.owner_id == self.owner_id)).mappings().all()

    async def test_duplicate_names_are_committed_with_own_identity_and_exact_original_bytes(self):
        content = b"\xef\xbb\xbfcode,name\r\n001,Alice\r\n"
        replies = [await self.upload(content) for _ in range(2)]
        self.assertEqual([status for status, _ in replies], [201, 201])
        rows = self.stored_rows()  # 独立连接可见，证明确实提交。
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["id"] for row in rows}, {body["file_id"] for _, body in replies})
        self.assertNotEqual(rows[0]["storage_key"], rows[1]["storage_key"])
        for row in rows:
            self.assertEqual(row["owner_id"], self.owner_id)
            self.assertEqual(row["original_filename"], "same.csv")
            self.assertEqual(row["size_bytes"], len(content))
            self.assertIsNotNone(row["created_at"])
            self.assertEqual((self.root / row["storage_key"]).read_bytes(), content)
        for _, body in replies:
            self.assertTrue(body["persisted"])
            self.assertNotIn("storage_key", body)
            self.assertEqual(body["preview_rows"][1][0], "001")
        self.assertEqual(self.engine.pool.checkedout(), 0)

    async def test_invalid_file_creates_neither_record_nor_saved_file(self):
        self.assertEqual((await self.upload(b""))[0], 422)
        self.assertEqual((await self.upload(b'a,b\n1,"unfinished'))[0], 422)
        self.assertEqual(self.stored_rows(), [])
        self.assertEqual(list(self.root.rglob("*.csv")), [])

    async def test_failed_insert_rolls_back_and_removes_saved_file(self):
        class FailingInsert(MySQLFileUnitOfWork):
            def __init__(self, session):
                super().__init__(session)
                original_add = self.files.add

                def fail_after_flush(record):
                    original_add(record)
                    raise RuntimeError("simulated insert failure after flush")

                self.files.add = fail_after_flush

        def failing_uow(session: Session = Depends(get_database_session)):
            return FailingInsert(session)

        self.app.dependency_overrides[get_file_unit_of_work] = failing_uow
        with self.assertLogs("backend.app.api.middleware.request_logging", level="ERROR"):
            status, body = await self.upload()
        self.assertEqual(status, 500)
        self.assertEqual(body["detail"], "Internal Server Error")
        self.assertEqual(self.stored_rows(), [])
        self.assertEqual(list(self.root.rglob("*.csv")), [])
        self.assertEqual(self.engine.pool.checkedout(), 0)

    async def test_commit_succeeded_but_acknowledgement_failed_preserves_referenced_file(self):
        class LostCommitResponse(MySQLFileUnitOfWork):
            def commit(self):
                super().commit()
                raise RuntimeError("simulated lost commit acknowledgement")

        def uncertain_uow(session: Session = Depends(get_database_session)):
            return LostCommitResponse(session)

        self.app.dependency_overrides[get_file_unit_of_work] = uncertain_uow
        with self.assertLogs("backend.app.application.store_uploaded_file", level="WARNING"), \
             self.assertLogs("backend.app.api.middleware.request_logging", level="ERROR"):
            status, _ = await self.upload()
        self.assertEqual(status, 500)
        rows = self.stored_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual((self.root / rows[0]["storage_key"]).read_bytes(), b"code,name\r\n001,Alice\r\n")
        self.assertEqual(self.engine.pool.checkedout(), 0)


if __name__ == "__main__":
    unittest.main()
