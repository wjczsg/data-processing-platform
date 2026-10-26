"""登录和当前用户查询：复用用户仓储、密码处理和令牌接口。"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from backend.app.application.ports.password_hasher import PasswordHasher
from backend.app.application.ports.auth_sessions import RefreshCredentialCodec
from backend.app.application.ports.unit_of_work import UserUnitOfWork
from backend.app.application.ports.token_service import AccessToken, InvalidAccessTokenError, TokenService
from backend.app.domain.login_session import LoginSession
from backend.app.domain.user import User, normalize_username


class InvalidCredentialsError(Exception):
    """账号不存在、密码错误或账号不可用，统一对外提示。"""


@dataclass(frozen=True)
class LoginResult:
    user: User
    token: AccessToken
    refresh_token: str = field(repr=False)
    refresh_expires_in: int


class AuthenticationService:
    def __init__(
        self, unit_of_work: UserUnitOfWork, password_hasher: PasswordHasher,
        tokens: TokenService, credentials: RefreshCredentialCodec, dummy_password_hash: str,
        refresh_window_hours: int = 12, clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._uow = unit_of_work
        self._users = unit_of_work.users
        self._sessions = unit_of_work.auth_sessions
        self._password_hasher = password_hasher
        self._tokens = tokens
        self._dummy_password_hash = dummy_password_hash
        self._credentials = credentials
        self._window = timedelta(hours=refresh_window_hours)
        self._clock = clock or (lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    def login(self, username: str, password: str) -> LoginResult:
        try:
            username = normalize_username(username)
            # 不能编码为 UTF-8 的输入不可能匹配本项目保存的密码。
            password.encode("utf-8")
        except (ValueError, UnicodeEncodeError):
            raise InvalidCredentialsError("账号或密码错误") from None

        # 登录不新增用户；验证通过后单独保存该次登录的会话。
        user = self._users.get_by_username(username)
        # 用户不存在也做一次真实密码验证，减少通过耗时猜测账号的机会。
        stored_hash = user.password_hash if user is not None else self._dummy_password_hash
        matches = self._password_hasher.verify_password(password, stored_hash)
        if user is None or not matches or not user.is_active:
            raise InvalidCredentialsError("账号或密码错误")
        if user.id is None:
            raise RuntimeError("数据库用户缺少 ID")
        now = self._clock()
        session = LoginSession(id=uuid4().hex, user_id=user.id, created_at=now,
            last_refreshed_at=now, expires_at=now + self._window)
        refresh_token = self._credentials.create(session.id)
        self._sessions.create(session, self._credentials.digest(refresh_token))
        result = self._result(user, session, refresh_token, now)
        self._uow.commit()
        return result

    def _result(self, user: User, session: LoginSession, refresh_token: str, now: datetime) -> LoginResult:
        if user.id is None:
            raise RuntimeError("数据库用户缺少 ID")
        return LoginResult(user=user, token=self._tokens.issue_access_token(user.id, session.id),
            refresh_token=refresh_token, refresh_expires_in=max(1, int((session.expires_at - now).total_seconds())))

    def current_user(self, token: str) -> User:
        identity = self._tokens.verify_access_token(token)
        session = self._sessions.find_by_id(identity.session_id)
        if session is None or session.user_id != identity.user_id or not session.is_active(self._clock()):
            raise InvalidAccessTokenError("登录已失效，请重新登录")
        user = self._users.get_by_id(identity.user_id)
        # 每次读取数据库中的最新状态，停用账号不能继续使用已有令牌。
        if user is None or not user.is_active:
            raise InvalidAccessTokenError("登录已失效，请重新登录")
        return user

    def refresh(self, refresh_token: str, request_id: UUID) -> LoginResult:
        try:
            token_hash = self._credentials.digest(refresh_token)
            session_id = self._credentials.session_id(refresh_token)
            request_key = str(UUID(str(request_id)))
        except ValueError:
            raise InvalidAccessTokenError("续期凭据无效") from None
        grant = self._sessions.find_by_refresh_hash(token_hash, session_id=session_id, lock=True)
        now = self._clock()
        if grant is None or not grant.session.is_active(now):
            raise InvalidAccessTokenError("登录已失效，请重新登录")
        user = self._users.get_by_id(grant.session.user_id)
        if user is None or not user.is_active:
            self._sessions.revoke(session_id, now)
            self._uow.commit()
            raise InvalidAccessTokenError("登录已失效，请重新登录")
        successor = self._credentials.successor(refresh_token, request_key)
        successor_hash = self._credentials.digest(successor)
        if grant.used_at is not None:
            next_grant = self._sessions.find_by_refresh_hash(
                successor_hash, session_id=session_id, lock=True,
            ) if grant.request_id == request_key and grant.successor_hash == successor_hash else None
            if next_grant is not None and next_grant.used_at is None:
                # 恢复同一请求丢失的响应，不重复轮换、不延长旧操作的会话窗口。
                return self._result(user, grant.session, successor, now)
            self._sessions.revoke(session_id, now)
            self._uow.commit()
            raise InvalidAccessTokenError("续期凭据已使用，请重新登录")
        expires_at = now + self._window
        self._sessions.rotate(token_hash, successor_hash, request_key, now, expires_at)
        updated = LoginSession(id=session_id, user_id=grant.session.user_id,
            created_at=grant.session.created_at, last_refreshed_at=now, expires_at=expires_at)
        result = self._result(user, updated, successor, now)
        self._uow.commit()
        return result

    def logout(self, refresh_token: str) -> None:
        try:
            token_hash = self._credentials.digest(refresh_token)
            session_id = self._credentials.session_id(refresh_token)
        except ValueError:
            return
        grant = self._sessions.find_by_refresh_hash(token_hash, session_id=session_id, lock=True)
        if grant is not None and grant.session.revoked_at is None:
            self._sessions.revoke(session_id, self._clock())
            self._uow.commit()
