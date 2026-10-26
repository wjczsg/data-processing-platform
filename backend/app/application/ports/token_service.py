"""登录令牌的签发和验证约定，业务不依赖 JWT 库。"""

from dataclasses import dataclass, field
from typing import Protocol


class InvalidAccessTokenError(Exception):
    """令牌无效、过期，或令牌关联的用户已不可用。"""


@dataclass(frozen=True)
class AccessToken:
    value: str = field(repr=False)
    expires_in: int


class TokenService(Protocol):
    def issue_access_token(self, user_id: int) -> AccessToken:
        """签发带有效期的访问令牌，仅包含身份信息。"""
        ...

    def verify_access_token(self, token: str) -> int:
        """验证后返回用户 ID，无效时抛 InvalidAccessTokenError。"""
        ...
