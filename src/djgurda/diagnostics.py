"""Exception diagnostics without credentials or signed download URLs."""

import logging
import os
import re
import traceback
from typing import Any


def redact(text: str) -> str:
    for name in ("BOT_TOKEN", "YANDEX_MUSIC_TOKEN"):
        if value := os.environ.get(name):
            text = text.replace(value, "[REDACTED]")
    text = re.sub(r"\b\d{6,}:[A-Za-z0-9_-]+", "[REDACTED]", text)
    return re.sub(r"https?://[^\s\"'<>]+", "[URL]", text)


def diagnostic(error: Exception) -> str:
    return redact("".join(traceback.format_exception(error)))


class DownloadLogger(logging.LoggerAdapter[logging.Logger]):
    def process(self, msg: Any, kwargs: Any) -> tuple[str, Any]:
        return redact(str(msg)), kwargs
