"""统一读取环境变量和项目根目录的 .env，并校验配置。"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
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
    )

    app_name: str = Field(default="数据处理平台", min_length=1)
    app_version: str = Field(default="0.1.0", min_length=1)
    app_env: Literal["development", "test", "production"] = "development"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """每个进程首次读取时加载配置，后续复用同一个配置对象。"""
    return Settings()
