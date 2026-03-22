#!/usr/bin/env python3
"""Phase 3 swarm role executor and orchestration helpers."""

from __future__ import annotations

import json

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.config import ROOT
from scripts.agents.knowledge import get_verification_profile
from scripts.agents.lifecycle import apply as apply_stage
from scripts.agents.lifecycle import execute as execute_stage
from scripts.agents.lifecycle import request_approval as request_approval_stage
from scripts.agents.lifecycle import review as review_stage
from scripts.agents.lifecycle import sandbox as sandbox_stage
from scripts.agents.lifecycle import verify as verify_stage
from scripts.agents.runtime_trace import (
    append_runtime_trace_event,
    artifact_rel_path,
    runtime_trace_path,
)
from scripts.agents.sandbox_adapters import (
    DEFAULT_GITHUB_ACTIONS_WORKFLOW,
    DEFAULT_SANDBOX_IMAGE,
    DOCKER_ADAPTER,
    GITHUB_ACTIONS_ADAPTER,
    LOCAL_DRY_RUN_ADAPTER,
    derive_conclusion,
    execute_sandbox_request,
    resolve_sandbox_adapter,
    write_json as write_adapter_json,
)
from scripts.agents.workspace import (
    WorkspaceRef,
    prepare_workspace,
    read_workspace_ref,
    resolve_workspace_root,
    write_workspace_json,
)


JOBS_DIR_NAME = "jobs"
ROLE_SEQUENCE = [
    "planner",
    "context_loader",
    "workspace_prepare",
    "coder",
    "tester",
    "sandbox_runner",
    "reviewer",
    "release_manager",
]
EXTERNAL_ROLES = {"coder", "reviewer"}
LOCAL_ROLES = set(ROLE_SEQUENCE) - EXTERNAL_ROLES
VALID_JOB_STATUSES = {"queued", "running", "completed", "failed", "blocked"}


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


def jobs_dir(run_dir: Path) -> Path:
    """Returns the jobs directory path."""
    return run_dir / JOBS_DIR_NAME


def jobs_index_path(run_dir: Path) -> Path:
    """Returns the jobs index path."""
    return jobs_dir(run_dir) / "index.json"


def workspace_json_path(run_dir: Path) -> Path:
    """Returns the workspace metadata path."""
    return run_dir / "workspace.json"


def verification_plan_path(run_dir: Path) -> Path:
    """Returns the verification plan path."""
    return run_dir / "verification-plan.json"


def verification_profile_path(run_dir: Path) -> Path:
    """Returns the verification profile artifact path."""
    return run_dir / "verification-profile.json"


def sandbox_plan_path(run_dir: Path) -> Path:
    """Returns the sandbox plan artifact path."""
    return run_dir / "sandbox-plan.json"


def load_run_summary(run_dir: Path) -> dict[str, Any]:
    """Loads run-summary.json."""
    return load_json(run_dir / "run-summary.json")


def write_run_summary(run_dir: Path, payload: dict[str, Any]) -> None:
    """Writes run-summary.json."""
    write_json(run_dir / "run-summary.json", payload)


def persist_runtime_trace_ref(run_dir: Path) -> None:
    """Persists runtime trace artifact ref if the file exists."""
    trace_path = runtime_trace_path(run_dir)
    if not trace_path.is_file():
        return
    persist_artifact_ref(run_dir, "runtime_context_trace", trace_path)


