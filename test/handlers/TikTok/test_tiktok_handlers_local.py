"""Локальный smoke-тест для проверки TikTokHandler на 3 типах контента.

Сценарий:
1. Разрешает короткий URL через resolve_url.
2. Ищет обработчик через ServiceManager.
3. Вызывает handler.process(...) и проверяет ожидаемый тип результата.
4. Очищает временные файлы через typed cleanup.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# test/handlers/TikTok/test_tiktok_handlers_local.py -> project root это parents[3]
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

from src.handlers.contracts import MediaResult
from src.handlers.manager import ServiceManager
from src.handlers.resources import TikTokHandler
from src.utils.url import resolve_url
from TikTok_urls import TIKTOK_TEST_CASES


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
    for case in TIKTOK_TEST_CASES
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

    if not isinstance(handler, TikTokHandler):
        return CaseResult(
            case=case,
            resolved_url=resolved_url,
            ok=False,
            message=f"ожидался TikTokHandler, получен: {handler.__class__.__name__}",
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
    print("=== TikTokHandler local smoke ===")
    print(f"project_root: {PROJECT_ROOT}")
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
        description="Локальный smoke-тест для TikTokHandler (video/profile/media_group)."
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
