from __future__ import annotations

import json
import shutil
import subprocess
import sys

from pathlib import Path
from uuid import uuid4

from scripts.agents.workspace import cleanup_workspace


ROOT = Path(__file__).resolve().parents[2]
TASKS_PATH = ROOT / ".vscode" / "tasks.json"


def run_module(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def cleanup_run_dir(run_dir: Path) -> None:
    if (run_dir / "workspace.json").is_file():
        cleanup_workspace(run_dir / "workspace.json", source_root=ROOT, keep_workspace=False)
    shutil.rmtree(run_dir, ignore_errors=True)


def approve_run_checks(run_id: str) -> dict[str, object]:
    result = run_module(
        "-m",
        "scripts.agents.lifecycle.approve",
        "--run-id",
        run_id,
        "--checkpoint",
        "run_checks",
        "--action",
        "approve",
    )
    assert result.returncode == 0, result.stderr or result.stdout
    return json.loads(result.stdout)


def create_approval_ready_run(run_id: str) -> Path:
    run_dir = ROOT / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    plan_payload = {
        "plan": [
            {"id": "classify_task", "status": "completed"},
            {"id": "load_context", "status": "completed"},
            {"id": "implement_change", "status": "completed"},
            {"id": "verify_change", "status": "completed"},
            {"id": "review_result", "status": "completed"},
            {"id": "request_approval", "status": "pending"},
        ]
    }
    approval_payload = {
        "needs_manual_review": False,
        "escalation_reasons": [],
        "checkpoints": [
            {"id": "run_checks", "required": True, "status": "approved", "reason": "tests done"},
            {"id": "commit", "required": True, "status": "awaiting_approval", "reason": "commit approval required"},
            {"id": "push", "required": True, "status": "awaiting_approval", "reason": "push approval required"},
        ],
    }
    run_summary = {
        "run_id": run_id,
        "status": "review_passed_pending_approval",
        "next_action": "request_approval",
        "task_type": {"id": "docs_only_change", "label": "Docs-Only Change"},
        "changed_paths": ["docs/swarm-usage.md"],
        "artifacts": {},
        "approval": approval_payload,
        "commit": {"commit_created": False},
    }

    (run_dir / "plan.json").write_text(json.dumps(plan_payload), encoding="utf-8")
    (run_dir / "approval-checkpoints.json").write_text(json.dumps(approval_payload), encoding="utf-8")
    (run_dir / "run-summary.json").write_text(json.dumps(run_summary), encoding="utf-8")
    return run_dir


def test_plan_task_returns_plan_preview() -> None:
    result = run_module(
        "-m",
        "scripts.agents.mcp",
        "plan_task",
        "--prompt",
        "Обновить swarm usage docs",
        "--pretty",
    )

    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert payload["tool"] == "plan_task"
    assert payload["plan"]["verification_profile"]["profile_id"] == "docs_only_change"
    assert "recommended_agents" in payload["plan"]


def test_start_swarm_run_prepares_workspace_and_local_jobs() -> None:
    run_id = f"mcp-smoke-{uuid4().hex}"
    result = run_module(
        "-m",
        "scripts.agents.mcp",
        "start_swarm_run",
        "--prompt",
        "Обновить swarm usage docs",
        "--run-id",
        run_id,
        "--pretty",
    )

    run_dir = ROOT / "runs" / run_id
    try:
        assert result.returncode == 0, result.stderr or result.stdout
        payload = json.loads(result.stdout)
        assert payload["tool"] == "start_swarm_run"
        assert (run_dir / "workspace.json").is_file()
        assert (run_dir / "jobs" / "index.json").is_file()

        jobs = read_json(run_dir / "jobs" / "index.json")
        statuses = {job["job_id"]: job["status"] for job in jobs["jobs"]}
        assert statuses["planner"] == "completed"
        assert statuses["context_loader"] == "completed"
        assert statuses["workspace_prepare"] == "completed"
        assert statuses["coder"] == "queued"

        summary = read_json(run_dir / "run-summary.json")
        assert summary["status"] == "context_loaded_pending_run_checks_approval"
        assert summary["next_action"] == "approve_run_checks_before_implementation"
        assert "workspace" in summary["artifacts"]
        assert "jobs_index" in summary["artifacts"]
    finally:
        cleanup_run_dir(run_dir)


def test_show_run_status_includes_workspace_and_jobs() -> None:
    run_id = f"mcp-status-{uuid4().hex}"
    run_module(
        "-m",
        "scripts.agents.mcp",
        "start_swarm_run",
        "--prompt",
        "Обновить swarm usage docs",
        "--run-id",
        run_id,
    )

    run_dir = ROOT / "runs" / run_id
    try:
        result = run_module(
            "-m",
            "scripts.agents.mcp",
            "show_run_status",
            "--run-id",
            run_id,
        )

        assert result.returncode == 0, result.stderr or result.stdout
        payload = json.loads(result.stdout)
        assert payload["tool"] == "show_run_status"
        assert payload["workspace"]["mode"] in {"git_worktree", "snapshot_copy"}
        assert run_id in payload["workspace"]["root_path"]
        assert payload["jobs"]["total_jobs"] == 8
        assert {job["job_id"] for job in payload["jobs"]["external_jobs"]} == {"coder", "reviewer"}
    finally:
        cleanup_run_dir(run_dir)


def test_continue_swarm_run_resumes_after_run_checks_approval() -> None:
    run_id = f"mcp-continue-{uuid4().hex}"
    run_module(
        "-m",
        "scripts.agents.mcp",
        "start_swarm_run",
        "--prompt",
        "Обновить swarm usage docs",
        "--run-id",
        run_id,
    )

    run_dir = ROOT / "runs" / run_id
    try:
        approve_payload = approve_run_checks(run_id)
        assert approve_payload["status"] == "approved_for_implementation"

        result = run_module(
            "-m",
            "scripts.agents.mcp",
            "continue_swarm_run",
            "--run-id",
            run_id,
            "--sandbox-adapter",
            "local_dry_run",
            "--pretty",
        )
        assert result.returncode == 0, result.stderr or result.stdout
        payload = json.loads(result.stdout)
        assert payload["tool"] == "continue_swarm_run"
        assert payload["status"]["status"] == "approved_for_implementation"
        assert payload["status"]["next_action"] == "implement_change"

        jobs = read_json(run_dir / "jobs" / "index.json")
        status_by_job = {job["job_id"]: job["status"] for job in jobs["jobs"]}
        assert status_by_job["coder"] == "queued"
        assert status_by_job["tester"] == "queued"
    finally:
        cleanup_run_dir(run_dir)


def test_external_role_jobs_resume_pipeline_until_commit_approval() -> None:
    run_id = f"mcp-external-{uuid4().hex}"
    run_module(
        "-m",
        "scripts.agents.mcp",
        "start_swarm_run",
        "--prompt",
        "Обновить swarm usage docs",
        "--run-id",
        run_id,
    )

    run_dir = ROOT / "runs" / run_id
    try:
        approve_payload = approve_run_checks(run_id)
        assert approve_payload["status"] == "approved_for_implementation"

        claim_coder = run_module(
            "-m",
            "scripts.agents.mcp",
            "claim_role_job",
            "--run-id",
            run_id,
            "--job-id",
            "coder",
            "--claimed-by",
            "codex-runtime",
        )
        assert claim_coder.returncode == 0, claim_coder.stderr or claim_coder.stdout

        workspace_root = Path(read_json(run_dir / "workspace.json")["workspace"]["root_path"])
        target_file = workspace_root / "docs" / "swarm-usage.md"
        original_text = target_file.read_text(encoding="utf-8")
        target_file.write_text(original_text + "\nPhase 3 MCP smoke coverage.\n", encoding="utf-8")

        complete_coder = run_module(
            "-m",
            "scripts.agents.mcp",
            "complete_role_job",
            "--run-id",
            run_id,
            "--job-id",
            "coder",
            "--sandbox-adapter",
            "local_dry_run",
            "--result-json",
            json.dumps(
                {
                    "summary": "External coder updated docs in isolated workspace.",
                    "applied_by": "codex-runtime",
                    "applied_files": ["docs/swarm-usage.md"],
                },
                ensure_ascii=False,
            ),
        )
        assert complete_coder.returncode == 0, complete_coder.stderr or complete_coder.stdout
        complete_coder_payload = json.loads(complete_coder.stdout)
        assert complete_coder_payload["resume"]["next_action"] == "review_result"
        assert (run_dir / "verification-plan.json").is_file()
        assert (run_dir / "sandbox-plan.json").is_file()
        assert (run_dir / "sandbox-result.json").is_file()

        jobs_after_coder = read_json(run_dir / "jobs" / "index.json")
        status_by_job = {job["job_id"]: job["status"] for job in jobs_after_coder["jobs"]}
        assert status_by_job["tester"] == "completed"
        assert status_by_job["sandbox_runner"] == "completed"
        assert status_by_job["reviewer"] == "queued"

        claim_reviewer = run_module(
            "-m",
            "scripts.agents.mcp",
            "claim_role_job",
            "--run-id",
            run_id,
            "--job-id",
            "reviewer",
            "--claimed-by",
            "review-runtime",
        )
        assert claim_reviewer.returncode == 0, claim_reviewer.stderr or claim_reviewer.stdout

        complete_reviewer = run_module(
            "-m",
            "scripts.agents.mcp",
            "complete_role_job",
            "--run-id",
            run_id,
            "--job-id",
            "reviewer",
            "--result-json",
            json.dumps(
                {
                    "summary": "Structured review completed.",
                    "reviewed_by": "review-runtime",
                    "conclusion": "passed",
                    "findings": [],
                    "risks": ["Dry-run sandbox only"],
                },
                ensure_ascii=False,
            ),
        )
        assert complete_reviewer.returncode == 0, complete_reviewer.stderr or complete_reviewer.stdout
        review_payload = json.loads(complete_reviewer.stdout)
        assert review_payload["resume"]["status"] == "awaiting_commit_approval"
        assert (run_dir / "approval-request.json").is_file()
        assert (run_dir / "jobs" / "reviewer-result.json").is_file()

        summary = read_json(run_dir / "run-summary.json")
        assert summary["status"] == "awaiting_commit_approval"
        assert summary["next_action"] == "await_commit_approval"
    finally:
        cleanup_run_dir(run_dir)


def test_fail_role_job_marks_external_job_failure() -> None:
    run_id = f"mcp-fail-{uuid4().hex}"
    run_module(
        "-m",
        "scripts.agents.mcp",
        "start_swarm_run",
        "--prompt",
        "Обновить swarm usage docs",
        "--run-id",
        run_id,
    )

    run_dir = ROOT / "runs" / run_id
    try:
        approve_run_checks(run_id)
        claim = run_module(
            "-m",
            "scripts.agents.mcp",
            "claim_role_job",
            "--run-id",
            run_id,
            "--job-id",
            "coder",
            "--claimed-by",
            "codex-runtime",
        )
        assert claim.returncode == 0, claim.stderr or claim.stdout

        fail = run_module(
            "-m",
            "scripts.agents.mcp",
            "fail_role_job",
            "--run-id",
            run_id,
            "--job-id",
            "coder",
            "--summary",
            "Implementation failed.",
            "--reason",
            "workspace_conflict",
        )
        assert fail.returncode == 0, fail.stderr or fail.stdout
        failed_payload = json.loads(fail.stdout)
        assert failed_payload["job"]["status"] == "failed"
        assert failed_payload["status"] == "external_job_failed"
        assert failed_payload["next_action"] == "resolve_coder_failure"
    finally:
        cleanup_run_dir(run_dir)


def test_commit_and_push_approval_wrappers_delegate_to_request_approval() -> None:
    run_id = f"mcp-approval-{uuid4().hex}"
    run_dir = create_approval_ready_run(run_id)
    try:
        commit = run_module(
            "-m",
            "scripts.agents.mcp",
            "request_commit_approval",
            "--run-id",
            run_id,
            "--summary",
            "request commit approval",
            "--pretty",
        )
        assert commit.returncode == 0, commit.stderr or commit.stdout
        commit_payload = json.loads(commit.stdout)
        assert commit_payload["tool"] == "request_commit_approval"
        assert (run_dir / "approval-request.json").is_file()

        push_ready = read_json(run_dir / "run-summary.json")
        push_ready["status"] = "approved_for_push_decision"
        push_ready["next_action"] = "request_push_approval"
        push_ready["approval"]["checkpoints"][1]["status"] = "approved"
        push_ready["approval"]["checkpoints"][2]["status"] = "awaiting_approval"
        push_ready["commit"] = {"commit_created": True}
        push_ready["artifacts"]["commit_result"] = "runs/%s/commit-result.json" % run_id
        (run_dir / "commit-result.json").write_text(json.dumps({"commit": "abc123"}), encoding="utf-8")
        (run_dir / "run-summary.json").write_text(json.dumps(push_ready), encoding="utf-8")
        (run_dir / "approval-checkpoints.json").write_text(json.dumps(push_ready["approval"]), encoding="utf-8")

        push = run_module(
            "-m",
            "scripts.agents.mcp",
            "request_push_approval",
            "--run-id",
            run_id,
            "--summary",
            "request push approval",
            "--pretty",
        )
        assert push.returncode == 0, push.stderr or push.stdout
        push_payload = json.loads(push.stdout)
        assert push_payload["tool"] == "request_push_approval"
    finally:
        cleanup_run_dir(run_dir)


def test_tasks_json_calls_front_door_commands() -> None:
    tasks = read_json(TASKS_PATH)
    labels = {task["label"] for task in tasks["tasks"]}
    assert labels == {
        "Plan task",
        "Start swarm run",
        "Continue swarm run",
        "Show run status",
        "Request commit approval",
        "Request push approval",
    }

    for task in tasks["tasks"]:
        command = task["command"]
        args = task["args"]
        assert "scripts.agents.mcp" in args
        assert command.endswith(r"venv\Scripts\python.exe")
