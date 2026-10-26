"""使用 PyJWT 签发、验证 HS256 访问令牌。"""

from datetime import datetime, timezone

import jwt

from backend.app.application.ports.token_service import AccessToken, InvalidAccessTokenError, TokenService


class JWTTokenService(TokenService):
    ISSUER = "data-processing-platform"
    AUDIENCE = "data-processing-platform-api"

    def __init__(self, secret_key: str, expire_minutes: int = 30) -> None:
        if not isinstance(secret_key, str) or len(secret_key) < 32 or not secret_key.strip():
            raise ValueError("JWT 密钥必须至少为 32 个字符，且不能全部为空白")
        if type(expire_minutes) is not int or not 1 <= expire_minutes <= 1440:
            raise ValueError("令牌有效期必须为 1～1440 分钟")
        self._secret_key = secret_key
        self._expires_in = expire_minutes * 60

    def issue_access_token(self, user_id: int) -> AccessToken:
        if type(user_id) is not int or user_id <= 0:
            raise ValueError("用户 ID 必须为正整数")
        now = int(datetime.now(timezone.utc).timestamp())
        payload = {
            "sub": str(user_id), "iat": now, "exp": now + self._expires_in,
            "iss": self.ISSUER, "aud": self.AUDIENCE, "token_type": "access",
        }
        token = jwt.encode(payload, self._secret_key, algorithm="HS256")
        return AccessToken(value=token, expires_in=self._expires_in)

    def verify_access_token(self, token: str) -> int:
        if not isinstance(token, str) or not token or len(token) > 4096:
            raise InvalidAccessTokenError("登录令牌无效或已过期")
        try:
            # 只接受服务器指定的算法，不读取请求令牌中的 alg 来选择算法。
            payload = jwt.decode(
                token, self._secret_key, algorithms=["HS256"],
                issuer=self.ISSUER, audience=self.AUDIENCE,
                options={"require": ["sub", "iat", "exp", "iss", "aud", "token_type"]},
            )
            subject = payload["sub"]
            if (
                payload["token_type"] != "access"
                or not isinstance(subject, str)
                or not subject.isascii()
                or not subject.isdigit()
                or int(subject) <= 0
            ):
                raise InvalidAccessTokenError("登录令牌无效或已过期")
            return int(subject)
        except (jwt.PyJWTError, ValueError, TypeError) as error:
            raise InvalidAccessTokenError("登录令牌无效或已过期") from error
