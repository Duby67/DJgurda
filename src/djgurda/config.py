"""Validated runtime configuration."""

from typing import Literal

from pydantic import Field, PositiveInt, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    bot_token: SecretStr
    admin_ids: list[PositiveInt] = Field(min_length=1, repr=False)
    app_env: Literal["development", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    @field_validator("bot_token")
    @classmethod
    def require_token(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("BOT_TOKEN must not be empty")
        return value
