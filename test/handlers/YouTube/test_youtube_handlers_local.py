"""Локальный smoke-тест для проверки YouTubeHandler на 2 типах контента.

Сценарий:
1. Разрешает URL через resolve_url.
2. Ищет обработчик через ServiceManager.
3. Вызывает handler.process(...) и проверяет ожидаемый тип результата.
4. Очищает временные файлы через handler.cleanup(...).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

# test/handlers/YouTube/test_youtube_handlers_local.py -> project root это parents[3]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
HANDLERS_TEST_ROOT = PROJECT_ROOT / "test" / "handlers"
if str(HANDLERS_TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(HANDLERS_TEST_ROOT))

from _local_cookie_setup import prepare_local_cookies

prepare_local_cookies(PROJECT_ROOT)

# Фиктивные значения для локального прогона теста.
os.environ.setdefault("BOT_DB_PATH", str(PROJECT_ROOT / "src" / "data" / "db" / "bot.db"))
os.environ.setdefault("BOT_VERSION", "local-test")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("BOT_TOKEN", "local-test-token")
os.environ.setdefault("YANDEX_MUSIC_TOKEN", "local-test-token")
os.environ.setdefault(
    "YOUTUBE_COOKIES_PATH",
    str(PROJECT_ROOT / "src" / "data" / "cookies" / "www.youtube.com_cookies.txt"),
)

from src.handlers.manager import ServiceManager
from src.handlers.resources import YouTubeHandler
from src.utils.url import resolve_url
from YouTube_urls import YOUTUBE_TEST_CASES


@dataclass(frozen=True)
class TestCase:
    """Описание одного тест-кейса."""

    name: str
    url: str
    expected_type: str
    description: str


@dataclass
class TestResult:
    """Результат выполнения одного тест-кейса."""

    case: TestCase
    resolved_url: str
    ok: bool
    message: str
    actual_type: Optional[str] = None


DEFAULT_CASES = tuple(
    TestCase(
        name=case["name"],
        url=case["url"],
        expected_type=case["expected_type"],
        description=case["description"],
    )
    for case in YOUTUBE_TEST_CASES
)


async def run_case(case: TestCase, timeout_sec: int) -> TestResult:
    """Запускает один тест-кейс и возвращает результат."""
    service_manager = ServiceManager()
    resolved_url = await resolve_url(case.url)
    handler = service_manager.get_handler(resolved_url)

    if not handler:
        return TestResult(
            case=case,
            resolved_url=resolved_url,
            ok=False,
            message="обработчик не найден для resolved URL",
        )

    if not isinstance(handler, YouTubeHandler):
        return TestResult(
            case=case,
            resolved_url=resolved_url,
            ok=False,
            message=f"ожидался YouTubeHandler, получен: {handler.__class__.__name__}",
        )

    file_info: Optional[dict[str, Any]] = None
    try:
        file_info = await asyncio.wait_for(
            handler.process(case.url, context=f"local-smoke:{case.name}", resolved_url=resolved_url),
            timeout=timeout_sec,
        )
    except asyncio.TimeoutError:
        return TestResult(
            case=case,
            resolved_url=resolved_url,
            ok=False,
            message=f"таймаут обработки ({timeout_sec} сек)",
        )
    except Exception as exc:  # noqa: BLE001
        return TestResult(
            case=case,
            resolved_url=resolved_url,
            ok=False,
            message=f"исключение: {exc}",
        )
    finally:
        if file_info:
            handler.cleanup(file_info)

    if not file_info:
        return TestResult(
            case=case,
            resolved_url=resolved_url,
            ok=False,
            message="handler.process вернул None",
        )

    actual_type = file_info.get("type")
    if actual_type != case.expected_type:
        return TestResult(
            case=case,
            resolved_url=resolved_url,
            ok=False,
            message=f"ожидался type={case.expected_type}, получен type={actual_type}",
            actual_type=actual_type,
        )

    return TestResult(
        case=case,
        resolved_url=resolved_url,
        ok=True,
        message="успешно",
        actual_type=actual_type,
    )


async def run_all(timeout_sec: int) -> int:
    """Выполняет все тест-кейсы и возвращает код завершения."""
    print("=== YouTubeHandler local smoke ===")
    print(f"project_root: {PROJECT_ROOT}")
    print("")

    results: list[TestResult] = []
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
        description="Локальный smoke-тест для YouTubeHandler (shorts/channel)."
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
