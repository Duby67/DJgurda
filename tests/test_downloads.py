"""Real subprocesses exercise cancellation, deadlines and unknown-size downloads offline."""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from djgurda import downloads
from djgurda.media import Info, Job, MediaError
from djgurda.sources import classify, yandex_music


def test_worker_reports_unconfigured_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(yandex_music, "token", None)
    link = classify("https://music.yandex.ru/album/1/track/2")
    assert link is not None
    with pytest.raises(MediaError, match="Яндекс Музыка не подключена") as error:
        asyncio.run(downloads.fetch(link, tmp_path, Job(1000, lambda duration: None)))
    # Failure reports carry the worker's own traceback, not only the parent's.
    assert "yandex_music.py" in "".join(error.value.__notes__)


@pytest.mark.parametrize("stop", ["cancel", "timeout", "size", "result"])
def test_supervisor_stops_worker_and_children(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stop: str
) -> None:
    script = tmp_path / "worker.py"
    target = tmp_path / "download"
    target.mkdir()
    info = json.dumps({"title": "", "uploader": "", "duration": 1, "width": 2, "height": 3})
    script.write_text(
        "import json, subprocess, sys, time\n"
        "from pathlib import Path\n"
        "s=json.loads(sys.stdin.readline())\n"
        "p=Path(s['target'])\n"
        "child=subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], "
        "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL)\n"
        "(p.parent/'child.pid').write_text(str(child.pid))\n"
        "print(json.dumps({'type':'admit', 'duration':1}), flush=True)\n"
        "assert sys.stdin.readline().strip() == 'ok'\n"
        + ("(p/'unknown-size.part').write_bytes(b'x'*3000)\n" if stop == "size" else "")
        + (
            "(p/'video.mp4').write_bytes(b'video')\n"
            f"print(json.dumps({{'type':'result', 'path':str(p/'video.mp4'), "
            f"'info':{info}, "
            "'cover':None, 'thumbnail':None}), flush=True)\n"
            if stop == "result"
            else ""
        )
        + "time.sleep(60)\n"
    )
    spawn = asyncio.create_subprocess_exec
    processes: list[asyncio.subprocess.Process] = []

    async def substitute(*args: Any, **kwargs: Any) -> asyncio.subprocess.Process:
        process = await spawn(sys.executable, str(script), **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", substitute)
    monkeypatch.setattr(downloads, "DOWNLOAD_TIMEOUT", 0.5 if stop == "timeout" else 5)
    admitted = asyncio.Event()

    async def scenario() -> None:
        loop = asyncio.get_running_loop()

        def admit(duration: int | None) -> None:
            loop.call_soon_threadsafe(admitted.set)

        job = Job(1000, admit)
        link = classify("youtu.be/test")
        assert link is not None
        task = asyncio.create_task(downloads.fetch(link, target, job))
        await asyncio.wait_for(admitted.wait(), 3)
        if stop == "cancel":
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        elif stop == "result":
            result = await task
            assert result.path.read_bytes() == b"video"
            assert result.info == Info("", "", 1, 2, 3)
        else:
            with pytest.raises(MediaError, match="не уложилась" if stop == "timeout" else "больше"):
                await task
        assert processes[0].returncode is not None
        # A killed grandchild may await reaping by init; a zombie cannot write or consume CPU.
        pid = (tmp_path / "child.pid").read_text()
        stat = Path(f"/proc/{pid}/stat")
        for _ in range(50):
            if not stat.exists() or stat.read_text().split()[2] == "Z":
                break
            await asyncio.sleep(0.01)
        else:
            pytest.fail("Download child survived cleanup")

    asyncio.run(scenario())
