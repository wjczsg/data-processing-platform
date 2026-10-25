"""认证相关 HTTP 接口，当前提供注册。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.api.dependencies import get_registration_service
from backend.app.api.schemas.auth import RegisteredUserResponse, RegisterRequest
from backend.app.application.ports.user_repository import UsernameAlreadyExistsError
from backend.app.application.register_user import RegisterUserService, RegistrationValidationError

router = APIRouter(prefix="/api/auth", tags=["账号"])


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
