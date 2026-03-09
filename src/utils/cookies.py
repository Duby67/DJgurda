"""
Общие утилиты для работы с cookies в обработчиках.
"""

from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path
from typing import Dict, Optional

from src.config import PROJECT_TEMP_DIR

logger = logging.getLogger(__name__)

_WARNED_KEYS: set[str] = set()
_DEFAULT_YTDLP_COOKIE_RUNTIME_DIR = PROJECT_TEMP_DIR / "_cookies"
_MAX_RUNTIME_COPIES_PER_PROVIDER = 20


class CookieFile:
    """
    Нейтральный интерфейс для работы с cookies-файлом провайдера.

    Хранит параметры исходного файла (source of truth) и умеет:
    - проверять валидность cookies-файла;
    - создавать runtime-копию для yt-dlp;
    - формировать опции/словарь cookies для разных сценариев.
    """

    def __init__(
        self,
        *,
        provider_key: str,
        provider_name: str,
        enabled: bool,
        cookie_path: Optional[Path],
        path_env_name: str,
        runtime_dir: Optional[Path] = None,
        log: Optional[logging.Logger] = None,
    ) -> None:
        self._provider_key = provider_key
        self._provider_name = provider_name
        self._enabled = enabled
        self._cookie_path = cookie_path
        self._path_env_name = path_env_name
        self._runtime_dir = runtime_dir
        self._log = log or logger

    def resolve_valid_path(self) -> Optional[Path]:
        """
        Возвращает валидный cookies-файл или `None`, если файл отключен/не найден.
        """
        return resolve_valid_cookie_path(
            provider_key=self._provider_key,
            provider_name=self._provider_name,
            enabled=self._enabled,
            cookie_path=self._cookie_path,
            path_env_name=self._path_env_name,
            log=self._log,
        )

    def prepare_runtime_copy(self) -> Optional[Path]:
        """
        Создает runtime-копию для yt-dlp (отдельный файл на запуск/сессию).
        """
        valid_path = self.resolve_valid_path()
        if not valid_path:
            return None
        return prepare_cookiefile_for_ytdlp(
            valid_path,
            provider_key=self._provider_key,
            runtime_dir=self._runtime_dir,
        )

    def build_ytdlp_opts(self) -> Dict[str, str]:
        """
        Возвращает опции `cookiefile` для yt-dlp (runtime-копия на каждый вызов).
        """
        return build_ytdlp_cookiefile_opt(
            provider_key=self._provider_key,
            provider_name=self._provider_name,
            enabled=self._enabled,
            cookie_path=self._cookie_path,
            path_env_name=self._path_env_name,
            log=self._log,
            runtime_dir=self._runtime_dir,
        )

    def build_request_cookies(self) -> Dict[str, str]:
        """
        Возвращает cookies-словарь для HTTP-запросов провайдера.
        """
        return build_request_cookies(
            provider_key=self._provider_key,
            provider_name=self._provider_name,
            enabled=self._enabled,
            cookie_path=self._cookie_path,
            path_env_name=self._path_env_name,
            log=self._log,
        )


def warn_once(log: logging.Logger, key: str, message: str, *args: object) -> None:
    """
    Логирует предупреждение только один раз для указанного ключа.
    """
    if key in _WARNED_KEYS:
        return
    _WARNED_KEYS.add(key)
    log.warning(message, *args)


def looks_like_cookie_placeholder(path: Path) -> bool:
    """
    Проверяет, похож ли cookie-файл на заглушку.

    Корректным считается формат Netscape c tab-separated строками cookies.
    Строки-комментарии `# ...` игнорируются, кроме `#HttpOnly_...`.
    """
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return True

    if not content.strip():
        return True

    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        return True

    cookie_lines = []
    for line in lines:
        if "\t" not in line:
            continue
        if line.startswith("#") and not line.startswith("#HttpOnly_"):
            continue
        cookie_lines.append(line)

    return len(cookie_lines) == 0


def resolve_valid_cookie_path(
    *,
    provider_key: str,
    provider_name: str,
    enabled: bool,
    cookie_path: Optional[Path],
    path_env_name: str,
    log: logging.Logger,
) -> Optional[Path]:
    """
    Возвращает валидный cookie-файл для провайдера или `None`.
    """
    if not enabled:
        return None

    if not isinstance(cookie_path, Path):
        warn_once(
            log,
            f"{provider_key}-cookies-path-not-set",
            "%s cookies enabled, but %s is not set.",
            provider_name,
            path_env_name,
        )
        return None

    if not cookie_path.exists():
        warn_once(
            log,
            f"{provider_key}-cookies-missing:{cookie_path}",
            "%s cookies enabled, but cookie file does not exist: %s",
            provider_name,
            cookie_path,
        )
        return None

    if looks_like_cookie_placeholder(cookie_path):
        warn_once(
            log,
            f"{provider_key}-cookies-placeholder:{cookie_path}",
            "%s cookies file looks like a placeholder and will be ignored: %s",
            provider_name,
            cookie_path,
        )
        return None

    return cookie_path


