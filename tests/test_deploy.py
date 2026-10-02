"""Run the remote release lifecycle with an offline Docker substitute."""

import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
BOT_API_IMAGE = "ghcr.io/example/bot-api@sha256:" + "e" * 64


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
if args[0] == 'login':
    sys.stdin.read()
elif args[0] == 'compose':
    config = pathlib.Path(args[args.index('--env-file') + 1]).read_text()
    image = next(
        line.split('=', 1)[1] for line in config.splitlines() if line.startswith('DJGURDA_IMAGE=')
    )
    if 'up' in args:
        state.write_text(image)
        if image == os.environ.get('FAIL_IMAGE'):
            raise SystemExit(1)
    elif 'stop' in args:
        state.unlink(missing_ok=True)
    elif '--services' in args:
        override = pathlib.Path(args[len(args) - 1 - args[::-1].index('-f') + 1]).read_text()
        print('bot')
        if 'bot-api:' in override:
            print('bot-api')
    elif 'ps' in args:
        print(args[-1])  # The service name stands in for the container ID.
elif args[0] == 'inspect':
    image_field = args[args.index('--format') + 1] == '{{.Config.Image}}'
    if not image_field:
        print('true 0 false healthy')
    else:
        print(state.read_text() if args[-1] == 'bot' else os.environ['BOT_API_IMAGE'])
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
        (stage / "compose.environment.yaml").write_bytes(
            (ROOT / "deploy" / f"compose.{environment}.yaml").read_bytes()
        )
        image = "ghcr.io/example/bot@sha256:" + digest * 64
        (stage / "runtime.env").write_text(
            f"DJGURDA_IMAGE={image}\nBOT_API_IMAGE={BOT_API_IMAGE}\nBOT_TOKEN=offline-bot-secret\n"
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
                "BOT_API_IMAGE": BOT_API_IMAGE,
            },
        )
        assert (result.returncode != 0) == fail, result.stdout + result.stderr
        assert "offline-registry-secret" not in result.stdout + result.stderr
        assert "offline-bot-secret" not in result.stdout + result.stderr
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
