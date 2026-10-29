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
from backend.app.infrastructure.db.models.processing_task import ProcessingTaskModel
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
        self.usernames = [self.username]
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
                user_ids = select(UserModel.id).where(UserModel.username.in_(self.usernames))
                connection.execute(delete(ProcessingTaskModel).where(ProcessingTaskModel.owner_id.in_(user_ids)))
                connection.execute(delete(UploadedFileModel).where(UploadedFileModel.owner_id.in_(user_ids)))
                connection.execute(delete(UserModel).where(UserModel.username.in_(self.usernames)))
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

    async def confirm_header(self, file_id, has_header, *, token=None):
        return await request_json(self.app, f"/api/files/{file_id}/header", "PUT", {"has_header": has_header},
            headers={"Authorization": f"Bearer {token or self.token}"})

    async def test_uploaded_file_can_create_a_committed_pending_task(self):
        status, upload = await self.upload()
        self.assertEqual(status, 201)
        # 绕过前端直接提交未确认的文件，也必须被后端拒绝且不落任务记录。
        status, error = await request_json(self.app, "/api/tasks", "POST", {"file_id": upload["file_id"]},
                                         headers={"Authorization": f"Bearer {self.token}"})
        self.assertEqual((status, error), (409, {"detail": "请先确认文件表头"}))
        with self.engine.connect() as connection:
            self.assertEqual(connection.execute(select(ProcessingTaskModel.id).where(
                ProcessingTaskModel.file_id == upload["file_id"],
            )).all(), [])
        status, configuration = await self.confirm_header(upload["file_id"], True)
        self.assertEqual(status, 200)
        status, task = await request_json(self.app, "/api/tasks", "POST", {"file_id": upload["file_id"]},
                                        headers={"Authorization": f"Bearer {self.token}"})
        self.assertEqual(status, 201)
        self.assertEqual(task["file_id"], upload["file_id"])
        self.assertEqual(task["status"], "pending")
        with self.engine.connect() as connection:
            row = connection.execute(select(ProcessingTaskModel.__table__).where(
                ProcessingTaskModel.id == task["task_id"],
            )).mappings().one()
        self.assertEqual(row["owner_id"], self.owner_id)
        self.assertEqual(row["file_id"], upload["file_id"])
        self.assertEqual(row["status"], "pending")
        self.assertIsNotNone(row["created_at"])
        self.assertIsNotNone(row["updated_at"])
        expected = {"version": 1, "has_header": True, "columns": configuration["columns"]}
        self.assertEqual(row["input_config"], expected)
        self.assertTrue(self.stored_rows()[0]["has_header"])
        # 通过真实表头接口修改文件，已经提交的任务配置仍保持创建时的含义。
        self.assertEqual((await self.confirm_header(upload["file_id"], False))[0], 200)
        with self.engine.connect() as connection:
            saved = connection.execute(select(ProcessingTaskModel.__table__).where(
                ProcessingTaskModel.id == task["task_id"],
            )).mappings().one()
        self.assertEqual(saved["input_config"], expected)

    async def test_confirmed_no_header_file_can_create_a_task(self):
        status, upload = await self.upload(b"001,Alice\r\n002,Bob\r\n")
        self.assertEqual(status, 201)
        status, configuration = await self.confirm_header(upload["file_id"], False)
        self.assertEqual(status, 200)
        status, task = await request_json(self.app, "/api/tasks", "POST", {"file_id": upload["file_id"]},
                                        headers={"Authorization": f"Bearer {self.token}"})
        self.assertEqual(status, 201)
        with self.engine.connect() as connection:
            saved = connection.execute(select(ProcessingTaskModel.__table__).where(
                ProcessingTaskModel.id == task["task_id"],
            )).mappings().one()
        self.assertEqual(saved["input_config"], {
            "version": 1, "has_header": False, "columns": configuration["columns"],
        })

    async def test_header_confirmation_commits_full_columns_and_repeated_calls_update_one_record(self):
        names = [" 长列名" + "名" * 250 + " ", *[f"列{index}" for index in range(1, 55)]]
        content = ("\ufeff" + ",".join(names) + "\n" + ",".join(["001"] * 55) + "\n").encode("utf-8")
        status, upload = await self.upload(content)
        self.assertEqual(status, 201)
        self.assertEqual(len(upload["preview_rows"][0]), 50)
        self.assertEqual(len(upload["preview_rows"][0][0]), 200)
        before = self.stored_rows()[0]
        for _ in range(2):
            status, body = await self.confirm_header(upload["file_id"], True)
            self.assertEqual(status, 200, body)
            expected = [{"index": index, "name": name.strip()} for index, name in enumerate(names)]
            self.assertEqual(body["columns"], expected)
            row = self.stored_rows()[0]
            self.assertTrue(row["has_header"])
            self.assertEqual(row["columns"], expected)
        status, body = await self.confirm_header(upload["file_id"], False)
        self.assertEqual(status, 200)
        self.assertFalse(body["has_header"])
        expected = [{"index": index, "name": f"column_{index + 1}"} for index in range(55)]
        rows = self.stored_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["columns"], expected)
        for key in ("id", "owner_id", "original_filename", "storage_key", "size_bytes", "created_at"):
            self.assertEqual(rows[0][key], before[key])
        self.assertEqual((self.root / before["storage_key"]).read_bytes(), content)
        self.assertEqual(self.engine.pool.checkedout(), 0)

    async def test_invalid_headers_do_not_replace_a_saved_no_header_configuration(self):
        status, upload = await self.upload(b"name, name \n001,Alice\n")
        self.assertEqual(status, 201)
        self.assertEqual((await self.confirm_header(upload["file_id"], False))[0], 200)
        before = dict(self.stored_rows()[0])
        status, _ = await self.confirm_header(upload["file_id"], True)
        self.assertEqual(status, 422)
        self.assertEqual(dict(self.stored_rows()[0]), before)

    async def test_other_logged_in_user_cannot_confirm_or_update_file(self):
        status, upload = await self.upload()
        self.assertEqual(status, 201)
        username = self.username + "_b"
        self.usernames.append(username)
        status, other = await post_json(self.app, {"username": username, "password": "FileIntegration42!",
            "password_confirmation": "FileIntegration42!"})
        self.assertEqual(status, 201)
        status, login = await request_json(self.app, "/api/auth/login", "POST", {
            "username": username, "password": "FileIntegration42!",
        })
        self.assertEqual(status, 200)
        status, response = await self.confirm_header(upload["file_id"], True, token=login["access_token"])
        self.assertEqual((status, response), (404, {"detail": "文件不存在"}))
        self.assertIsNone(self.stored_rows()[0]["has_header"])
        self.assertIsNone(self.stored_rows()[0]["columns"])
        # 仓库更新自身也校验归属，防止错误调用绕过前面的查询。
        from backend.app.application.ports.file_repository import UploadedFileNotFoundError
        from backend.app.domain.file_header import FileColumn, FileHeaderConfiguration
        from backend.app.infrastructure.repositories.file_repository import MySQLFileRepository
        with self.assertRaises(UploadedFileNotFoundError):
            with self.app.state.session_factory.begin() as session:
                MySQLFileRepository(session).update_header(
                    FileHeaderConfiguration(upload["file_id"], True, (FileColumn(0, "code"),)), other["id"],
                )
        self.assertIsNone(self.stored_rows()[0]["has_header"])

    async def test_header_commit_failure_rolls_back_both_configuration_fields(self):
        status, upload = await self.upload()
        self.assertEqual(status, 201)
        self.assertEqual((await self.confirm_header(upload["file_id"], True))[0], 200)
        before = dict(self.stored_rows()[0])

        class FailingHeaderCommit(MySQLFileUnitOfWork):
            def commit(self):
                raise RuntimeError("simulated header commit failure")

        def failing_uow(session: Session = Depends(get_database_session)):
            return FailingHeaderCommit(session)

        self.app.dependency_overrides[get_file_unit_of_work] = failing_uow
        with self.assertLogs("backend.app.api.middleware.request_logging", level="ERROR"):
            status, response = await self.confirm_header(upload["file_id"], False)
        self.assertEqual(status, 500)
        self.assertEqual(response["detail"], "Internal Server Error")
        self.assertEqual(dict(self.stored_rows()[0]), before)
        self.assertEqual(self.engine.pool.checkedout(), 0)

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
            self.assertIsNone(row["has_header"])
            self.assertIsNone(row["columns"])
            self.assertEqual((self.root / row["storage_key"]).read_bytes(), content)
        for _, body in replies:
            self.assertTrue(body["persisted"])
            self.assertNotIn("storage_key", body)
            self.assertEqual(body["preview_rows"][1][0], "001")
        self.assertEqual(self.engine.pool.checkedout(), 0)

    async def test_header_configuration_fields_round_trip_without_changing_original_file(self):
        content = "学号,姓名\n001,张三\n".encode("utf-8")
        status, response = await self.upload(content)
        self.assertEqual(status, 201)
        before = self.stored_rows()[0]
        configurations = (
            (True, [{"index": 0, "name": "学号"}, {"index": 1, "name": "姓名"}]),
            (False, [{"index": 0, "name": "column_1"}, {"index": 1, "name": "column_2"}]),
            (None, None),
        )
        for has_header, columns in configurations:
            with self.subTest(has_header=has_header):
                # 直接验证 ORM 字段读写；HTTP 确认链路由本文件的其他测试覆盖。
                with self.app.state.session_factory.begin() as session:
                    model = session.get(UploadedFileModel, response["file_id"])
                    model.has_header = has_header
                    model.columns = columns
                row = self.stored_rows()[0]
                self.assertIs(row["has_header"], has_header)
                self.assertEqual(row["columns"], columns)
                for key in ("id", "owner_id", "original_filename", "storage_key", "size_bytes", "created_at"):
                    self.assertEqual(row[key], before[key])
                self.assertEqual((self.root / row["storage_key"]).read_bytes(), content)
        with self.engine.connect() as connection:
            sql_null = connection.execute(select(UploadedFileModel.id).where(
                UploadedFileModel.id == response["file_id"], UploadedFileModel.columns.is_(None),
            )).scalar_one()
        self.assertEqual(sql_null, response["file_id"])

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