def trace_event(
    run_dir: Path,
    *,
    phase: str,
    job_id: str,
    requested_by: str,
    category: str,
    item: str,
    reason: str,
    source_artifact: Path,
    resolution: str,
    before_summary: dict[str, Any] | None = None,
    after_summary: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Appends a runtime trace event and wires it into run-summary artifacts."""
    event = append_runtime_trace_event(
        run_dir,
        phase=phase,
        job_id=job_id,
        requested_by=requested_by,
        category=category,
        item=item,
        reason=reason,
        source_artifact=artifact_rel_path(source_artifact),
        resolution=resolution,
        before_summary=before_summary,
        after_summary=after_summary,
        extra=extra,
    )
    persist_runtime_trace_ref(run_dir)
    return event


def summarize_dispatcher_state(jobs_payload: dict[str, Any]) -> dict[str, Any]:
    """Builds dispatcher metadata from external role jobs."""
    by_dispatch_status: dict[str, int] = {}
    current_external_job: dict[str, Any] | None = None

    for job in jobs_payload.get("jobs", []):
        if job.get("backend") != "external_ai":
            continue
        dispatch_status = str(job.get("dispatch_status") or "queued")
        by_dispatch_status[dispatch_status] = by_dispatch_status.get(dispatch_status, 0) + 1
        if current_external_job is None and job.get("status") not in {"completed", "failed", "blocked"}:
            current_external_job = {
                "job_id": job.get("job_id", ""),
                "role": job.get("role", ""),
                "status": job.get("status", ""),
                "dispatch_status": dispatch_status,
                "runtime_target": job.get("runtime_target", ""),
                "runtime_ref": job.get("runtime_ref", ""),
            }

    return {
        "external_job_count": sum(1 for job in jobs_payload.get("jobs", []) if job.get("backend") == "external_ai"),
        "by_dispatch_status": by_dispatch_status,
        "current_external_job": current_external_job,
    }


def sync_jobs_summary(run_dir: Path, jobs_payload: dict[str, Any]) -> None:
    """Keeps run-summary aligned with job/dispatcher metadata."""
    run_summary = load_run_summary(run_dir)
    run_summary["dispatcher"] = summarize_dispatcher_state(jobs_payload)
    run_summary.setdefault("jobs", {})["sandbox_adapter"] = jobs_payload.get("sandbox_adapter", "")
    write_run_summary(run_dir, run_summary)


def record_selected_sandbox_adapter(run_dir: Path, *, sandbox_adapter: str) -> None:
    """Persists the resolved sandbox adapter into run-summary."""
    run_summary = load_run_summary(run_dir)
    sandbox = run_summary.setdefault("sandbox", {})
    sandbox["selected_adapter"] = sandbox_adapter
    run_summary["sandbox"] = sandbox
    write_run_summary(run_dir, run_summary)


def resolve_run_sandbox_adapter(run_dir: Path, *, requested_adapter_id: str | None) -> str:
    """Resolves the effective sandbox adapter for a run."""
    run_summary = load_run_summary(run_dir)
    verification_profile = run_summary.get("verification_profile") or get_verification_profile(run_summary["task_type"]["id"])
    return resolve_sandbox_adapter(
        requested_adapter_id=requested_adapter_id,
        verification_profile=verification_profile,
    )


def persist_artifact_ref(run_dir: Path, artifact_key: str, artifact_path: Path) -> None:
    """Persists an artifact reference to run-summary.json."""
    run_summary = load_run_summary(run_dir)
    artifacts = run_summary.setdefault("artifacts", {})
    artifacts[artifact_key] = str(artifact_path.relative_to(ROOT)).replace("\\", "/")
    run_summary["artifacts"] = artifacts
    write_run_summary(run_dir, run_summary)


def build_workspace_for_run(
    run_dir: Path,
    *,
    cleanup_policy: str = "remove_after_run",
) -> dict[str, Any]:
    """Builds and writes workspace metadata for a run if missing."""
    workspace_path = workspace_json_path(run_dir)
    if workspace_path.is_file():
        payload = load_json(workspace_path)
        persist_artifact_ref(run_dir, "workspace", workspace_path)
        return payload

    workspace_root = run_dir / "workspace"
    plan = prepare_workspace(
        source_root=ROOT,
        workspace_root=workspace_root,
        cleanup_policy=cleanup_policy,
    )
    workspace = WorkspaceRef.from_dict(plan["workspace"])
    write_workspace_json(workspace_path, workspace=workspace, plan=plan)
    persist_artifact_ref(run_dir, "workspace", workspace_path)
    return load_json(workspace_path)


def build_job_specs(
    run_dir: Path,
    *,
    workspace_ref: WorkspaceRef,
    sandbox_adapter: str,
) -> list[dict[str, Any]]:
    """Builds deterministic Phase 3 role job specs."""
    run_summary = load_run_summary(run_dir)
    changed_paths = run_summary.get("changed_paths", [])
    now = now_utc()
    expected_outputs = {
        "planner": ["plan.json", "route-result.json"],
        "context_loader": ["loaded-context.json", "context-brief.json"],
        "workspace_prepare": ["workspace.json"],
        "coder": ["apply-result.json", "workspace-diff.patch", "changed-files.json"],
        "tester": ["verification-plan.json", "verification-profile.json"],
        "sandbox_runner": ["verification-result.json", "sandbox-result.json", "sandbox-plan.json"],
        "reviewer": ["review-result.json"],
        "release_manager": ["approval-request.json", "approval-request.md"],
    }
    input_artifacts = {
        "planner": ["input.json", "plan.json"],
        "context_loader": ["context-pack.json", "plan.json", "run-summary.json"],
        "workspace_prepare": ["workspace.json"],
        "coder": ["loaded-context.json", "workspace.json", "plan.json"],
        "tester": ["apply-result.json", "workspace.json"],
        "sandbox_runner": ["verification-plan.json", "workspace.json"],
        "reviewer": ["verification-result.json", "sandbox-result.json", "changed-files.json", "context-brief.json"],
        "release_manager": ["review-result.json", "verification-result.json", "sandbox-result.json"],
    }

    jobs: list[dict[str, Any]] = []
    previous_job_id = ""
    for role in ROLE_SEQUENCE:
        job_id = role
        backend = "external_ai" if role in EXTERNAL_ROLES else "local"
        jobs.append(
            {
                "job_id": job_id,
                "role": role,
                "backend": backend,
                "status": "queued",
                "workspace_ref": workspace_ref.to_dict(),
                "dependencies": [previous_job_id] if previous_job_id else [],
                "input_artifacts": input_artifacts.get(role, []),
                "write_scope": changed_paths if role == "coder" else ["runs"],
                "expected_outputs": expected_outputs.get(role, []),
                "external_ref": f"external://{run_summary['run_id']}/{job_id}" if backend == "external_ai" else "",
                "adapter": sandbox_adapter if role == "sandbox_runner" else "",
                "dispatch_status": "queued" if backend == "external_ai" else "",
                "dispatched_at_utc": "",
                "runtime_target": "codex_bridge" if backend == "external_ai" else "",
                "runtime_ref": "",
                "created_at_utc": now,
                "updated_at_utc": now,
            }
        )
        previous_job_id = job_id
    return jobs


def load_jobs(run_dir: Path) -> dict[str, Any]:
    """Loads jobs/index.json."""
    return load_json(jobs_index_path(run_dir))


def persist_jobs(run_dir: Path, jobs_payload: dict[str, Any]) -> None:
    """Writes jobs/index.json and per-job records."""
    jobs_dir(run_dir).mkdir(parents=True, exist_ok=True)
    write_json(jobs_index_path(run_dir), jobs_payload)
    for job in jobs_payload.get("jobs", []):
        write_json(jobs_dir(run_dir) / f"{job['job_id']}.json", job)
    persist_artifact_ref(run_dir, "jobs_index", jobs_index_path(run_dir))
    sync_jobs_summary(run_dir, jobs_payload)


def ensure_jobs_seeded(run_dir: Path, *, sandbox_adapter: str) -> dict[str, Any]:
    """Creates jobs/index.json if it does not yet exist."""
    index_path = jobs_index_path(run_dir)
    if index_path.is_file():
        payload = load_json(index_path)
        if payload.get("sandbox_adapter") != sandbox_adapter:
            payload["sandbox_adapter"] = sandbox_adapter
            for job in payload.get("jobs", []):
                if job.get("role") == "sandbox_runner":
                    job["adapter"] = sandbox_adapter
            persist_jobs(run_dir, payload)
        record_selected_sandbox_adapter(run_dir, sandbox_adapter=sandbox_adapter)
        return payload

    workspace_ref = read_workspace_ref(workspace_json_path(run_dir))
    payload = {
        "version": 1,
        "run_id": run_dir.name,
        "sandbox_adapter": sandbox_adapter,
        "jobs": build_job_specs(run_dir, workspace_ref=workspace_ref, sandbox_adapter=sandbox_adapter),
    }
    persist_jobs(run_dir, payload)
    record_selected_sandbox_adapter(run_dir, sandbox_adapter=sandbox_adapter)
    return payload


def find_job(jobs_payload: dict[str, Any], job_id: str) -> dict[str, Any]:
    """Finds a job by id."""
    for job in jobs_payload.get("jobs", []):
        if job.get("job_id") == job_id:
            return job
    raise KeyError(f"Job '{job_id}' not found")


def dependencies_completed(jobs_payload: dict[str, Any], job: dict[str, Any]) -> bool:
    """Checks whether all job dependencies are completed."""
    completed = {
        item["job_id"]
        for item in jobs_payload.get("jobs", [])
        if item.get("status") == "completed"
    }
    return all(dep_id in completed for dep_id in job.get("dependencies", []))


def update_job_status(
    run_dir: Path,
    jobs_payload: dict[str, Any],
    job: dict[str, Any],
    *,
    status: str,
    claimed_by: str = "",
    result_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Updates a job status and optionally writes a result artifact."""
    if status not in VALID_JOB_STATUSES:
        raise ValueError(f"Unsupported job status: {status}")

    now = now_utc()
    job["status"] = status
    job["updated_at_utc"] = now
    if status == "running":
        job["started_at_utc"] = now
        if claimed_by:
            job["claimed_by"] = claimed_by
        if job.get("backend") == "external_ai":
            job["dispatch_status"] = "claimed"
    if status in {"completed", "failed", "blocked"}:
        job["completed_at_utc"] = now
        if job.get("backend") == "external_ai":
            job["dispatch_status"] = status
        if result_payload is not None:
            result_path = jobs_dir(run_dir) / f"{job['job_id']}-result.json"
            write_json(result_path, result_payload)
            job["result_artifact"] = str(result_path.relative_to(ROOT)).replace("\\", "/")

    persist_jobs(run_dir, jobs_payload)
    return job


def update_job_dispatch(
    run_dir: Path,
    jobs_payload: dict[str, Any],
    job: dict[str, Any],
    *,
    dispatch_status: str,
    runtime_target: str = "",
    runtime_ref: str = "",
) -> dict[str, Any]:
    """Updates external dispatch metadata for a job."""
    job["dispatch_status"] = dispatch_status
    if dispatch_status == "dispatched":
        job["dispatched_at_utc"] = now_utc()
    if runtime_target:
        job["runtime_target"] = runtime_target
    if runtime_ref:
        job["runtime_ref"] = runtime_ref
    job["updated_at_utc"] = now_utc()
    persist_jobs(run_dir, jobs_payload)
    return job


def build_job_result(
    job: dict[str, Any],
    *,
    status: str,
    summary: str,
    output: dict[str, Any] | None = None,
    reason: str = "",
) -> dict[str, Any]:
    """Builds a machine-readable job result payload."""
    return {
        "version": 1,
        "job_id": job["job_id"],
        "role": job["role"],
        "status": status,
        "summary": summary,
        "reason": reason,
        "recorded_at_utc": now_utc(),
        "output": output or {},
    }


def build_verification_plan(run_dir: Path, *, sandbox_adapter: str) -> dict[str, Any]:
    """Builds and writes a verification plan from the current verification profile."""
    run_summary = load_run_summary(run_dir)
    record_selected_sandbox_adapter(run_dir, sandbox_adapter=sandbox_adapter)
    profile = run_summary.get("verification_profile") or get_verification_profile(run_summary["task_type"]["id"])
    workspace_ref = read_workspace_ref(workspace_json_path(run_dir))
    commands = [
        {
            "id": f"command_{index + 1}",
            "command": command,
        }
        for index, command in enumerate(profile.get("allowed_commands", []))
    ]
    checks = [
        {"id": check_id, "required": True}
        for check_id in profile.get("required_checks", [])
    ] + [
        {"id": check_id, "required": False}
        for check_id in profile.get("optional_checks", [])
    ]
    payload = {
        "version": 1,
        "run_id": run_summary["run_id"],
        "task_type": run_summary["task_type"],
        "profile_id": profile.get("profile_id", ""),
        "risk_level": profile.get("risk_level", "unknown"),
        "adapter_id": sandbox_adapter,
        "workspace_ref": workspace_ref.to_dict(),
        "checks": checks,
        "commands": commands,
        "notes": profile.get("notes", []),
    }
    write_json(verification_plan_path(run_dir), payload)
    write_json(verification_profile_path(run_dir), profile)
    persist_artifact_ref(run_dir, "verification_plan", verification_plan_path(run_dir))
    persist_artifact_ref(run_dir, "verification_profile", verification_profile_path(run_dir))
    trace_event(
        run_dir,
        phase="tester",
        job_id="tester",
        requested_by="tester",
        category="verification_profile",
        item=profile.get("profile_id", ""),
        reason="verification_plan_built_from_profile",
        source_artifact=verification_plan_path(run_dir),
        resolution="resolved",
        after_summary={
            "adapter_id": sandbox_adapter,
            "required_checks": len(profile.get("required_checks", [])),
            "optional_checks": len(profile.get("optional_checks", [])),
            "command_count": len(commands),
        },
    )
    return payload


def checks_from_conclusion(profile: dict[str, Any], *, conclusion: str) -> list[dict[str, str]]:
    """Builds verification checks from an aggregate sandbox conclusion."""
    required_ids = list(profile.get("required_checks", []))
    optional_ids = list(profile.get("optional_checks", []))
    checks: list[dict[str, str]] = []

    if conclusion == "passed":
        checks.extend({"id": check_id, "status": "passed", "note": ""} for check_id in required_ids)
        checks.extend({"id": check_id, "status": "skipped", "note": "optional check not expanded in v1"} for check_id in optional_ids)
        return checks

    if conclusion == "failed":
        checks.extend({"id": check_id, "status": "failed", "note": "sandbox command failed"} for check_id in required_ids)
        checks.extend({"id": check_id, "status": "skipped", "note": "optional check not executed"} for check_id in optional_ids)
        return checks

    if conclusion == "blocked":
        checks.extend({"id": check_id, "status": "blocked", "note": "sandbox adapter blocked execution"} for check_id in required_ids)
        checks.extend({"id": check_id, "status": "skipped", "note": "optional check not executed"} for check_id in optional_ids)
        return checks

    if conclusion == "partial" and required_ids:
        checks.append({"id": required_ids[0], "status": "passed", "note": ""})
        checks.extend({"id": check_id, "status": "skipped", "note": "partial v1 execution"} for check_id in required_ids[1:])
        checks.extend({"id": check_id, "status": "skipped", "note": "optional check not executed"} for check_id in optional_ids)
        return checks

    checks.extend({"id": check_id, "status": "skipped", "note": "sandbox preview only"} for check_id in required_ids)
    checks.extend({"id": check_id, "status": "skipped", "note": "sandbox preview only"} for check_id in optional_ids)
    return checks


def augment_sandbox_result(
    run_dir: Path,
    *,
    adapter_result: dict[str, Any],
    sandbox_plan: dict[str, Any],
) -> None:
    """Augments sandbox-result.json and run-summary.json with Phase 3 fields."""
    sandbox_result_path = run_dir / "sandbox-result.json"
    if not sandbox_result_path.is_file():
        return

    payload = load_json(sandbox_result_path)
    payload["adapter_id"] = adapter_result.get("adapter_id", "")
    payload["workspace_ref"] = sandbox_plan.get("workspace_ref", {})
    payload["sandbox_plan"] = {
        "path": str(sandbox_plan_path(run_dir).relative_to(ROOT)).replace("\\", "/"),
        "adapter_id": sandbox_plan.get("adapter_id", ""),
    }
    payload["command_results"] = adapter_result.get("command_results", [])
    payload["command_summary"] = adapter_result.get("command_summary", {})
    payload["blocked_reason"] = adapter_result.get("blocked_reason", "")
    payload["logs"] = [
        {
            "copied_to": str(Path(item["log_path"]).relative_to(ROOT)).replace("\\", "/")
            if str(item.get("log_path", "")).startswith(str(ROOT))
            else item.get("log_path", "")
        }
        for item in adapter_result.get("command_results", [])
        if item.get("log_path")
    ]
    write_json(sandbox_result_path, payload)

    run_summary = load_run_summary(run_dir)
    sandbox_summary = run_summary.setdefault("sandbox", {})
    sandbox_summary["selected_adapter"] = sandbox_plan.get("adapter_id", adapter_result.get("adapter_id", ""))
    sandbox_summary["adapter_id"] = adapter_result.get("adapter_id", "")
    sandbox_summary["workspace_root"] = sandbox_plan.get("workspace_ref", {}).get("root_path", "")
    run_summary["sandbox"] = sandbox_summary
    persist_artifact_ref(run_dir, "sandbox_result", sandbox_result_path)
    write_run_summary(run_dir, run_summary)


def execute_sandbox_for_run(
    run_dir: Path,
    *,
    adapter_id: str,
) -> dict[str, Any]:
    """Executes the verification plan through the selected sandbox adapter."""
    run_summary = load_run_summary(run_dir)
    record_selected_sandbox_adapter(run_dir, sandbox_adapter=adapter_id)
    verification_plan = load_json(verification_plan_path(run_dir))
    workspace_ref = read_workspace_ref(workspace_json_path(run_dir))
    profile = run_summary.get("verification_profile") or get_verification_profile(run_summary["task_type"]["id"])

    sandbox_plan = {
        "version": 1,
        "run_id": run_summary["run_id"],
        "task_type": run_summary["task_type"],
        "adapter_id": adapter_id,
        "workspace_ref": workspace_ref.to_dict(),
        "commands": verification_plan.get("commands", []),
        "checks": verification_plan.get("checks", []),
        "image": DEFAULT_SANDBOX_IMAGE,
        "env_allowlist": {},
        "timeout_seconds": 900,
        "artifact_download_path": str((run_dir / "github-actions-download").relative_to(ROOT)).replace("\\", "/"),
    }
    if adapter_id == GITHUB_ACTIONS_ADAPTER:
        sandbox_plan["workflow_name"] = DEFAULT_GITHUB_ACTIONS_WORKFLOW
    write_json(sandbox_plan_path(run_dir), sandbox_plan)
    persist_artifact_ref(run_dir, "sandbox_plan", sandbox_plan_path(run_dir))

    adapter_request = {
        "run_id": run_summary["run_id"],
        "run_dir": str(run_dir),
        "adapter_id": adapter_id,
        "verification_profile": profile,
        "workspace_root": resolve_workspace_root(workspace_json_path(run_dir), fallback=ROOT),
        "sandbox_plan_path": str(sandbox_plan_path(run_dir).relative_to(ROOT)).replace("\\", "/"),
        "commands": verification_plan.get("commands", []),
        "env_allowlist": {},
        "image": DEFAULT_SANDBOX_IMAGE,
        "timeout_seconds": 900,
        "artifact_download_path": str((run_dir / "github-actions-download").relative_to(ROOT)).replace("\\", "/"),
    }
    if adapter_id == GITHUB_ACTIONS_ADAPTER:
        adapter_request["workflow_name"] = DEFAULT_GITHUB_ACTIONS_WORKFLOW
    adapter_result = execute_sandbox_request(adapter_request)
    adapter_result_path = run_dir / "sandbox-adapter-result.json"
    write_adapter_json(adapter_result_path, adapter_result)
    persist_artifact_ref(run_dir, "sandbox_adapter_result", adapter_result_path)

    conclusion = adapter_result.get("conclusion", derive_conclusion(adapter_result.get("command_results", [])))
    checks = checks_from_conclusion(profile, conclusion=conclusion)
    log_paths = [
        Path(item["log_path"])
        for item in adapter_result.get("command_results", [])
        if item.get("log_path")
    ]

    verify_payload = verify_stage.build_output(
        run_dir,
        conclusion=conclusion,
        summary_text=adapter_result.get("summary", ""),
        verified_by="tester",
        checks=checks,
        commands=[item["command"] for item in adapter_result.get("command_results", [])],
        log_paths=log_paths,
    )
    sandbox_payload = sandbox_stage.build_output(
        run_dir,
        conclusion=conclusion,
        summary_text=adapter_result.get("summary", ""),
        sandbox_by="sandbox_runner",
        environment=adapter_result.get("environment", adapter_id),
        sandbox_ref=adapter_result.get("sandbox_ref", ""),
        checks=checks,
        log_paths=[],
        artifact_paths=[],
    )
    augment_sandbox_result(
        run_dir,
        adapter_result=adapter_result,
        sandbox_plan=sandbox_plan,
    )
    trace_event(
        run_dir,
        phase="sandbox_runner",
        job_id="sandbox_runner",
        requested_by="sandbox_runner",
        category="sandbox_adapter",
        item=adapter_id,
        reason="sandbox_plan_executed",
        source_artifact=sandbox_plan_path(run_dir),
        resolution=(
            "blocking"
            if conclusion in {"blocked", "failed"}
            else "advisory"
            if conclusion in {"skipped", "partial"}
            else "resolved"
        ),
        before_summary={
            "command_count": len(verification_plan.get("commands", [])),
            "check_count": len(verification_plan.get("checks", [])),
        },
        after_summary={
            "conclusion": conclusion,
            "command_summary": adapter_result.get("command_summary", {}),
        },
        extra={
            "sandbox_ref": adapter_result.get("sandbox_ref", ""),
        },
    )

    return {
        "verification": verify_payload,
        "sandbox": sandbox_payload,
        "adapter": adapter_result,
    }


def run_summary_blocks_orchestration(run_summary: dict[str, Any]) -> bool:
    """Checks whether current run status should pause orchestration."""
    return run_summary.get("status") in {
        "instruction_conflict",
        "context_insufficient",
        "context_loaded_pending_run_checks_approval",
        "context_loaded_awaiting_manual_review",
        "sandbox_failed",
        "sandbox_blocked",
        "review_failed",
        "review_blocked",
        "awaiting_commit_approval",
        "awaiting_push_approval",
        "approval_rejected",
        "closed",
    }


def execute_local_job(
    run_dir: Path,
    jobs_payload: dict[str, Any],
    job: dict[str, Any],
    *,
    sandbox_adapter: str,
) -> dict[str, Any]:
    """Executes a local role job."""
    update_job_status(run_dir, jobs_payload, job, status="running", claimed_by="executor")

    if job["role"] == "planner":
        result = build_job_result(job, status="completed", summary="Planner artifacts were already prepared in the run bundle.")
        return update_job_status(run_dir, jobs_payload, job, status="completed", result_payload=result)

    if job["role"] == "context_loader":
        output = execute_stage.build_output(run_dir)
        status = "blocked" if output["status"] in {"instruction_conflict", "context_insufficient"} else "completed"
        loaded_context = load_json(run_dir / "loaded-context.json")
        trace_event(
            run_dir,
            phase="context_loader",
            job_id="context_loader",
            requested_by="context_loader",
            category="context_pack",
            item="context-pack.json",
            reason="context_loaded_into_runtime_state",
            source_artifact=run_dir / "loaded-context.json",
            resolution="blocking" if status == "blocked" else "resolved",
            after_summary=loaded_context.get("summary", {}),
        )
        result = build_job_result(job, status=status, summary="Context pack loaded.", output=output)
        return update_job_status(run_dir, jobs_payload, job, status=status, result_payload=result)

    if job["role"] == "workspace_prepare":
        payload = load_json(workspace_json_path(run_dir))
        result = build_job_result(job, status="completed", summary="Workspace is ready.", output=payload)
        return update_job_status(run_dir, jobs_payload, job, status="completed", result_payload=result)

    if job["role"] == "tester":
        payload = build_verification_plan(run_dir, sandbox_adapter=sandbox_adapter)
        result = build_job_result(job, status="completed", summary="Verification plan built from verification profile.", output=payload)
        return update_job_status(run_dir, jobs_payload, job, status="completed", result_payload=result)

    if job["role"] == "sandbox_runner":
        payload = execute_sandbox_for_run(run_dir, adapter_id=sandbox_adapter)
        run_summary = load_run_summary(run_dir)
        status = "blocked" if run_summary["status"] == "sandbox_blocked" else "completed"
        if run_summary["status"] == "sandbox_failed":
            status = "failed"
        result = build_job_result(job, status=status, summary="Sandbox runner executed verification commands.", output=payload)
        return update_job_status(run_dir, jobs_payload, job, status=status, result_payload=result)

    if job["role"] == "release_manager":
        output = request_approval_stage.build_output(
            run_dir,
            requested_by="release_manager",
            summary_text="Swarm run is ready for commit approval.",
            requested_checkpoints=["commit"],
        )
        result = build_job_result(job, status="completed", summary="Commit approval packet prepared.", output=output)
        return update_job_status(run_dir, jobs_payload, job, status="completed", result_payload=result)

    raise ValueError(f"Unsupported local role: {job['role']}")


def find_next_job(jobs_payload: dict[str, Any]) -> dict[str, Any] | None:
    """Returns the next non-completed job in sequence order."""
    ordered_jobs = {
        item["job_id"]: item
        for item in jobs_payload.get("jobs", [])
    }
    for role in ROLE_SEQUENCE:
        job = ordered_jobs.get(role)
        if job is None:
            continue
        if job.get("status") in {"completed"}:
            continue
        return job
    return None


def next_claimable_external_job(run_dir: Path) -> dict[str, Any] | None:
    """Returns the next external AI job that can be claimed right now."""
    jobs_payload = load_jobs(run_dir)
    for role in ROLE_SEQUENCE:
        job = find_job(jobs_payload, role)
        if job.get("backend") != "external_ai":
            continue
        if job.get("status") != "queued":
            continue
        if not dependencies_completed(jobs_payload, job):
            continue
        try:
            job_is_claimable(run_dir, job, jobs_payload)
        except ValueError:
            continue
        return job
    return None


def build_external_work_item(run_dir: Path, *, job_id: str) -> dict[str, Any]:
    """Builds a Codex-facing work item payload for an external role job."""
    jobs_payload = load_jobs(run_dir)
    job = find_job(jobs_payload, job_id)
    workspace_ref = read_workspace_ref(workspace_json_path(run_dir)).to_dict()
    run_summary = load_run_summary(run_dir)
    artifacts = run_summary.get("artifacts", {})
    artifact_refs: dict[str, str] = {}
    for key, value in artifacts.items():
        candidate = ROOT / normalize_rel_path(value)
        if not candidate.exists():
            continue
        artifact_refs[key] = value
        artifact_refs[candidate.name] = value

    return {
        "version": 1,
        "run_id": run_dir.name,
        "job_id": job_id,
        "role": job.get("role", ""),
        "workspace_ref": workspace_ref,
        "input_artifacts": {
            key: artifact_refs[key]
            for key in job.get("input_artifacts", [])
            if key in artifact_refs
        },
        "expected_outputs": job.get("expected_outputs", []),
        "write_scope": job.get("write_scope", []),
        "next_action": "complete_role_job",
        "result_contract": {
            "coder": {
                "required_fields": ["summary", "applied_files"],
                "optional_fields": ["applied_by", "allow_empty_diff"],
            },
            "reviewer": {
                "required_fields": ["summary", "conclusion"],
                "optional_fields": ["reviewed_by", "findings", "risks"],
            },
        }.get(job.get("role", ""), {}),
    }


def job_is_claimable(run_dir: Path, job: dict[str, Any], jobs_payload: dict[str, Any]) -> None:
    """Validates that an external job is ready to be claimed."""
    if job.get("backend") != "external_ai":
        raise ValueError(f"Job '{job['job_id']}' is not an external AI role")
    if job.get("status") not in {"queued", "running"}:
        raise ValueError(f"Job '{job['job_id']}' is in status '{job.get('status')}' and cannot be claimed")
    if not dependencies_completed(jobs_payload, job):
        raise ValueError(f"Job '{job['job_id']}' is waiting on dependencies")

    run_summary = load_run_summary(run_dir)
    if job["role"] == "coder" and run_summary.get("next_action") != "implement_change":
        raise ValueError("Coder job cannot be claimed before the run reaches implement_change")
    if job["role"] == "reviewer" and run_summary.get("next_action") != "review_result":
        raise ValueError("Reviewer job cannot be claimed before review_result is the next action")


def mark_external_job_failed(run_dir: Path, job: dict[str, Any], *, reason: str, summary: str) -> None:
    """Marks an external job as failed and updates run-summary."""
    run_summary = load_run_summary(run_dir)
    run_summary["status"] = "external_job_failed"
    run_summary["next_action"] = f"resolve_{job['job_id']}_failure"
    run_summary["job_failure"] = {
        "job_id": job["job_id"],
        "role": job["role"],
        "summary": summary,
        "reason": reason,
    }
    write_run_summary(run_dir, run_summary)


def ensure_external_job_active(
    run_dir: Path,
    *,
    job: dict[str, Any],
    jobs_payload: dict[str, Any],
    action: str,
) -> None:
    """Ensures an external role job is active before completion or failure."""
    if job.get("backend") != "external_ai":
        raise ValueError(f"Job '{job['job_id']}' is not an external AI role")
    if not dependencies_completed(jobs_payload, job):
        raise ValueError(f"Job '{job['job_id']}' is waiting on dependencies")
    if job.get("status") != "running":
        raise ValueError(f"Job '{job['job_id']}' must be claimed before {action}")

    run_summary = load_run_summary(run_dir)
    if job["role"] == "coder" and run_summary.get("next_action") != "implement_change":
        raise ValueError("Coder job cannot be completed before the run reaches implement_change")
    if job["role"] == "reviewer" and run_summary.get("next_action") != "review_result":
        raise ValueError("Reviewer job cannot be completed before the run reaches review_result")


def start_or_continue_run(
    run_dir: Path,
    *,
    sandbox_adapter: str | None = None,
) -> dict[str, Any]:
    """Runs local orchestration steps until the next external or approval boundary."""
    sandbox_adapter = resolve_run_sandbox_adapter(run_dir, requested_adapter_id=sandbox_adapter)
    record_selected_sandbox_adapter(run_dir, sandbox_adapter=sandbox_adapter)
    build_workspace_for_run(run_dir)
    jobs_payload = ensure_jobs_seeded(run_dir, sandbox_adapter=sandbox_adapter)

    while True:
        jobs_payload = load_jobs(run_dir)
        next_job = find_next_job(jobs_payload)
        if next_job is None:
            break
        if next_job.get("status") in {"failed", "blocked"}:
            break
        if not dependencies_completed(jobs_payload, next_job):
            break

        if next_job.get("backend") == "external_ai":
            break

        execute_local_job(
            run_dir,
            jobs_payload,
            next_job,
            sandbox_adapter=sandbox_adapter,
        )
        current_run_summary = load_run_summary(run_dir)
        if run_summary_blocks_orchestration(current_run_summary):
            if next_job.get("role") == "context_loader":
                refreshed_jobs = load_jobs(run_dir)
                workspace_job = find_job(refreshed_jobs, "workspace_prepare")
                if (
                    workspace_job.get("status") == "queued"
                    and dependencies_completed(refreshed_jobs, workspace_job)
                ):
                    continue
            break

    return {
        "run_id": run_dir.name,
        "run_dir": str(run_dir.relative_to(ROOT)).replace("\\", "/"),
        "status": load_run_summary(run_dir).get("status"),
        "next_action": load_run_summary(run_dir).get("next_action"),
        "jobs": load_jobs(run_dir),
    }


def claim_job(run_dir: Path, *, job_id: str, claimed_by: str) -> dict[str, Any]:
    """Claims an external job for execution."""
    jobs_payload = load_jobs(run_dir)
    job = find_job(jobs_payload, job_id)
    job_is_claimable(run_dir, job, jobs_payload)
    result = build_job_result(job, status="running", summary=f"Claimed by {claimed_by}.")
    update_job_status(run_dir, jobs_payload, job, status="running", claimed_by=claimed_by, result_payload=result)
    return {
        "run_id": run_dir.name,
        "job": job,
        "jobs": load_jobs(run_dir),
    }


def mark_job_dispatched(
    run_dir: Path,
    *,
    job_id: str,
    runtime_target: str,
    runtime_ref: str,
    dispatched_by: str,
) -> dict[str, Any]:
    """Marks an external job as dispatched to a runtime target."""
    jobs_payload = load_jobs(run_dir)
    job = find_job(jobs_payload, job_id)
    if job.get("backend") != "external_ai":
        raise ValueError(f"Job '{job_id}' is not an external AI role")
    update_job_dispatch(
        run_dir,
        jobs_payload,
        job,
        dispatch_status="dispatched",
        runtime_target=runtime_target,
        runtime_ref=runtime_ref,
    )
    trace_event(
        run_dir,
        phase="dispatcher",
        job_id=job_id,
        requested_by=dispatched_by,
        category="external_job",
        item=job_id,
        reason="external_job_dispatched_to_runtime",
        source_artifact=jobs_dir(run_dir) / f"{job_id}.json",
        resolution="resolved",
        extra={
            "runtime_target": runtime_target,
            "runtime_ref": runtime_ref,
        },
    )
    return find_job(load_jobs(run_dir), job_id)


def read_external_payload(
    *,
    summary: str,
    result_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    """Normalizes an external completion payload."""
    payload = dict(result_payload or {})
    if summary and not payload.get("summary"):
        payload["summary"] = summary
    return payload


def complete_external_job(
    run_dir: Path,
    *,
    job_id: str,
    summary: str,
    result_payload: dict[str, Any] | None,
    sandbox_adapter: str | None = None,
) -> dict[str, Any]:
    """Completes an external role job and resumes orchestration."""
    jobs_payload = load_jobs(run_dir)
    job = find_job(jobs_payload, job_id)
    ensure_external_job_active(
        run_dir,
        job=job,
        jobs_payload=jobs_payload,
        action="completion",
    )
    payload = read_external_payload(summary=summary, result_payload=result_payload)

    if job["role"] == "coder":
        output = apply_stage.build_output(
            run_dir,
            explicit_paths=[normalize_rel_path(item) for item in payload.get("applied_files", [])],
            summary_text=payload.get("summary", "External coder applied workspace changes."),
            applied_by=payload.get("applied_by", "coder"),
            allow_empty_diff=bool(payload.get("allow_empty_diff", False)),
        )
    elif job["role"] == "reviewer":
        output = review_stage.build_output(
            run_dir,
            conclusion=payload.get("conclusion", "passed"),
            summary_text=payload.get("summary", "External reviewer completed structured review."),
            reviewed_by=payload.get("reviewed_by", "reviewer"),
            findings=[str(item) for item in payload.get("findings", [])],
            risks=[str(item) for item in payload.get("risks", [])],
        )
    else:
        output = payload

    result = build_job_result(
        job,
        status="completed",
        summary=payload.get("summary", f"External job '{job_id}' completed."),
        output=output,
    )
    update_job_status(run_dir, jobs_payload, job, status="completed", result_payload=result)
    resumed = start_or_continue_run(run_dir, sandbox_adapter=sandbox_adapter)
    if job["role"] == "coder":
        refreshed_jobs = load_jobs(run_dir)
        reviewer_job = find_job(refreshed_jobs, "reviewer")
        if reviewer_job.get("status") == "queued":
            trace_event(
                run_dir,
                phase="reviewer_handoff",
                job_id="reviewer",
                requested_by="executor",
                category="external_job",
                item="reviewer",
                reason="reviewer_ready_after_coder_and_verification",
                source_artifact=jobs_dir(run_dir) / "reviewer.json",
                resolution="resolved",
                after_summary={
                    "next_action": resumed.get("next_action", ""),
                    "sandbox_adapter": sandbox_adapter,
                },
            )
    return {
        "run_id": run_dir.name,
        "job": find_job(load_jobs(run_dir), job_id),
        "resume": resumed,
    }


def fail_external_job(
    run_dir: Path,
    *,
    job_id: str,
    summary: str,
    reason: str,
) -> dict[str, Any]:
    """Marks an external role job as failed."""
    jobs_payload = load_jobs(run_dir)
    job = find_job(jobs_payload, job_id)
    ensure_external_job_active(
        run_dir,
        job=job,
        jobs_payload=jobs_payload,
        action="failure",
    )
    result = build_job_result(job, status="failed", summary=summary or "External job failed.", reason=reason)
    update_job_status(run_dir, jobs_payload, job, status="failed", result_payload=result)
    mark_external_job_failed(run_dir, job, reason=reason, summary=summary)
    return {
        "run_id": run_dir.name,
        "job": find_job(load_jobs(run_dir), job_id),
        "status": load_run_summary(run_dir).get("status"),
        "next_action": load_run_summary(run_dir).get("next_action"),
    }
