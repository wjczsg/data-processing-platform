"""在 HTTP 请求边界组装业务依赖和独立数据库会话。"""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request

from backend.app.application.ports.password_hasher import PasswordHasher
from backend.app.application.ports.unit_of_work import UserUnitOfWork
from backend.app.application.register_user import RegisterUserService
from backend.app.infrastructure.db.session import session_scope
from backend.app.infrastructure.db.unit_of_work import MySQLUserUnitOfWork


def get_user_unit_of_work(request: Request) -> Iterator[UserUnitOfWork]:
    # 每个请求独立取得会话，异常回滚，结束时归还连接。
    with session_scope(request.app.state.session_factory) as session:
        yield MySQLUserUnitOfWork(session)


def get_password_hasher(request: Request) -> PasswordHasher:
    return request.app.state.password_hasher


def get_registration_service(
    unit_of_work: Annotated[UserUnitOfWork, Depends(get_user_unit_of_work)],
    password_hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
) -> RegisterUserService:
    return RegisterUserService(unit_of_work, password_hasher)
