#!/usr/bin/env python3
"""Sandbox adapter execution for swarm verification runs."""

from __future__ import annotations

import json
import shutil
import subprocess
import time

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.config import ROOT


LOCAL_DRY_RUN_ADAPTER = "local_dry_run"
DOCKER_ADAPTER = "docker"
GITHUB_ACTIONS_ADAPTER = "github_actions"
DEFAULT_SANDBOX_IMAGE = "djgurda-swarm-test:latest"
DEFAULT_GITHUB_ACTIONS_WORKFLOW = "swarm-sandbox.yml"
DEFAULT_GITHUB_ACTIONS_POLL_INTERVAL_SECONDS = 10.0
DEFAULT_GITHUB_ACTIONS_TIMEOUT_SECONDS = 900.0

SUPPORTED_SANDBOX_ADAPTERS = {
    LOCAL_DRY_RUN_ADAPTER,
    DOCKER_ADAPTER,
    GITHUB_ACTIONS_ADAPTER,
}


def write_json(path: Path, payload: Any) -> None:
    """Writes a JSON file."""
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def normalize_rel_path(value: str) -> str:
    """Normalizes a repository-relative path."""
    return value.strip().replace("\\", "/").lstrip("./")


def normalize_adapter_id(value: str | None) -> str:
    """Normalizes a sandbox adapter identifier."""
    return str(value or "").strip().casefold()


def resolve_sandbox_adapter(
    *,
    requested_adapter_id: str | None = None,
    verification_profile: dict[str, Any] | None = None,
) -> str:
    """Resolves the sandbox adapter from an explicit override or profile policy."""
    requested = normalize_adapter_id(requested_adapter_id)
    if requested:
        if requested not in SUPPORTED_SANDBOX_ADAPTERS:
            raise ValueError(f"Unsupported sandbox adapter: {requested}")
        return requested

    sandbox_required_for = []
    if verification_profile is not None:
        sandbox_required_for = list(verification_profile.get("sandbox_required_for", []))
    if sandbox_required_for:
        return DOCKER_ADAPTER
    return LOCAL_DRY_RUN_ADAPTER


def ensure_logs_dir(run_dir: Path) -> Path:
    """Ensures the sandbox logs directory exists."""
    logs_dir = run_dir / "sandbox-logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def write_run_artifact(path: Path, payload: Any) -> None:
    """Writes a JSON artifact inside the run bundle."""
    write_json(path, payload)


def display_path(path: Path) -> str:
    """Formats a path for artifact output, preferring repository-relative paths when possible."""
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def build_github_actions_config(request: dict[str, Any]) -> dict[str, Any]:
    """Normalizes GitHub Actions adapter configuration from a sandbox request."""
    workflow_name = str(
        request.get("workflow_name")
        or request.get("workflow")
        or DEFAULT_GITHUB_ACTIONS_WORKFLOW
    ).strip()
    repository = str(request.get("repository") or request.get("repo") or "").strip()
    ref = str(request.get("ref") or request.get("branch") or "main").strip()
    poll_interval_seconds = float(
        request.get("poll_interval_seconds", DEFAULT_GITHUB_ACTIONS_POLL_INTERVAL_SECONDS),
    )
    timeout_seconds = float(request.get("timeout_seconds", DEFAULT_GITHUB_ACTIONS_TIMEOUT_SECONDS))
    artifact_download_path = str(request.get("artifact_download_path") or "").strip()

    if not workflow_name:
        raise ValueError("GitHub Actions adapter requires workflow_name")
    if not repository:
        raise ValueError("GitHub Actions adapter requires repository")

    return {
        "workflow_name": workflow_name,
        "repository": repository,
        "ref": ref or "main",
        "poll_interval_seconds": max(poll_interval_seconds, 0.0),
        "timeout_seconds": max(timeout_seconds, 0.0),
        "artifact_download_path": artifact_download_path,
    }


