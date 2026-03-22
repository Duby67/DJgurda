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
    build_github_actions_config,
    build_github_actions_dispatch_inputs,
    build_sandbox_image_build_command,
    build_workspace_transfer_payload,
    execute_github_actions,
    detect_docker,
    execute_docker,
    execute_local_dry_run,
    parse_github_repository,
    resolve_sandbox_adapter,
    select_github_actions_run,
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


def test_build_sandbox_image_build_command_points_to_test_dockerfile() -> None:
    command = build_sandbox_image_build_command(docker_binary="docker")

    assert command[:3] == ["docker", "build", "-f"]
    assert "test" in command[3]
    assert "swarm-test" in command[3]
    assert "-t" in command
    assert DEFAULT_SANDBOX_IMAGE in command
    assert command[-1]


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


def test_execute_docker_blocks_when_image_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "scripts.agents.sandbox_adapters.detect_docker",
        lambda: {"available": True, "binary": "docker", "version": "27.0.0"},
    )
    monkeypatch.setattr(
        "scripts.agents.sandbox_adapters.detect_docker_image",
        lambda **_kwargs: {
            "available": False,
            "reason": "docker_image_not_found",
            "build_command": ["docker", "build", "-f", "test/docker/swarm-test/Dockerfile", "-t", DEFAULT_SANDBOX_IMAGE, "."],
        },
    )

    result = execute_docker(build_request(tmp_path, adapter_id=DOCKER_ADAPTER))

    assert result["conclusion"] == "blocked"
    assert result["blocked_reason"] == "docker_image_not_found"
    assert result["image_build_command"][0:2] == ["docker", "build"]
    assert any(item["type"] == "docker_image_build_hint" for item in result["artifacts"])


