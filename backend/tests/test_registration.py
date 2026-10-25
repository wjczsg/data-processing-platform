"""注册 HTTP 行为和业务规则检查；用内存事务替代 MySQL。"""

import json
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from backend.app.api.auth import router
from backend.app.api.dependencies import get_password_hasher, get_user_unit_of_work
from backend.app.api.exception_handlers import request_validation_exception_handler, unhandled_exception_handler
from backend.app.application.ports.password_hasher import PasswordHashError
from backend.app.application.ports.user_repository import UsernameAlreadyExistsError
from backend.app.infrastructure.security.password_hasher import Argon2PasswordHasher
from backend.tests.asgi_client import post_json


class MemoryUsers:
    def __init__(self):
        self.saved = {}

    def get_by_id(self, user_id):
        return next((user for user in self.saved.values() if user.id == user_id), None)

    def get_by_username(self, username):
        return self.saved.get(username)

    def add(self, user):
        if user.username in self.saved:
            raise UsernameAlreadyExistsError("用户名已存在")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        saved = replace(user, id=len(self.saved) + 1, created_at=now, updated_at=now)
        self.saved[user.username] = saved
        return saved


class MemoryUserUnitOfWork:
    def __init__(self):
        self.users = MemoryUsers()
        self.commits = 0

    def commit(self):
        self.commits += 1


class RegistrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.unit_of_work = MemoryUserUnitOfWork()
        self.hasher = Argon2PasswordHasher()
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.add_exception_handler(RequestValidationError, request_validation_exception_handler)
        self.app.add_exception_handler(Exception, unhandled_exception_handler)
        self.app.dependency_overrides[get_user_unit_of_work] = lambda: self.unit_of_work
        self.app.dependency_overrides[get_password_hasher] = lambda: self.hasher
        self.payload = {
            "username": "  Student_01  ",
            "password": "LearningPython42!",
            "password_confirmation": "LearningPython42!",
        }

    async def test_success_normalizes_account_hashes_password_and_returns_only_public_fields(self):
        status, response = await post_json(self.app, self.payload)
        self.assertEqual(status, 201, response)
        self.assertEqual(set(response), {"id", "username", "role", "is_active", "created_at", "updated_at"})
        self.assertEqual(response["username"], "student_01")
        self.assertEqual(response["role"], "user")
        self.assertIs(response["is_active"], True)
        self.assertTrue(response["created_at"].endswith("Z"))
        saved = self.unit_of_work.users.get_by_username("student_01")
        self.assertTrue(self.hasher.verify_password(self.payload["password"], saved.password_hash))
        self.assertNotIn(saved.password_hash, json.dumps(response))
        self.assertNotIn(self.payload["password"], json.dumps(response))
        self.assertEqual(self.unit_of_work.commits, 1)

    async def test_duplicate_account_returns_conflict_without_second_commit(self):
        self.assertEqual((await post_json(self.app, self.payload))[0], 201)
        status, response = await post_json(self.app, {**self.payload, "username": "STUDENT_01"})
        self.assertEqual(status, 409)
        self.assertEqual(response, {"detail": "用户名已存在"})
        self.assertEqual(self.unit_of_work.commits, 1)

    async def test_invalid_registration_never_writes_or_commits(self):
        cases = [
            {"username": "a"},
            {"username": "用户账号"},
            {"password": "short", "password_confirmation": "short"},
            {"password": "password", "password_confirmation": "password"},
            {"password": " " * 8, "password_confirmation": " " * 8},
            {"password": "a" * 129, "password_confirmation": "a" * 129},
            {"password": "abcd\nefgh", "password_confirmation": "abcd\nefgh"},
            {"password_confirmation": "DifferentPassword42!"},
            {"password": 12345678},
        ]
        for changes in cases:
            with self.subTest(fields=list(changes)):
                status, response = await post_json(self.app, {**self.payload, **changes})
                self.assertEqual(status, 422, response)
        self.assertFalse(self.unit_of_work.users.saved)
        self.assertEqual(self.unit_of_work.commits, 0)

    async def test_registration_cannot_choose_role_or_active_status(self):
        for field, value in (("role", "admin"), ("is_active", False), ("password_hash", "injected-hash")):
            with self.subTest(field=field):
                status, _ = await post_json(self.app, {**self.payload, field: value})
                self.assertEqual(status, 422)
        self.assertFalse(self.unit_of_work.users.saved)

    async def test_validation_errors_do_not_echo_password_or_whole_body(self):
        for payload in (
            {**self.payload, "password": "private"},
            {**self.payload, "password_confirmation": "x" * 129},
            [self.payload],
        ):
            status, response = await post_json(self.app, payload)
            self.assertEqual(status, 422)
            serialized = json.dumps(response)
            self.assertNotIn(self.payload["password"], serialized)
            self.assertNotIn("private", serialized)
            for error in response["detail"]:
                self.assertEqual(set(error), {"loc", "msg", "type"})

    async def test_spaces_in_password_are_preserved_through_http(self):
        password = "  LearningPython42!  "
        status, _ = await post_json(self.app, {
            **self.payload, "password": password, "password_confirmation": password,
        })
        self.assertEqual(status, 201)
        saved = self.unit_of_work.users.get_by_username("student_01")
        self.assertTrue(self.hasher.verify_password(password, saved.password_hash))
        self.assertFalse(self.hasher.verify_password(password.strip(), saved.password_hash))

    async def test_conflict_during_insert_also_returns_409(self):
        with patch.object(self.unit_of_work.users, "add", side_effect=UsernameAlreadyExistsError()):
            status, _ = await post_json(self.app, self.payload)
        self.assertEqual(status, 409)
        self.assertEqual(self.unit_of_work.commits, 0)

    async def test_hashing_failure_returns_generic_500_without_writing_user(self):
        with patch.object(self.hasher, "hash_password", side_effect=PasswordHashError("simulated hashing failure")):
            status, response = await post_json(self.app, self.payload)
        self.assertEqual(status, 500)
        self.assertEqual(response["detail"], "Internal Server Error")
        self.assertFalse(self.unit_of_work.users.saved)
        self.assertEqual(self.unit_of_work.commits, 0)


if __name__ == "__main__":
    unittest.main()
