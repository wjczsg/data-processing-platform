"""MySQL 登录会话存储；事务提交由业务层控制。"""

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.app.application.ports.auth_sessions import AuthSessionRepository
from backend.app.domain.login_session import LoginSession, RefreshGrant
from backend.app.infrastructure.db.models.auth_session import AuthSessionModel, RefreshTokenModel


class MySQLAuthSessionRepository(AuthSessionRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _domain(row: AuthSessionModel) -> LoginSession:
        return LoginSession(id=row.id, user_id=row.user_id, created_at=row.created_at,
            last_refreshed_at=row.last_refreshed_at, expires_at=row.expires_at, revoked_at=row.revoked_at)

    def create(self, session: LoginSession, token_hash: str) -> None:
        self._session.add(AuthSessionModel(id=session.id, user_id=session.user_id,
            created_at=session.created_at, last_refreshed_at=session.last_refreshed_at,
            expires_at=session.expires_at, revoked_at=session.revoked_at))
        self._session.flush()
        self._session.add(RefreshTokenModel(session_id=session.id, token_hash=token_hash, created_at=session.created_at))
        self._session.flush()

    def find_by_id(self, session_id: str) -> LoginSession | None:
        row = self._session.get(AuthSessionModel, session_id)
        return self._domain(row) if row is not None else None

    def find_by_refresh_hash(self, token_hash: str, *, session_id: str, lock: bool = False) -> RefreshGrant | None:
        statement = select(AuthSessionModel).where(AuthSessionModel.id == session_id)
        if lock:
            statement = statement.with_for_update()
        row = self._session.scalar(statement.execution_options(populate_existing=True))
        if row is None:
            return None
        statement = select(RefreshTokenModel).where(
            RefreshTokenModel.token_hash == token_hash, RefreshTokenModel.session_id == session_id,
        )
        if lock:
            statement = statement.with_for_update()
        token = self._session.scalar(statement.execution_options(populate_existing=True))
        if token is None:
            return None
        return RefreshGrant(session=self._domain(row), token_hash=token.token_hash,
            used_at=token.used_at, request_id=token.request_id, successor_hash=token.successor_hash)

    def rotate(self, token_hash: str, successor_hash: str, request_id: str,
               now: datetime, expires_at: datetime) -> None:
        token = self._session.scalar(select(RefreshTokenModel).where(RefreshTokenModel.token_hash == token_hash))
        if token is None:
            raise RuntimeError("已锁定的续期凭据不存在")
        token.used_at, token.request_id, token.successor_hash = now, request_id, successor_hash
        self._session.add(RefreshTokenModel(session_id=token.session_id, token_hash=successor_hash, created_at=now))
        self._session.execute(update(AuthSessionModel).where(AuthSessionModel.id == token.session_id)
                              .values(last_refreshed_at=now, expires_at=expires_at))
        self._session.flush()

    def revoke(self, session_id: str, now: datetime) -> None:
        self._session.execute(update(AuthSessionModel).where(AuthSessionModel.id == session_id).values(revoked_at=now))
        self._session.flush()
