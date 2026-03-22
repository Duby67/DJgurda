#!/usr/bin/env python3
"""Sandbox adapter execution for swarm verification runs."""

from __future__ import annotations

import json
import shutil
import subprocess

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LOCAL_DRY_RUN_ADAPTER = "local_dry_run"
DOCKER_ADAPTER = "docker"
GITHUB_ACTIONS_ADAPTER = "github_actions"
DEFAULT_SANDBOX_IMAGE = "djgurda-swarm-test:latest"


def write_json(path: Path, payload: Any) -> None:
    """Writes a JSON file."""
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def normalize_rel_path(value: str) -> str:
    """Normalizes a repository-relative path."""
    return value.strip().replace("\\", "/").lstrip("./")


def ensure_logs_dir(run_dir: Path) -> Path:
    """Ensures the sandbox logs directory exists."""
    logs_dir = run_dir / "sandbox-logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


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


def execute_sandbox_request(request: dict[str, Any]) -> dict[str, Any]:
    """Executes a sandbox request against the selected adapter."""
    adapter_id = request.get("adapter_id", LOCAL_DRY_RUN_ADAPTER)
    if adapter_id == LOCAL_DRY_RUN_ADAPTER:
        return execute_local_dry_run(request)
    if adapter_id == DOCKER_ADAPTER:
        return execute_docker(request)
    if adapter_id == GITHUB_ACTIONS_ADAPTER:
        return {
            "adapter_id": GITHUB_ACTIONS_ADAPTER,
            "environment": GITHUB_ACTIONS_ADAPTER,
            "sandbox_ref": "",
            "conclusion": "blocked",
            "summary": "GitHub Actions adapter is reserved for a later phase.",
            "blocked_reason": "github_actions_adapter_not_implemented",
            "command_results": [],
            "command_summary": summarize_command_results([]),
            "artifacts": [],
        }
    raise ValueError(f"Unsupported sandbox adapter: {adapter_id}")
