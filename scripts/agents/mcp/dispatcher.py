#!/usr/bin/env python3
"""Sequential dispatcher and CLI-first UX helpers for external swarm jobs."""

from __future__ import annotations

import difflib
import json
import subprocess
import time

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.agents.executor import (
    build_external_work_item,
    claim_job,
    complete_external_job,
    fail_external_job,
    load_jobs,
    mark_job_dispatched,
    next_claimable_external_job,
    start_or_continue_run,
)
from scripts.agents.workspace import resolve_workspace_root
from scripts.config import ROOT


JOB_QUEUE_MARKDOWN_NAME = "job-queue.md"
DIFF_PREVIEW_MARKDOWN_NAME = "diff-preview.md"
DISPATCHER_STATE_NAME = "dispatcher-state.json"
SUPERVISOR_STATE_NAME = "supervisor-state.json"
TERMINAL_DISPATCH_STATUSES = {"completed", "failed", "blocked"}
DEFAULT_LOOP_MAX_CYCLES = 8
DEFAULT_SUPERVISOR_MAX_ITERATIONS = 32
AUTONOMOUS_TERMINAL_RUN_STATUSES = {
    "instruction_conflict",
    "context_insufficient",
    "context_loaded_pending_run_checks_approval",
    "context_loaded_awaiting_manual_review",
    "sandbox_failed",
    "sandbox_blocked",
    "review_failed",
    "review_blocked",
    "external_job_failed",
    "awaiting_commit_approval",
    "awaiting_push_approval",
    "approval_rejected",
    "closed",
}


def load_json(path: Path) -> dict[str, Any]:
    """Reads a JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    """Writes a JSON file."""
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def now_utc() -> str:
    """Returns an ISO8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def normalize_rel_path(value: str) -> str:
    """Normalizes a repository-relative path."""
    return value.strip().replace("\\", "/").lstrip("./")


def rel_to_root(path: Path) -> str:
    """Converts an absolute path to a repo-relative POSIX path."""
    return str(path.relative_to(ROOT)).replace("\\", "/")


def load_optional_json(path: Path) -> dict[str, Any] | None:
    """Reads an optional JSON file."""
    if not path.is_file():
        return None
    return load_json(path)


def load_run_summary(run_dir: Path) -> dict[str, Any]:
    """Loads run-summary.json."""
    return load_json(run_dir / "run-summary.json")


def write_run_summary(run_dir: Path, payload: dict[str, Any]) -> None:
    """Writes run-summary.json."""
    write_json(run_dir / "run-summary.json", payload)


def jobs_index_path(run_dir: Path) -> Path:
    """Returns the jobs index path."""
    return run_dir / "jobs" / "index.json"


def dispatcher_state_path(run_dir: Path) -> Path:
    """Returns dispatcher-state.json path."""
    return run_dir / DISPATCHER_STATE_NAME


def job_queue_markdown_path(run_dir: Path) -> Path:
    """Returns job-queue.md path."""
    return run_dir / JOB_QUEUE_MARKDOWN_NAME


def diff_preview_path(run_dir: Path) -> Path:
    """Returns diff-preview.md path."""
    return run_dir / DIFF_PREVIEW_MARKDOWN_NAME


def supervisor_state_path(run_dir: Path) -> Path:
    """Returns supervisor-state.json path."""
    return run_dir / SUPERVISOR_STATE_NAME


def job_dispatch_path(run_dir: Path, job_id: str) -> Path:
    """Returns a dispatch artifact path for a job."""
    return run_dir / "jobs" / f"{job_id}-dispatch.json"


def job_completion_path(run_dir: Path, job_id: str) -> Path:
    """Returns a completion inbox artifact path for an external job."""
    return run_dir / "jobs" / f"{job_id}-completion.json"


def job_completion_processed_path(run_dir: Path, job_id: str) -> Path:
    """Returns the processed completion artifact path for an external job."""
    return run_dir / "jobs" / f"{job_id}-completion-processed.json"


def find_job(jobs_payload: dict[str, Any], job_id: str) -> dict[str, Any]:
    """Finds a job inside jobs/index.json."""
    for job in jobs_payload.get("jobs", []):
        if job.get("job_id") == job_id:
            return job
    raise KeyError(f"Job '{job_id}' not found")


def persist_jobs_payload(run_dir: Path, jobs_payload: dict[str, Any]) -> None:
    """Writes jobs/index.json and per-job artifacts."""
    jobs_dir = run_dir / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    write_json(jobs_index_path(run_dir), jobs_payload)
    for job in jobs_payload.get("jobs", []):
        write_json(jobs_dir / f"{job['job_id']}.json", job)


def update_run_summary_artifacts(run_dir: Path, artifact_key: str, artifact_path: Path) -> None:
    """Registers a generated artifact in run-summary.json."""
    run_summary = load_run_summary(run_dir)
    artifacts = run_summary.setdefault("artifacts", {})
    artifacts[artifact_key] = rel_to_root(artifact_path)
    run_summary["artifacts"] = artifacts
    write_run_summary(run_dir, run_summary)


