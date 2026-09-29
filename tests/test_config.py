"""Check the required configuration boundary without reading local secrets."""

import pytest
from pydantic import ValidationError

from djgurda.config import Settings


@pytest.mark.parametrize("token", [None, "   "])
def test_token_is_required(token: str | None, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("BOT_TOKEN", "APP_ENV", "LOG_LEVEL"):
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.lower(), raising=False)
    if token is not None:
        monkeypatch.setenv("BOT_TOKEN", token)

    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None)

    assert {item["loc"] for item in error.value.errors()} == {("bot_token",)}