def test_execute_docker_captures_stdout_stderr_and_exit_code(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "scripts.agents.sandbox_adapters.detect_docker",
        lambda: {"available": True, "binary": "docker", "version": "27.0.0"},
    )
    monkeypatch.setattr(
        "scripts.agents.sandbox_adapters.detect_docker_image",
        lambda **_kwargs: {"available": True, "image": DEFAULT_SANDBOX_IMAGE},
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
    monkeypatch.setattr(
        "scripts.agents.sandbox_adapters.detect_docker_image",
        lambda **_kwargs: {"available": True, "image": DEFAULT_SANDBOX_IMAGE},
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
    assert result["blocked_reason"] == "gh_binary_not_found"


def test_parse_github_repository_supports_https_and_ssh() -> None:
    assert parse_github_repository("https://github.com/example/repo.git") == "example/repo"
    assert parse_github_repository("git@github.com:example/repo.git") == "example/repo"
    assert parse_github_repository("ssh://git@github.com/example/repo.git") == "example/repo"
    assert parse_github_repository("https://gitlab.com/example/repo.git") == ""


def test_build_github_actions_config_infers_repository_and_defaults_artifact_download_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("scripts.agents.sandbox_adapters.infer_github_repository", lambda: "djgurda/example")

    config = build_github_actions_config(
        build_request(
            tmp_path,
            adapter_id=GITHUB_ACTIONS_ADAPTER,
            workflow_name="swarm-sandbox.yml",
        ),
    )

    assert config["repository"] == "djgurda/example"
    assert config["workflow_name"] == "swarm-sandbox.yml"
    assert config["correlation_id"].startswith("sandbox-smoke-")
    assert config["artifact_name"].startswith("swarm-sandbox-")
    assert config["artifact_download_path"].endswith("github-actions-download")


def test_build_workspace_transfer_payload_inlines_existing_diff(tmp_path: Path) -> None:
    diff_path = tmp_path / "workspace-diff.patch"
    diff_path.write_text("diff --git a/file.txt b/file.txt\n", encoding="utf-8")

    payload = build_workspace_transfer_payload({"workspace_diff_path": str(diff_path)})

    assert payload["mode"] == "inline_git_patch"
    assert payload["present"] is True
    assert payload["path"].endswith("workspace-diff.patch")
    assert payload["sha256"]
    assert payload["gzip_base64"]
    assert payload["blocked_reason"] == ""


def test_build_github_actions_dispatch_inputs_include_workspace_transfer_fields(tmp_path: Path) -> None:
    diff_path = tmp_path / "workspace-diff.patch"
    diff_path.write_text("diff --git a/file.txt b/file.txt\n", encoding="utf-8")
    request = build_request(
        tmp_path,
        adapter_id=GITHUB_ACTIONS_ADAPTER,
        repository="djgurda/example",
        workflow_name="swarm-sandbox.yml",
        workspace_diff_path=str(diff_path),
    )
    config = build_github_actions_config(request)
    transfer = build_workspace_transfer_payload(request)

    inputs = build_github_actions_dispatch_inputs(request, config, transfer)

    assert inputs["workspace_transfer_mode"] == "inline_git_patch"
    assert inputs["workspace_diff_sha256"] == transfer["sha256"]
    assert inputs["workspace_diff_gzip_base64"] == transfer["gzip_base64"]


def test_select_github_actions_run_uses_correlation_id() -> None:
    payload = {
        "workflow_runs": [
            {
                "id": 10,
                "status": "completed",
                "conclusion": "success",
                "head_branch": "main",
                "path": ".github/workflows/swarm-sandbox.yml",
                "display_title": "Swarm Sandbox / run-1 / wrong-correlation",
            },
            {
                "id": 11,
                "status": "completed",
                "conclusion": "success",
                "head_branch": "main",
                "path": ".github/workflows/swarm-sandbox.yml",
                "display_title": "Swarm Sandbox / run-1 / expected-correlation",
            },
        ],
    }

    selected = select_github_actions_run(
        payload,
        repository="djgurda/example",
        workflow_name="swarm-sandbox.yml",
        ref="main",
        correlation_id="expected-correlation",
    )

    assert selected is not None
    assert selected["id"] == 11


def test_execute_github_actions_blocks_when_auth_is_not_configured(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("scripts.agents.sandbox_adapters.shutil.which", lambda _name: "gh")
    monkeypatch.setattr(
        "scripts.agents.sandbox_adapters.run_gh_command",
        lambda _args: subprocess.CompletedProcess(args=["gh"], returncode=1, stdout="", stderr="not logged in"),
    )

    result = execute_github_actions(
        build_request(
            tmp_path,
            adapter_id=GITHUB_ACTIONS_ADAPTER,
            repository="djgurda/example",
        ),
    )

    assert result["conclusion"] == "blocked"
    assert result["blocked_reason"] == "gh_auth_not_configured"


def test_execute_github_actions_blocks_when_workflow_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("scripts.agents.sandbox_adapters.shutil.which", lambda _name: "gh")

    def fake_run_gh_command(args: list[str]) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["auth", "status"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="ok", stderr="")
        raise AssertionError(f"Unexpected gh command: {args}")

    def fake_run_gh_api(args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=args, returncode=1, stdout="", stderr="404 Not Found")

    monkeypatch.setattr("scripts.agents.sandbox_adapters.run_gh_command", fake_run_gh_command)
    monkeypatch.setattr("scripts.agents.sandbox_adapters.run_gh_api", fake_run_gh_api)

    result = execute_github_actions(
        build_request(
            tmp_path,
            adapter_id=GITHUB_ACTIONS_ADAPTER,
            repository="djgurda/example",
            workflow_name="swarm-sandbox.yml",
        ),
    )

    assert result["conclusion"] == "blocked"
    assert result["blocked_reason"] == "github_actions_workflow_not_found"


def test_execute_github_actions_dispatches_and_polls_to_completion(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("scripts.agents.sandbox_adapters.shutil.which", lambda _name: "gh")

    def fake_run_gh_command(args: list[str]) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["auth", "status"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="ok", stderr="")
        if args[:3] == ["run", "download", "123"]:
            target_dir = Path(args[args.index("--dir") + 1])
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / "logs").mkdir(exist_ok=True)
            (target_dir / "logs" / "command_1.log").write_text("pytest ok\n", encoding="utf-8")
            (target_dir / "sandbox-metadata.json").write_text(
                json.dumps(
                    {
                        "run_id": "sandbox-smoke",
                        "correlation_id": "expected-correlation",
                        "adapter_id": GITHUB_ACTIONS_ADAPTER,
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            (target_dir / "sandbox-result.json").write_text(
                json.dumps(
                    {
                        "conclusion": "passed",
                        "summary": "Remote sandbox completed.",
                        "command_results": [
                            {
                                "id": "command_1",
                                "command": "python -V",
                                "status": "passed",
                                "exit_code": 0,
                                "stdout": "pytest ok\n",
                                "stderr": "",
                                "log_path": "logs/command_1.log",
                            }
                        ],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="downloaded", stderr="")
        raise AssertionError(f"Unexpected gh command: {args}")

    def fake_run_gh_api(args: list[str]) -> subprocess.CompletedProcess[str]:
        joined = " ".join(args)
        if args[-1] == "repos/djgurda/example/actions/workflows/swarm-sandbox.yml":
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=json.dumps({"id": 1}), stderr="")
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
                                "id": 122,
                                "status": "completed",
                                "conclusion": "success",
                                "html_url": "https://github.test/runs/122",
                                "head_branch": "main",
                                "path": ".github/workflows/swarm-sandbox.yml",
                                "display_title": "Swarm Sandbox / sandbox-smoke / wrong-correlation",
                            },
                            {
                                "id": 123,
                                "status": "completed",
                                "conclusion": "success",
                                "html_url": "https://github.test/runs/123",
                                "head_branch": "main",
                                "path": ".github/workflows/swarm-sandbox.yml",
                                "display_title": "Swarm Sandbox / sandbox-smoke / expected-correlation",
                            },
                        ]
                    },
                    ensure_ascii=False,
                ),
                stderr="",
            )
        raise AssertionError(f"Unexpected gh api command: {args}")

    monkeypatch.setattr("scripts.agents.sandbox_adapters.run_gh_command", fake_run_gh_command)
    monkeypatch.setattr("scripts.agents.sandbox_adapters.run_gh_api", fake_run_gh_api)

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
            correlation_id="expected-correlation",
        ),
    )

    assert result["adapter_id"] == GITHUB_ACTIONS_ADAPTER
    assert result["conclusion"] == "passed"
    assert result["blocked_reason"] == ""
    assert result["command_summary"]["by_status"] == {"passed": 1}
    assert result["workflow_run"]["id"] == 123
    assert result["summary"] == "Remote sandbox completed."
    assert result["command_results"][0]["log_path"] == "runs/sandbox-smoke/artifacts/logs/command_1.log"
    assert any(item["type"] == "github_actions_dispatch" for item in result["artifacts"])
    assert any(item["type"] == "github_actions_download_dir" for item in result["artifacts"])
    assert result["artifact_downloaded"] is True
    assert result["downloaded_result"]["metadata"]["correlation_id"] == "expected-correlation"


