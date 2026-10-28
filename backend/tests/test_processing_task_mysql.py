"""验证真实 MySQL 任务表的默认值、关联约束和时间更新，写入全部回滚。"""

import os
import unittest
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError, OperationalError

from backend.app.core.config import get_settings
from backend.app.infrastructure.db.connection import create_database_engine
from backend.app.infrastructure.db.models import ProcessingTaskModel, UploadedFileModel, UserModel
from backend.app.infrastructure.db.session import create_session_factory


@unittest.skipUnless(os.environ.get("RUN_MYSQL_TESTS") == "1", "需要显式开启 MySQL 集成测试")
class MySQLProcessingTaskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_database_engine(get_settings())
        cls.addClassCleanup(cls.engine.dispose)
        cls.factory = create_session_factory(cls.engine)

    def setUp(self):
        self.session = self.factory()
        self.addCleanup(self.session.close)
        self.user = UserModel(username="it_task_" + uuid4().hex[:20], password_hash="test-only-hash")
        self.session.add(self.user)
        self.session.flush()
        file_id = uuid4().hex
        self.file = UploadedFileModel(
            id=file_id, owner_id=self.user.id, original_filename="tasks.csv",
            storage_key=f"uploads/{self.user.id}/{file_id}.csv", size_bytes=8,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        self.session.add(self.file)
        self.session.flush()

    def new_task(self, **overrides):
        values = {"id": uuid4().hex, "file_id": self.file.id, "owner_id": self.user.id}
        values.update(overrides)
        return ProcessingTaskModel(**values)

    def test_same_file_can_have_multiple_tasks_and_uncommitted_writes_roll_back(self):
        before = datetime.now(timezone.utc).replace(tzinfo=None)
        tasks = [self.new_task(), self.new_task()]
        self.session.add_all(tasks)
        self.session.flush()
        rows = self.session.execute(select(ProcessingTaskModel.__table__).where(
            ProcessingTaskModel.file_id == self.file.id,
        )).mappings().all()
        after = datetime.now(timezone.utc).replace(tzinfo=None)
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row["status"], "pending")
            self.assertEqual(row["owner_id"], self.user.id)
            self.assertLessEqual(before, row["created_at"])
            self.assertLessEqual(row["created_at"], row["updated_at"])
            self.assertLessEqual(row["updated_at"], after)
        task_ids = [task.id for task in tasks]
        self.session.rollback()
        with self.factory() as observer:
            self.assertEqual(observer.scalars(select(ProcessingTaskModel.id).where(
                ProcessingTaskModel.id.in_(task_ids),
            )).all(), [])

    def test_database_default_and_status_constraint_apply_to_direct_sql(self):
        task_id = uuid4().hex
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        self.session.execute(text(
            "INSERT INTO processing_tasks (id, file_id, owner_id, created_at, updated_at) "
            "VALUES (:id, :file_id, :owner_id, :now, :now)"
        ), {"id": task_id, "file_id": self.file.id, "owner_id": self.user.id, "now": now})
        self.assertEqual(self.session.scalar(select(ProcessingTaskModel.status).where(
            ProcessingTaskModel.id == task_id,
        )), "pending")
        for status in ("pending", "running", "succeeded", "failed"):
            self.session.execute(text("UPDATE processing_tasks SET status=:status WHERE id=:id"),
                                 {"status": status, "id": task_id})
        for status in ("unknown", "RUNNING"):
            with self.subTest(status=status):
                # PyMySQL 将 MySQL CHECK 约束错误 3819 映射为 OperationalError。
                with self.assertRaises(OperationalError) as raised:
                    with self.session.begin_nested():
                        self.session.execute(text("UPDATE processing_tasks SET status=:status WHERE id=:id"),
                                             {"status": status, "id": task_id})
                self.assertEqual(raised.exception.orig.args[0], 3819)

    def test_foreign_keys_reject_missing_references_and_protect_linked_records(self):
        for overrides in ({"file_id": uuid4().hex}, {"owner_id": 0}):
            with self.subTest(overrides=overrides), self.assertRaises(IntegrityError):
                with self.session.begin_nested():
                    self.session.add(self.new_task(**overrides))
                    self.session.flush()
        self.session.add(self.new_task())
        self.session.flush()
        for model, record_id in ((UploadedFileModel, self.file.id), (UserModel, self.user.id)):
            with self.subTest(table=model.__tablename__), self.assertRaises(IntegrityError):
                with self.session.begin_nested():
                    self.session.execute(delete(model).where(model.id == record_id))

    def test_orm_status_update_preserves_created_at_and_refreshes_updated_at(self):
        original = datetime(2020, 1, 1)
        task = self.new_task(created_at=original, updated_at=original)
        self.session.add(task)
        self.session.flush()
        task.status = "running"
        self.session.flush()
        self.session.refresh(task)
        self.assertEqual(task.created_at, original)
        self.assertGreater(task.updated_at, original)
        self.assertIsNone(task.updated_at.tzinfo)


if __name__ == "__main__":
    unittest.main()
