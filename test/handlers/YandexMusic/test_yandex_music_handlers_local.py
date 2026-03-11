"""Локальный smoke-тест для проверки YandexMusicHandler на типе `audio`.

Сценарий:
1. Загружает env из `.env.yandex_music_tests`.
2. Разрешает URL через resolve_url.
3. Ищет обработчик через ServiceManager.
4. Вызывает handler.process(...) и проверяет ожидаемый тип результата.
5. Очищает временные файлы через typed cleanup.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# test/handlers/YandexMusic/test_yandex_music_handlers_local.py -> project root это parents[3]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
HANDLERS_TEST_ROOT = PROJECT_ROOT / "test" / "handlers"
if str(HANDLERS_TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(HANDLERS_TEST_ROOT))

ENV_FILE_PATH = PROJECT_ROOT / "test" / "handlers" / "YandexMusic" / ".env.yandex_music_tests"


def _load_env_file(path: Path) -> None:
    """Загружает env-переменные из файла формата KEY=VALUE."""
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key:
            os.environ.setdefault(key, value)


_load_env_file(ENV_FILE_PATH)

# Фиктивные значения для локального прогона теста.
os.environ.setdefault("BOT_DB_PATH", str(PROJECT_ROOT / "src" / "data" / "db" / "bot.db"))
os.environ.setdefault("BOT_VERSION", "local-test")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("BOT_TOKEN", "local-test-token")
os.environ.setdefault("YANDEX_MUSIC_TOKEN", "local-test-token")

from src.handlers.contracts import MediaResult
from src.handlers.manager import ServiceManager
from src.handlers.resources import YandexMusicHandler
from src.utils.url import resolve_url
from YandexMusic_urls import YANDEX_MUSIC_TEST_CASES


@dataclass(frozen=True)
class CaseSpec:
    """Описание одного тест-кейса."""

    name: str
    url: str
    expected_type: str
    description: str


@dataclass
class CaseResult:
    """Результат выполнения одного тест-кейса."""

    case: CaseSpec
    resolved_url: str
    ok: bool
    message: str
    actual_type: Optional[str] = None


DEFAULT_CASES = tuple(
    CaseSpec(
        name=case["name"],
        url=case["url"],
        expected_type=case["expected_type"],
        description=case["description"],
    )
    for case in YANDEX_MUSIC_TEST_CASES
)


def _cleanup_media_result(result: MediaResult) -> None:
    """Очищает runtime-файлы для typed-результата."""
    for path in result.iter_cleanup_paths():
        try:
            path.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass


def _extract_actual_type(handler_output: MediaResult) -> str:
    """Возвращает тип контента для typed-результата."""
    return handler_output.content_type.value


async def run_case(case: CaseSpec, timeout_sec: int) -> CaseResult:
    """Запускает один тест-кейс и возвращает результат."""
    service_manager = ServiceManager()
    resolved_url = await resolve_url(case.url)
    handler = service_manager.get_handler(resolved_url)

    if not handler:
        return CaseResult(
            case=case,
            resolved_url=resolved_url,
            ok=False,
            message="обработчик не найден для resolved URL",
        )

    if not isinstance(handler, YandexMusicHandler):
        return CaseResult(
            case=case,
            resolved_url=resolved_url,
            ok=False,
            message=f"ожидался YandexMusicHandler, получен: {handler.__class__.__name__}",
        )

    handler_output: MediaResult | None = None
    try:
        handler_output = await asyncio.wait_for(
            handler.process(case.url, context=f"local-smoke:{case.name}", resolved_url=resolved_url),
            timeout=timeout_sec,
        )
    except asyncio.TimeoutError:
        return CaseResult(
            case=case,
            resolved_url=resolved_url,
            ok=False,
            message=f"таймаут обработки ({timeout_sec} сек)",
        )
    except Exception as exc:  # noqa: BLE001
        return CaseResult(
            case=case,
            resolved_url=resolved_url,
            ok=False,
            message=f"исключение: {exc}",
        )
    finally:
        if isinstance(handler_output, MediaResult):
            _cleanup_media_result(handler_output)

    if not handler_output:
        return CaseResult(
            case=case,
            resolved_url=resolved_url,
            ok=False,
            message="handler.process вернул None",
        )

    actual_type = _extract_actual_type(handler_output)
    if actual_type != case.expected_type:
        return CaseResult(
            case=case,
            resolved_url=resolved_url,
            ok=False,
            message=f"ожидался type={case.expected_type}, получен type={actual_type}",
            actual_type=actual_type,
        )

    return CaseResult(
        case=case,
        resolved_url=resolved_url,
        ok=True,
        message="успешно",
        actual_type=actual_type,
    )


async def run_all(timeout_sec: int) -> int:
    """Выполняет все тест-кейсы и возвращает код завершения."""
    print("=== YandexMusicHandler local smoke ===")
    print(f"project_root: {PROJECT_ROOT}")
    print(f"env_file: {ENV_FILE_PATH}")
    print("")

    results: list[CaseResult] = []
    for case in DEFAULT_CASES:
        print(f"[RUN] {case.name}: {case.url}")
        print(f"  description: {case.description}")
        result = await run_case(case, timeout_sec=timeout_sec)
        results.append(result)
        status = "OK" if result.ok else "FAIL"
        print(f"  status: {status}")
        print(f"  resolved_url: {result.resolved_url}")
        print(f"  expected_type: {case.expected_type}")
        print(f"  actual_type: {result.actual_type}")
        print(f"  message: {result.message}")
        print("")

    ok_count = sum(1 for r in results if r.ok)
    fail_count = len(results) - ok_count
    print("=== Summary ===")
    print(f"passed: {ok_count}")
    print(f"failed: {fail_count}")

    return 0 if fail_count == 0 else 1


def parse_args() -> argparse.Namespace:
    """Парсит аргументы CLI."""
    parser = argparse.ArgumentParser(
        description="Локальный smoke-тест для YandexMusicHandler (track/audio)."
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=180,
        help="Таймаут на один кейс в секундах (по умолчанию: 180).",
    )
    return parser.parse_args()


def main() -> int:
    """Точка входа."""
    args = parse_args()
    return asyncio.run(run_all(timeout_sec=args.timeout))


if __name__ == "__main__":
    raise SystemExit(main())
