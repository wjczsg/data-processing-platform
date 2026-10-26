"""账号注册、登录及查询当前用户的 HTTP 接口。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.app.api.dependencies import get_authentication_service, get_registration_service
from backend.app.api.schemas.auth import LoginRequest, LoginResponse, LogoutRequest, RefreshRequest, RegisteredUserResponse, RegisterRequest
from backend.app.application.authenticate_user import AuthenticationService, InvalidCredentialsError, LoginResult
from backend.app.application.ports.token_service import InvalidAccessTokenError
from backend.app.application.ports.user_repository import UsernameAlreadyExistsError
from backend.app.application.register_user import RegisterUserService, RegistrationValidationError

router = APIRouter(prefix="/api/auth", tags=["账号"])
bearer = HTTPBearer(auto_error=False)


def login_response(result: LoginResult, response: Response) -> LoginResponse:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return LoginResponse(access_token=result.token.value, expires_in=result.token.expires_in,
        refresh_token=result.refresh_token, refresh_expires_in=result.refresh_expires_in,
        user=RegisteredUserResponse.model_validate(result.user))


@router.post(
    "/register",
    response_model=RegisteredUserResponse,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "用户名已存在"}},
)
def register_user(
    payload: RegisterRequest,
    service: Annotated[RegisterUserService, Depends(get_registration_service)],
) -> RegisteredUserResponse:
    try:
        user = service.register(
            username=payload.username,
            password=payload.password.get_secret_value(),
            password_confirmation=payload.password_confirmation.get_secret_value(),
        )
    except RegistrationValidationError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error
    except UsernameAlreadyExistsError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在") from error

    return RegisteredUserResponse.model_validate(user)


@router.post("/login", response_model=LoginResponse)
def login_user(
    payload: LoginRequest,
    response: Response,
    service: Annotated[AuthenticationService, Depends(get_authentication_service)],
) -> LoginResponse:
    try:
        result = service.login(payload.username, payload.password.get_secret_value())
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=401, detail="账号或密码错误",
                            headers={"WWW-Authenticate": "Bearer"}) from error
    return login_response(result, response)


@router.post("/refresh", response_model=LoginResponse)
def refresh_login(payload: RefreshRequest, response: Response,
    service: Annotated[AuthenticationService, Depends(get_authentication_service)],
) -> LoginResponse:
    try:
        result = service.refresh(payload.refresh_token.get_secret_value(), payload.request_id)
    except InvalidAccessTokenError as error:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录",
                            headers={"WWW-Authenticate": "Bearer"}) from error
    return login_response(result, response)


@router.post("/logout", status_code=204)
def logout_user(payload: LogoutRequest,
    service: Annotated[AuthenticationService, Depends(get_authentication_service)],
) -> Response:
    service.logout(payload.refresh_token.get_secret_value())
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.get("/me", response_model=RegisteredUserResponse)
def current_user(
    response: Response,
    service: Annotated[AuthenticationService, Depends(get_authentication_service)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> RegisteredUserResponse:
    if credentials is None:
        raise HTTPException(status_code=401, detail="请先登录", headers={"WWW-Authenticate": "Bearer"})
    try:
        user = service.current_user(credentials.credentials)
    except InvalidAccessTokenError as error:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录",
                            headers={"WWW-Authenticate": "Bearer"}) from error
    response.headers["Cache-Control"] = "no-store"
    return RegisteredUserResponse.model_validate(user)
