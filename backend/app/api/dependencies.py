"""在 HTTP 请求边界组装业务依赖和独立数据库会话。"""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.app.application.authenticate_user import AuthenticationService
from backend.app.application.ports.password_hasher import PasswordHasher
from backend.app.application.ports.auth_sessions import RefreshCredentialCodec
from backend.app.application.ports.unit_of_work import FileUnitOfWork, UserUnitOfWork
from backend.app.application.ports.file_storage import FileStorage
from backend.app.application.ports.token_service import InvalidAccessTokenError, TokenService
from backend.app.application.register_user import RegisterUserService
from backend.app.application.store_uploaded_file import StoreUploadedFileService
from backend.app.application.confirm_file_header import ConfirmFileHeaderService
from backend.app.core.config import Settings, get_settings
from backend.app.domain.user import User
from backend.app.infrastructure.db.session import session_scope
from backend.app.infrastructure.db.unit_of_work import MySQLFileUnitOfWork, MySQLUserUnitOfWork
from backend.app.infrastructure.files.local_storage import LocalFileStorage
from backend.app.infrastructure.files.csv_format import read_file_columns


bearer = HTTPBearer(auto_error=False)


def get_database_session(request: Request) -> Iterator[Session]:
    # 一个请求内的身份查询和文件写入复用会话，避免各自占用连接。
    with session_scope(request.app.state.session_factory) as session:
        yield session


def get_user_unit_of_work(session: Annotated[Session, Depends(get_database_session)]) -> UserUnitOfWork:
    return MySQLUserUnitOfWork(session)


def get_file_unit_of_work(session: Annotated[Session, Depends(get_database_session)]) -> FileUnitOfWork:
    return MySQLFileUnitOfWork(session)


def get_file_storage(settings: Annotated[Settings, Depends(get_settings)]) -> FileStorage:
    return LocalFileStorage(settings.upload_storage_dir)


def get_store_uploaded_file_service(
    unit_of_work: Annotated[FileUnitOfWork, Depends(get_file_unit_of_work)],
    storage: Annotated[FileStorage, Depends(get_file_storage)],
) -> StoreUploadedFileService:
    return StoreUploadedFileService(unit_of_work, storage)


def get_confirm_file_header_service(
    unit_of_work: Annotated[FileUnitOfWork, Depends(get_file_unit_of_work)],
    storage: Annotated[FileStorage, Depends(get_file_storage)],
) -> ConfirmFileHeaderService:
    return ConfirmFileHeaderService(unit_of_work, storage, read_file_columns)


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


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    service: Annotated[AuthenticationService, Depends(get_authentication_service)],
) -> User:
    """受保护接口共用：验证令牌、登录会话和账号状态，返回当前用户。"""
    if credentials is None:
        raise HTTPException(
            status_code=401, detail="请先登录", headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return service.current_user(credentials.credentials)
    except InvalidAccessTokenError as error:
        raise HTTPException(
            status_code=401, detail="登录已失效，请重新登录",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error


def get_registration_service(
    unit_of_work: Annotated[UserUnitOfWork, Depends(get_user_unit_of_work)],
    password_hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
) -> RegisterUserService:
    return RegisterUserService(unit_of_work, password_hasher)
