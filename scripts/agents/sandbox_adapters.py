#!/usr/bin/env python3
"""Sandbox adapter execution for swarm verification runs."""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
import re
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
DEFAULT_GITHUB_ACTIONS_ARTIFACT_PREFIX = "swarm-sandbox"
DEFAULT_GITHUB_ACTIONS_POLL_INTERVAL_SECONDS = 10.0
DEFAULT_GITHUB_ACTIONS_TIMEOUT_SECONDS = 900.0
MAX_GITHUB_ACTIONS_INLINE_WORKSPACE_DIFF_CHARS = 50000

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


def sanitize_identifier(value: str) -> str:
    """Normalizes an identifier for workflow correlation and artifact naming."""
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip()).strip("._-")
    return normalized or "swarm-run"


def parse_github_repository(remote_url: str) -> str:
    """Extracts owner/repo from a git remote URL when it points to GitHub."""
    candidate = str(remote_url or "").strip()
    if not candidate:
        return ""

    github_prefixes = (
        "https://github.com/",
        "http://github.com/",
        "ssh://git@github.com/",
        "git@github.com:",
    )
    for prefix in github_prefixes:
        if candidate.startswith(prefix):
            remainder = candidate[len(prefix) :]
            if remainder.endswith(".git"):
                remainder = remainder[:-4]
            return remainder.strip("/")
    return ""


def infer_github_repository() -> str:
    """Infers owner/repo from the local git remote when possible."""
    probe = subprocess.run(
        ["git", "config", "--get", "remote.origin.url"],
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        cwd=ROOT,
    )
    if probe.returncode != 0:
        return ""
    return parse_github_repository(probe.stdout.strip())


def infer_git_ref() -> str:
    """Infers the current git ref when possible."""
    probe = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        cwd=ROOT,
    )
    if probe.returncode != 0:
        return ""
    ref = probe.stdout.strip()
    if not ref or ref == "HEAD":
        return ""
    return ref


