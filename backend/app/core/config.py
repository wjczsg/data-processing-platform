"""统一读取环境变量和项目根目录的 .env，并校验配置。"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """当前阶段使用的应用配置，字段名对应同名的大写环境变量。"""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="forbid",
        str_strip_whitespace=True,
        frozen=True,
        hide_input_in_errors=True,
    )

    app_name: str = Field(default="数据处理平台", min_length=1)
    app_version: str = Field(default="0.1.0", min_length=1)
    app_env: Literal["development", "test", "production"] = "development"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    cors_allowed_origins: list[str] = Field(default_factory=lambda: [
        "http://127.0.0.1:8765",
        "http://localhost:8765",
    ])

    mysql_host: str = Field(default="127.0.0.1", min_length=1)
    mysql_port: int = Field(default=3306, ge=1, le=65535)
    mysql_database: str = Field(default="data_processing_platform", min_length=1)
    mysql_user: str = Field(min_length=1)
    mysql_password: SecretStr = Field(min_length=1)
    jwt_secret_key: SecretStr | None = None
    jwt_access_token_expire_minutes: int = Field(default=30, ge=1, le=1440)
    auth_refresh_window_hours: int = Field(default=12, ge=1, le=168)

    @field_validator("jwt_secret_key", mode="before")
    @classmethod
    def preserve_jwt_key(cls, value: object) -> object:
        if value == "":
            return None
        return SecretStr(value) if isinstance(value, str) else value

    @field_validator("jwt_secret_key")
    @classmethod
    def validate_jwt_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None:
            secret = value.get_secret_value()
            if len(secret) < 32 or not secret.strip():
                raise ValueError("JWT 密钥必须至少为 32 个字符，且不能全部为空白")
        return value

    @field_validator("mysql_password", mode="before")
    @classmethod
    def preserve_password_characters(cls, value: object) -> object:
        """密码保留原始字符，不应用其他文本字段的空格清理规则。"""
        if isinstance(value, str):
            return SecretStr(value)
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """每个进程首次读取时加载配置，后续复用同一个配置对象。"""
    return Settings()
