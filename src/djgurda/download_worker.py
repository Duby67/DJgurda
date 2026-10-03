"""Private pipe protocol for one supervised download; stdout contains only JSON events."""

import json
import os
import resource
import sys
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any

from djgurda.diagnostics import diagnostic
from djgurda.media import Job, MediaError
from djgurda.sources import classify, yandex_music


def main() -> None:
    settings = json.loads(sys.stdin.readline())
    if settings["music_token"]:
        os.environ["YANDEX_MUSIC_TOKEN"] = settings["music_token"]
    yandex_music.configure(settings["music_token"])
    link = classify(settings["url"])
    if link is None or not link.downloadable:
        raise RuntimeError("Worker needs a downloadable link")
    # Bound individual writes too, before the parent's aggregate disk check runs.
    cap = settings["max_bytes"] + 1  # One excess byte lets the parent identify an oversize file.
    resource.setrlimit(resource.RLIMIT_FSIZE, (cap, cap))
    lock = threading.Lock()
    stopped = threading.Event()

    def emit(event: dict[str, Any]) -> None:
        with lock:
            print(json.dumps(event), flush=True)

    def admit(duration: int | None) -> None:
        emit({"type": "admit", "duration": duration})
        if sys.stdin.readline().strip() != "ok":
            raise MediaError("загрузка отменена")

    job = Job(settings["max_bytes"], admit)

    def progress() -> None:
        while not stopped.wait(0.2):
            emit({"type": "progress", "stage": job.stage})

    thread = threading.Thread(target=progress, daemon=True)
    thread.start()
    try:
        media = link.source.fetch(link.url, Path(settings["target"]), job)
        stopped.set()
        thread.join()
        emit(
            {
                "type": "result",
                "path": str(media.path),
                "info": asdict(media.info),
                "cover": str(media.cover) if media.cover else None,
                "thumbnail": str(media.thumbnail) if media.thumbnail else None,
            }
        )
    except Exception as error:
        stopped.set()
        thread.join()
        # The parent reports the cause with its own diagnostics, so it is not logged here.
        emit(
            {
                "type": "error",
                "reason": str(error) if isinstance(error, MediaError) else None,
                "diagnostic": diagnostic(error),
            }
        )


if __name__ == "__main__":
    main()
