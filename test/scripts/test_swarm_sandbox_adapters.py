from __future__ import annotations

import subprocess

from pathlib import Path

import pytest

from scripts.agents.sandbox_adapters import (
    DEFAULT_SANDBOX_IMAGE,
    DOCKER_ADAPTER,
    LOCAL_DRY_RUN_ADAPTER,
    build_docker_run_command,
    detect_docker,
    execute_docker,
    execute_local_dry_run,
)


def build_request(tmp_path: Path, *, adapter_id: str = LOCAL_DRY_RUN_ADAPTER) -> dict[str, object]:
    run_dir = tmp_path / "run"
    workspace_root = tmp_path / "workspace"
    run_dir.mkdir()
    workspace_root.mkdir()
    return {
        "run_id": "sandbox-smoke",
        "run_dir": str(run_dir),
        "adapter_id": adapter_id,
        "workspace_root": str(workspace_root),
        "sandbox_plan_path": "runs/sandbox-smoke/sandbox-plan.json",
        "commands": [{"id": "command_1", "command": "python -V"}],
        "env_allowlist": {"PYTHONUNBUFFERED": "1"},
        "image": DEFAULT_SANDBOX_IMAGE,
        "timeout_seconds": 30,
    }


def test_build_docker_run_command_includes_isolation_and_env(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    command = build_docker_run_command(
        docker_binary="docker",
        workspace_root=workspace_root,
        image="sandbox:test",
        command="python -V",
        env_allowlist={"PYTHONUNBUFFERED": "1"},
    )

    assert command[:6] == ["docker", "run", "--rm", "--network", "none", "-v"]
    assert f"{workspace_root}:/workspace" in command
    assert "-e" in command
    assert "PYTHONUNBUFFERED=1" in command
    assert command[-3:] == ["sandbox:test", "sh", "-lc", "python -V"][-3:]


def test_local_dry_run_generates_preview_logs_and_artifacts(tmp_path: Path) -> None:
    request = build_request(tmp_path)

    result = execute_local_dry_run(request)

    assert result["adapter_id"] == LOCAL_DRY_RUN_ADAPTER
    assert result["conclusion"] == "skipped"
    assert result["command_summary"]["by_status"] == {"skipped": 1}
    log_path = Path(result["command_results"][0]["log_path"])
    assert log_path.is_file()
    assert "python -V" in log_path.read_text(encoding="utf-8")


def test_execute_docker_returns_blocked_when_unavailable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "scripts.agents.sandbox_adapters.detect_docker",
        lambda: {"available": False, "reason": "docker_binary_not_found", "command": []},
    )

    result = execute_docker(build_request(tmp_path, adapter_id=DOCKER_ADAPTER))

    assert result["adapter_id"] == DOCKER_ADAPTER
    assert result["conclusion"] == "blocked"
    assert result["blocked_reason"] == "docker_binary_not_found"
    assert result["command_results"] == []


def test_execute_docker_captures_stdout_stderr_and_exit_code(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "scripts.agents.sandbox_adapters.detect_docker",
        lambda: {"available": True, "binary": "docker", "version": "27.0.0"},
    )

    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["docker"],
            returncode=0,
            stdout="pytest ok\n",
            stderr="",
        )

    monkeypatch.setattr("scripts.agents.sandbox_adapters.subprocess.run", fake_run)

    result = execute_docker(build_request(tmp_path, adapter_id=DOCKER_ADAPTER))

    command_result = result["command_results"][0]
    assert result["conclusion"] == "passed"
    assert command_result["status"] == "passed"
    assert command_result["exit_code"] == 0
    assert command_result["stdout"] == "pytest ok\n"
    assert Path(command_result["log_path"]).is_file()


def test_execute_docker_timeout_returns_blocked_command(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "scripts.agents.sandbox_adapters.detect_docker",
        lambda: {"available": True, "binary": "docker", "version": "27.0.0"},
    )

    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd=["docker"], timeout=30, output="partial", stderr="timeout")

    monkeypatch.setattr("scripts.agents.sandbox_adapters.subprocess.run", fake_run)

    result = execute_docker(build_request(tmp_path, adapter_id=DOCKER_ADAPTER))

    command_result = result["command_results"][0]
    assert result["conclusion"] == "blocked"
    assert command_result["status"] == "blocked"
    assert command_result["timed_out"] is True
    assert "timed out" in command_result["stderr"]


def test_real_docker_adapter_smoke_if_image_available(tmp_path: Path) -> None:
    docker_info = detect_docker()
    if not docker_info.get("available"):
        pytest.skip("docker not available")

    inspect = subprocess.run(
        [docker_info["binary"], "image", "inspect", DEFAULT_SANDBOX_IMAGE],
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if inspect.returncode != 0:
        pytest.skip(f"sandbox image not available locally: {DEFAULT_SANDBOX_IMAGE}")

    request = build_request(tmp_path, adapter_id=DOCKER_ADAPTER)
    result = execute_docker(request)

    assert result["adapter_id"] == DOCKER_ADAPTER
    assert result["conclusion"] == "passed"
    assert result["command_results"][0]["exit_code"] == 0
