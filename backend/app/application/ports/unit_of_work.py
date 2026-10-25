"""用户业务所需的事务约定，不依赖 SQLAlchemy。"""

from typing import Protocol

from backend.app.application.ports.user_repository import UserRepository


class UserUnitOfWork(Protocol):
    """将用户数据访问和事务提交绑定到同一会话。

    业务决定何时提交；异常回滚、关闭由外部会话管理负责。
    """

    users: UserRepository

    def commit(self) -> None:
        """提交当前业务事务，失败时继续抛出异常。"""
        ...
