"""登录会话与一次续期凭据的业务数据，时间统一使用不带时区的 UTC。"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, kw_only=True)
class LoginSession:
    id: str
    user_id: int
    created_at: datetime
    last_refreshed_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None

    def is_active(self, now: datetime) -> bool:
        return self.revoked_at is None and self.expires_at > now


@dataclass(frozen=True, kw_only=True)
class RefreshGrant:
    session: LoginSession
    token_hash: str
    used_at: datetime | None
    request_id: str | None
    successor_hash: str | None
