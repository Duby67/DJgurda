"""Validated runtime configuration."""

from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, PositiveInt, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    bot_token: SecretStr
    # Local Bot API server; it must see work_dir at the same path. Unset: cloud API, 50 MB.
    bot_api_url: AnyHttpUrl | None = None
    admin_ids: list[PositiveInt] = Field(min_length=1, repr=False)
    database_path: Path
    work_dir: Path
    yandex_music_token: SecretStr | None = None  # Optional: Yandex Music downloads.
    # Optional: chat where inline mode uploads new videos for their file_id and the bot reports
    # delivery failures.
    inline_chat_id: int | None = None
    app_env: Literal["development", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    @field_validator("yandex_music_token")
    @classmethod
    def blank_token_is_unset(cls, value: SecretStr | None) -> SecretStr | None:
        return value if value and value.get_secret_value().strip() else None

    @field_validator("inline_chat_id", mode="before")
    @classmethod
    def blank_chat_is_unset(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @model_validator(mode="after")
    def production_uses_local_api(self) -> Settings:
        if self.app_env == "production" and self.bot_api_url is None:
            raise ValueError("BOT_API_URL is required in production")
        return self

    @field_validator("bot_token")
    @classmethod
    def require_token(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("BOT_TOKEN must not be empty")
        return value