def update_dispatcher_snapshot(
    run_dir: Path,
    *,
    jobs_payload: dict[str, Any] | None = None,
    current_job_id: str = "",
    runtime_target: str = "",
    dispatch_status: str = "",
) -> dict[str, Any]:
    """Writes dispatcher-state.json and stores a compact dispatcher summary."""
    jobs_payload = jobs_payload or load_jobs(run_dir)
    queue = build_job_queue_payload(run_dir, jobs_payload=jobs_payload)
    current_job = next(
        (item for item in queue["jobs"] if item["job_id"] == current_job_id),
        queue.get("current_external_job"),
    )
    payload = {
        "version": 1,
        "run_id": run_dir.name,
        "recorded_at_utc": now_utc(),
        "runtime_target": runtime_target or (current_job or {}).get("runtime_target", ""),
        "dispatch_status": dispatch_status or (current_job or {}).get("dispatch_status", queue.get("dispatcher_status", "queued")),
        "current_job": current_job,
        "queue": queue,
    }
    write_json(dispatcher_state_path(run_dir), payload)
    update_run_summary_artifacts(run_dir, "dispatcher_state", dispatcher_state_path(run_dir))

    run_summary = load_run_summary(run_dir)
    run_summary["dispatcher"] = {
        "dispatch_status": payload["dispatch_status"],
        "runtime_target": payload["runtime_target"],
        "current_job": current_job,
        "job_counts": queue.get("by_status", {}),
        "by_dispatch_status": queue.get("by_dispatch_status", {}),
    }
    write_run_summary(run_dir, run_summary)
    return payload


