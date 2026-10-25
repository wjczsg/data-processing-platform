"""用户数据访问约定，业务代码只需依赖此接口。"""

from typing import Protocol

from backend.app.domain.user import User


class UsernameAlreadyExistsError(Exception):
    """数据库已存在相同的规范化用户名。"""


class UserRepository(Protocol):
    """实现类接收外部会话，不自行提交、回滚或关闭会话。"""

    def get_by_id(self, user_id: int) -> User | None:
        """按 ID 查询；不存在时返回 None。"""
        ...

    def get_by_username(self, username: str) -> User | None:
        """先按账号规则规范化，再查询；不存在返回 None，格式非法抛 ValueError。"""
        ...

    def add(self, user: User) -> User:
        """新增并返回带 ID、时间的用户，仍需调用方提交事务。

        仅接收 ID 为空的新用户，否则抛 ValueError。
        用户名重复抛 UsernameAlreadyExistsError；写入异常后由调用方回滚事务。
        password_hash 必须由调用方预先生成，本方法不处理明文密码。
        """
        ...
