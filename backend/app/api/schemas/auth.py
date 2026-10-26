"""注册请求与公开用户响应，不对外暴露密码哈希。"""

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from backend.app.domain.password import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH
from backend.app.domain.user import UserRole


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    username: str = Field(strict=True, min_length=1)
    password: SecretStr = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)
    password_confirmation: SecretStr = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)


class RegisteredUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def include_utc_timezone(cls, value: datetime) -> datetime:
        # 数据库存的是不带时区的 UTC，HTTP 响应显式标记时区。
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    username: str = Field(strict=True, min_length=1)
    # 登录不套用注册的最小长度或弱密码规则。
    password: SecretStr = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)


class LoginResponse(BaseModel):
    access_token: str = Field(repr=False)
    token_type: str = "bearer"
    expires_in: int
    user: RegisteredUserResponse