def update_supervisor_snapshot(
    run_dir: Path,
    *,
    supervisor_status: str,
    runtime_target: str,
    iterations: int,
    poll_interval_seconds: float,
    runtime_command: list[str] | None = None,
    current_job_id: str = "",
    last_event: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Writes supervisor-state.json and stores a compact supervisor summary."""
    payload = {
        "version": 1,
        "run_id": run_dir.name,
        "recorded_at_utc": now_utc(),
        "status": supervisor_status,
        "runtime_target": runtime_target,
        "runtime_command": list(runtime_command or []),
        "iterations": iterations,
        "poll_interval_seconds": poll_interval_seconds,
        "current_job_id": current_job_id,
        "last_event": last_event or {},
    }
    write_json(supervisor_state_path(run_dir), payload)
    update_run_summary_artifacts(run_dir, "supervisor_state", supervisor_state_path(run_dir))

    run_summary = load_run_summary(run_dir)
    run_summary["supervisor"] = {
        "status": supervisor_status,
        "runtime_target": runtime_target,
        "runtime_command": list(runtime_command or []),
        "iterations": iterations,
        "poll_interval_seconds": poll_interval_seconds,
        "current_job_id": current_job_id,
        "last_event": last_event or {},
    }
    write_run_summary(run_dir, run_summary)
    return payload


def resolve_input_artifacts(run_dir: Path, job: dict[str, Any], run_summary: dict[str, Any]) -> list[dict[str, str]]:
    """Resolves job input artifacts to available repo-relative paths."""
    resolved: list[dict[str, str]] = []
    artifacts = run_summary.get("artifacts", {})

    for item in job.get("input_artifacts", []):
        rel_path = ""
        if item in artifacts:
            rel_path = normalize_rel_path(artifacts[item])
        else:
            candidate = run_dir / item
            if candidate.exists():
                rel_path = rel_to_root(candidate)
        resolved.append(
            {
                "name": item,
                "path": rel_path,
                "available": bool(rel_path and (ROOT / rel_path).exists()),
            }
        )
    return resolved


def completion_contract_for(job: dict[str, Any], *, sandbox_adapter: str) -> dict[str, Any]:
    """Builds a role-specific completion contract."""
    if job.get("role") == "coder":
        return {
            "command": "complete_role_job",
            "preferred_command": "submit_role_result",
            "required_fields": ["summary", "applied_files"],
            "optional_fields": ["applied_by", "allow_empty_diff"],
            "resume_sandbox_adapter": sandbox_adapter,
        }
    if job.get("role") == "reviewer":
        return {
            "command": "complete_role_job",
            "preferred_command": "submit_role_result",
            "required_fields": ["summary", "conclusion", "findings", "risks"],
            "optional_fields": ["reviewed_by"],
            "resume_sandbox_adapter": sandbox_adapter,
        }
    return {
        "command": "complete_role_job",
        "preferred_command": "submit_role_result",
        "required_fields": ["summary"],
        "optional_fields": [],
        "resume_sandbox_adapter": sandbox_adapter,
    }


def ensure_dispatch_record(run_dir: Path, *, job_id: str, runtime_target: str) -> dict[str, Any]:
    """Ensures a claimed/running external job has dispatcher metadata and a work item."""
    jobs_payload = load_jobs(run_dir)
    job = find_job(jobs_payload, job_id)
    dispatch_artifact = job_dispatch_path(run_dir, job_id)
    runtime_ref = str(job.get("runtime_ref", "")).strip() or f"codex://{run_dir.name}/{job_id}"
    dispatched_job = mark_job_dispatched(
        run_dir,
        job_id=job_id,
        runtime_target=runtime_target,
        runtime_ref=runtime_ref,
        dispatched_by="dispatcher",
    )
    work_item = build_external_work_item(run_dir, job_id=job_id)
    work_item["runtime_target"] = runtime_target
    work_item["runtime_ref"] = runtime_ref
    work_item["workspace_root"] = work_item.get("workspace_ref", {}).get("root_path", "")
    work_item["completion_contract"] = completion_contract_for(dispatched_job, sandbox_adapter=str(load_jobs(run_dir).get("sandbox_adapter", "")).strip())
    work_item["completion_inbox"] = rel_to_root(job_completion_path(run_dir, job_id))
    write_json(dispatch_artifact, work_item)
    jobs_payload = load_jobs(run_dir)
    job = find_job(jobs_payload, job_id)
    job["dispatch_artifact"] = rel_to_root(dispatch_artifact)
    persist_jobs_payload(run_dir, jobs_payload)

    update_run_summary_artifacts(run_dir, f"{job_id}_dispatch", dispatch_artifact)
    dispatcher_state = update_dispatcher_snapshot(
        run_dir,
        jobs_payload=jobs_payload,
        current_job_id=job_id,
        runtime_target=runtime_target,
        dispatch_status=job.get("dispatch_status", "dispatched"),
    )
    return {
        "job": job,
        "work_item": work_item,
        "dispatcher": dispatcher_state,
    }


def mark_dispatch_terminal(
    run_dir: Path,
    *,
    job_id: str,
    dispatch_status: str,
    runtime_target: str = "",
) -> dict[str, Any]:
    """Marks a dispatched job as completed/failed/blocked for queue UX."""
    if dispatch_status not in TERMINAL_DISPATCH_STATUSES:
        raise ValueError(f"Unsupported terminal dispatch status: {dispatch_status}")

    jobs_payload = load_jobs(run_dir)
    job = find_job(jobs_payload, job_id)
    job["dispatch_status"] = dispatch_status
    job["runtime_target"] = runtime_target or job.get("runtime_target", "")
    job["dispatched_at_utc"] = job.get("dispatched_at_utc") or now_utc()
    persist_jobs_payload(run_dir, jobs_payload)
    dispatcher_state = update_dispatcher_snapshot(
        run_dir,
        jobs_payload=jobs_payload,
        current_job_id="",
        runtime_target=job.get("runtime_target", ""),
        dispatch_status=dispatch_status,
    )
    return {
        "job": job,
        "dispatcher": dispatcher_state,
    }


def active_external_job(jobs_payload: dict[str, Any]) -> dict[str, Any] | None:
    """Returns the currently active external job if one exists."""
    for job in jobs_payload.get("jobs", []):
        if job.get("backend") == "external_ai" and job.get("status") == "running":
            return job
    return None


def consume_completion_artifact(
    run_dir: Path,
    *,
    job_id: str,
    default_sandbox_adapter: str = "",
) -> dict[str, Any] | None:
    """Consumes a completion inbox artifact and advances orchestration."""
    completion_path = job_completion_path(run_dir, job_id)
    if not completion_path.is_file():
        return None

    payload = load_json(completion_path)
    processed_path = job_completion_processed_path(run_dir, job_id)
    if processed_path.exists():
        processed_path.unlink()
    completion_path.replace(processed_path)
    update_run_summary_artifacts(run_dir, f"{job_id}_completion", processed_path)

    status = str(payload.get("status") or payload.get("action") or "completed").strip().casefold()
    summary = str(payload.get("summary", "")).strip()
    sandbox_adapter = str(payload.get("sandbox_adapter", "")).strip() or default_sandbox_adapter

    if status == "completed":
        result_payload = payload.get("result")
        if not isinstance(result_payload, dict):
            result_payload = {
                key: value
                for key, value in payload.items()
                if key not in {"status", "action", "summary", "sandbox_adapter"}
            }
        result = complete_external_job(
            run_dir,
            job_id=job_id,
            summary=summary,
            result_payload=result_payload,
            sandbox_adapter=sandbox_adapter or None,
        )
        dispatch = mark_dispatch_terminal(run_dir, job_id=job_id, dispatch_status="completed")
        return {
            "job_id": job_id,
            "consumed_artifact": rel_to_root(processed_path),
            "status": "completed",
            "result": result,
            "dispatch": dispatch,
        }

    if status in {"failed", "blocked"}:
        reason = str(payload.get("reason", "")).strip() or status
        result = fail_external_job(
            run_dir,
            job_id=job_id,
            summary=summary or f"External job {job_id} {status}.",
            reason=reason,
        )
        dispatch = mark_dispatch_terminal(run_dir, job_id=job_id, dispatch_status=status)
        return {
            "job_id": job_id,
            "consumed_artifact": rel_to_root(processed_path),
            "status": status,
            "result": result,
            "dispatch": dispatch,
        }

    raise ValueError(f"Unsupported completion artifact status: {status}")


def submit_role_result(
    run_dir: Path,
    *,
    job_id: str,
    payload: dict[str, Any],
    runtime_target: str = "",
    sandbox_adapter: str = "",
    auto_consume: bool = True,
) -> dict[str, Any]:
    """Writes a completion inbox artifact for an external role job."""
    jobs_payload = load_jobs(run_dir)
    job = find_job(jobs_payload, job_id)
    if job.get("backend") != "external_ai":
        raise ValueError(f"Job '{job_id}' is not an external AI role")
    if job.get("status") != "running":
        raise ValueError(f"Job '{job_id}' must be running before submitting a role result")

    completion_path = job_completion_path(run_dir, job_id)
    submission = dict(payload)
    submission.setdefault("status", "completed")
    if runtime_target and not submission.get("submitted_by"):
        submission["submitted_by"] = runtime_target
    if sandbox_adapter and not submission.get("sandbox_adapter"):
        submission["sandbox_adapter"] = sandbox_adapter
    submission["job_id"] = job_id
    submission["recorded_at_utc"] = now_utc()
    write_json(completion_path, submission)
    update_run_summary_artifacts(run_dir, f"{job_id}_completion_pending", completion_path)

    result: dict[str, Any] = {
        "run_id": run_dir.name,
        "job_id": job_id,
        "completion_artifact": rel_to_root(completion_path),
        "submitted_payload": submission,
    }
    if auto_consume:
        result["loop"] = run_dispatcher_loop(
            run_dir,
            runtime_target=runtime_target or str(job.get("runtime_target", "")).strip() or "codex",
            sandbox_adapter=sandbox_adapter or str(load_jobs(run_dir).get("sandbox_adapter", "")).strip(),
            max_cycles=DEFAULT_LOOP_MAX_CYCLES,
        )
    return result


def build_job_queue_payload(run_dir: Path, *, jobs_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Builds a machine-readable job queue summary."""
    jobs_payload = jobs_payload or load_jobs(run_dir)
    run_summary = load_run_summary(run_dir)
    jobs = jobs_payload.get("jobs", [])

    entries: list[dict[str, Any]] = []
    by_status: dict[str, int] = {}
    by_dispatch_status: dict[str, int] = {}
    dispatcher_status = "completed"
    current_external_job: dict[str, Any] | None = None

    for job in jobs:
        status = str(job.get("status", "unknown"))
        by_status[status] = by_status.get(status, 0) + 1
        dispatch_status = job.get("dispatch_status", "queued" if job.get("backend") == "external_ai" else "")
        if dispatch_status:
            by_dispatch_status[dispatch_status] = by_dispatch_status.get(dispatch_status, 0) + 1
        entry = {
            "job_id": job.get("job_id", ""),
            "role": job.get("role", ""),
            "backend": job.get("backend", ""),
            "status": status,
            "dispatch_status": dispatch_status,
            "claimed_by": job.get("claimed_by", ""),
            "runtime_target": job.get("runtime_target", ""),
            "runtime_ref": job.get("runtime_ref", ""),
            "external_ref": job.get("external_ref", ""),
            "dependencies": job.get("dependencies", []),
            "result_artifact": job.get("result_artifact", ""),
        }
        entries.append(entry)

        if entry["backend"] == "external_ai" and entry["status"] == "running" and current_external_job is None:
            current_external_job = entry
            dispatcher_status = entry["dispatch_status"] or "dispatched"

    if current_external_job is None:
        pending_external = [
            item for item in entries
            if item["backend"] == "external_ai" and item["status"] in {"queued", "running"}
        ]
        if pending_external:
            dispatcher_status = "queued"

    return {
        "version": 1,
        "run_id": run_dir.name,
        "run_status": run_summary.get("status", ""),
        "next_action": run_summary.get("next_action", ""),
        "sandbox_adapter": str(jobs_payload.get("sandbox_adapter", "")).strip(),
        "total_jobs": len(entries),
        "by_status": by_status,
        "by_dispatch_status": by_dispatch_status,
        "current_external_job": current_external_job,
        "jobs": entries,
        "dispatcher_status": dispatcher_status,
    }


def render_job_queue_markdown(queue_payload: dict[str, Any]) -> str:
    """Renders a compact markdown view of the job queue."""
    current = queue_payload.get("current_external_job") or {}
    lines = [
        "# Job Queue",
        "",
        f"- Run ID: `{queue_payload.get('run_id', '')}`",
        f"- Run Status: `{queue_payload.get('run_status', '')}`",
        f"- Next Action: `{queue_payload.get('next_action', '')}`",
        f"- Sandbox Adapter: `{queue_payload.get('sandbox_adapter', '') or '-'}`",
        f"- Dispatcher Status: `{queue_payload.get('dispatcher_status', '')}`",
        f"- Current External Job: `{current.get('job_id', '-')}`",
        "",
        "## Jobs",
        "",
    ]
    for item in queue_payload.get("jobs", []):
        lines.append(
            f"- `{item['job_id']}` role=`{item['role']}` backend=`{item['backend']}` "
            f"status=`{item['status']}` dispatch=`{item.get('dispatch_status', '') or '-'}`"
        )
    return "\n".join(lines) + "\n"


def show_job_queue(run_dir: Path) -> dict[str, Any]:
    """Builds and writes queue UX artifacts."""
    payload = build_job_queue_payload(run_dir)
    markdown = render_job_queue_markdown(payload)
    markdown_path = job_queue_markdown_path(run_dir)
    markdown_path.write_text(markdown, encoding="utf-8")
    update_run_summary_artifacts(run_dir, "job_queue_markdown", markdown_path)
    update_dispatcher_snapshot(
        run_dir,
        jobs_payload=load_jobs(run_dir),
        current_job_id=((payload.get("current_external_job") or {}).get("job_id", "")),
        runtime_target=((payload.get("current_external_job") or {}).get("runtime_target", "")),
        dispatch_status=payload.get("dispatcher_status", ""),
    )
    return {
        **payload,
        "job_queue_markdown": rel_to_root(markdown_path),
        "human": markdown,
    }


def read_text_if_available(path: Path) -> tuple[str | None, str]:
    """Reads a UTF-8 text file if available."""
    if not path.exists():
        return None, "missing"
    if not path.is_file():
        return None, "not_a_file"
    try:
        return path.read_text(encoding="utf-8"), "text"
    except UnicodeDecodeError:
        return None, "binary_or_non_utf8"


def candidate_diff_paths(run_dir: Path, explicit_paths: list[str] | None = None) -> list[str]:
    """Selects candidate paths for isolated-workspace diff preview."""
    normalized = [normalize_rel_path(item) for item in (explicit_paths or []) if item.strip()]
    if normalized:
        return list(dict.fromkeys(normalized))

    run_summary = load_run_summary(run_dir)
    changed_files = load_optional_json(run_dir / "changed-files.json") or {}
    apply_result = load_optional_json(run_dir / "apply-result.json") or {}

    candidates: list[str] = []
    candidates.extend(str(item) for item in apply_result.get("applied_files", []))
    candidates.extend(str(item) for item in changed_files.get("changed_files", []))
    candidates.extend(str(item) for item in run_summary.get("changed_paths", []))
    if not candidates:
        workspace_root = resolve_workspace_root(run_dir / "workspace.json", fallback=ROOT)
        git_status = subprocess.run(
            ["git", "-C", str(workspace_root), "status", "--short", "--untracked-files=all"],
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if git_status.returncode == 0:
            for raw_line in git_status.stdout.splitlines():
                if len(raw_line) < 4:
                    continue
                candidates.append(raw_line[3:].strip())
    return list(dict.fromkeys(normalize_rel_path(item) for item in candidates if str(item).strip()))


def build_diff_preview(run_dir: Path, *, explicit_paths: list[str] | None = None) -> dict[str, Any]:
    """Builds a markdown diff preview between source root and isolated workspace."""
    workspace_root = resolve_workspace_root(run_dir / "workspace.json", fallback=ROOT)
    paths = candidate_diff_paths(run_dir, explicit_paths=explicit_paths)
    file_previews: list[dict[str, Any]] = []
    sections: list[str] = []

    for rel_path in paths:
        source_path = ROOT / rel_path
        workspace_path = workspace_root / rel_path
        source_text, source_kind = read_text_if_available(source_path)
        workspace_text, workspace_kind = read_text_if_available(workspace_path)

        if source_kind == "binary_or_non_utf8" or workspace_kind == "binary_or_non_utf8":
            file_previews.append(
                {
                    "path": rel_path,
                    "changed": True,
                    "kind": "binary_or_non_utf8",
                    "summary": "Binary or non-UTF8 diff preview is not rendered.",
                }
            )
            sections.extend(
                [
                    f"## `{rel_path}`",
                    "",
                    "- binary_or_non_utf8",
                    "",
                ]
            )
            continue

        source_lines = [] if source_text is None else source_text.splitlines()
        workspace_lines = [] if workspace_text is None else workspace_text.splitlines()
        diff_lines = list(
            difflib.unified_diff(
                source_lines,
                workspace_lines,
                fromfile=f"a/{rel_path}",
                tofile=f"b/{rel_path}",
                lineterm="",
            )
        )
        changed = bool(diff_lines)
        if not changed:
            continue

        file_previews.append(
            {
                "path": rel_path,
                "changed": True,
                "kind": "text",
                "summary": f"{len(diff_lines)} diff lines",
            }
        )
        sections.extend(
            [
                f"## `{rel_path}`",
                "",
                "```diff",
                *diff_lines,
                "```",
                "",
            ]
        )

    markdown = "\n".join(
        [
            "# Diff Preview",
            "",
            f"- Run ID: `{run_dir.name}`",
            f"- Workspace Root: `{workspace_root}`",
            f"- Candidate Paths: {len(paths)}",
            f"- Changed Files: {len(file_previews)}",
            "",
            *(sections or ["- no textual differences detected", ""]),
        ]
    )
    markdown_path = diff_preview_path(run_dir)
    markdown_path.write_text(markdown, encoding="utf-8")
    update_run_summary_artifacts(run_dir, "diff_preview", markdown_path)

    return {
        "version": 1,
        "run_id": run_dir.name,
        "workspace_root": str(workspace_root),
        "candidate_paths": paths,
        "changed_files": file_previews,
        "diff_preview_markdown": rel_to_root(markdown_path),
        "human": markdown,
    }


def dispatch_next_job(
    run_dir: Path,
    *,
    runtime_target: str,
    claimed_by: str = "",
) -> dict[str, Any]:
    """Claims or reuses the next sequential external job and emits a work item."""
    jobs_payload = load_jobs(run_dir)

    for job in jobs_payload.get("jobs", []):
        if job.get("backend") == "external_ai" and job.get("status") == "running":
            record = ensure_dispatch_record(
                run_dir,
                job_id=str(job.get("job_id", "")),
                runtime_target=runtime_target or str(job.get("claimed_by", "")).strip() or "codex-runtime",
            )
            queue = show_job_queue(run_dir)
            return {
                "run_id": run_dir.name,
                "dispatch_status": "dispatched",
                "job": record["job"],
                "work_item": record["work_item"],
                "queue": queue,
            }

    next_job = next_claimable_external_job(run_dir)
    if next_job is not None:
        role = str(next_job.get("job_id", ""))
        claim_result = claim_job(
            run_dir,
            job_id=role,
            claimed_by=claimed_by or runtime_target,
        )
        record = ensure_dispatch_record(
            run_dir,
            job_id=role,
            runtime_target=runtime_target,
        )
        queue = show_job_queue(run_dir)
        return {
            "run_id": run_dir.name,
            "dispatch_status": "dispatched",
            "job": record["job"],
            "claim_result": claim_result,
            "work_item": record["work_item"],
            "queue": queue,
        }

    queue = show_job_queue(run_dir)
    return {
        "run_id": run_dir.name,
        "dispatch_status": queue.get("dispatcher_status", "completed"),
        "job": queue.get("current_external_job"),
        "queue": queue,
    }


def run_dispatcher_loop(
    run_dir: Path,
    *,
    runtime_target: str,
    claimed_by: str = "",
    sandbox_adapter: str = "",
    max_cycles: int = DEFAULT_LOOP_MAX_CYCLES,
) -> dict[str, Any]:
    """Runs a small autonomous dispatcher loop over completion inbox + next dispatch."""
    cycles = 0
    events: list[dict[str, Any]] = []

    while cycles < max_cycles:
        cycles += 1
        jobs_payload = load_jobs(run_dir)
        current_job = active_external_job(jobs_payload)

        if current_job is not None:
            consumed = consume_completion_artifact(
                run_dir,
                job_id=str(current_job.get("job_id", "")),
                default_sandbox_adapter=sandbox_adapter or str(jobs_payload.get("sandbox_adapter", "")).strip(),
            )
            if consumed is not None:
                events.append({"type": "completion_consumed", **consumed})
                continue

            queue = show_job_queue(run_dir)
            return {
                "run_id": run_dir.name,
                "loop_status": "awaiting_external_result",
                "cycles": cycles,
                "events": events,
                "current_job": queue.get("current_external_job"),
                "queue": queue,
            }

        dispatch = dispatch_next_job(
            run_dir,
            runtime_target=runtime_target,
            claimed_by=claimed_by,
        )
        events.append(
            {
                "type": "dispatch_attempt",
                "dispatch_status": dispatch.get("dispatch_status", ""),
                "job_id": (dispatch.get("job") or {}).get("job_id", ""),
            }
        )

        if dispatch.get("dispatch_status") == "dispatched":
            return {
                "run_id": run_dir.name,
                "loop_status": "dispatched_external_job",
                "cycles": cycles,
                "events": events,
                **dispatch,
            }

        queue = dispatch.get("queue") or show_job_queue(run_dir)
        return {
            "run_id": run_dir.name,
            "loop_status": "idle",
            "cycles": cycles,
            "events": events,
            "current_job": queue.get("current_external_job"),
            "queue": queue,
        }

    queue = show_job_queue(run_dir)
    return {
        "run_id": run_dir.name,
        "loop_status": "max_cycles_reached",
        "cycles": cycles,
        "events": events,
        "current_job": queue.get("current_external_job"),
        "queue": queue,
    }


def run_autonomous_cycle(
    run_dir: Path,
    *,
    runtime_target: str,
    claimed_by: str = "",
    sandbox_adapter: str = "",
    max_cycles: int = DEFAULT_LOOP_MAX_CYCLES,
) -> dict[str, Any]:
    """Runs local orchestration and dispatcher loop until the next stable boundary."""
    cycles = 0
    events: list[dict[str, Any]] = []

    while cycles < max_cycles:
        cycles += 1
        before_summary = load_run_summary(run_dir)
        orchestration = start_or_continue_run(
            run_dir,
            sandbox_adapter=sandbox_adapter or None,
        )
        after_summary = load_run_summary(run_dir)
        events.append(
            {
                "type": "orchestration",
                "status": after_summary.get("status", ""),
                "next_action": after_summary.get("next_action", ""),
            }
        )

        if after_summary.get("status") in AUTONOMOUS_TERMINAL_RUN_STATUSES:
            queue = show_job_queue(run_dir)
            return {
                "run_id": run_dir.name,
                "cycle_status": "human_or_terminal_boundary",
                "cycles": cycles,
                "events": events,
                "orchestration": orchestration,
                "queue": queue,
                "run_status": after_summary.get("status", ""),
                "next_action": after_summary.get("next_action", ""),
            }

        loop = run_dispatcher_loop(
            run_dir,
            runtime_target=runtime_target,
            claimed_by=claimed_by,
            sandbox_adapter=sandbox_adapter,
            max_cycles=max_cycles,
        )
        events.append(
            {
                "type": "dispatcher_loop",
                "loop_status": loop.get("loop_status", ""),
                "job_id": (loop.get("job") or {}).get("job_id", "") or (loop.get("current_job") or {}).get("job_id", ""),
            }
        )

        current_summary = load_run_summary(run_dir)
        if loop.get("loop_status") in {"dispatched_external_job", "awaiting_external_result"}:
            return {
                "run_id": run_dir.name,
                "cycle_status": loop.get("loop_status", ""),
                "cycles": cycles,
                "events": events,
                "orchestration": orchestration,
                "loop": loop,
                "run_status": current_summary.get("status", ""),
                "next_action": current_summary.get("next_action", ""),
            }

        if current_summary.get("status") in AUTONOMOUS_TERMINAL_RUN_STATUSES:
            return {
                "run_id": run_dir.name,
                "cycle_status": "human_or_terminal_boundary",
                "cycles": cycles,
                "events": events,
                "orchestration": orchestration,
                "loop": loop,
                "run_status": current_summary.get("status", ""),
                "next_action": current_summary.get("next_action", ""),
            }

        no_progress = (
            before_summary.get("status") == current_summary.get("status")
            and before_summary.get("next_action") == current_summary.get("next_action")
            and loop.get("loop_status") == "idle"
        )
        if no_progress:
            return {
                "run_id": run_dir.name,
                "cycle_status": "idle",
                "cycles": cycles,
                "events": events,
                "orchestration": orchestration,
                "loop": loop,
                "run_status": current_summary.get("status", ""),
                "next_action": current_summary.get("next_action", ""),
            }

    queue = show_job_queue(run_dir)
    summary = load_run_summary(run_dir)
    return {
        "run_id": run_dir.name,
        "cycle_status": "max_cycles_reached",
        "cycles": cycles,
        "events": events,
        "queue": queue,
        "run_status": summary.get("status", ""),
        "next_action": summary.get("next_action", ""),
    }


def parse_runtime_response(stdout: str) -> dict[str, Any]:
    """Parses a runtime worker response from stdout."""
    payload = stdout.strip()
    if not payload:
        raise ValueError("Runtime worker returned empty stdout")
    lines = [line.strip() for line in payload.splitlines() if line.strip()]
    candidates = [payload, *(reversed(lines))]
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    raise ValueError("Runtime worker stdout did not contain a valid JSON object")


def invoke_runtime_worker(
    run_dir: Path,
    *,
    work_item: dict[str, Any],
    runtime_command: list[str],
    timeout_seconds: int,
) -> dict[str, Any]:
    """Invokes a configured runtime worker over stdio and records execution logs."""
    if not runtime_command:
        raise ValueError("Runtime worker command is required")

    job_id = str(work_item.get("job_id", "")).strip() or "external-job"
    log_path = run_dir / "jobs" / f"{job_id}-runtime.log"
    response_path = run_dir / "jobs" / f"{job_id}-runtime-response.json"
    payload_text = json.dumps(work_item, ensure_ascii=False)

    try:
        process = subprocess.run(
            runtime_command,
            input=payload_text,
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=timeout_seconds,
            cwd=ROOT,
        )
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        process = subprocess.CompletedProcess(
            args=list(runtime_command),
            returncode=124,
            stdout=exc.stdout or "",
            stderr=(exc.stderr or "") + f"\nruntime worker timed out after {timeout_seconds}s",
        )
        timed_out = True

    log_path.write_text(
        "\n".join(
            [
                "$ " + " ".join(runtime_command),
                "",
                "stdin:",
                payload_text,
                "",
                f"returncode: {process.returncode}",
                "",
                "stdout:",
                process.stdout or "",
                "",
                "stderr:",
                process.stderr or "",
                "",
            ],
        ),
        encoding="utf-8",
    )

    response: dict[str, Any]
    if timed_out:
        response = {
            "status": "blocked",
            "summary": f"Runtime worker timed out for {job_id}.",
            "reason": "runtime_worker_timeout",
        }
    elif process.returncode != 0:
        response = {
            "status": "failed",
            "summary": f"Runtime worker failed for {job_id}.",
            "reason": "runtime_worker_nonzero_exit",
            "stderr": process.stderr,
        }
    else:
        response = parse_runtime_response(process.stdout)
        if "status" not in response:
            response = {
                "status": "completed",
                "result": response,
                "summary": str(response.get("summary", "")).strip(),
            }

    response.setdefault("job_id", job_id)
    response.setdefault("runtime_log", rel_to_root(log_path))
    write_json(response_path, response)
    update_run_summary_artifacts(run_dir, f"{job_id}_runtime_log", log_path)
    update_run_summary_artifacts(run_dir, f"{job_id}_runtime_response", response_path)
    return response


def execute_runtime_worker_for_run(
    run_dir: Path,
    *,
    runtime_target: str,
    runtime_command: list[str],
    claimed_by: str = "",
    sandbox_adapter: str = "",
    timeout_seconds: int = 1200,
) -> dict[str, Any]:
    """Dispatches the next external job and executes it through the configured runtime worker."""
    dispatch = dispatch_next_job(
        run_dir,
        runtime_target=runtime_target,
        claimed_by=claimed_by,
    )
    if dispatch.get("dispatch_status") != "dispatched":
        return {
            "run_id": run_dir.name,
            "runtime_status": "idle",
            "dispatch": dispatch,
        }

    work_item = dict(dispatch.get("work_item") or {})
    response = invoke_runtime_worker(
        run_dir,
        work_item=work_item,
        runtime_command=runtime_command,
        timeout_seconds=timeout_seconds,
    )
    status = str(response.get("status", "completed")).strip().casefold() or "completed"
    submission_payload = dict(response.get("result", {}) if isinstance(response.get("result"), dict) else {})
    if not submission_payload:
        submission_payload = {
            key: value
            for key, value in response.items()
            if key not in {"status", "job_id", "runtime_log", "summary", "reason"}
        }
    if response.get("summary") and not submission_payload.get("summary"):
        submission_payload["summary"] = response["summary"]
    submission_payload["status"] = status
    if response.get("reason") and not submission_payload.get("reason"):
        submission_payload["reason"] = response["reason"]

    if status in {"completed", "failed", "blocked"}:
        submission = submit_role_result(
            run_dir,
            job_id=str(work_item.get("job_id", "")).strip(),
            payload=submission_payload,
            runtime_target=runtime_target,
            sandbox_adapter=sandbox_adapter,
            auto_consume=True,
        )
        return {
            "run_id": run_dir.name,
            "runtime_status": status,
            "dispatch": dispatch,
            "runtime_response": response,
            "submission": submission,
        }

    return {
        "run_id": run_dir.name,
        "runtime_status": "awaiting_external_result",
        "dispatch": dispatch,
        "runtime_response": response,
    }


def run_supervisor(
    run_dir: Path,
    *,
    runtime_target: str,
    runtime_command: list[str] | None = None,
    claimed_by: str = "",
    sandbox_adapter: str = "",
    poll_interval_seconds: float = 2.0,
    max_iterations: int = DEFAULT_SUPERVISOR_MAX_ITERATIONS,
    max_cycles: int = DEFAULT_LOOP_MAX_CYCLES,
    runtime_timeout_seconds: int = 1200,
) -> dict[str, Any]:
    """Runs a persistent orchestration supervisor for a single run."""
    iterations = 0
    events: list[dict[str, Any]] = []
    runtime_command = list(runtime_command or [])

    while iterations < max_iterations:
        iterations += 1
        cycle = run_autonomous_cycle(
            run_dir,
            runtime_target=runtime_target,
            claimed_by=claimed_by,
            sandbox_adapter=sandbox_adapter,
            max_cycles=max_cycles,
        )
        cycle_event = {
            "type": "cycle",
            "iteration": iterations,
            "cycle_status": cycle.get("cycle_status", ""),
            "run_status": cycle.get("run_status", ""),
            "next_action": cycle.get("next_action", ""),
        }
        events.append(cycle_event)

        if cycle.get("cycle_status") == "human_or_terminal_boundary":
            supervisor = update_supervisor_snapshot(
                run_dir,
                supervisor_status="awaiting_human_or_terminal_boundary",
                runtime_target=runtime_target,
                iterations=iterations,
                poll_interval_seconds=poll_interval_seconds,
                runtime_command=runtime_command,
                current_job_id="",
                last_event=cycle_event,
            )
            return {
                "run_id": run_dir.name,
                "supervisor_status": "awaiting_human_or_terminal_boundary",
                "iterations": iterations,
                "events": events,
                "cycle": cycle,
                "supervisor": supervisor,
            }

        if cycle.get("cycle_status") in {"dispatched_external_job", "awaiting_external_result"}:
            current_job = (cycle.get("loop") or {}).get("job") or (cycle.get("loop") or {}).get("current_job") or {}
            current_job_id = str(current_job.get("job_id", "")).strip()
            if not runtime_command:
                supervisor = update_supervisor_snapshot(
                    run_dir,
                    supervisor_status="awaiting_runtime_worker",
                    runtime_target=runtime_target,
                    iterations=iterations,
                    poll_interval_seconds=poll_interval_seconds,
                    runtime_command=runtime_command,
                    current_job_id=current_job_id,
                    last_event=cycle_event,
                )
                return {
                    "run_id": run_dir.name,
                    "supervisor_status": "awaiting_runtime_worker",
                    "iterations": iterations,
                    "events": events,
                    "cycle": cycle,
                    "supervisor": supervisor,
                }

            runtime_execution = execute_runtime_worker_for_run(
                run_dir,
                runtime_target=runtime_target,
                runtime_command=runtime_command,
                claimed_by=claimed_by,
                sandbox_adapter=sandbox_adapter,
                timeout_seconds=runtime_timeout_seconds,
            )
            runtime_event = {
                "type": "runtime_execution",
                "iteration": iterations,
                "runtime_status": runtime_execution.get("runtime_status", ""),
                "job_id": current_job_id,
            }
            events.append(runtime_event)
            current_summary = load_run_summary(run_dir)
            if current_summary.get("status") in AUTONOMOUS_TERMINAL_RUN_STATUSES:
                supervisor = update_supervisor_snapshot(
                    run_dir,
                    supervisor_status="awaiting_human_or_terminal_boundary",
                    runtime_target=runtime_target,
                    iterations=iterations,
                    poll_interval_seconds=poll_interval_seconds,
                    runtime_command=runtime_command,
                    current_job_id=current_job_id,
                    last_event=runtime_event,
                )
                return {
                    "run_id": run_dir.name,
                    "supervisor_status": "awaiting_human_or_terminal_boundary",
                    "iterations": iterations,
                    "events": events,
                    "cycle": cycle,
                    "runtime_execution": runtime_execution,
                    "supervisor": supervisor,
                }
            continue

        if poll_interval_seconds > 0:
            time.sleep(poll_interval_seconds)

    supervisor = update_supervisor_snapshot(
        run_dir,
        supervisor_status="max_iterations_reached",
        runtime_target=runtime_target,
        iterations=iterations,
        poll_interval_seconds=poll_interval_seconds,
        runtime_command=runtime_command,
        current_job_id="",
        last_event=events[-1] if events else {},
    )
    return {
        "run_id": run_dir.name,
        "supervisor_status": "max_iterations_reached",
        "iterations": iterations,
        "events": events,
        "supervisor": supervisor,
    }
