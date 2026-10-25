"""组织注册业务，通过接口使用数据库事务和密码哈希能力。"""

from backend.app.application.ports.password_hasher import PasswordHasher
from backend.app.application.ports.unit_of_work import UserUnitOfWork
from backend.app.application.ports.user_repository import UsernameAlreadyExistsError
from backend.app.domain.password import validate_new_password, validate_password_confirmation
from backend.app.domain.user import User, normalize_username


class RegistrationValidationError(ValueError):
    """注册输入不符合账号或密码规则。"""


class RegisterUserService:
    def __init__(self, unit_of_work: UserUnitOfWork, password_hasher: PasswordHasher) -> None:
        self._unit_of_work = unit_of_work
        self._password_hasher = password_hasher

    def register(self, username: str, password: str, password_confirmation: str) -> User:
        try:
            username = normalize_username(username)
            validate_new_password(password)
            validate_password_confirmation(password, password_confirmation)
        except ValueError as error:
            raise RegistrationValidationError(str(error)) from error

        if self._unit_of_work.users.get_by_username(username) is not None:
            raise UsernameAlreadyExistsError("用户名已存在")

        password_hash = self._password_hasher.hash_password(password)
        # 角色和启用状态使用 User 的默认值，不接受注册者自行指定。
        user = self._unit_of_work.users.add(User(username=username, password_hash=password_hash))
        # 并发重复写入仍由数据库唯一约束拒绝，add 的冲突异常继续向上抛出。
        self._unit_of_work.commit()
        return user
