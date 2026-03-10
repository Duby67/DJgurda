"""Локальный smoke-тест для проверки CoubHandler на video/view ссылках.

Сценарий:
1. Разрешает URL через resolve_url.
2. Ищет обработчик через ServiceManager.
3. Вызывает handler.process(...) и проверяет ожидаемый тип результата.
4. Очищает временные файлы через typed cleanup.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# test/handlers/Coub/test_coub_handlers_local.py -> project root это parents[3]
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
from src.handlers.resources import CoubHandler
from src.utils.url import resolve_url
from Coub_urls import COUB_TEST_CASES


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
    for case in COUB_TEST_CASES
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


def _extract_main_file_path(handler_output: MediaResult) -> Optional[Path]:
    """Возвращает путь к итоговому медиафайлу для typed-результата."""
    return handler_output.main_file_path


def validate_video_streams(handler_output: MediaResult) -> tuple[bool, str]:
    """Проверяет, что итоговый файл содержит video и audio потоки."""
    file_path = _extract_main_file_path(handler_output)
    if not isinstance(file_path, Path):
        return False, "в результате отсутствует корректный путь к файлу"
    if not file_path.exists():
        return False, f"файл не найден: {file_path}"

    ffprobe_path = shutil.which("ffprobe")
    if not ffprobe_path:
        return True, "ffprobe не найден, проверка потоков пропущена"

    try:
        probe_result = subprocess.run(
            [
                ffprobe_path,
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_streams",
                str(file_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"ошибка ffprobe: {exc}"

    if probe_result.returncode != 0:
        stderr = (probe_result.stderr or "").strip()
        return False, f"ffprobe завершился с ошибкой: {stderr or 'без stderr'}"

    try:
        payload = json.loads(probe_result.stdout or "{}")
    except json.JSONDecodeError as exc:
        return False, f"не удалось распарсить JSON ffprobe: {exc}"

    streams = payload.get("streams")
    if not isinstance(streams, list):
        return False, "ffprobe не вернул список streams"

    has_video = any(
        isinstance(stream, dict) and stream.get("codec_type") == "video"
        for stream in streams
    )
    has_audio = any(
        isinstance(stream, dict) and stream.get("codec_type") == "audio"
        for stream in streams
    )

    if not has_video:
        return False, "в итоговом файле нет видео-потока"
    if not has_audio:
        return False, "в итоговом файле нет аудио-потока"
    return True, "аудио- и видео-потоки подтверждены"


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

    if not isinstance(handler, CoubHandler):
        return CaseResult(
            case=case,
            resolved_url=resolved_url,
            ok=False,
            message=f"ожидался CoubHandler, получен: {handler.__class__.__name__}",
        )

    handler_output: MediaResult | None = None
    try:
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

        streams_ok, streams_message = validate_video_streams(handler_output)
        if not streams_ok:
            return CaseResult(
                case=case,
                resolved_url=resolved_url,
                ok=False,
                message=streams_message,
                actual_type=actual_type,
            )

        return CaseResult(
            case=case,
            resolved_url=resolved_url,
            ok=True,
            message=f"успешно ({streams_message})",
            actual_type=actual_type,
        )
    finally:
        if isinstance(handler_output, MediaResult):
            _cleanup_media_result(handler_output)


async def run_all(timeout_sec: int) -> int:
    """Выполняет все тест-кейсы и возвращает код завершения."""
    print("=== CoubHandler local smoke ===")
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
        description="Локальный smoke-тест для CoubHandler (/view/<id>)."
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