def test_execute_github_actions_pins_polling_to_resolved_run_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("scripts.agents.sandbox_adapters.shutil.which", lambda _name: "gh")
    seen_api_calls: list[str] = []

    def fake_run_gh_command(args: list[str]) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["auth", "status"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="ok", stderr="")
        if args[:3] == ["run", "download", "123"]:
            target_dir = Path(args[args.index("--dir") + 1])
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / "sandbox-metadata.json").write_text(
                json.dumps(
                    {
                        "run_id": "sandbox-smoke",
                        "correlation_id": "expected-correlation",
                        "adapter_id": GITHUB_ACTIONS_ADAPTER,
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            (target_dir / "workspace-transfer.json").write_text(
                json.dumps(
                    {
                        "mode": "inline_git_patch",
                        "applied": True,
                        "sha256": "abc123",
                        "path": "workspace-diff.patch",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            (target_dir / "sandbox-result.json").write_text(
                json.dumps(
                    {
                        "conclusion": "passed",
                        "summary": "Remote sandbox completed.",
                        "workspace_transfer": {
                            "mode": "inline_git_patch",
                            "applied": True,
                            "sha256": "abc123",
                            "path": "workspace-diff.patch",
                        },
                        "command_results": [],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="downloaded", stderr="")
        raise AssertionError(f"Unexpected gh command: {args}")

    def fake_transfer(_request: dict[str, object]) -> dict[str, object]:
        return {
            "mode": "inline_git_patch",
            "present": True,
            "path": "runs/sandbox-smoke/workspace-diff.patch",
            "sha256": "abc123",
            "gzip_base64": "ZmFrZQ==",
            "encoded_length": 8,
            "blocked_reason": "",
        }

    def fake_run_gh_api(args: list[str]) -> subprocess.CompletedProcess[str]:
        joined = " ".join(args)
        seen_api_calls.append(joined)
        if args[-1] == "repos/djgurda/example/actions/workflows/swarm-sandbox.yml":
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=json.dumps({"id": 1}), stderr="")
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
                                "status": "in_progress",
                                "conclusion": "",
                                "html_url": "https://github.test/runs/123",
                                "head_branch": "main",
                                "path": ".github/workflows/swarm-sandbox.yml",
                                "display_title": "Swarm Sandbox / sandbox-smoke / expected-correlation",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                stderr="",
            )
        if args[-1] == "repos/djgurda/example/actions/runs/123":
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=json.dumps(
                    {
                        "id": 123,
                        "status": "completed",
                        "conclusion": "success",
                        "html_url": "https://github.test/runs/123",
                        "head_branch": "main",
                        "path": ".github/workflows/swarm-sandbox.yml",
                        "display_title": "Swarm Sandbox / sandbox-smoke / expected-correlation",
                    },
                    ensure_ascii=False,
                ),
                stderr="",
            )
        raise AssertionError(f"Unexpected gh api command: {args}")

    monkeypatch.setattr("scripts.agents.sandbox_adapters.run_gh_command", fake_run_gh_command)
    monkeypatch.setattr("scripts.agents.sandbox_adapters.run_gh_api", fake_run_gh_api)
    monkeypatch.setattr("scripts.agents.sandbox_adapters.build_workspace_transfer_payload", fake_transfer)

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
            correlation_id="expected-correlation",
            workspace_diff_path="runs/sandbox-smoke/workspace-diff.patch",
        ),
    )

    assert result["conclusion"] == "passed"
    assert result["resolved_workflow_run_id"] == "123"
    assert any("runs?event=workflow_dispatch" in call for call in seen_api_calls)
    assert any(call.endswith("repos/djgurda/example/actions/runs/123") for call in seen_api_calls)


def test_execute_github_actions_blocks_when_downloaded_metadata_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("scripts.agents.sandbox_adapters.shutil.which", lambda _name: "gh")

    def fake_run_gh_command(args: list[str]) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["auth", "status"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="ok", stderr="")
        if args[:3] == ["run", "download", "123"]:
            target_dir = Path(args[args.index("--dir") + 1])
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / "sandbox-result.json").write_text(
                json.dumps(
                    {
                        "conclusion": "passed",
                        "summary": "Remote sandbox completed.",
                        "command_results": [],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="downloaded", stderr="")
        raise AssertionError(f"Unexpected gh command: {args}")

    def fake_run_gh_api(args: list[str]) -> subprocess.CompletedProcess[str]:
        joined = " ".join(args)
        if args[-1] == "repos/djgurda/example/actions/workflows/swarm-sandbox.yml":
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=json.dumps({"id": 1}), stderr="")
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
                                "display_title": "Swarm Sandbox / sandbox-smoke / expected-correlation",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                stderr="",
            )
        raise AssertionError(f"Unexpected gh api command: {args}")

    monkeypatch.setattr("scripts.agents.sandbox_adapters.run_gh_command", fake_run_gh_command)
    monkeypatch.setattr("scripts.agents.sandbox_adapters.run_gh_api", fake_run_gh_api)

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
            correlation_id="expected-correlation",
        ),
    )

    assert result["conclusion"] == "blocked"
    assert result["blocked_reason"] == "github_actions_metadata_missing"