def _prune_old_runtime_copies(provider_key: str, runtime_dir: Path) -> None:
    """
    Ограничивает число runtime-копий cookies для одного провайдера.
    """
    try:
        candidates = sorted(
            runtime_dir.glob(f"runtime_{provider_key}_*.txt"),
            key=lambda path: path.stat().st_mtime if path.exists() else 0,
            reverse=True,
        )
    except Exception:
        return

    for stale_path in candidates[_MAX_RUNTIME_COPIES_PER_PROVIDER:]:
        try:
            stale_path.unlink(missing_ok=True)
        except Exception:
            continue


def prepare_cookiefile_for_ytdlp(
    source_path: Path,
    provider_key: str,
    runtime_dir: Optional[Path] = None,
) -> Optional[Path]:
    """
    Создает рабочую копию cookie-файла для yt-dlp и возвращает путь к ней.

    Оригинальный cookie-файл не передается в yt-dlp напрямую, чтобы исключить
    его изменение сторонним инструментом.
    """
    if not isinstance(source_path, Path):
        return None

    safe_provider_key = (provider_key or "provider").strip().lower().replace(" ", "_")
    if not safe_provider_key:
        safe_provider_key = "provider"

    runtime_root = runtime_dir if isinstance(runtime_dir, Path) else _DEFAULT_YTDLP_COOKIE_RUNTIME_DIR
    try:
        runtime_root.mkdir(parents=True, exist_ok=True)
        runtime_copy_path = runtime_root / f"runtime_{safe_provider_key}_{uuid.uuid4().hex[:12]}.txt"
        shutil.copy2(source_path, runtime_copy_path)
        _prune_old_runtime_copies(safe_provider_key, runtime_root)
        return runtime_copy_path
    except Exception as exc:
        logger.warning(
            "Failed to prepare temporary cookies copy for %s (%s): %s",
            safe_provider_key,
            source_path,
            exc,
        )
        return None


def build_ytdlp_cookiefile_opt(
    *,
    provider_key: str,
    provider_name: str,
    enabled: bool,
    cookie_path: Optional[Path],
    path_env_name: str,
    log: logging.Logger,
    runtime_dir: Optional[Path] = None,
) -> Dict[str, str]:
    """
    Возвращает `cookiefile`-опцию для yt-dlp в безопасном auto-режиме.
    """
    valid_cookie_path = resolve_valid_cookie_path(
        provider_key=provider_key,
        provider_name=provider_name,
        enabled=enabled,
        cookie_path=cookie_path,
        path_env_name=path_env_name,
        log=log,
    )
    if not valid_cookie_path:
        return {}

    runtime_cookie_path = prepare_cookiefile_for_ytdlp(
        valid_cookie_path,
        provider_key=provider_key,
        runtime_dir=runtime_dir,
    )
    if not isinstance(runtime_cookie_path, Path):
        warn_once(
            log,
            f"{provider_key}-cookies-runtime-copy-failed:{valid_cookie_path}",
            "%s cookies file is valid, but runtime copy for yt-dlp failed and will be ignored: %s",
            provider_name,
            valid_cookie_path,
        )
        return {}

    return {"cookiefile": str(runtime_cookie_path)}


def cleanup_runtime_cookiefile(cookiefile: Optional[Path | str]) -> None:
    """
    Удаляет runtime cookie-файл, если он был создан для yt-dlp.
    """
    if not cookiefile:
        return

    try:
        runtime_path = Path(cookiefile).resolve()
    except Exception:
        return

    try:
        if not runtime_path.is_relative_to(PROJECT_TEMP_DIR):
            return
    except Exception:
        try:
            if PROJECT_TEMP_DIR.resolve() not in runtime_path.parents:
                return
        except Exception:
            return

    if not runtime_path.name.startswith("runtime_"):
        return

    try:
        runtime_path.unlink(missing_ok=True)
    except Exception:
        return


def parse_netscape_cookie_file(path: Path) -> Dict[str, str]:
    """
    Загружает cookies из Netscape-файла в словарь для HTTP-запросов.
    """
    cookies: Dict[str, str] = {}

    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_"):]
        elif line.startswith("#"):
            continue

        parts = line.split("\t")
        if len(parts) < 7:
            continue

        name = parts[5].strip()
        value = parts[6].strip()
        if not name:
            continue
        cookies[name] = value

    return cookies


def build_request_cookies(
    *,
    provider_key: str,
    provider_name: str,
    enabled: bool,
    cookie_path: Optional[Path],
    path_env_name: str,
    log: logging.Logger,
) -> Dict[str, str]:
    """
    Возвращает cookies-словарь для HTTP-запросов провайдера.
    """
    valid_cookie_path = resolve_valid_cookie_path(
        provider_key=provider_key,
        provider_name=provider_name,
        enabled=enabled,
        cookie_path=cookie_path,
        path_env_name=path_env_name,
        log=log,
    )
    if not valid_cookie_path:
        return {}

    try:
        cookies = parse_netscape_cookie_file(valid_cookie_path)
    except Exception as exc:
        warn_once(
            log,
            f"{provider_key}-cookies-parse-failed:{valid_cookie_path}",
            "Failed to parse %s cookies file %s: %s",
            provider_name,
            valid_cookie_path,
            exc,
        )
        return {}

    if not cookies:
        warn_once(
            log,
            f"{provider_key}-cookies-empty:{valid_cookie_path}",
            "%s cookies file is valid but contains no parsable cookies: %s",
            provider_name,
            valid_cookie_path,
        )

    return cookies
