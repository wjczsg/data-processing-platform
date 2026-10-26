"""验证登录、令牌校验、当前身份及账号状态，不连接数据库。"""

import json
import time
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from backend.app.api.auth import router
from backend.app.api.dependencies import (
    get_dummy_password_hash, get_password_hasher, get_token_service, get_user_unit_of_work,
    get_refresh_credentials, get_refresh_window_hours,
)
from backend.app.api.exception_handlers import request_validation_exception_handler, unhandled_exception_handler
from backend.app.application.ports.token_service import InvalidAccessTokenError
from backend.app.domain.user import User, UserRole
from backend.app.domain.login_session import LoginSession, RefreshGrant
from backend.app.infrastructure.security.password_hasher import Argon2PasswordHasher
from backend.app.infrastructure.security.token_service import JWTTokenService
from backend.app.infrastructure.security.refresh_credentials import OpaqueRefreshCredentials
from backend.tests.asgi_client import request_json
from backend.tests.test_registration import MemoryUserUnitOfWork

TEST_KEY = "test-only-signing-key-not-for-production-" + "x" * 32
SESSION_ID = "a" * 32


class MemoryAuthSessions:
    def __init__(self):
        self.sessions = {}
        self.grants = {}

    def create(self, session, token_hash):
        self.sessions[session.id] = session
        self.grants[token_hash] = (session.id, None, None, None)

    def find_by_id(self, session_id):
        return self.sessions.get(session_id)

    def find_by_refresh_hash(self, token_hash, *, session_id, lock=False):
        grant = self.grants.get(token_hash)
        if grant is None or grant[0] != session_id:
            return None
        return RefreshGrant(session=self.sessions[session_id], token_hash=token_hash,
            used_at=grant[1], request_id=grant[2], successor_hash=grant[3])

    def rotate(self, token_hash, successor_hash, request_id, now, expires_at):
        session_id = self.grants[token_hash][0]
        self.grants[token_hash] = (session_id, now, request_id, successor_hash)
        self.grants[successor_hash] = (session_id, None, None, None)
        self.sessions[session_id] = replace(self.sessions[session_id], last_refreshed_at=now, expires_at=expires_at)

    def revoke(self, session_id, now):
        self.sessions[session_id] = replace(self.sessions[session_id], revoked_at=now)


class TokenServiceTests(unittest.TestCase):
    def setUp(self):
        self.tokens = JWTTokenService(TEST_KEY)

    def claims(self):
        now = int(time.time())
        return {"sub": "1", "sid": SESSION_ID, "iat": now, "exp": now + 1800, "iss": self.tokens.ISSUER,
                "aud": self.tokens.AUDIENCE, "token_type": "access"}

    def test_issued_token_round_trip_and_lifetime(self):
        token = self.tokens.issue_access_token(7, SESSION_ID)
        identity = self.tokens.verify_access_token(token.value)
        self.assertEqual((identity.user_id, identity.session_id), (7, SESSION_ID))
        self.assertEqual(token.expires_in, 1800)
        self.assertNotIn(token.value, repr(token))

    def test_expired_and_missing_claims_are_rejected(self):
        expired = {**self.claims(), "iat": int(time.time()) - 3600, "exp": int(time.time()) - 1}
        missing = self.claims()
        missing.pop("exp")
        for claims in (expired, missing):
            with self.assertRaises(InvalidAccessTokenError):
                self.tokens.verify_access_token(jwt.encode(claims, TEST_KEY, algorithm="HS256"))

    def test_wrong_signature_algorithm_and_purpose_are_rejected(self):
        invalid = [
            jwt.encode(self.claims(), "another-test-key-" + "y" * 32, algorithm="HS256"),
            jwt.encode(self.claims(), TEST_KEY, algorithm="HS384"),
            jwt.encode(self.claims(), None, algorithm="none"),
        ]
        for change in ({"iss": "other-app"}, {"aud": "other-api"}, {"token_type": "refresh"},
                       {"sub": "0"}, {"sub": "not-an-id"}, {"sub": 1}):
            invalid.append(jwt.encode({**self.claims(), **change}, TEST_KEY, algorithm="HS256"))
        for token in invalid:
            with self.assertRaises(InvalidAccessTokenError):
                self.tokens.verify_access_token(token)


class AuthenticationTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.hasher = Argon2PasswordHasher()
        cls.password = "  LearningPython你好42!  "
        cls.password_hash = cls.hasher.hash_password(cls.password)
        cls.dummy_hash = cls.hasher.hash_password("DummyAccountPassword42!")

    def setUp(self):
        self.uow = MemoryUserUnitOfWork()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        self.user = User(id=1, username="student_01", password_hash=self.password_hash, created_at=now, updated_at=now)
        self.uow.users.saved[self.user.username] = self.user
        self.tokens = JWTTokenService(TEST_KEY)
        self.credentials = OpaqueRefreshCredentials(TEST_KEY)
        self.uow.auth_sessions = MemoryAuthSessions()
        self.uow.auth_sessions.create(LoginSession(id=SESSION_ID, user_id=1, created_at=now,
            last_refreshed_at=now, expires_at=now + timedelta(hours=12)),
            self.credentials.digest(self.credentials.create(SESSION_ID)))
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.add_exception_handler(RequestValidationError, request_validation_exception_handler)
        self.app.add_exception_handler(Exception, unhandled_exception_handler)
        self.app.dependency_overrides.update({
            get_user_unit_of_work: lambda: self.uow,
            get_password_hasher: lambda: self.hasher,
            get_token_service: lambda: self.tokens,
            get_dummy_password_hash: lambda: self.dummy_hash,
            get_refresh_credentials: lambda: self.credentials,
            get_refresh_window_hours: lambda: 12,
        })

    async def login(self, username=" Student_01 ", password=None):
        return await request_json(self.app, "/api/auth/login", "POST", {
            "username": username, "password": self.password if password is None else password,
        })

    async def me(self, token=None):
        headers = {"Authorization": f"Bearer {token}"} if token is not None else None
        return await request_json(self.app, "/api/auth/me", headers=headers)

    async def test_login_and_current_user_round_trip(self):
        status, body = await self.login()
        self.assertEqual(status, 200, body)
        self.assertEqual(body["token_type"], "bearer")
        self.assertEqual(body["expires_in"], 1800)
        self.assertEqual(body["user"]["username"], "student_01")
        self.assertNotIn(self.password, json.dumps(body))
        self.assertNotIn(self.password_hash, json.dumps(body))
        status, user = await self.me(body["access_token"])
        self.assertEqual(status, 200)
        self.assertEqual(user["id"], 1)
        self.assertNotIn("password_hash", user)
        self.assertEqual(self.uow.commits, 1)

    async def test_unknown_wrong_password_and_inactive_account_use_same_error(self):
        for username, password in (("unknown_user", self.password), ("student_01", "wrong"),
                                   ("student_01", self.password.strip()), ("student_01", "bad\ud800")):
            status, body = await self.login(username, password)
            self.assertEqual((status, body), (401, {"detail": "账号或密码错误"}))
        self.uow.users.saved["student_01"] = replace(self.user, is_active=False)
        self.assertEqual(await self.login(), (401, {"detail": "账号或密码错误"}))

    async def test_missing_invalid_and_expired_tokens_return_401(self):
        self.assertEqual((await self.me())[0], 401)
        self.assertEqual((await self.me("not-a-token"))[0], 401)
        now = int(time.time())
        expired = jwt.encode({"sub": "1", "sid": SESSION_ID, "iat": now - 3600, "exp": now - 1,
            "iss": self.tokens.ISSUER, "aud": self.tokens.AUDIENCE, "token_type": "access"}, TEST_KEY, algorithm="HS256")
        self.assertEqual((await self.me(expired))[0], 401)

    async def test_current_user_comes_from_latest_database_record(self):
        token = self.tokens.issue_access_token(1, SESSION_ID).value
        self.uow.users.saved["student_01"] = replace(self.user, role=UserRole.ADMIN)
        self.assertEqual((await self.me(token))[1]["role"], "admin")
        self.uow.users.saved["student_01"] = replace(self.user, is_active=False)
        self.assertEqual((await self.me(token))[0], 401)
        self.uow.users.saved.clear()
        self.assertEqual((await self.me(token))[0], 401)

    async def test_login_does_not_reapply_registration_password_rules(self):
        self.uow.users.saved["student_01"] = replace(self.user, password_hash=self.hasher.hash_password("short"))
        self.assertEqual((await self.login(password="short"))[0], 200)

    async def test_invalid_request_does_not_echo_password(self):
        status, body = await request_json(self.app, "/api/auth/login", "POST", {
            "username": "student_01", "password": self.password, "role": "admin",
        })
        self.assertEqual(status, 422)
        self.assertNotIn(self.password, json.dumps(body))

    async def refresh(self, token, request_id):
        return await request_json(self.app, "/api/auth/refresh", "POST", {
            "refresh_token": token, "request_id": str(request_id),
        })

    async def test_refresh_rotates_credentials_and_same_operation_recovers_lost_response(self):
        _, login = await self.login()
        request_id = uuid4()
        status, first = await self.refresh(login["refresh_token"], request_id)
        self.assertEqual(status, 200)
        self.assertNotEqual(first["refresh_token"], login["refresh_token"])
        self.assertNotEqual(first["access_token"], login["access_token"])
        self.assertEqual(first["refresh_expires_in"], 43200)
        status, recovered = await self.refresh(login["refresh_token"], request_id)
        self.assertEqual(status, 200)
        self.assertEqual(recovered["refresh_token"], first["refresh_token"])
        self.assertEqual(self.uow.commits, 2)
        self.assertEqual((await self.me(recovered["access_token"]))[0], 200)

    async def test_old_credential_reused_for_new_operation_revokes_session(self):
        _, login = await self.login()
        _, refreshed = await self.refresh(login["refresh_token"], uuid4())
        self.assertEqual((await self.refresh(login["refresh_token"], uuid4()))[0], 401)
        self.assertEqual((await self.me(refreshed["access_token"]))[0], 401)

    async def test_expired_access_can_recover_with_valid_refresh_credential(self):
        _, login = await self.login()
        identity = self.tokens.verify_access_token(login["access_token"])
        now = int(time.time())
        expired = jwt.encode({"sub": "1", "sid": identity.session_id, "iat": now - 3600,
            "exp": now - 1, "iss": self.tokens.ISSUER, "aud": self.tokens.AUDIENCE,
            "token_type": "access"}, TEST_KEY, algorithm="HS256")
        self.assertEqual((await self.me(expired))[0], 401)
        status, refreshed = await self.refresh(login["refresh_token"], uuid4())
        self.assertEqual(status, 200)
        self.assertEqual((await self.me(refreshed["access_token"]))[0], 200)

    async def test_expired_recovery_window_and_disabled_account_cannot_refresh(self):
        _, login = await self.login()
        identity = self.tokens.verify_access_token(login["access_token"])
        record = self.uow.auth_sessions.sessions[identity.session_id]
        self.uow.auth_sessions.sessions[identity.session_id] = replace(record,
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1))
        self.assertEqual((await self.refresh(login["refresh_token"], uuid4()))[0], 401)
        _, another = await self.login()
        self.uow.users.saved["student_01"] = replace(self.user, is_active=False)
        self.assertEqual((await self.refresh(another["refresh_token"], uuid4()))[0], 401)

    async def test_logout_revokes_current_and_pre_refresh_access_tokens(self):
        _, login = await self.login()
        _, refreshed = await self.refresh(login["refresh_token"], uuid4())
        for _ in range(2):
            status, _ = await request_json(self.app, "/api/auth/logout", "POST", {"refresh_token": login["refresh_token"]})
            self.assertEqual(status, 204)
        self.assertEqual((await self.me(login["access_token"]))[0], 401)
        self.assertEqual((await self.me(refreshed["access_token"]))[0], 401)
        self.assertEqual((await self.refresh(refreshed["refresh_token"], uuid4()))[0], 401)


if __name__ == "__main__":
    unittest.main()