def test_execute_github_actions_blocks_on_poll_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("scripts.agents.sandbox_adapters.shutil.which", lambda _name: "gh")

    def fake_run_gh_command(args: list[str]) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["auth", "status"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="ok", stderr="")
        raise AssertionError(f"Unexpected gh command: {args}")

    def fake_run_gh_api(args: list[str]) -> subprocess.CompletedProcess[str]:
        joined = " ".join(args)
        if args[-1] == "repos/djgurda/example/actions/workflows/swarm-sandbox.yml":
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=json.dumps({"id": 1}), stderr="")
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
                                "display_title": "Swarm Sandbox / sandbox-smoke / expected-correlation",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                stderr="",
            )
        raise AssertionError(f"Unexpected gh api command: {args}")

    monkeypatch.setattr("scripts.agents.sandbox_adapters.run_gh_command", fake_run_gh_command)
    monkeypatch.setattr("scripts.agents.sandbox_adapters.run_gh_api", fake_run_gh_api)

    result = execute_github_actions(
        build_request(
            tmp_path,
            adapter_id=GITHUB_ACTIONS_ADAPTER,
            repository="djgurda/example",
            workflow_name="swarm-sandbox.yml",
            ref="main",
            poll_interval_seconds=0,
            timeout_seconds=0,
            correlation_id="expected-correlation",
        ),
    )

    assert result["adapter_id"] == GITHUB_ACTIONS_ADAPTER
    assert result["conclusion"] == "blocked"
    assert result["blocked_reason"] == "github_actions_poll_timeout"


