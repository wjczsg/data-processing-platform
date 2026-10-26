"""高熵续期凭据及摘要；独立子密钥让丢失响应后的同操作重试可恢复。"""

import base64
import hashlib
import hmac
import re
import secrets

from backend.app.application.ports.auth_sessions import RefreshCredentialCodec


class OpaqueRefreshCredentials(RefreshCredentialCodec):
    def __init__(self, secret_key: str) -> None:
        self._key = hmac.digest(secret_key.encode("utf-8"), b"xingxu-refresh-rotation-v1", "sha256")

    def create(self, session_id: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{32}", session_id):
            raise ValueError("登录会话编号无效")
        return session_id + "." + secrets.token_urlsafe(48)

    def session_id(self, token: str) -> str:
        if not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{32}\.[A-Za-z0-9_-]{32,64}", token):
            raise ValueError("续期凭据格式无效")
        return token.split(".", 1)[0]

    def digest(self, token: str) -> str:
        self.session_id(token)
        return hashlib.sha256(token.encode("ascii")).hexdigest()

    def successor(self, token: str, request_id: str) -> str:
        self.digest(token)
        message = token.encode("ascii") + b"\x00" + request_id.encode("ascii")
        secret = base64.urlsafe_b64encode(hmac.digest(self._key, message, "sha256")).rstrip(b"=").decode("ascii")
        return self.session_id(token) + "." + secret
