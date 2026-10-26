"""登录和当前用户查询：复用用户仓储、密码处理和令牌接口。"""

from dataclasses import dataclass

from backend.app.application.ports.password_hasher import PasswordHasher
from backend.app.application.ports.token_service import AccessToken, InvalidAccessTokenError, TokenService
from backend.app.application.ports.user_repository import UserRepository
from backend.app.domain.user import User, normalize_username


class InvalidCredentialsError(Exception):
    """账号不存在、密码错误或账号不可用，统一对外提示。"""


@dataclass(frozen=True)
class LoginResult:
    user: User
    token: AccessToken


class AuthenticationService:
    def __init__(
        self, users: UserRepository, password_hasher: PasswordHasher,
        tokens: TokenService, dummy_password_hash: str,
    ) -> None:
        self._users = users
        self._password_hasher = password_hasher
        self._tokens = tokens
        self._dummy_password_hash = dummy_password_hash

    def login(self, username: str, password: str) -> LoginResult:
        try:
            username = normalize_username(username)
            # 不能编码为 UTF-8 的输入不可能匹配本项目保存的密码。
            password.encode("utf-8")
        except (ValueError, UnicodeEncodeError):
            raise InvalidCredentialsError("账号或密码错误") from None

        # 读取已有用户，登录过程不新增用户，也不提交写事务。
        user = self._users.get_by_username(username)
        # 用户不存在也做一次真实密码验证，减少通过耗时猜测账号的机会。
        stored_hash = user.password_hash if user is not None else self._dummy_password_hash
        matches = self._password_hasher.verify_password(password, stored_hash)
        if user is None or not matches or not user.is_active:
            raise InvalidCredentialsError("账号或密码错误")
        if user.id is None:
            raise RuntimeError("数据库用户缺少 ID")
        return LoginResult(user=user, token=self._tokens.issue_access_token(user.id))

    def current_user(self, token: str) -> User:
        user_id = self._tokens.verify_access_token(token)
        user = self._users.get_by_id(user_id)
        # 每次读取数据库中的最新状态，停用账号不能继续使用已有令牌。
        if user is None or not user.is_active:
            raise InvalidAccessTokenError("登录已失效，请重新登录")
        return user
