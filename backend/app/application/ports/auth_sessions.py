"""登录会话存储与随机续期凭据处理的接口约定。"""

from datetime import datetime
from typing import Protocol

from backend.app.domain.login_session import LoginSession, RefreshGrant


class AuthSessionRepository(Protocol):
    def create(self, session: LoginSession, token_hash: str) -> None: ...

    def find_by_id(self, session_id: str) -> LoginSession | None: ...

    def find_by_refresh_hash(self, token_hash: str, *, session_id: str, lock: bool = False) -> RefreshGrant | None:
        """写操作先锁会话，再读取凭据最新状态，避免并发重复轮换。"""
        ...

    def rotate(self, token_hash: str, successor_hash: str, request_id: str,
               now: datetime, expires_at: datetime) -> None: ...

    def revoke(self, session_id: str, now: datetime) -> None: ...


class RefreshCredentialCodec(Protocol):
    def create(self, session_id: str) -> str: ...

    def session_id(self, token: str) -> str: ...

    def digest(self, token: str) -> str: ...

    def successor(self, token: str, request_id: str) -> str:
        """同一凭据、同一请求编号可重建同一后继凭据，无需保存明文。"""
        ...
