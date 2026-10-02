"""Run the remote release lifecycle with an offline Docker substitute."""

import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


Run = Callable[..., subprocess.CompletedProcess[str]]


@pytest.fixture
def deployment(tmp_path: Path) -> tuple[Path, Run]:
    tools = tmp_path / "bin"
    tools.mkdir()
    docker = tools / "docker"
    docker.write_text(
        f"#!{sys.executable}\n"
        + """
import os, pathlib, sys
args = sys.argv[1:]
state = pathlib.Path(os.environ['FAKE_STATE'])
# Each project runs one service; the service name stands in for its container ID.
running = {'bot': state, 'bot-api': state.with_name(state.name + '-api')}
if args[0] == 'login':
    sys.stdin.read()
elif args[0] == 'compose':
    config = pathlib.Path(args[args.index('--env-file') + 1]).read_text()
    service, variable = ('bot-api', 'BOT_API_IMAGE=') if 'BOT_API_IMAGE=' in config else (
        'bot', 'DJGURDA_IMAGE='
    )
    image = next(line[len(variable):] for line in config.splitlines() if line.startswith(variable))
    if 'up' in args:
        running[service].write_text(image)
        if image == os.environ.get('FAIL_IMAGE'):
            raise SystemExit(1)
    elif 'stop' in args:
        running[service].unlink(missing_ok=True)
    elif '--services' in args or 'ps' in args:
        print(service)
elif args[0] == 'inspect':
    image_field = args[args.index('--format') + 1] == '{{.Config.Image}}'
    print(running[args[-1]].read_text() if image_field else 'true 0 false healthy')
"""
    )
    docker.chmod(0o755)
    sleep = tools / "sleep"
    sleep.write_text("#!/bin/sh\nexit 0\n")
    sleep.chmod(0o755)
    stage = tmp_path / "stage"
    stage.mkdir()
    for source, target in [
        ("compose.yaml", "compose.yaml"),
        ("compose.development.yaml", "compose.environment.yaml"),
    ]:
        (stage / target).write_bytes((ROOT / "deploy" / source).read_bytes())
    (stage / "registry-user").write_text("offline")
    (stage / "registry-token").write_text("offline-registry-secret")

    def run(
        digest: str, *, fail: bool = False, environment: str = "production"
    ) -> subprocess.CompletedProcess[str]:
        bot_api = environment == "production-botapi"
        base = "compose.bot-api.yaml" if bot_api else "compose.yaml"
        (stage / "compose.yaml").write_bytes((ROOT / "deploy" / base).read_bytes())
        (stage / "compose.environment.yaml").write_bytes(
            (ROOT / "deploy" / f"compose.{environment}.yaml").read_bytes()
        )
        image = f"ghcr.io/example/{'bot-api' if bot_api else 'bot'}@sha256:" + digest * 64
        (stage / "runtime.env").write_text(
            f"BOT_API_IMAGE={image}\nTELEGRAM_API_HASH=offline-api-secret\n"
            if bot_api
            else f"DJGURDA_IMAGE={image}\nBOT_TOKEN=offline-bot-secret\n"
        )
        result = subprocess.run(
            ["bash", str(ROOT / "scripts/deploy-remote.sh"), "stage", environment],
            cwd=tmp_path,
            text=True,
            capture_output=True,
            env={
                **os.environ,
                "PATH": str(tools) + ":" + os.environ["PATH"],
                "FAKE_STATE": str(tmp_path / "running-image"),
                "FAIL_IMAGE": image if fail else "",
            },
        )
        assert (result.returncode != 0) == fail, result.stdout + result.stderr
        assert "offline-registry-secret" not in result.stdout + result.stderr
        assert "offline-bot-secret" not in result.stdout + result.stderr
        assert "offline-api-secret" not in result.stdout + result.stderr
        return result

    return tmp_path, run


def test_failed_retries_preserve_successful_releases_and_recover(
    deployment: tuple[Path, Run],
) -> None:
    root, run = deployment
    env = root / "production"
    run("a")
    first = (env / "current").resolve()
    assert not (env / "previous").exists()
    run("b")
    second = (env / "current").resolve()
    assert (env / "previous").resolve() == first
    for _ in range(2):
        result = run("c", fail=True)
        assert "restored the last successful release" in result.stderr
        assert (env / "current").resolve() == second
        assert (env / "previous").resolve() == first
        assert (root / "running-image").read_text().endswith("b" * 64)
        assert len(list((env / "releases").iterdir())) == 2
    run("d")
    assert (env / "previous").resolve() == second
    assert not first.exists()
    assert len(list((env / "releases").iterdir())) == 2
    assert (env / "current/runtime.env").stat().st_mode & 0o777 == 0o600


def test_first_failed_release_is_stopped_without_promotion(deployment: tuple[Path, Run]) -> None:
    root, run = deployment
    result = run("a", fail=True)
    assert "no successful release exists" in result.stderr
    assert not (root / "production/current").exists()
    assert not (root / "running-image").exists()
    assert not list((root / "production/releases").iterdir())


def test_development_stops_after_success_and_failure(deployment: tuple[Path, Run]) -> None:
    root, run = deployment
    env = root / "development"
    run("a", fail=True, environment="development")
    assert not (root / "running-image").exists()
    assert not (env / "current").exists()
    result = run("b", environment="development")
    assert "bot stopped" in result.stdout
    assert not (root / "running-image").exists()
    current = (env / "current").resolve()
    run("c", fail=True, environment="development")
    assert not (root / "running-image").exists()
    assert (env / "current").resolve() == current
    run("d", environment="development")
    assert not (root / "running-image").exists()
    assert (env / "previous").resolve() == current


def test_bot_api_and_bot_deploy_independently(deployment: tuple[Path, Run]) -> None:
    root, run = deployment
    bot, api = root / "running-image", root / "running-image-api"
    run("a")
    run("b", environment="production-botapi")
    assert bot.read_text().endswith("a" * 64) and api.read_text().endswith("b" * 64)
    result = run("c", fail=True, environment="production-botapi")
    assert "restored the last successful release" in result.stderr
    assert api.read_text().endswith("b" * 64)
    run("d")
    assert bot.read_text().endswith("d" * 64) and api.read_text().endswith("b" * 64)
    assert (root / "production-botapi/current").resolve() != (root / "production/current").resolve()
