"""创建任务的真实 MySQL 验证，仅清理本次生成的临时用户、文件和任务。"""

import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import delete, select

from backend.app.application.create_processing_task import (
    FileConfigurationNotReadyError, create_processing_task,
)
from backend.app.application.ports.file_repository import UploadedFileNotFoundError
from backend.app.core.config import get_settings
from backend.app.infrastructure.db.connection import create_database_engine
from backend.app.infrastructure.db.models import ProcessingTaskModel, UploadedFileModel, UserModel
from backend.app.infrastructure.db.session import create_session_factory, session_scope


@unittest.skipUnless(os.environ.get("RUN_MYSQL_TESTS") == "1", "需要显式开启 MySQL 集成测试")
class MySQLCreateProcessingTaskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_database_engine(get_settings())
        cls.addClassCleanup(cls.engine.dispose)
        cls.factory = create_session_factory(cls.engine)

    def setUp(self):
        self.username = "it_task_" + uuid4().hex[:16]
        self.other_username = self.username + "_other"
        self.file_id = uuid4().hex
        self.addCleanup(self.cleanup_records)
        with session_scope(self.factory) as session:
            owner = UserModel(username=self.username, password_hash="test-only-hash")
            other = UserModel(username=self.other_username, password_hash="test-only-hash")
            session.add_all([owner, other])
            session.flush()
            self.owner_id, self.other_owner_id = owner.id, other.id
            session.add(UploadedFileModel(
                id=self.file_id, owner_id=self.owner_id, original_filename="tasks.csv",
                storage_key=f"uploads/{self.owner_id}/{self.file_id}.csv", size_bytes=8,
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
                has_header=True, columns=[{"index": 0, "name": "订单编号"}, {"index": 1, "name": "金额"}],
            ))
            session.commit()

    def cleanup_records(self):
        with self.engine.begin() as connection:
            connection.execute(delete(ProcessingTaskModel).where(ProcessingTaskModel.file_id == self.file_id))
            connection.execute(delete(UploadedFileModel).where(UploadedFileModel.id == self.file_id))
            connection.execute(delete(UserModel).where(
                UserModel.username.in_([self.username, self.other_username]),
            ))

    def task_rows(self):
        with self.engine.connect() as connection:
            return connection.execute(select(ProcessingTaskModel.__table__).where(
                ProcessingTaskModel.file_id == self.file_id,
            )).mappings().all()

    def test_create_commits_a_pending_task_without_changing_file_configuration(self):
        with self.engine.connect() as connection:
            before = dict(connection.execute(select(UploadedFileModel.__table__).where(
                UploadedFileModel.id == self.file_id,
            )).mappings().one())
        with session_scope(self.factory) as session:
            result = create_processing_task(session, file_id=self.file_id, owner_id=self.owner_id)
            # 在服务返回时，独立连接已能看到提交结果。
            rows = self.task_rows()
        self.assertRegex(result["task_id"], r"^[0-9a-f]{32}$")
        self.assertEqual(result, {"task_id": rows[0]["id"], "file_id": self.file_id, "status": "pending"})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["owner_id"], self.owner_id)
        self.assertIsNotNone(rows[0]["created_at"])
        self.assertIsNotNone(rows[0]["updated_at"])
        self.assertEqual(rows[0]["input_config"], {
            "version": 1, "has_header": True, "columns": before["columns"],
        })
        self.assertEqual(rows[0]["processed_rows"], 0)
        for field in ("error_message", "started_at", "finished_at"):
            self.assertIsNone(rows[0][field])
        with self.engine.connect() as connection:
            after = dict(connection.execute(select(UploadedFileModel.__table__).where(
                UploadedFileModel.id == self.file_id,
            )).mappings().one())
        self.assertEqual(after, before)

    def test_missing_file_and_another_users_file_cannot_create_tasks(self):
        # 即使文件尚未确认，也应先检查归属，只对外返回 404。
        with session_scope(self.factory) as session:
            session.get(UploadedFileModel, self.file_id).has_header = None
            session.commit()
        for file_id, owner_id in ((uuid4().hex, self.owner_id), (self.file_id, self.other_owner_id)):
            with self.subTest(file_id=file_id, owner_id=owner_id):
                with self.assertRaisesRegex(UploadedFileNotFoundError, "^文件不存在$"):
                    with session_scope(self.factory) as session:
                        create_processing_task(session, file_id=file_id, owner_id=owner_id)
                self.assertEqual(self.task_rows(), [])

    def test_unconfirmed_or_invalid_columns_do_not_create_tasks(self):
        valid = [{"index": 0, "name": "订单编号"}]
        cases = [(None, valid), (None, None), (True, None), (False, []),
                 (True, {}), (True, [None]), (True, [{"index": 1, "name": "订单编号"}]),
                 (True, [{"index": False, "name": "订单编号"}]),
                 (True, [{"index": 0, "name": " "}]), (True, [{"index": 0, "name": 1}]),
                 (True, [{"index": 0, "name": "金额"}, {"index": 1, "name": "金额"}])]
        for has_header, columns in cases:
            with self.subTest(has_header=has_header, columns=columns):
                with session_scope(self.factory) as session:
                    uploaded_file = session.get(UploadedFileModel, self.file_id)
                    uploaded_file.has_header, uploaded_file.columns = has_header, columns
                    session.commit()
                with self.assertRaises(FileConfigurationNotReadyError):
                    with session_scope(self.factory) as session:
                        create_processing_task(session, file_id=self.file_id, owner_id=self.owner_id)
                self.assertEqual(self.task_rows(), [])

    def test_file_changes_do_not_change_existing_snapshot_and_new_task_uses_new_configuration(self):
        with session_scope(self.factory) as session:
            first = create_processing_task(session, file_id=self.file_id, owner_id=self.owner_id)
        original = self.task_rows()[0]["input_config"]
        columns = [{"index": 0, "name": "column_1"}, {"index": 1, "name": "column_2"}]
        with session_scope(self.factory) as session:
            uploaded_file = session.get(UploadedFileModel, self.file_id)
            uploaded_file.has_header, uploaded_file.columns = False, columns
            session.commit()
        with session_scope(self.factory) as session:
            second = create_processing_task(session, file_id=self.file_id, owner_id=self.owner_id)
        rows = {row["id"]: row for row in self.task_rows()}
        self.assertEqual(rows[first["task_id"]]["input_config"], original)
        self.assertEqual(rows[second["task_id"]]["input_config"], {
            "version": 1, "has_header": False, "columns": columns,
        })

    def test_separate_calls_create_distinct_tasks_for_the_same_file(self):
        results = []
        for _ in range(2):
            with session_scope(self.factory) as session:
                results.append(create_processing_task(session, file_id=self.file_id, owner_id=self.owner_id))
        self.assertNotEqual(results[0]["task_id"], results[1]["task_id"])
        self.assertEqual(len(self.task_rows()), 2)

    def test_commit_failure_propagates_and_request_scope_rolls_back_flushed_task(self):
        with self.assertRaisesRegex(RuntimeError, "模拟提交失败"):
            with session_scope(self.factory) as session:
                def fail_commit():
                    session.flush()
                    raise RuntimeError("模拟提交失败")

                with patch.object(session, "commit", side_effect=fail_commit):
                    create_processing_task(session, file_id=self.file_id, owner_id=self.owner_id)
        self.assertEqual(self.task_rows(), [])


if __name__ == "__main__":
    unittest.main()
