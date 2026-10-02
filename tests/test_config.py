"""Check the required configuration boundary without reading local secrets."""

import pytest
from pydantic import ValidationError

from djgurda.config import Settings


@pytest.mark.parametrize("token", [None, "   "])
def test_token_is_required(token: str | None, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("BOT_TOKEN", "APP_ENV", "LOG_LEVEL"):
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.lower(), raising=False)
    monkeypatch.setenv("ADMIN_IDS", "[100]")
    monkeypatch.setenv("DATABASE_PATH", "db.sqlite3")
    monkeypatch.setenv("WORK_DIR", "work")
    monkeypatch.setenv("BOT_API_URL", "http://bot-api:8081")
    if token is not None:
        monkeypatch.setenv("BOT_TOKEN", token)

    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None)

    assert {item["loc"] for item in error.value.errors()} == {("bot_token",)}


@pytest.mark.parametrize("admin_ids", [None, "[]", "[0]", "[-1]"])
def test_admin_ids_are_required(admin_ids: str | None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "offline-test-token")
    monkeypatch.setenv("DATABASE_PATH", "db.sqlite3")
    monkeypatch.setenv("WORK_DIR", "work")
    monkeypatch.setenv("BOT_API_URL", "http://bot-api:8081")
    for name in ("ADMIN_IDS", "admin_ids", "APP_ENV", "app_env", "LOG_LEVEL", "log_level"):
        monkeypatch.delenv(name, raising=False)
    if admin_ids is not None:
        monkeypatch.setenv("ADMIN_IDS", admin_ids)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_admin_ids_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "offline-test-token")
    monkeypatch.setenv("DATABASE_PATH", "db.sqlite3")
    monkeypatch.setenv("WORK_DIR", "work")
    monkeypatch.setenv("BOT_API_URL", "http://bot-api:8081")
    monkeypatch.setenv("ADMIN_IDS", "[100, 200]")
    settings = Settings(_env_file=None)
    assert settings.admin_ids == [100, 200]
    assert "admin_ids" not in repr(settings)