def test_execute_github_actions_blocks_when_artifact_download_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("scripts.agents.sandbox_adapters.shutil.which", lambda _name: "gh")

    def fake_run_gh_command(args: list[str]) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["auth", "status"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="ok", stderr="")
        if args[:3] == ["run", "download", "123"]:
            return subprocess.CompletedProcess(args=args, returncode=1, stdout="", stderr="artifact missing")
        raise AssertionError(f"Unexpected gh command: {args}")

    def fake_run_gh_api(args: list[str]) -> subprocess.CompletedProcess[str]:
        joined = " ".join(args)
        if args[-1] == "repos/djgurda/example/actions/workflows/swarm-sandbox.yml":
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=json.dumps({"id": 1}), stderr="")
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
                                "display_title": "Swarm Sandbox / sandbox-smoke / expected-correlation",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                stderr="",
            )
        raise AssertionError(f"Unexpected gh api command: {args}")

    monkeypatch.setattr("scripts.agents.sandbox_adapters.run_gh_command", fake_run_gh_command)
    monkeypatch.setattr("scripts.agents.sandbox_adapters.run_gh_api", fake_run_gh_api)

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
            correlation_id="expected-correlation",
        ),
    )

    assert result["conclusion"] == "blocked"
    assert result["blocked_reason"] == "artifact missing"


def test_swarm_sandbox_workflow_exists() -> None:
    workflow_path = Path(".github/workflows/swarm-sandbox.yml")
    assert workflow_path.is_file()
    payload = workflow_path.read_text(encoding="utf-8")
    assert "workflow_dispatch" in payload
    assert "correlation_id" in payload
    assert "artifact_name" in payload
    assert "workspace_diff_gzip_base64" in payload
    assert "workspace-transfer.json" in payload
    assert "git apply --binary --allow-empty" in payload
    assert "actions/upload-artifact@v4" in payload


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
        build_command = build_sandbox_image_build_command(
            docker_binary=docker_info["binary"],
            image=DEFAULT_SANDBOX_IMAGE,
        )
        build = subprocess.run(
            build_command,
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        assert build.returncode == 0, build.stderr

    request = build_request(tmp_path, adapter_id=DOCKER_ADAPTER)
    result = execute_docker(request)

    assert result["adapter_id"] == DOCKER_ADAPTER
    assert result["conclusion"] == "passed"
    assert result["command_results"][0]["exit_code"] == 0
