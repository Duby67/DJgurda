"""Локальный smoke-тест для проверки VKHandler (playlist + audio + clip + post + profile).

Сценарий:
1. Разрешает URL через resolve_url.
2. Ищет обработчик через ServiceManager.
3. Вызывает handler.process(...) и проверяет ожидаемый тип результата.
4. Для треков дополнительно проверяет, что скачанный файл валиден.
5. Очищает временные файлы через typed cleanup.
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

# test/handlers/VK/test_vk_handlers_local.py -> project root это parents[3]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
HANDLERS_TEST_ROOT = PROJECT_ROOT / "test" / "handlers"
if str(HANDLERS_TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(HANDLERS_TEST_ROOT))

from _cookie_setup import prepare_test_cookies

prepare_test_cookies(PROJECT_ROOT)

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
os.environ.setdefault(
    "VK_COOKIES_PATH",
    str(PROJECT_ROOT / "src" / "data" / "cookies" / "vk.com_cookies.txt"),
)

from src.handlers.manager import ServiceManager
from src.handlers.contracts import AttachmentKind, MediaResult
from src.handlers.resources import VKHandler
from src.utils.url import resolve_url
from VK_urls import (
    VK_CLIP_TEST_CASE,
    VK_PLAYLIST_TEST_CASE,
    VK_POST_TEST_CASE,
    VK_PROFILE_TEST_CASES,
    VK_TRACK_TEST_CASES,
)


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
CLIP_CASE = SmokeCase(
    name=VK_CLIP_TEST_CASE["name"],
    url=VK_CLIP_TEST_CASE["url"],
    expected_type=VK_CLIP_TEST_CASE["expected_type"],
    description=VK_CLIP_TEST_CASE["description"],
)
POST_CASE = SmokeCase(
    name=VK_POST_TEST_CASE["name"],
    url=VK_POST_TEST_CASE["url"],
    expected_type=VK_POST_TEST_CASE["expected_type"],
    description=VK_POST_TEST_CASE["description"],
)
PROFILE_CASES = tuple(
    SmokeCase(
        name=case["name"],
        url=case["url"],
        expected_type=case["expected_type"],
        description=case["description"],
    )
    for case in VK_PROFILE_TEST_CASES
)


def _build_vk_service_manager() -> ServiceManager:
    """Создает ServiceManager c VK в default active runtime."""
    return ServiceManager()


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
    if handler_output.audio is not None:
        return handler_output.audio.file_path
    return handler_output.main_file_path


def validate_audio_file(handler_output: MediaResult) -> tuple[bool, str]:
    """Проверяет, что файл существует, имеет размер > 0 и читается как аудио."""
    file_path = _extract_main_file_path(handler_output)
    if not isinstance(file_path, Path):
        return False, "в результате отсутствует корректный путь к аудиофайлу"
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


def validate_media_file(handler_output: MediaResult) -> tuple[bool, str]:
    """Проверяет existence для одиночного media file."""
    file_path = _extract_main_file_path(handler_output)
    if not isinstance(file_path, Path):
        return False, "в результате отсутствует корректный путь к медиафайлу"
    if not file_path.exists():
        return False, f"файл не найден: {file_path}"
    file_size = file_path.stat().st_size
    if file_size <= 0:
        return False, "размер медиафайла равен 0"
    return True, f"валидный медиафайл ({file_size} bytes)"


def validate_media_group(handler_output: MediaResult) -> tuple[bool, str]:
    """Проверяет media_group поста."""
    if not handler_output.media_group:
        return False, "post typed-результат не содержит media_group"
    for attachment in handler_output.media_group:
        if attachment.kind not in {AttachmentKind.PHOTO, AttachmentKind.VIDEO}:
            return False, f"неподдерживаемый тип вложения: {attachment.kind}"
        if not attachment.file_path.exists():
            return False, f"вложение не найдено: {attachment.file_path}"
        if attachment.file_path.stat().st_size <= 0:
            return False, f"пустое вложение: {attachment.file_path}"
    return True, f"media_group ok ({len(handler_output.media_group)} files)"


def validate_profile_result(handler_output: MediaResult) -> tuple[bool, str]:
    """Проверяет profile-card результат."""
    caption_text = str(handler_output.caption_text or "").strip()
    if not caption_text:
        return False, "profile typed-результат не содержит caption_text"
    return True, "profile caption сформирован"


async def run_playlist_case(case: SmokeCase, timeout_sec: int) -> SmokeResult:
    """Запускает smoke-кейс плейлиста VK."""
    service_manager = _build_vk_service_manager()
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

    handler_output: MediaResult | None = None
    try:
        try:
            handler_output = await asyncio.wait_for(
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

        if not handler_output:
            return SmokeResult(
                case=case,
                resolved_url=resolved_url,
                ok=False,
                message="handler.process вернул None",
            )

        actual_type = _extract_actual_type(handler_output)
        if actual_type != case.expected_type:
            return SmokeResult(
                case=case,
                resolved_url=resolved_url,
                ok=False,
                message=f"ожидался type={case.expected_type}, получен type={actual_type}",
                actual_type=actual_type,
            )

        caption_text = str(handler_output.caption_text or "").strip()
        if not caption_text:
            return SmokeResult(
                case=case,
                resolved_url=resolved_url,
                ok=False,
                message="playlist typed-результат не содержит caption_text",
                actual_type=actual_type,
            )

        return SmokeResult(
            case=case,
            resolved_url=resolved_url,
            ok=True,
            message="успешно (playlist caption сформирован)",
            actual_type=actual_type,
        )
    finally:
        if isinstance(handler_output, MediaResult):
            _cleanup_media_result(handler_output)


async def run_track_case(case: SmokeCase, timeout_sec: int) -> SmokeResult:
    """Запускает smoke-кейс одиночного трека VK."""
    service_manager = _build_vk_service_manager()
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

    handler_output: MediaResult | None = None
    try:
        try:
            handler_output = await asyncio.wait_for(
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

        if not handler_output:
            return SmokeResult(
                case=case,
                resolved_url=resolved_url,
                ok=False,
                message="handler.process вернул None",
            )

        actual_type = _extract_actual_type(handler_output)
        if actual_type != case.expected_type:
            return SmokeResult(
                case=case,
                resolved_url=resolved_url,
                ok=False,
                message=f"ожидался type={case.expected_type}, получен type={actual_type}",
                actual_type=actual_type,
            )

        file_ok, file_message = validate_audio_file(handler_output)
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
        if isinstance(handler_output, MediaResult):
            _cleanup_media_result(handler_output)


async def run_generic_case(case: SmokeCase, timeout_sec: int) -> SmokeResult:
    """Запускает generic smoke-кейс для clip/post/profile."""
    service_manager = _build_vk_service_manager()
    resolved_url = await resolve_url(case.url)
    handler = service_manager.get_handler(resolved_url)

    if not handler:
        return SmokeResult(case=case, resolved_url=resolved_url, ok=False, message="обработчик не найден для resolved URL")
    if not isinstance(handler, VKHandler):
        return SmokeResult(
            case=case,
            resolved_url=resolved_url,
            ok=False,
            message=f"ожидался VKHandler, получен: {handler.__class__.__name__}",
        )

    handler_output: MediaResult | None = None
    try:
        try:
            handler_output = await asyncio.wait_for(
                handler.process(case.url, context=f"local-smoke:{case.name}", resolved_url=resolved_url),
                timeout=timeout_sec,
            )
        except asyncio.TimeoutError:
            return SmokeResult(case=case, resolved_url=resolved_url, ok=False, message=f"таймаут обработки ({timeout_sec} сек)")
        except Exception as exc:  # noqa: BLE001
            return SmokeResult(case=case, resolved_url=resolved_url, ok=False, message=f"исключение: {exc}")

        if not handler_output:
            return SmokeResult(case=case, resolved_url=resolved_url, ok=False, message="handler.process вернул None")

        actual_type = _extract_actual_type(handler_output)
        if actual_type != case.expected_type:
            return SmokeResult(
                case=case,
                resolved_url=resolved_url,
                ok=False,
                message=f"ожидался type={case.expected_type}, получен type={actual_type}",
                actual_type=actual_type,
            )

        if actual_type == "video":
            ok, message = validate_media_file(handler_output)
        elif actual_type == "media_group":
            ok, message = validate_media_group(handler_output)
        elif actual_type == "profile":
            ok, message = validate_profile_result(handler_output)
        else:
            ok, message = False, f"generic validator does not support type={actual_type}"

        return SmokeResult(
            case=case,
            resolved_url=resolved_url,
            ok=ok,
            message=message,
            actual_type=actual_type,
        )
    finally:
        if isinstance(handler_output, MediaResult):
            _cleanup_media_result(handler_output)


async def run_all(timeout_sec: int) -> int:
    """Выполняет все тест-кейсы и возвращает код завершения."""
    print("=== VKHandler local smoke ===")
    print(f"project_root: {PROJECT_ROOT}")
    print("")

    results: list[SmokeResult] = []

    all_cases: list[tuple[SmokeCase, str]] = [(PLAYLIST_CASE, "playlist")]
    all_cases.extend((case, "audio") for case in TRACK_CASES)
    all_cases.append((CLIP_CASE, "generic"))
    all_cases.append((POST_CASE, "generic"))
    all_cases.extend((case, "generic") for case in PROFILE_CASES)

    for case, runner_kind in all_cases:
        print(f"[RUN] {case.name}: {case.url}")
        print(f"  description: {case.description}")
        if runner_kind == "playlist":
            result = await run_playlist_case(case, timeout_sec=timeout_sec)
        elif runner_kind == "audio":
            result = await run_track_case(case, timeout_sec=timeout_sec)
        else:
            result = await run_generic_case(case, timeout_sec=timeout_sec)
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
        description="Локальный smoke-тест для VKHandler (playlist/audio/clip/post/profile)."
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
