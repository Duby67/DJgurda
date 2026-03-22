from __future__ import annotations

import json
import shutil

from pathlib import Path
from uuid import uuid4

import pytest

from scripts.agents.executor import (
    claim_job,
    complete_external_job,
    fail_external_job,
    load_jobs,
    start_or_continue_run,
)
from scripts.agents.lifecycle.approve import build_output as approve_checkpoint
from scripts.agents.routing.run import build_run_bundle
from scripts.agents.sandbox_adapters import LOCAL_DRY_RUN_ADAPTER
from scripts.agents.workspace import cleanup_workspace
from scripts.config import ROOT


def cleanup_run_dir(run_dir: Path) -> None:
    if (run_dir / "workspace.json").is_file():
        cleanup_workspace(run_dir / "workspace.json", source_root=ROOT, keep_workspace=False)
    shutil.rmtree(run_dir, ignore_errors=True)


def create_started_run(*, prompt: str = "Обновить swarm usage docs") -> Path:
    run_id = f"executor-{uuid4().hex}"
    run_dir = ROOT / "runs" / run_id
    build_run_bundle(prompt=prompt, paths=[], run_id=run_id, run_dir=run_dir)
    start_or_continue_run(run_dir, sandbox_adapter=LOCAL_DRY_RUN_ADAPTER)
    return run_dir


def test_start_or_continue_run_builds_workspace_jobs_and_stops_at_external_boundary() -> None:
    run_dir = create_started_run()
    try:
        assert (run_dir / "workspace.json").is_file()
        assert (run_dir / "jobs" / "index.json").is_file()

        jobs = load_jobs(run_dir)
        status_by_job = {job["job_id"]: job["status"] for job in jobs["jobs"]}
        assert status_by_job["planner"] == "completed"
        assert status_by_job["context_loader"] == "completed"
        assert status_by_job["workspace_prepare"] == "completed"
        assert status_by_job["coder"] == "queued"
        assert status_by_job["tester"] == "queued"

        summary = json.loads((run_dir / "run-summary.json").read_text(encoding="utf-8"))
        assert summary["status"] == "context_loaded_pending_run_checks_approval"
        assert summary["next_action"] == "approve_run_checks_before_implementation"
    finally:
        cleanup_run_dir(run_dir)


def test_complete_external_job_requires_claim_before_completion() -> None:
    run_dir = create_started_run()
    try:
        approve_checkpoint(run_dir, checkpoint_id="run_checks", action="approve", note="ready")

        with pytest.raises(ValueError, match="must be claimed before completion"):
            complete_external_job(
                run_dir,
                job_id="coder",
                summary="complete without claim",
                result_payload={"applied_files": ["docs/swarm-usage.md"]},
                sandbox_adapter=LOCAL_DRY_RUN_ADAPTER,
            )
    finally:
        cleanup_run_dir(run_dir)


def test_external_job_flow_progresses_to_commit_approval() -> None:
    run_dir = create_started_run()
    try:
        approve_checkpoint(run_dir, checkpoint_id="run_checks", action="approve", note="ready")
        claim_job(run_dir, job_id="coder", claimed_by="codex-runtime")

        workspace_root = Path(json.loads((run_dir / "workspace.json").read_text(encoding="utf-8"))["workspace"]["root_path"])
        target_file = workspace_root / "docs" / "swarm-usage.md"
        target_file.write_text(
            target_file.read_text(encoding="utf-8") + "\nExecutor smoke change.\n",
            encoding="utf-8",
        )

        coder_result = complete_external_job(
            run_dir,
            job_id="coder",
            summary="coder done",
            result_payload={
                "summary": "Coder updated swarm docs in isolated workspace.",
                "applied_by": "codex-runtime",
                "applied_files": ["docs/swarm-usage.md"],
            },
            sandbox_adapter=LOCAL_DRY_RUN_ADAPTER,
        )
        assert coder_result["resume"]["next_action"] == "review_result"
        assert (run_dir / "verification-result.json").is_file()
        assert (run_dir / "sandbox-result.json").is_file()

        claim_job(run_dir, job_id="reviewer", claimed_by="review-runtime")
        reviewer_result = complete_external_job(
            run_dir,
            job_id="reviewer",
            summary="reviewer done",
            result_payload={
                "summary": "Structured review completed.",
                "reviewed_by": "review-runtime",
                "conclusion": "passed",
                "findings": [],
                "risks": ["Dry-run sandbox only"],
            },
            sandbox_adapter=LOCAL_DRY_RUN_ADAPTER,
        )
        assert reviewer_result["resume"]["status"] == "awaiting_commit_approval"

        summary = json.loads((run_dir / "run-summary.json").read_text(encoding="utf-8"))
        assert summary["status"] == "awaiting_commit_approval"
        assert summary["next_action"] == "await_commit_approval"
        assert (run_dir / "approval-request.json").is_file()
    finally:
        cleanup_run_dir(run_dir)


def test_fail_external_job_records_failure_state() -> None:
    run_dir = create_started_run()
    try:
        approve_checkpoint(run_dir, checkpoint_id="run_checks", action="approve", note="ready")
        claim_job(run_dir, job_id="coder", claimed_by="codex-runtime")

        payload = fail_external_job(
            run_dir,
            job_id="coder",
            summary="coder failed",
            reason="workspace_conflict",
        )

        assert payload["status"] == "external_job_failed"
        assert payload["next_action"] == "resolve_coder_failure"
    finally:
        cleanup_run_dir(run_dir)
