"""Локальный smoke-тест для проверки VKHandler (playlist + audio tracks).

Сценарий:
1. Разрешает URL через resolve_url.
2. Ищет обработчик через ServiceManager.
3. Вызывает handler.process(...) и проверяет ожидаемый тип результата.
4. Для треков дополнительно проверяет, что скачанный файл валиден.
5. Очищает временные файлы через handler.cleanup(...).
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
from typing import Any, Optional

# test/handlers/VK/test_vk_handlers_local.py -> project root это parents[3]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Фиктивные значения для локального прогона теста.
os.environ.setdefault("BOT_DB_PATH", str(PROJECT_ROOT / "src" / "data" / "db" / "bot.db"))
os.environ.setdefault("BOT_VERSION", "local-test")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("BOT_TOKEN", "local-test-token")
os.environ.setdefault("YANDEX_MUSIC_TOKEN", "local-test-token")
os.environ.setdefault(
    "YOUTUBE_COOKIES_PATH",
    str(PROJECT_ROOT / "src" / "data" / "cookies" / "youtube_cookies.txt"),
)
os.environ.setdefault(
    "VK_COOKIES_PATH",
    str(PROJECT_ROOT / "src" / "data" / "cookies" / "vk.com_cookies.txt"),
)

from src.handlers.manager import ServiceManager
from src.handlers.resources import VKHandler
from src.utils.url import resolve_url
from VK_urls import VK_PLAYLIST_TEST_CASE, VK_TRACK_TEST_CASES


@dataclass(frozen=True)
class SmokeCase:
    """Описание одного тест-кейса."""

    name: str
    url: str
    expected_type: str
    description: str


@dataclass
class SmokeResult:
    """Результат выполнения одного тест-кейса."""

    case: SmokeCase
    resolved_url: str
    ok: bool
    message: str
    actual_type: Optional[str] = None


PLAYLIST_CASE = SmokeCase(
    name=VK_PLAYLIST_TEST_CASE["name"],
    url=VK_PLAYLIST_TEST_CASE["url"],
    expected_type=VK_PLAYLIST_TEST_CASE["expected_type"],
    description=VK_PLAYLIST_TEST_CASE["description"],
)

TRACK_CASES = tuple(
    SmokeCase(
        name=case["name"],
        url=case["url"],
        expected_type=case["expected_type"],
        description=case["description"],
    )
    for case in VK_TRACK_TEST_CASES
)


def validate_audio_file(file_info: dict[str, Any]) -> tuple[bool, str]:
    """Проверяет, что файл существует, имеет размер > 0 и читается как аудио."""
    file_path = file_info.get("file_path")
    if not isinstance(file_path, Path):
        return False, "file_info['file_path'] имеет неверный тип"
    if not file_path.exists():
        return False, f"файл не найден: {file_path}"

    file_size = file_path.stat().st_size
    if file_size <= 0:
        return False, "размер аудиофайла равен 0"

    ffprobe_path = shutil.which("ffprobe")
    if not ffprobe_path:
        return True, f"файл существует ({file_size} bytes), ffprobe не найден"

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

    has_audio = any(
        isinstance(stream, dict) and stream.get("codec_type") == "audio"
        for stream in streams
    )
    if not has_audio:
        return False, "в итоговом файле не найден аудио-поток"

    return True, f"валидный аудиофайл ({file_size} bytes)"


async def run_playlist_case(case: SmokeCase, timeout_sec: int) -> SmokeResult:
    """Запускает smoke-кейс плейлиста VK."""
    service_manager = ServiceManager()
    resolved_url = await resolve_url(case.url)
    handler = service_manager.get_handler(resolved_url)

    if not handler:
        return SmokeResult(
            case=case,
            resolved_url=resolved_url,
            ok=False,
            message="обработчик не найден для resolved URL",
        )
    if not isinstance(handler, VKHandler):
        return SmokeResult(
            case=case,
            resolved_url=resolved_url,
            ok=False,
            message=f"ожидался VKHandler, получен: {handler.__class__.__name__}",
        )

    file_info: Optional[dict[str, Any]] = None
    try:
        try:
            file_info = await asyncio.wait_for(
                handler.process(case.url, context=f"local-smoke:{case.name}", resolved_url=resolved_url),
                timeout=timeout_sec,
            )
        except asyncio.TimeoutError:
            return SmokeResult(
                case=case,
                resolved_url=resolved_url,
                ok=False,
                message=f"таймаут обработки ({timeout_sec} сек)",
            )
        except Exception as exc:  # noqa: BLE001
            return SmokeResult(
                case=case,
                resolved_url=resolved_url,
                ok=False,
                message=f"исключение: {exc}",
            )

        if not file_info:
            return SmokeResult(
                case=case,
                resolved_url=resolved_url,
                ok=False,
                message="handler.process вернул None",
            )

        actual_type = file_info.get("type")
        if actual_type != case.expected_type:
            return SmokeResult(
                case=case,
                resolved_url=resolved_url,
                ok=False,
                message=f"ожидался type={case.expected_type}, получен type={actual_type}",
                actual_type=actual_type,
            )

        metadata = file_info.get("metadata")
        if not isinstance(metadata, dict):
            return SmokeResult(
                case=case,
                resolved_url=resolved_url,
                ok=False,
                message="playlist metadata отсутствует или имеет неверный тип",
                actual_type=actual_type,
            )

        tracks = metadata.get("tracks")
        if not isinstance(tracks, list) or not tracks:
            return SmokeResult(
                case=case,
                resolved_url=resolved_url,
                ok=False,
                message="playlist распознан, но список треков пуст",
                actual_type=actual_type,
            )

        track_count = metadata.get("track_count")
        if not isinstance(track_count, int) or track_count <= 0:
            return SmokeResult(
                case=case,
                resolved_url=resolved_url,
                ok=False,
                message="playlist metadata не содержит корректный track_count",
                actual_type=actual_type,
            )

        return SmokeResult(
            case=case,
            resolved_url=resolved_url,
            ok=True,
            message=f"успешно (tracks parsed: {len(tracks)}, declared count: {track_count})",
            actual_type=actual_type,
        )
    finally:
        if file_info:
            handler.cleanup(file_info)


async def run_track_case(case: SmokeCase, timeout_sec: int) -> SmokeResult:
    """Запускает smoke-кейс одиночного трека VK."""
    service_manager = ServiceManager()
    resolved_url = await resolve_url(case.url)
    handler = service_manager.get_handler(resolved_url)

    if not handler:
        return SmokeResult(
            case=case,
            resolved_url=resolved_url,
            ok=False,
            message="обработчик не найден для resolved URL",
        )
    if not isinstance(handler, VKHandler):
        return SmokeResult(
            case=case,
            resolved_url=resolved_url,
            ok=False,
            message=f"ожидался VKHandler, получен: {handler.__class__.__name__}",
        )

    file_info: Optional[dict[str, Any]] = None
    try:
        try:
            file_info = await asyncio.wait_for(
                handler.process(case.url, context=f"local-smoke:{case.name}", resolved_url=resolved_url),
                timeout=timeout_sec,
            )
        except asyncio.TimeoutError:
            return SmokeResult(
                case=case,
                resolved_url=resolved_url,
                ok=False,
                message=f"таймаут обработки ({timeout_sec} сек)",
            )
        except Exception as exc:  # noqa: BLE001
            return SmokeResult(
                case=case,
                resolved_url=resolved_url,
                ok=False,
                message=f"исключение: {exc}",
            )

        if not file_info:
            return SmokeResult(
                case=case,
                resolved_url=resolved_url,
                ok=False,
                message="handler.process вернул None",
            )

        actual_type = file_info.get("type")
        if actual_type != case.expected_type:
            return SmokeResult(
                case=case,
                resolved_url=resolved_url,
                ok=False,
                message=f"ожидался type={case.expected_type}, получен type={actual_type}",
                actual_type=actual_type,
            )

        file_ok, file_message = validate_audio_file(file_info)
        if not file_ok:
            return SmokeResult(
                case=case,
                resolved_url=resolved_url,
                ok=False,
                message=file_message,
                actual_type=actual_type,
            )

        return SmokeResult(
            case=case,
            resolved_url=resolved_url,
            ok=True,
            message=f"успешно ({file_message})",
            actual_type=actual_type,
        )
    finally:
        if file_info:
            handler.cleanup(file_info)


async def run_all(timeout_sec: int) -> int:
    """Выполняет все тест-кейсы и возвращает код завершения."""
    print("=== VKHandler local smoke ===")
    print(f"project_root: {PROJECT_ROOT}")
    print("")

    results: list[SmokeResult] = []

    print(f"[RUN] {PLAYLIST_CASE.name}: {PLAYLIST_CASE.url}")
    print(f"  description: {PLAYLIST_CASE.description}")
    playlist_result = await run_playlist_case(PLAYLIST_CASE, timeout_sec=timeout_sec)
    results.append(playlist_result)
    playlist_status = "OK" if playlist_result.ok else "FAIL"
    print(f"  status: {playlist_status}")
    print(f"  resolved_url: {playlist_result.resolved_url}")
    print(f"  expected_type: {PLAYLIST_CASE.expected_type}")
    print(f"  actual_type: {playlist_result.actual_type}")
    print(f"  message: {playlist_result.message}")
    print("")

    for case in TRACK_CASES:
        print(f"[RUN] {case.name}: {case.url}")
        print(f"  description: {case.description}")
        result = await run_track_case(case, timeout_sec=timeout_sec)
        results.append(result)
        status = "OK" if result.ok else "FAIL"
        print(f"  status: {status}")
        print(f"  resolved_url: {result.resolved_url}")
        print(f"  expected_type: {case.expected_type}")
        print(f"  actual_type: {result.actual_type}")
        print(f"  message: {result.message}")
        print("")

    ok_count = sum(1 for result in results if result.ok)
    fail_count = len(results) - ok_count
    print("=== Summary ===")
    print(f"passed: {ok_count}")
    print(f"failed: {fail_count}")

    return 0 if fail_count == 0 else 1


def parse_args() -> argparse.Namespace:
    """Парсит аргументы CLI."""
    parser = argparse.ArgumentParser(
        description="Локальный smoke-тест для VKHandler (playlist/audio)."
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
