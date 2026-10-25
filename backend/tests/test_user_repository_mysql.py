"""真实 MySQL 集成检查；显式开启后运行，测试写入全部回滚。"""

import os
import unittest
from uuid import uuid4

from backend.app.application.ports.user_repository import (
    UserRepository,
    UsernameAlreadyExistsError,
)
from backend.app.core.config import get_settings
from backend.app.domain.user import User, UserRole
from backend.app.infrastructure.db.connection import create_database_engine
from backend.app.infrastructure.db.session import create_session_factory, session_scope
from backend.app.infrastructure.repositories.user_repository import MySQLUserRepository


@unittest.skipUnless(os.environ.get("RUN_MYSQL_TESTS") == "1", "需要显式开启 MySQL 集成测试")
class MySQLUserRepositoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_database_engine(get_settings())
        cls.factory = create_session_factory(cls.engine)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def new_username(self):
        return "test_" + uuid4().hex[:24]

    def test_add_lookup_mapping_and_no_implicit_commit(self):
        username = self.new_username()
        with session_scope(self.factory) as session:
            repository: UserRepository = MySQLUserRepository(session)
            saved = repository.add(User(
                username=username.upper(),
                password_hash="test-only-hash-not-for-login",
                role=UserRole.ADMIN,
                is_active=False,
            ))
            self.assertIsInstance(saved, User)
            self.assertGreater(saved.id, 0)
            self.assertIsNotNone(saved.created_at)
            self.assertIsNotNone(saved.updated_at)
            self.assertEqual(saved.username, username)
            self.assertEqual(saved.password_hash, "test-only-hash-not-for-login")
            self.assertEqual(saved.role, UserRole.ADMIN)
            self.assertFalse(saved.is_active)
            self.assertEqual(repository.get_by_id(saved.id), saved)
            self.assertEqual(repository.get_by_username(" " + username.upper() + " "), saved)

            # 独立连接看不到未提交用户，证明 add 没有私自 commit。
            with session_scope(self.factory) as observer:
                self.assertIsNone(MySQLUserRepository(observer).get_by_username(username))

            with self.assertRaises(ValueError):
                repository.add(saved)

        # 会话关闭后数据对象仍可用，数据库中的未提交写入已回滚。
        self.assertEqual(saved.username, username)
        with session_scope(self.factory) as session:
            repository = MySQLUserRepository(session)
            self.assertIsNone(repository.get_by_username(username))
            self.assertIsNone(repository.get_by_id(saved.id))

    def test_duplicate_username_is_translated_and_transaction_rolled_back(self):
        username = self.new_username()
        with self.assertRaises(UsernameAlreadyExistsError):
            with session_scope(self.factory) as session:
                repository = MySQLUserRepository(session)
                repository.add(User(username=username, password_hash="test-only-hash"))
                repository.add(User(username=username.upper(), password_hash="test-only-hash"))

        with session_scope(self.factory) as session:
            self.assertIsNone(MySQLUserRepository(session).get_by_username(username))

    def test_missing_username_and_invalid_username(self):
        with session_scope(self.factory) as session:
            repository = MySQLUserRepository(session)
            self.assertIsNone(repository.get_by_username(self.new_username()))
            with self.assertRaises(ValueError):
                repository.get_by_username("bad username!")


if __name__ == "__main__":
    unittest.main()
