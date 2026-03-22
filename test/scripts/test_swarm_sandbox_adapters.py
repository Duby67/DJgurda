from __future__ import annotations

import json
import subprocess

from pathlib import Path

import pytest

from scripts.agents.sandbox_adapters import (
    DEFAULT_SANDBOX_IMAGE,
    DOCKER_ADAPTER,
    GITHUB_ACTIONS_ADAPTER,
    LOCAL_DRY_RUN_ADAPTER,
    build_docker_run_command,
    execute_github_actions,
    detect_docker,
    execute_docker,
    execute_local_dry_run,
    resolve_sandbox_adapter,
)


def build_request(
    tmp_path: Path,
    *,
    adapter_id: str = LOCAL_DRY_RUN_ADAPTER,
    **extra_fields: object,
) -> dict[str, object]:
    run_dir = tmp_path / "run"
    workspace_root = tmp_path / "workspace"
    run_dir.mkdir()
    workspace_root.mkdir()
    payload: dict[str, object] = {
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
    payload.update(extra_fields)
    return payload


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


def test_resolve_sandbox_adapter_prefers_override_and_profile_policy() -> None:
    assert resolve_sandbox_adapter(
        requested_adapter_id=DOCKER_ADAPTER,
        verification_profile={"sandbox_required_for": []},
    ) == DOCKER_ADAPTER
    assert resolve_sandbox_adapter(
        requested_adapter_id=None,
        verification_profile={"sandbox_required_for": ["isolated execution"]},
    ) == DOCKER_ADAPTER
    assert resolve_sandbox_adapter(
        requested_adapter_id=None,
        verification_profile={"sandbox_required_for": []},
    ) == LOCAL_DRY_RUN_ADAPTER


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


def test_execute_github_actions_blocks_when_gh_cli_is_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("scripts.agents.sandbox_adapters.shutil.which", lambda _name: None)

    result = execute_github_actions(
        build_request(
            tmp_path,
            adapter_id=GITHUB_ACTIONS_ADAPTER,
            repository="djgurda/example",
            workflow_name="swarm-sandbox.yml",
            ref="main",
            poll_interval_seconds=0,
            timeout_seconds=1,
        ),
    )

    assert result["adapter_id"] == GITHUB_ACTIONS_ADAPTER
    assert result["conclusion"] == "blocked"
    assert "gh binary not found" in result["blocked_reason"]


def test_execute_github_actions_dispatches_and_polls_to_completion(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("scripts.agents.sandbox_adapters.shutil.which", lambda _name: "gh")

    def fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        joined = " ".join(args)
        if "dispatches" in joined:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
        if "runs?event=workflow_dispatch" in joined:
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=json.dumps(
                    {
                        "workflow_runs": [
                            {
                                "id": 123,
                                "status": "completed",
                                "conclusion": "success",
                                "html_url": "https://github.test/runs/123",
                                "head_branch": "main",
                                "path": ".github/workflows/swarm-sandbox.yml",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                stderr="",
            )
        raise AssertionError(f"Unexpected command: {joined}")

    monkeypatch.setattr("scripts.agents.sandbox_adapters.subprocess.run", fake_run)

    result = execute_github_actions(
        build_request(
            tmp_path,
            adapter_id=GITHUB_ACTIONS_ADAPTER,
            repository="djgurda/example",
            workflow_name="swarm-sandbox.yml",
            ref="main",
            poll_interval_seconds=0,
            timeout_seconds=5,
            artifact_download_path="runs/sandbox-smoke/artifacts",
        ),
    )

    assert result["adapter_id"] == GITHUB_ACTIONS_ADAPTER
    assert result["conclusion"] == "passed"
    assert result["blocked_reason"] == ""
    assert result["command_summary"]["by_status"] == {"passed": 1}
    assert result["workflow_run"]["id"] == 123
    assert any(item["type"] == "github_actions_dispatch" for item in result["artifacts"])


def test_execute_github_actions_blocks_on_poll_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("scripts.agents.sandbox_adapters.shutil.which", lambda _name: "gh")

    def fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        joined = " ".join(args)
        if "dispatches" in joined:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
        if "runs?event=workflow_dispatch" in joined:
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=json.dumps(
                    {
                        "workflow_runs": [
                            {
                                "id": 124,
                                "status": "queued",
                                "conclusion": "",
                                "html_url": "https://github.test/runs/124",
                                "head_branch": "main",
                                "path": ".github/workflows/swarm-sandbox.yml",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                stderr="",
            )
        raise AssertionError(f"Unexpected command: {joined}")

    monkeypatch.setattr("scripts.agents.sandbox_adapters.subprocess.run", fake_run)

    result = execute_github_actions(
        build_request(
            tmp_path,
            adapter_id=GITHUB_ACTIONS_ADAPTER,
            repository="djgurda/example",
            workflow_name="swarm-sandbox.yml",
            ref="main",
            poll_interval_seconds=0,
            timeout_seconds=0,
        ),
    )

    assert result["adapter_id"] == GITHUB_ACTIONS_ADAPTER
    assert result["conclusion"] == "blocked"
    assert result["blocked_reason"] == "github_actions_poll_timeout"


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
