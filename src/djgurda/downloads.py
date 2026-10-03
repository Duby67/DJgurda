"""Supervise a download process and its children before releasing files or a lane."""

import asyncio
import json
import os
import shutil
import signal
import sys
import time
from contextlib import suppress
from pathlib import Path

from djgurda.media import (
    DOWNLOAD_TIMEOUT,
    LONG_DOWNLOAD_TIMEOUT,
    LONG_DURATION,
    Info,
    Job,
    Media,
    MediaError,
    megabytes,
)
from djgurda.sources import yandex_music
from djgurda.sources.base import Link

POLL_INTERVAL = 0.2
MIN_FREE_BYTES = 16 * 1024 * 1024


async def fetch(link: Link, target: Path, job: Job) -> Media:
    started = time.monotonic()
    limit = DOWNLOAD_TIMEOUT
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "djgurda.download_worker",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    assert process.stdin is not None and process.stdout is not None
    # Configuration may have come from .env. Pass the token through a pipe, never argv or disk.
    process.stdin.write(
        (
            json.dumps(
                {
                    "url": link.url,
                    "target": str(target),
                    "max_bytes": job.max_bytes,
                    "music_token": yandex_music.token,
                }
            )
            + "\n"
        ).encode()
    )
    line = asyncio.create_task(process.stdout.readline())
    try:
        while True:
            if time.monotonic() - started > limit:
                raise MediaError(f"загрузка не уложилась в {limit // 60} мин")
            files = []
            for path in target.rglob("*"):
                with suppress(FileNotFoundError):  # ffmpeg/yt-dlp may rename a stream meanwhile.
                    if path.is_file():
                        files.append(path.stat().st_size)
            if sum(files) > 2 * job.max_bytes or any(size > job.max_bytes for size in files):
                raise MediaError(f"файл больше {megabytes(job.max_bytes)}")
            # Initial merge space is checked by the source. Keep a small emergency reserve
            # if another download consumes that space; merged output is already in `files`.
            if shutil.disk_usage(target).free < MIN_FREE_BYTES:
                raise MediaError("на сервере недостаточно места для загрузки")
            done, _ = await asyncio.wait({line}, timeout=POLL_INTERVAL)
            if not done:
                continue
            raw = line.result()
            if not raw:
                raise MediaError("процесс загрузки завершился без результата; проверьте логи")
            event = json.loads(raw)
            if event["type"] == "admit":
                duration = event["duration"]
                await asyncio.to_thread(job.admit, duration)
                if (duration or 0) > LONG_DURATION:
                    limit = LONG_DOWNLOAD_TIMEOUT
                process.stdin.write(b"ok\n")
                await process.stdin.drain()
            elif event["type"] == "progress":
                job.stage = event["stage"]
            elif event["type"] == "error":
                failure = (
                    MediaError(event["reason"])
                    if event["reason"] is not None
                    else RuntimeError("Download worker failed")
                )
                failure.add_note(f"Download worker traceback:\n{event['diagnostic']}")
                raise failure
            elif event["type"] == "result":
                return Media(
                    Path(event["path"]),
                    Info(**event["info"]),
                    Path(event["cover"]) if event["cover"] else None,
                    Path(event["thumbnail"]) if event["thumbnail"] else None,
                )
            else:
                raise RuntimeError("Unknown download worker event")
            line = asyncio.create_task(process.stdout.readline())
    finally:
        line.cancel()
        await asyncio.gather(line, return_exceptions=True)
        # SIGKILL reaches ffmpeg/deno too, including children surviving the worker itself.
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        await process.wait()
        process.stdin.close()