def build_github_actions_dispatch_inputs(
    request: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, str]:
    """Builds workflow dispatch inputs for the GitHub Actions adapter."""
    return {
        "run_id": str(request.get("run_id", "")),
        "adapter_id": GITHUB_ACTIONS_ADAPTER,
        "workspace_root": str(request.get("workspace_root", "")),
        "sandbox_plan_path": str(request.get("sandbox_plan_path", "")),
        "commands_json": json.dumps(request.get("commands", []), ensure_ascii=False),
        "env_allowlist_json": json.dumps(request.get("env_allowlist", {}), ensure_ascii=False),
        "image": str(request.get("image", DEFAULT_SANDBOX_IMAGE)),
        "requested_timeout_seconds": str(request.get("timeout_seconds", "")),
        "poll_interval_seconds": str(config["poll_interval_seconds"]),
        "artifact_download_path": config["artifact_download_path"],
    }


def run_gh_api(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    """Runs a gh api command."""
    gh_bin = shutil.which("gh")
    if not gh_bin:
        return subprocess.CompletedProcess(
            args=["gh", *arguments],
            returncode=127,
            stdout="",
            stderr="gh binary not found",
        )

    return subprocess.run(
        [gh_bin, *arguments],
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def parse_gh_json(output: str) -> dict[str, Any]:
    """Parses a JSON payload returned by gh api."""
    payload = output.strip()
    if not payload:
        return {}
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("Expected gh api JSON object response")
    return data


def build_github_actions_dispatch_artifact(
    request: dict[str, Any],
    config: dict[str, Any],
    dispatch_inputs: dict[str, str],
) -> dict[str, Any]:
    """Builds a dispatch artifact for the GitHub Actions adapter."""
    return {
        "version": 1,
        "adapter_id": GITHUB_ACTIONS_ADAPTER,
        "workflow_name": config["workflow_name"],
        "repository": config["repository"],
        "ref": config["ref"],
        "poll_interval_seconds": config["poll_interval_seconds"],
        "timeout_seconds": config["timeout_seconds"],
        "artifact_download_path": config["artifact_download_path"],
        "request": {
            "run_id": request.get("run_id", ""),
            "sandbox_plan_path": request.get("sandbox_plan_path", ""),
            "command_count": len(request.get("commands", [])),
            "workspace_root": request.get("workspace_root", ""),
        },
        "dispatch_inputs": dispatch_inputs,
    }


def select_github_actions_run(
    payload: dict[str, Any],
    *,
    repository: str,
    workflow_name: str,
    ref: str,
) -> dict[str, Any] | None:
    """Selects the newest workflow run from a gh api payload."""
    runs = payload.get("workflow_runs", [])
    if not isinstance(runs, list) or not runs:
        return None

    for run in runs:
        if not isinstance(run, dict):
            continue
        if str(run.get("head_branch", "")).strip() != ref:
            continue
        if str(run.get("path", "")).strip() and workflow_name not in str(run.get("path", "")):
            continue
        run["repository"] = repository
        run["workflow_name"] = workflow_name
        return run

    return None


def map_github_actions_conclusion(workflow_run: dict[str, Any] | None) -> tuple[str, str]:
    """Maps a GitHub Actions workflow run to adapter conclusion and block reason."""
    if workflow_run is None:
        return "blocked", "github_actions_workflow_run_not_found"

    status = str(workflow_run.get("status", "")).strip().casefold()
    conclusion = str(workflow_run.get("conclusion", "")).strip().casefold()
    if status != "completed":
        return "blocked", "github_actions_workflow_run_incomplete"
    if conclusion in {"success", "neutral", "skipped"}:
        return "passed", ""
    if conclusion in {"timed_out", "action_required"}:
        return "blocked", f"github_actions_workflow_{conclusion}"
    if conclusion:
        return "failed", f"github_actions_workflow_{conclusion}"
    return "blocked", "github_actions_workflow_missing_conclusion"


def build_github_actions_command_results(
    request: dict[str, Any],
    *,
    workflow_run: dict[str, Any] | None,
    log_path: Path,
    status: str,
    stderr: str = "",
) -> list[dict[str, Any]]:
    """Builds command results for the GitHub Actions adapter."""
    command_results: list[dict[str, Any]] = []
    workflow_run_id = "" if workflow_run is None else str(workflow_run.get("id", ""))
    workflow_run_url = "" if workflow_run is None else str(workflow_run.get("html_url", workflow_run.get("url", "")))

    for command_payload in request.get("commands", []):
        command_results.append(
            {
                "id": command_payload["id"],
                "command": command_payload["command"],
                "status": status,
                "exit_code": 0 if status == "passed" else (1 if status == "failed" else None),
                "stdout": "",
                "stderr": stderr,
                "log_path": str(log_path),
                "github_actions_run_id": workflow_run_id,
                "github_actions_run_url": workflow_run_url,
                "github_actions_status": "" if workflow_run is None else workflow_run.get("status", ""),
                "github_actions_conclusion": "" if workflow_run is None else workflow_run.get("conclusion", ""),
            }
        )

    return command_results


def detect_docker() -> dict[str, Any]:
    """Detects whether Docker is available locally."""
    docker_bin = shutil.which("docker")
    if not docker_bin:
        return {
            "available": False,
            "reason": "docker_binary_not_found",
            "command": [],
        }

    probe = subprocess.run(
        [docker_bin, "version", "--format", "{{.Server.Version}}"],
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if probe.returncode != 0:
        return {
            "available": False,
            "reason": "docker_version_probe_failed",
            "command": [docker_bin, "version", "--format", "{{.Server.Version}}"],
            "stderr": probe.stderr.strip(),
            "stdout": probe.stdout.strip(),
        }

    return {
        "available": True,
        "binary": docker_bin,
        "version": probe.stdout.strip(),
    }


def build_docker_run_command(
    *,
    docker_binary: str,
    workspace_root: Path,
    image: str,
    command: str,
    env_allowlist: dict[str, str] | None = None,
) -> list[str]:
    """Builds a docker run command for a single verification command."""
    docker_command = [
        docker_binary,
        "run",
        "--rm",
        "--network",
        "none",
        "-v",
        f"{workspace_root}:/workspace",
        "-w",
        "/workspace",
    ]
    for key, value in (env_allowlist or {}).items():
        docker_command.extend(["-e", f"{key}={value}"])
    docker_command.extend([image, "sh", "-lc", command])
    return docker_command


def summarize_command_results(command_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Builds an aggregate command summary."""
    by_status: dict[str, int] = {}
    for result in command_results:
        status = result.get("status", "unknown")
        by_status[status] = by_status.get(status, 0) + 1
    return {
        "total_commands": len(command_results),
        "by_status": by_status,
    }


def derive_conclusion(command_results: list[dict[str, Any]], *, blocked_reason: str = "") -> str:
    """Derives a sandbox conclusion from command-level results."""
    if blocked_reason:
        return "blocked"
    statuses = {item.get("status") for item in command_results}
    if not statuses:
        return "skipped"
    if "failed" in statuses:
        return "failed"
    if "blocked" in statuses:
        return "blocked"
    if statuses == {"skipped"}:
        return "skipped"
    if "passed" in statuses and "skipped" in statuses:
        return "partial"
    if statuses == {"passed"}:
        return "passed"
    return "partial"


def execute_local_dry_run(request: dict[str, Any]) -> dict[str, Any]:
    """Builds a non-executing sandbox preview."""
    logs_dir = ensure_logs_dir(Path(request["run_dir"]))
    command_results: list[dict[str, Any]] = []

    for command_payload in request.get("commands", []):
        log_path = logs_dir / f"{command_payload['id']}.log"
        preview_text = (
            f"[local_dry_run] command_id={command_payload['id']}\n"
            f"command={command_payload['command']}\n"
        )
        log_path.write_text(preview_text, encoding="utf-8")
        command_results.append(
            {
                "id": command_payload["id"],
                "command": command_payload["command"],
                "status": "skipped",
                "exit_code": None,
                "stdout": "",
                "stderr": "",
                "log_path": str(log_path),
            }
        )

    return {
        "adapter_id": LOCAL_DRY_RUN_ADAPTER,
        "environment": LOCAL_DRY_RUN_ADAPTER,
        "sandbox_ref": f"local:{request['run_id']}",
        "conclusion": derive_conclusion(command_results),
        "summary": "Sandbox preview generated without executing commands.",
        "blocked_reason": "",
        "command_results": command_results,
        "command_summary": summarize_command_results(command_results),
        "artifacts": [
            {
                "type": "sandbox_plan",
                "path": request.get("sandbox_plan_path", ""),
            }
        ],
    }


def execute_docker(request: dict[str, Any]) -> dict[str, Any]:
    """Executes verification commands inside Docker."""
    docker_info = detect_docker()
    if not docker_info.get("available", False):
        return {
            "adapter_id": DOCKER_ADAPTER,
            "environment": DOCKER_ADAPTER,
            "sandbox_ref": "",
            "conclusion": "blocked",
            "summary": "Docker adapter is unavailable.",
            "blocked_reason": docker_info.get("reason", "docker_unavailable"),
            "command_results": [],
            "command_summary": summarize_command_results([]),
            "artifacts": [],
        }

    logs_dir = ensure_logs_dir(Path(request["run_dir"]))
    command_results: list[dict[str, Any]] = []
    workspace_root = Path(request["workspace_root"])
    image = request.get("image", DEFAULT_SANDBOX_IMAGE)

    for command_payload in request.get("commands", []):
        docker_command = build_docker_run_command(
            docker_binary=docker_info["binary"],
            workspace_root=workspace_root,
            image=image,
            command=command_payload["command"],
            env_allowlist=request.get("env_allowlist", {}),
        )
        timeout_seconds = int(request.get("timeout_seconds", 900))
        timed_out = False
        try:
            process = subprocess.run(
                docker_command,
                text=True,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=timeout_seconds,
            )
            status = "passed" if process.returncode == 0 else "failed"
            stdout = process.stdout
            stderr = process.stderr
            exit_code = process.returncode
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            status = "blocked"
            stdout = exc.stdout or ""
            stderr = (exc.stderr or "") + f"\ncommand timed out after {timeout_seconds}s"
            exit_code = None
        log_path = logs_dir / f"{command_payload['id']}.log"
        log_path.write_text(
            (
                f"$ {' '.join(docker_command)}\n\n"
                f"stdout:\n{stdout}\n"
                f"stderr:\n{stderr}\n"
            ),
            encoding="utf-8",
        )
        command_results.append(
            {
                "id": command_payload["id"],
                "command": command_payload["command"],
                "status": status,
                "exit_code": exit_code,
                "stdout": stdout,
                "stderr": stderr,
                "log_path": str(log_path),
                "docker_command": docker_command,
                "timed_out": timed_out,
            }
        )

    conclusion = derive_conclusion(command_results)
    summary = "Docker sandbox execution completed."
    if conclusion == "failed":
        summary = "Docker sandbox execution recorded command failures."

    return {
        "adapter_id": DOCKER_ADAPTER,
        "environment": DOCKER_ADAPTER,
        "sandbox_ref": f"docker:{request['run_id']}:{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "conclusion": conclusion,
        "summary": summary,
        "blocked_reason": "",
        "command_results": command_results,
        "command_summary": summarize_command_results(command_results),
        "artifacts": [],
    }


def execute_github_actions(request: dict[str, Any]) -> dict[str, Any]:
    """Dispatches and polls a GitHub Actions workflow for sandbox execution."""
    run_dir = Path(request["run_dir"])
    logs_dir = ensure_logs_dir(run_dir)

    try:
        config = build_github_actions_config(request)
    except ValueError as exc:
        return {
            "adapter_id": GITHUB_ACTIONS_ADAPTER,
            "environment": GITHUB_ACTIONS_ADAPTER,
            "sandbox_ref": "",
            "conclusion": "blocked",
            "summary": "GitHub Actions adapter configuration is incomplete.",
            "blocked_reason": str(exc),
            "command_results": [],
            "command_summary": summarize_command_results([]),
            "artifacts": [],
        }

    dispatch_inputs = build_github_actions_dispatch_inputs(request, config)
    dispatch_artifact = build_github_actions_dispatch_artifact(request, config, dispatch_inputs)
    dispatch_artifact_path = logs_dir / "github-actions-dispatch.json"
    write_json(dispatch_artifact_path, dispatch_artifact)

    dispatch_command = [
        "api",
        "--method",
        "POST",
        "-H",
        "Accept: application/vnd.github+json",
        f"repos/{config['repository']}/actions/workflows/{config['workflow_name']}/dispatches",
        "-f",
        f"ref={config['ref']}",
    ]
    for key, value in dispatch_inputs.items():
        dispatch_command.extend(["-f", f"inputs[{key}]={value}"])

    dispatch_result = run_gh_api(dispatch_command)
    dispatch_log_path = logs_dir / "github-actions-dispatch.log"
    dispatch_log_path.write_text(
        "\n".join(
            [
                "$ gh " + " ".join(dispatch_command),
                f"returncode: {dispatch_result.returncode}",
                f"stdout: {dispatch_result.stdout.strip()}",
                f"stderr: {dispatch_result.stderr.strip()}",
            ],
        )
        + "\n",
        encoding="utf-8",
    )

    if dispatch_result.returncode != 0:
        return {
            "adapter_id": GITHUB_ACTIONS_ADAPTER,
            "environment": GITHUB_ACTIONS_ADAPTER,
            "sandbox_ref": "",
            "conclusion": "blocked",
            "summary": "GitHub Actions workflow dispatch failed.",
            "blocked_reason": dispatch_result.stderr.strip() or "github_actions_dispatch_failed",
            "command_results": [],
            "command_summary": summarize_command_results([]),
            "artifacts": [
                {"type": "github_actions_dispatch", "path": display_path(dispatch_artifact_path)},
                {"type": "github_actions_dispatch_log", "path": display_path(dispatch_log_path)},
            ],
            "workflow_dispatch": dispatch_artifact,
        }

    poll_artifact_path = logs_dir / "github-actions-poll.json"
    poll_log_path = logs_dir / "github-actions-poll.log"
    deadline = time.monotonic() + config["timeout_seconds"]
    poll_attempts = 0
    latest_payload: dict[str, Any] = {}
    workflow_run: dict[str, Any] | None = None
    timed_out = False

    while True:
        poll_attempts += 1
        poll_result = run_gh_api(
            [
                "api",
                "-H",
                "Accept: application/vnd.github+json",
                f"repos/{config['repository']}/actions/workflows/{config['workflow_name']}/runs?event=workflow_dispatch&branch={config['ref']}&per_page=10",
            ],
        )
        if poll_result.returncode != 0:
            poll_log_path.write_text(
                "\n".join(
                    [
                        f"attempt: {poll_attempts}",
                        f"returncode: {poll_result.returncode}",
                        f"stdout: {poll_result.stdout.strip()}",
                        f"stderr: {poll_result.stderr.strip()}",
                    ],
                )
                + "\n",
                encoding="utf-8",
            )
            return {
                "adapter_id": GITHUB_ACTIONS_ADAPTER,
                "environment": GITHUB_ACTIONS_ADAPTER,
                "sandbox_ref": "",
                "conclusion": "blocked",
                "summary": "GitHub Actions workflow polling failed.",
                "blocked_reason": poll_result.stderr.strip() or "github_actions_poll_failed",
                "command_results": [],
                "command_summary": summarize_command_results([]),
                "artifacts": [
                    {"type": "github_actions_dispatch", "path": display_path(dispatch_artifact_path)},
                    {"type": "github_actions_dispatch_log", "path": display_path(dispatch_log_path)},
                    {"type": "github_actions_poll_log", "path": display_path(poll_log_path)},
                ],
                "workflow_dispatch": dispatch_artifact,
            }

        latest_payload = parse_gh_json(poll_result.stdout)
        write_json(poll_artifact_path, latest_payload)
        workflow_run = select_github_actions_run(
            latest_payload,
            repository=config["repository"],
            workflow_name=config["workflow_name"],
            ref=config["ref"],
        )
        if workflow_run is not None and str(workflow_run.get("status", "")).strip().casefold() == "completed":
            break
        if time.monotonic() >= deadline:
            timed_out = True
            break
        if config["poll_interval_seconds"] > 0:
            time.sleep(config["poll_interval_seconds"])

    if timed_out:
        status = "blocked"
        blocked_reason = "github_actions_poll_timeout"
        summary = "GitHub Actions workflow polling timed out."
    else:
        status, blocked_reason = map_github_actions_conclusion(workflow_run)
        summary = "GitHub Actions workflow completed."
        if status == "failed":
            summary = "GitHub Actions workflow recorded failures."
        elif status == "blocked":
            summary = "GitHub Actions workflow did not reach a terminal success state."

    command_results = build_github_actions_command_results(
        request,
        workflow_run=workflow_run,
        log_path=poll_log_path,
        status=status,
        stderr=blocked_reason if status == "blocked" else "",
    )
    poll_log_path.write_text(
        "\n".join(
            [
                f"attempts: {poll_attempts}",
                f"workflow_run_id: {'' if workflow_run is None else workflow_run.get('id', '')}",
                f"workflow_status: {'' if workflow_run is None else workflow_run.get('status', '')}",
                f"workflow_conclusion: {'' if workflow_run is None else workflow_run.get('conclusion', '')}",
                f"blocked_reason: {blocked_reason}",
            ],
        )
        + "\n",
        encoding="utf-8",
    )

    artifacts = [
        {"type": "github_actions_dispatch", "path": display_path(dispatch_artifact_path)},
        {"type": "github_actions_dispatch_log", "path": display_path(dispatch_log_path)},
        {"type": "github_actions_poll_log", "path": display_path(poll_log_path)},
        {"type": "github_actions_poll_artifact", "path": display_path(poll_artifact_path)},
    ]
    if config["artifact_download_path"]:
        artifacts.append(
            {
                "type": "github_actions_artifact_download_path",
                "path": config["artifact_download_path"],
            }
        )

    sandbox_ref = ""
    if workflow_run is not None:
        sandbox_ref = f"github-actions:{config['repository']}:{config['workflow_name']}:{workflow_run.get('id', '')}"

    return {
        "adapter_id": GITHUB_ACTIONS_ADAPTER,
        "environment": GITHUB_ACTIONS_ADAPTER,
        "sandbox_ref": sandbox_ref,
        "conclusion": status,
        "summary": summary,
        "blocked_reason": blocked_reason if status == "blocked" else "",
        "command_results": command_results,
        "command_summary": summarize_command_results(command_results),
        "artifacts": artifacts,
        "workflow_dispatch": dispatch_artifact,
        "workflow_run": workflow_run or {},
        "workflow_poll": latest_payload,
        "poll_attempts": poll_attempts,
    }


def execute_sandbox_request(request: dict[str, Any]) -> dict[str, Any]:
    """Executes a sandbox request against the selected adapter."""
    adapter_id = resolve_sandbox_adapter(
        requested_adapter_id=request.get("adapter_id"),
        verification_profile=request.get("verification_profile"),
    )
    if adapter_id == LOCAL_DRY_RUN_ADAPTER:
        return execute_local_dry_run(request)
    if adapter_id == DOCKER_ADAPTER:
        return execute_docker(request)
    if adapter_id == GITHUB_ACTIONS_ADAPTER:
        return execute_github_actions(request)
    raise ValueError(f"Unsupported sandbox adapter: {adapter_id}")