def run_gh_command(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    """Runs an arbitrary gh command."""
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
    repository = str(request.get("repository") or request.get("repo") or "").strip() or infer_github_repository()
    ref = str(request.get("ref") or request.get("branch") or "").strip() or infer_git_ref() or "main"
    poll_interval_seconds = float(
        request.get("poll_interval_seconds", DEFAULT_GITHUB_ACTIONS_POLL_INTERVAL_SECONDS),
    )
    timeout_seconds = float(request.get("timeout_seconds", DEFAULT_GITHUB_ACTIONS_TIMEOUT_SECONDS))
    artifact_download_path = str(request.get("artifact_download_path") or "").strip()
    correlation_id = sanitize_identifier(
        str(request.get("correlation_id") or f"{request.get('run_id', 'swarm-run')}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"),
    )
    artifact_name = sanitize_identifier(
        str(request.get("artifact_name") or f"{DEFAULT_GITHUB_ACTIONS_ARTIFACT_PREFIX}-{correlation_id}"),
    )
    run_dir = Path(str(request.get("run_dir", "") or ROOT))
    if not artifact_download_path:
        artifact_download_path = str(run_dir / "github-actions-download")

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
        "correlation_id": correlation_id,
        "artifact_name": artifact_name,
        "expected_run_name": f"Swarm Sandbox / {request.get('run_id', '')} / {correlation_id}",
        "dispatch_requested_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def resolve_artifact_path(path_value: str) -> Path:
    """Resolves an artifact path relative to the repository root when needed."""
    candidate = Path(str(path_value or "").strip())
    if candidate.is_absolute():
        return candidate
    return ROOT / normalize_rel_path(str(candidate))


def build_workspace_transfer_payload(request: dict[str, Any]) -> dict[str, Any]:
    """Builds an inline workspace transfer payload for remote sandbox replay."""
    workspace_diff_path = str(request.get("workspace_diff_path", "")).strip()
    if not workspace_diff_path:
        return {
            "mode": "ref_checkout",
            "present": False,
            "path": "",
            "sha256": "",
            "gzip_base64": "",
            "encoded_length": 0,
            "blocked_reason": "",
        }

    diff_path = resolve_artifact_path(workspace_diff_path)
    if not diff_path.is_file():
        return {
            "mode": "inline_git_patch",
            "present": False,
            "path": display_path(diff_path),
            "sha256": "",
            "gzip_base64": "",
            "encoded_length": 0,
            "blocked_reason": "workspace_diff_artifact_missing",
        }

    raw = diff_path.read_bytes()
    sha256 = hashlib.sha256(raw).hexdigest()
    gzip_base64 = base64.b64encode(gzip.compress(raw)).decode("ascii")
    encoded_length = len(gzip_base64)
    blocked_reason = ""
    if encoded_length > MAX_GITHUB_ACTIONS_INLINE_WORKSPACE_DIFF_CHARS:
        blocked_reason = "github_actions_workspace_diff_too_large"

    return {
        "mode": "inline_git_patch",
        "present": True,
        "path": display_path(diff_path),
        "sha256": sha256,
        "gzip_base64": gzip_base64,
        "encoded_length": encoded_length,
        "blocked_reason": blocked_reason,
    }


def build_github_actions_dispatch_inputs(
    request: dict[str, Any],
    config: dict[str, Any],
    workspace_transfer: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Builds workflow dispatch inputs for the GitHub Actions adapter."""
    transfer = workspace_transfer or {}
    return {
        "run_id": str(request.get("run_id", "")),
        "correlation_id": config["correlation_id"],
        "artifact_name": config["artifact_name"],
        "adapter_id": GITHUB_ACTIONS_ADAPTER,
        "workspace_root": str(request.get("workspace_root", "")),
        "sandbox_plan_path": str(request.get("sandbox_plan_path", "")),
        "commands_json": json.dumps(request.get("commands", []), ensure_ascii=False),
        "env_allowlist_json": json.dumps(request.get("env_allowlist", {}), ensure_ascii=False),
        "image": str(request.get("image", DEFAULT_SANDBOX_IMAGE)),
        "requested_timeout_seconds": str(request.get("timeout_seconds", "")),
        "poll_interval_seconds": str(config["poll_interval_seconds"]),
        "artifact_download_path": config["artifact_download_path"],
        "workspace_transfer_mode": str(transfer.get("mode", "ref_checkout")),
        "workspace_diff_sha256": str(transfer.get("sha256", "")),
        "workspace_diff_gzip_base64": str(transfer.get("gzip_base64", "")),
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
    workspace_transfer: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Builds a dispatch artifact for the GitHub Actions adapter."""
    transfer = workspace_transfer or {}
    return {
        "version": 1,
        "adapter_id": GITHUB_ACTIONS_ADAPTER,
        "workflow_name": config["workflow_name"],
        "repository": config["repository"],
        "ref": config["ref"],
        "poll_interval_seconds": config["poll_interval_seconds"],
        "timeout_seconds": config["timeout_seconds"],
        "artifact_download_path": config["artifact_download_path"],
        "correlation_id": config["correlation_id"],
        "artifact_name": config["artifact_name"],
        "expected_run_name": config["expected_run_name"],
        "workspace_transfer": {
            "mode": transfer.get("mode", "ref_checkout"),
            "present": bool(transfer.get("present", False)),
            "path": transfer.get("path", ""),
            "sha256": transfer.get("sha256", ""),
            "encoded_length": transfer.get("encoded_length", 0),
        },
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
    correlation_id: str,
    expected_run_name: str = "",
    dispatched_after_utc: str = "",
) -> dict[str, Any] | None:
    """Selects the newest workflow run from a gh api payload."""
    runs = payload.get("workflow_runs", [])
    if not isinstance(runs, list) or not runs:
        return None

    dispatched_after = None
    if dispatched_after_utc:
        try:
            dispatched_after = datetime.fromisoformat(
                dispatched_after_utc.replace("Z", "+00:00"),
            )
        except ValueError:
            dispatched_after = None

    candidates: list[dict[str, Any]] = []
    for run in runs:
        if not isinstance(run, dict):
            continue
        if str(run.get("head_branch", "")).strip() != ref:
            continue
        if str(run.get("path", "")).strip() and workflow_name not in str(run.get("path", "")):
            continue
        created_at = str(run.get("created_at", "")).strip()
        if created_at and dispatched_after is not None:
            try:
                created_at_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except ValueError:
                created_at_dt = None
            if created_at_dt is not None and created_at_dt < dispatched_after:
                continue
        title_candidates = [
            str(run.get("display_title", "")).strip(),
            str(run.get("name", "")).strip(),
        ]
        if expected_run_name and expected_run_name not in title_candidates:
            continue
        if correlation_id and not any(correlation_id in title for title in title_candidates if title):
            continue
        run["repository"] = repository
        run["workflow_name"] = workflow_name
        candidates.append(run)

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: (
            str(item.get("created_at", "")),
            int(item.get("run_number", 0) or 0),
            int(item.get("id", 0) or 0),
        ),
        reverse=True,
    )
    return candidates[0]


def resolve_download_root(path_value: str) -> Path:
    """Resolves a local artifact download directory."""
    path = Path(path_value)
    if path.is_absolute():
        return path
    return ROOT / normalize_rel_path(path_value)


def collect_downloaded_files(root: Path) -> list[str]:
    """Collects downloaded artifact files as display paths."""
    if not root.exists():
        return []
    return [
        display_path(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]


def load_downloaded_json(root: Path, filename: str) -> dict[str, Any]:
    """Loads a downloaded JSON artifact by file name when present."""
    if not root.exists():
        return {}
    for candidate in sorted(root.rglob(filename)):
        payload = json.loads(candidate.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    return {}


def remap_downloaded_command_results(
    command_results: list[dict[str, Any]],
    *,
    download_root: Path,
) -> list[dict[str, Any]]:
    """Rewrites artifact-local log paths to local downloaded paths."""
    rewritten: list[dict[str, Any]] = []
    for item in command_results:
        payload = dict(item)
        log_path = str(payload.get("log_path", "")).strip()
        if log_path:
            candidate = download_root / normalize_rel_path(log_path)
            if candidate.is_file():
                payload["log_path"] = display_path(candidate)
        rewritten.append(payload)
    return rewritten


def download_github_actions_artifact(
    *,
    repository: str,
    workflow_run_id: str,
    artifact_name: str,
    artifact_download_path: str,
    logs_dir: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    """Downloads and parses the sandbox artifact from GitHub Actions."""
    download_root = resolve_download_root(artifact_download_path)
    if download_root.exists():
        shutil.rmtree(download_root)
    download_root.mkdir(parents=True, exist_ok=True)

    download_command = [
        "run",
        "download",
        workflow_run_id,
        "--repo",
        repository,
        "--name",
        artifact_name,
        "--dir",
        str(download_root),
    ]
    download_result = run_gh_command(download_command)
    download_log_path = logs_dir / "github-actions-download.log"
    download_log_path.write_text(
        "\n".join(
            [
                "$ gh " + " ".join(download_command),
                f"returncode: {download_result.returncode}",
                f"stdout: {download_result.stdout.strip()}",
                f"stderr: {download_result.stderr.strip()}",
            ],
        )
        + "\n",
        encoding="utf-8",
    )

    artifacts = [
        {"type": "github_actions_download_log", "path": display_path(download_log_path)},
    ]
    if download_result.returncode != 0:
        return {}, artifacts, download_result.stderr.strip() or "github_actions_artifact_download_failed"

    downloaded_files = collect_downloaded_files(download_root)
    artifacts.append({"type": "github_actions_download_dir", "path": display_path(download_root)})
    for file_path in downloaded_files:
        artifacts.append({"type": "github_actions_downloaded_file", "path": file_path})

    remote_result = load_downloaded_json(download_root, "sandbox-result.json")
    if not remote_result:
        return {}, artifacts, "github_actions_artifact_payload_missing"

    remote_metadata = load_downloaded_json(download_root, "sandbox-metadata.json")
    if remote_metadata:
        remote_result["metadata"] = remote_metadata

    workspace_transfer = load_downloaded_json(download_root, "workspace-transfer.json")
    if workspace_transfer:
        remote_result["workspace_transfer"] = workspace_transfer

    remote_result["command_results"] = remap_downloaded_command_results(
        list(remote_result.get("command_results", [])),
        download_root=download_root,
    )
    return remote_result, artifacts, ""


def detect_github_actions_environment(
    *,
    repository: str,
    workflow_name: str,
) -> dict[str, Any]:
    """Checks gh availability, auth and workflow presence for the adapter."""
    gh_bin = shutil.which("gh")
    if not gh_bin:
        return {
            "available": False,
            "reason": "gh_binary_not_found",
        }

    auth_result = run_gh_command(["auth", "status", "--hostname", "github.com"])
    if auth_result.returncode != 0:
        return {
            "available": False,
            "reason": "gh_auth_not_configured",
            "stderr": auth_result.stderr.strip(),
            "stdout": auth_result.stdout.strip(),
        }

    workflow_result = run_gh_api(
        [
            "api",
            "-H",
            "Accept: application/vnd.github+json",
            f"repos/{repository}/actions/workflows/{workflow_name}",
        ],
    )
    if workflow_result.returncode != 0:
        stderr = workflow_result.stderr.strip()
        reason = "github_actions_workflow_lookup_failed"
        if "404" in stderr or "Not Found" in stderr:
            reason = "github_actions_workflow_not_found"
        elif "401" in stderr or "403" in stderr:
            reason = "gh_auth_insufficient_for_actions"
        return {
            "available": False,
            "reason": reason,
            "stderr": stderr,
            "stdout": workflow_result.stdout.strip(),
        }

    return {
        "available": True,
        "binary": gh_bin,
    }


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


def build_sandbox_image_build_command(
    *,
    docker_binary: str,
    image: str = DEFAULT_SANDBOX_IMAGE,
) -> list[str]:
    """Builds the canonical docker build command for the swarm test image."""
    return [
        docker_binary,
        "build",
        "-f",
        str(ROOT / "test" / "docker" / "swarm-test" / "Dockerfile"),
        "-t",
        image,
        str(ROOT),
    ]


def detect_docker_image(
    *,
    docker_binary: str,
    image: str,
) -> dict[str, Any]:
    """Checks whether the requested Docker image exists locally."""
    probe = subprocess.run(
        [docker_binary, "image", "inspect", image],
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if probe.returncode != 0:
        return {
            "available": False,
            "reason": "docker_image_not_found",
            "image": image,
            "stdout": probe.stdout.strip(),
            "stderr": probe.stderr.strip(),
            "build_command": build_sandbox_image_build_command(
                docker_binary=docker_binary,
                image=image,
            ),
        }
    return {
        "available": True,
        "image": image,
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
    image_info = detect_docker_image(
        docker_binary=docker_info["binary"],
        image=str(image),
    )
    if not image_info.get("available", False):
        build_command = list(image_info.get("build_command", []))
        build_hint_path = logs_dir / "docker-image-build-hint.log"
        build_hint_path.write_text(
            (
                f"missing_image={image}\n"
                f"build_command={' '.join(build_command)}\n"
            ),
            encoding="utf-8",
        )
        return {
            "adapter_id": DOCKER_ADAPTER,
            "environment": DOCKER_ADAPTER,
            "sandbox_ref": "",
            "conclusion": "blocked",
            "summary": "Docker sandbox image is unavailable locally.",
            "blocked_reason": image_info.get("reason", "docker_image_not_found"),
            "command_results": [],
            "command_summary": summarize_command_results([]),
            "artifacts": [
                {
                    "type": "docker_image_build_hint",
                    "path": display_path(build_hint_path),
                },
            ],
            "image": image,
            "image_build_command": build_command,
        }

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

    environment = detect_github_actions_environment(
        repository=config["repository"],
        workflow_name=config["workflow_name"],
    )
    if not environment.get("available", False):
        return {
            "adapter_id": GITHUB_ACTIONS_ADAPTER,
            "environment": GITHUB_ACTIONS_ADAPTER,
            "sandbox_ref": "",
            "conclusion": "blocked",
            "summary": "GitHub Actions adapter preflight failed.",
            "blocked_reason": environment.get("reason", "github_actions_environment_unavailable"),
            "command_results": [],
            "command_summary": summarize_command_results([]),
            "artifacts": [],
            "workflow_dispatch": {
                "version": 1,
                "adapter_id": GITHUB_ACTIONS_ADAPTER,
                "repository": config["repository"],
                "workflow_name": config["workflow_name"],
                "correlation_id": config["correlation_id"],
                "artifact_name": config["artifact_name"],
            },
            "preflight": environment,
        }

    workspace_transfer = build_workspace_transfer_payload(request)
    if workspace_transfer.get("blocked_reason"):
        return {
            "adapter_id": GITHUB_ACTIONS_ADAPTER,
            "environment": GITHUB_ACTIONS_ADAPTER,
            "sandbox_ref": "",
            "conclusion": "blocked",
            "summary": "GitHub Actions workspace transfer payload is unavailable.",
            "blocked_reason": str(workspace_transfer.get("blocked_reason", "github_actions_workspace_transfer_blocked")),
            "command_results": [],
            "command_summary": summarize_command_results([]),
            "artifacts": [],
            "workspace_transfer": {
                "mode": workspace_transfer.get("mode", "ref_checkout"),
                "path": workspace_transfer.get("path", ""),
                "sha256": workspace_transfer.get("sha256", ""),
                "encoded_length": workspace_transfer.get("encoded_length", 0),
            },
            "preflight": environment,
        }

    dispatch_inputs = build_github_actions_dispatch_inputs(request, config, workspace_transfer)
    dispatch_artifact = build_github_actions_dispatch_artifact(request, config, dispatch_inputs, workspace_transfer)
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
            correlation_id=config["correlation_id"],
            expected_run_name=config["expected_run_name"],
            dispatched_after_utc=config["dispatch_requested_at_utc"],
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

    remote_result: dict[str, Any] = {}
    downloaded_artifacts: list[dict[str, Any]] = []
    artifact_download_error = ""
    workflow_status = "" if workflow_run is None else str(workflow_run.get("status", "")).strip().casefold()
    if workflow_run is not None and workflow_status == "completed" and str(workflow_run.get("id", "")).strip():
        remote_result, downloaded_artifacts, download_error = download_github_actions_artifact(
            repository=config["repository"],
            workflow_run_id=str(workflow_run.get("id", "")),
            artifact_name=config["artifact_name"],
            artifact_download_path=config["artifact_download_path"],
            logs_dir=logs_dir,
        )
        if download_error:
            status = "blocked"
            blocked_reason = download_error
            artifact_download_error = download_error
        elif remote_result:
            remote_metadata = remote_result.get("metadata", {})
            if remote_metadata and str(remote_metadata.get("correlation_id", "")).strip() != config["correlation_id"]:
                status = "blocked"
                blocked_reason = "github_actions_correlation_mismatch"
                artifact_download_error = blocked_reason
            elif not remote_metadata:
                status = "blocked"
                blocked_reason = "github_actions_metadata_missing"
                artifact_download_error = blocked_reason
            if workspace_transfer.get("present"):
                remote_transfer = remote_result.get("workspace_transfer", {})
                if not remote_transfer:
                    status = "blocked"
                    blocked_reason = "github_actions_workspace_transfer_missing"
                    artifact_download_error = blocked_reason
                elif not bool(remote_transfer.get("applied", False)):
                    status = "blocked"
                    blocked_reason = "github_actions_workspace_transfer_not_applied"
                    artifact_download_error = blocked_reason
                elif str(remote_transfer.get("sha256", "")).strip() != str(workspace_transfer.get("sha256", "")).strip():
                    status = "blocked"
                    blocked_reason = "github_actions_workspace_transfer_mismatch"
                    artifact_download_error = blocked_reason

    command_results = build_github_actions_command_results(
        request,
        workflow_run=workflow_run,
        log_path=poll_log_path,
        status=status,
        stderr=blocked_reason if status == "blocked" else "",
    )
    if remote_result.get("command_results"):
        command_results = list(remote_result.get("command_results", []))
    poll_log_path.write_text(
        "\n".join(
            [
                f"attempts: {poll_attempts}",
                f"workflow_run_id: {'' if workflow_run is None else workflow_run.get('id', '')}",
                f"workflow_status: {'' if workflow_run is None else workflow_run.get('status', '')}",
                f"workflow_conclusion: {'' if workflow_run is None else workflow_run.get('conclusion', '')}",
                f"correlation_id: {config['correlation_id']}",
                f"artifact_name: {config['artifact_name']}",
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
        {
            "type": "github_actions_artifact_download_path",
            "path": display_path(resolve_download_root(config["artifact_download_path"])),
        },
    ]
    artifacts.extend(downloaded_artifacts)

    sandbox_ref = ""
    if workflow_run is not None:
        sandbox_ref = f"github-actions:{config['repository']}:{config['workflow_name']}:{workflow_run.get('id', '')}"

    return {
        "adapter_id": GITHUB_ACTIONS_ADAPTER,
        "environment": GITHUB_ACTIONS_ADAPTER,
        "sandbox_ref": sandbox_ref,
        "conclusion": status,
        "summary": str(remote_result.get("summary", "")).strip() or summary,
        "blocked_reason": blocked_reason if status == "blocked" else "",
        "command_results": command_results,
        "command_summary": summarize_command_results(command_results),
        "artifacts": artifacts,
        "workflow_dispatch": dispatch_artifact,
        "workflow_run": workflow_run or {},
        "workflow_poll": latest_payload,
        "poll_attempts": poll_attempts,
        "preflight": environment,
        "workspace_transfer": {
            "mode": workspace_transfer.get("mode", "ref_checkout"),
            "present": bool(workspace_transfer.get("present", False)),
            "path": workspace_transfer.get("path", ""),
            "sha256": workspace_transfer.get("sha256", ""),
            "encoded_length": workspace_transfer.get("encoded_length", 0),
        },
        "downloaded_result": remote_result,
        "artifact_downloaded": bool(remote_result),
        "artifact_download_path": display_path(resolve_download_root(config["artifact_download_path"])),
        "artifact_download_error": artifact_download_error,
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
