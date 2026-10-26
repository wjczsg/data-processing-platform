"""在 HTTP 请求边界组装业务依赖和独立数据库会话。"""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from backend.app.application.authenticate_user import AuthenticationService

from backend.app.application.ports.password_hasher import PasswordHasher
from backend.app.application.ports.auth_sessions import RefreshCredentialCodec
from backend.app.application.ports.unit_of_work import UserUnitOfWork
from backend.app.application.ports.token_service import TokenService
from backend.app.application.register_user import RegisterUserService
from backend.app.infrastructure.db.session import session_scope
from backend.app.infrastructure.db.unit_of_work import MySQLUserUnitOfWork


def get_user_unit_of_work(request: Request) -> Iterator[UserUnitOfWork]:
    # 每个请求独立取得会话，异常回滚，结束时归还连接。
    with session_scope(request.app.state.session_factory) as session:
        yield MySQLUserUnitOfWork(session)


def get_password_hasher(request: Request) -> PasswordHasher:
    return request.app.state.password_hasher


def get_token_service(request: Request) -> TokenService:
    return request.app.state.token_service


def get_dummy_password_hash(request: Request) -> str:
    return request.app.state.dummy_password_hash


def get_refresh_credentials(request: Request) -> RefreshCredentialCodec:
    return request.app.state.refresh_credentials


def get_refresh_window_hours(request: Request) -> int:
    return request.app.state.refresh_window_hours


def get_authentication_service(
    unit_of_work: Annotated[UserUnitOfWork, Depends(get_user_unit_of_work)],
    password_hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
    tokens: Annotated[TokenService, Depends(get_token_service)],
    dummy_hash: Annotated[str, Depends(get_dummy_password_hash)],
    credentials: Annotated[RefreshCredentialCodec, Depends(get_refresh_credentials)],
    window_hours: Annotated[int, Depends(get_refresh_window_hours)],
) -> AuthenticationService:
    return AuthenticationService(unit_of_work, password_hasher, tokens, credentials, dummy_hash, window_hours)


def get_registration_service(
    unit_of_work: Annotated[UserUnitOfWork, Depends(get_user_unit_of_work)],
    password_hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
) -> RegisterUserService:
    return RegisterUserService(unit_of_work, password_hasher)
