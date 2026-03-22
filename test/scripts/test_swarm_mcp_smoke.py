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


def test_start_autonomous_swarm_run_reaches_first_stable_boundary() -> None:
    run_id = f"mcp-auto-start-{uuid4().hex}"
    result = run_module(
        "-m",
        "scripts.agents.mcp",
        "start_autonomous_swarm_run",
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
        assert payload["tool"] == "start_autonomous_swarm_run"
        assert (run_dir / "workspace.json").is_file()
        assert (run_dir / "jobs" / "index.json").is_file()
        assert payload["cycle"]["cycle_status"] == "human_or_terminal_boundary"
        assert payload["cycle"]["run_status"] == "context_loaded_pending_run_checks_approval"
        assert payload["status"]["status"] == "context_loaded_pending_run_checks_approval"
        assert payload["status"]["next_action"] == "approve_run_checks_before_implementation"
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
        assert payload["selected_sandbox_adapter"] == "local_dry_run"
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


def test_run_dispatcher_builds_work_item_and_dispatcher_artifacts() -> None:
    run_id = f"mcp-dispatch-{uuid4().hex}"
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
        dispatched = run_module(
            "-m",
            "scripts.agents.mcp",
            "run_dispatcher",
            "--run-id",
            run_id,
            "--pretty",
        )

        assert dispatched.returncode == 0, dispatched.stderr or dispatched.stdout
        payload = json.loads(dispatched.stdout)
        assert payload["tool"] == "run_dispatcher"
        assert payload["dispatch_status"] == "dispatched"
        assert payload["job"]["job_id"] == "coder"
        assert payload["job"]["dispatch_status"] == "dispatched"
        assert payload["work_item"]["role"] == "coder"
        assert payload["work_item"]["completion_contract"]["command"] == "complete_role_job"
        assert payload["work_item"]["completion_contract"]["preferred_command"] == "submit_role_result"
        assert payload["work_item"]["completion_inbox"].endswith("jobs/coder-completion.json")
        assert (run_dir / "jobs" / "coder-dispatch.json").is_file()
        assert (run_dir / "dispatcher-state.json").is_file()
        runtime_trace = (run_dir / "runtime-context-trace.jsonl").read_text(encoding="utf-8").splitlines()
        assert runtime_trace
        assert any(json.loads(line)["phase"] == "dispatcher" for line in runtime_trace)

        dispatcher_state = read_json(run_dir / "dispatcher-state.json")
        assert dispatcher_state["current_job"]["job_id"] == "coder"
    finally:
        cleanup_run_dir(run_dir)


def test_submit_role_result_writes_completion_inbox_and_advances_pipeline() -> None:
    run_id = f"mcp-submit-{uuid4().hex}"
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
        dispatch = run_module(
            "-m",
            "scripts.agents.mcp",
            "run_dispatcher",
            "--run-id",
            run_id,
            "--runtime-target",
            "codex-runtime",
        )
        assert dispatch.returncode == 0, dispatch.stderr or dispatch.stdout

        workspace_root = Path(read_json(run_dir / "workspace.json")["workspace"]["root_path"])
        target_file = workspace_root / "docs" / "swarm-usage.md"
        target_file.write_text(
            target_file.read_text(encoding="utf-8") + "\nSubmit role result smoke change.\n",
            encoding="utf-8",
        )

        submit = run_module(
            "-m",
            "scripts.agents.mcp",
            "submit_role_result",
            "--run-id",
            run_id,
            "--job-id",
            "coder",
            "--runtime-target",
            "codex-runtime",
            "--sandbox-adapter",
            "local_dry_run",
            "--result-json",
            json.dumps(
                {
                    "summary": "Submitted via completion inbox.",
                    "applied_by": "codex-runtime",
                    "applied_files": ["docs/swarm-usage.md"],
                },
                ensure_ascii=False,
            ),
            "--pretty",
        )
        assert submit.returncode == 0, submit.stderr or submit.stdout
        payload = json.loads(submit.stdout)
        assert payload["tool"] == "submit_role_result"
        assert payload["submitted_payload"]["job_id"] == "coder"
        assert payload["submitted_payload"]["status"] == "completed"
        assert payload["loop"]["events"][0]["type"] == "completion_consumed"
        assert payload["loop"]["loop_status"] == "dispatched_external_job"
        assert payload["loop"]["job"]["job_id"] == "reviewer"
        assert (run_dir / "jobs" / "coder-completion-processed.json").is_file()
    finally:
        cleanup_run_dir(run_dir)


def test_run_autonomous_cycle_drives_run_to_external_and_human_boundaries() -> None:
    run_id = f"mcp-auto-{uuid4().hex}"
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

        first_cycle = run_module(
            "-m",
            "scripts.agents.mcp",
            "run_autonomous_cycle",
            "--run-id",
            run_id,
            "--sandbox-adapter",
            "local_dry_run",
            "--pretty",
        )
        assert first_cycle.returncode == 0, first_cycle.stderr or first_cycle.stdout
        first_payload = json.loads(first_cycle.stdout)
        assert first_payload["tool"] == "run_autonomous_cycle"
        assert first_payload["cycle_status"] == "dispatched_external_job"
        assert first_payload["loop"]["job"]["job_id"] == "coder"

        workspace_root = Path(read_json(run_dir / "workspace.json")["workspace"]["root_path"])
        target_file = workspace_root / "docs" / "swarm-usage.md"
        target_file.write_text(
            target_file.read_text(encoding="utf-8") + "\nAutonomous cycle coder change.\n",
            encoding="utf-8",
        )
        (run_dir / "jobs" / "coder-completion.json").write_text(
            json.dumps(
                {
                    "status": "completed",
                    "summary": "Coder completion for autonomous cycle.",
                    "sandbox_adapter": "local_dry_run",
                    "result": {
                        "summary": "Coder completion for autonomous cycle.",
                        "applied_by": "codex-runtime",
                        "applied_files": ["docs/swarm-usage.md"],
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        second_cycle = run_module(
            "-m",
            "scripts.agents.mcp",
            "run_autonomous_cycle",
            "--run-id",
            run_id,
            "--sandbox-adapter",
            "local_dry_run",
            "--pretty",
        )
        assert second_cycle.returncode == 0, second_cycle.stderr or second_cycle.stdout
        second_payload = json.loads(second_cycle.stdout)
        assert second_payload["cycle_status"] == "dispatched_external_job"
        assert second_payload["loop"]["job"]["job_id"] == "reviewer"

        (run_dir / "jobs" / "reviewer-completion.json").write_text(
            json.dumps(
                {
                    "status": "completed",
                    "summary": "Reviewer completion for autonomous cycle.",
                    "result": {
                        "summary": "Reviewer completion for autonomous cycle.",
                        "reviewed_by": "review-runtime",
                        "conclusion": "passed",
                        "findings": [],
                        "risks": ["Dry-run sandbox only"],
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        third_cycle = run_module(
            "-m",
            "scripts.agents.mcp",
            "run_autonomous_cycle",
            "--run-id",
            run_id,
            "--sandbox-adapter",
            "local_dry_run",
            "--pretty",
        )
        assert third_cycle.returncode == 0, third_cycle.stderr or third_cycle.stdout
        third_payload = json.loads(third_cycle.stdout)
        assert third_payload["cycle_status"] == "human_or_terminal_boundary"
        assert third_payload["run_status"] == "awaiting_commit_approval"
        assert third_payload["next_action"] == "await_commit_approval"
    finally:
        cleanup_run_dir(run_dir)


def test_run_dispatcher_loop_consumes_completion_inbox_and_advances_pipeline() -> None:
    run_id = f"mcp-loop-{uuid4().hex}"
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
        first_loop = run_module(
            "-m",
            "scripts.agents.mcp",
            "run_dispatcher_loop",
            "--run-id",
            run_id,
            "--sandbox-adapter",
            "local_dry_run",
            "--pretty",
        )
        assert first_loop.returncode == 0, first_loop.stderr or first_loop.stdout
        first_payload = json.loads(first_loop.stdout)
        assert first_payload["tool"] == "run_dispatcher_loop"
        assert first_payload["loop_status"] == "dispatched_external_job"
        assert first_payload["job"]["job_id"] == "coder"

        workspace_root = Path(read_json(run_dir / "workspace.json")["workspace"]["root_path"])
        target_file = workspace_root / "docs" / "swarm-usage.md"
        target_file.write_text(
            target_file.read_text(encoding="utf-8") + "\nDispatcher loop smoke change.\n",
            encoding="utf-8",
        )

        coder_completion = {
            "status": "completed",
            "summary": "Coder completion inbox artifact processed.",
            "sandbox_adapter": "local_dry_run",
            "result": {
                "summary": "Coder completion inbox artifact processed.",
                "applied_by": "codex-runtime",
                "applied_files": ["docs/swarm-usage.md"],
            },
        }
        (run_dir / "jobs" / "coder-completion.json").write_text(
            json.dumps(coder_completion, ensure_ascii=False),
            encoding="utf-8",
        )

        second_loop = run_module(
            "-m",
            "scripts.agents.mcp",
            "run_dispatcher_loop",
            "--run-id",
            run_id,
            "--sandbox-adapter",
            "local_dry_run",
            "--pretty",
        )
        assert second_loop.returncode == 0, second_loop.stderr or second_loop.stdout
        second_payload = json.loads(second_loop.stdout)
        assert second_payload["tool"] == "run_dispatcher_loop"
        assert second_payload["events"][0]["type"] == "completion_consumed"
        assert second_payload["events"][0]["job_id"] == "coder"
        assert second_payload["loop_status"] == "dispatched_external_job"
        assert second_payload["job"]["job_id"] == "reviewer"
        assert (run_dir / "jobs" / "coder-completion-processed.json").is_file()

        jobs_payload = read_json(run_dir / "jobs" / "index.json")
        status_by_job = {job["job_id"]: job["status"] for job in jobs_payload["jobs"]}
        assert status_by_job["coder"] == "completed"
        assert status_by_job["tester"] == "completed"
        assert status_by_job["sandbox_runner"] == "completed"
        assert status_by_job["reviewer"] == "running"
    finally:
        cleanup_run_dir(run_dir)


def test_show_job_queue_and_diff_preview_generate_views() -> None:
    run_id = f"mcp-views-{uuid4().hex}"
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
        run_module(
            "-m",
            "scripts.agents.mcp",
            "run_dispatcher",
            "--run-id",
            run_id,
        )

        workspace_root = Path(read_json(run_dir / "workspace.json")["workspace"]["root_path"])
        target_file = workspace_root / "docs" / "swarm-usage.md"
        target_file.write_text(
            target_file.read_text(encoding="utf-8") + "\nDispatcher view smoke change.\n",
            encoding="utf-8",
        )

        queue = run_module(
            "-m",
            "scripts.agents.mcp",
            "show_job_queue",
            "--run-id",
            run_id,
            "--human",
        )
        assert queue.returncode == 0, queue.stderr or queue.stdout
        queue_payload = json.loads(queue.stdout)
        assert queue_payload["tool"] == "show_job_queue"
        assert "coder" in queue_payload["human"]
        assert (run_dir / "job-queue.md").is_file()

        diff = run_module(
            "-m",
            "scripts.agents.mcp",
            "show_diff_preview",
            "--run-id",
            run_id,
            "--human",
        )
        assert diff.returncode == 0, diff.stderr or diff.stdout
        diff_payload = json.loads(diff.stdout)
        assert diff_payload["tool"] == "show_diff_preview"
        assert "swarm-usage.md" in diff_payload["human"]
        assert (run_dir / "diff-preview.md").is_file()

        status = run_module(
            "-m",
            "scripts.agents.mcp",
            "show_run_status",
            "--run-id",
            run_id,
            "--human",
        )
        assert status.returncode == 0, status.stderr or status.stdout
        status_payload = json.loads(status.stdout)
        assert status_payload["tool"] == "show_run_status"
        assert (run_dir / "run-status.md").is_file()
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

        dispatch_coder = run_module(
            "-m",
            "scripts.agents.mcp",
            "run_dispatcher",
            "--run-id",
            run_id,
            "--runtime-target",
            "codex-runtime",
        )
        assert dispatch_coder.returncode == 0, dispatch_coder.stderr or dispatch_coder.stdout
        dispatch_coder_payload = json.loads(dispatch_coder.stdout)
        assert dispatch_coder_payload["job"]["job_id"] == "coder"
        assert dispatch_coder_payload["job"]["dispatch_status"] == "dispatched"

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
        assert complete_coder_payload["dispatch"]["job"]["dispatch_status"] == "completed"
        assert (run_dir / "verification-plan.json").is_file()
        assert (run_dir / "sandbox-plan.json").is_file()
        assert (run_dir / "sandbox-result.json").is_file()

        jobs_after_coder = read_json(run_dir / "jobs" / "index.json")
        status_by_job = {job["job_id"]: job["status"] for job in jobs_after_coder["jobs"]}
        assert status_by_job["tester"] == "completed"
        assert status_by_job["sandbox_runner"] == "completed"
        assert status_by_job["reviewer"] == "queued"

        dispatch_reviewer = run_module(
            "-m",
            "scripts.agents.mcp",
            "run_dispatcher",
            "--run-id",
            run_id,
            "--runtime-target",
            "review-runtime",
        )
        assert dispatch_reviewer.returncode == 0, dispatch_reviewer.stderr or dispatch_reviewer.stdout
        dispatch_reviewer_payload = json.loads(dispatch_reviewer.stdout)
        assert dispatch_reviewer_payload["job"]["job_id"] == "reviewer"
        assert dispatch_reviewer_payload["job"]["dispatch_status"] == "dispatched"

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
        assert review_payload["dispatch"]["job"]["dispatch_status"] == "completed"
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
        assert failed_payload["dispatch"]["job"]["dispatch_status"] == "failed"
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


def test_checkpoint_action_wrappers_delegate_to_lifecycle_approve() -> None:
    run_id = f"mcp-approve-{uuid4().hex}"
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
        run_checks = run_module(
            "-m",
            "scripts.agents.mcp",
            "approve_run_checks",
            "--run-id",
            run_id,
            "--pretty",
        )
        assert run_checks.returncode == 0, run_checks.stderr or run_checks.stdout
        run_checks_payload = json.loads(run_checks.stdout)
        assert run_checks_payload["tool"] == "approve_run_checks"
        assert run_checks_payload["updated_checkpoint"]["id"] == "run_checks"
        assert run_checks_payload["updated_checkpoint"]["new_status"] == "approved"
    finally:
        cleanup_run_dir(run_dir)

    resume_run_id = f"mcp-runchecks-continue-{uuid4().hex}"
    run_module(
        "-m",
        "scripts.agents.mcp",
        "start_swarm_run",
        "--prompt",
        "Обновить swarm usage docs",
        "--run-id",
        resume_run_id,
    )
    resume_run_dir = ROOT / "runs" / resume_run_id
    try:
        resume = run_module(
            "-m",
            "scripts.agents.mcp",
            "approve_run_checks_and_continue",
            "--run-id",
            resume_run_id,
            "--sandbox-adapter",
            "local_dry_run",
            "--pretty",
        )
        assert resume.returncode == 0, resume.stderr or resume.stdout
        resume_payload = json.loads(resume.stdout)
        assert resume_payload["tool"] == "approve_run_checks_and_continue"
        assert resume_payload["approval"]["updated_checkpoint"]["id"] == "run_checks"
        assert resume_payload["approval"]["updated_checkpoint"]["new_status"] == "approved"
        assert resume_payload["cycle"]["cycle_status"] == "dispatched_external_job"
        assert resume_payload["cycle"]["loop"]["job"]["job_id"] == "coder"
    finally:
        cleanup_run_dir(resume_run_dir)

    commit_continue_run_id = f"mcp-commit-continue-{uuid4().hex}"
    run_module(
        "-m",
        "scripts.agents.mcp",
        "start_swarm_run",
        "--prompt",
        "Обновить swarm usage docs",
        "--run-id",
        commit_continue_run_id,
    )
    commit_continue_run_dir = ROOT / "runs" / commit_continue_run_id
    try:
        approve_run_checks(commit_continue_run_id)
        run_module(
            "-m",
            "scripts.agents.mcp",
            "run_dispatcher",
            "--run-id",
            commit_continue_run_id,
            "--runtime-target",
            "codex-runtime",
        )

        workspace_root = Path(read_json(commit_continue_run_dir / "workspace.json")["workspace"]["root_path"])
        target_file = workspace_root / "docs" / "swarm-usage.md"
        target_file.write_text(
            target_file.read_text(encoding="utf-8") + "\nApprove commit and continue smoke change.\n",
            encoding="utf-8",
        )

        coder_complete = run_module(
            "-m",
            "scripts.agents.mcp",
            "complete_role_job",
            "--run-id",
            commit_continue_run_id,
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
        assert coder_complete.returncode == 0, coder_complete.stderr or coder_complete.stdout

        run_module(
            "-m",
            "scripts.agents.mcp",
            "run_dispatcher",
            "--run-id",
            commit_continue_run_id,
            "--runtime-target",
            "review-runtime",
        )
        reviewer_complete = run_module(
            "-m",
            "scripts.agents.mcp",
            "complete_role_job",
            "--run-id",
            commit_continue_run_id,
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
        assert reviewer_complete.returncode == 0, reviewer_complete.stderr or reviewer_complete.stdout

        resume_commit = run_module(
            "-m",
            "scripts.agents.mcp",
            "approve_commit_and_continue",
            "--run-id",
            commit_continue_run_id,
            "--pretty",
        )
        assert resume_commit.returncode == 0, resume_commit.stderr or resume_commit.stdout
        resume_commit_payload = json.loads(resume_commit.stdout)
        assert resume_commit_payload["tool"] == "approve_commit_and_continue"
        assert resume_commit_payload["approval"]["updated_checkpoint"]["id"] == "commit"
        assert resume_commit_payload["approval"]["updated_checkpoint"]["new_status"] == "approved"
        assert resume_commit_payload["commit"]["commit_created"] is True
        assert resume_commit_payload["commit"]["status"] == "commit_created_pending_push_decision"
        assert resume_commit_payload["commit"]["next_action"] == "decide_on_push"
        assert (commit_continue_run_dir / "commit-result.json").is_file()
    finally:
        cleanup_run_dir(commit_continue_run_dir)

    push_continue_run_id = f"mcp-push-continue-{uuid4().hex}"
    run_module(
        "-m",
        "scripts.agents.mcp",
        "start_swarm_run",
        "--prompt",
        "Обновить swarm usage docs",
        "--run-id",
        push_continue_run_id,
    )
    push_continue_run_dir = ROOT / "runs" / push_continue_run_id
    try:
        approve_run_checks(push_continue_run_id)
        run_module(
            "-m",
            "scripts.agents.mcp",
            "run_dispatcher",
            "--run-id",
            push_continue_run_id,
            "--runtime-target",
            "codex-runtime",
        )

        workspace_root = Path(read_json(push_continue_run_dir / "workspace.json")["workspace"]["root_path"])
        target_file = workspace_root / "docs" / "swarm-usage.md"
        target_file.write_text(
            target_file.read_text(encoding="utf-8") + "\nApprove push and continue smoke change.\n",
            encoding="utf-8",
        )

        run_module(
            "-m",
            "scripts.agents.mcp",
            "complete_role_job",
            "--run-id",
            push_continue_run_id,
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
        run_module(
            "-m",
            "scripts.agents.mcp",
            "run_dispatcher",
            "--run-id",
            push_continue_run_id,
            "--runtime-target",
            "review-runtime",
        )
        run_module(
            "-m",
            "scripts.agents.mcp",
            "complete_role_job",
            "--run-id",
            push_continue_run_id,
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
        run_module(
            "-m",
            "scripts.agents.mcp",
            "approve_commit_and_continue",
            "--run-id",
            push_continue_run_id,
        )

        request_push = run_module(
            "-m",
            "scripts.agents.mcp",
            "request_push_approval",
            "--run-id",
            push_continue_run_id,
            "--pretty",
        )
        assert request_push.returncode == 0, request_push.stderr or request_push.stdout

        resume_push = run_module(
            "-m",
            "scripts.agents.mcp",
            "approve_push_and_continue",
            "--run-id",
            push_continue_run_id,
            "--pretty",
        )
        assert resume_push.returncode == 0, resume_push.stderr or resume_push.stdout
        resume_push_payload = json.loads(resume_push.stdout)
        assert resume_push_payload["tool"] == "approve_push_and_continue"
        assert resume_push_payload["approval"]["updated_checkpoint"]["id"] == "push"
        assert resume_push_payload["approval"]["updated_checkpoint"]["new_status"] == "approved"
        assert resume_push_payload["push"]["mode"] == "dry_run"
        assert resume_push_payload["push"]["push_created"] is False
        assert resume_push_payload["push"]["status"] == "push_approved_pending_execution"
        assert resume_push_payload["push"]["next_action"] == "execute_push"
        assert (push_continue_run_dir / "push-result.json").is_file()
    finally:
        cleanup_run_dir(push_continue_run_dir)

    commit_run_id = f"mcp-commit-approve-{uuid4().hex}"
    commit_run_dir = create_approval_ready_run(commit_run_id)
    try:
        commit = run_module(
            "-m",
            "scripts.agents.mcp",
            "approve_commit",
            "--run-id",
            commit_run_id,
            "--pretty",
        )
        assert commit.returncode == 0, commit.stderr or commit.stdout
        commit_payload = json.loads(commit.stdout)
        assert commit_payload["tool"] == "approve_commit"
        assert commit_payload["updated_checkpoint"]["id"] == "commit"
        assert commit_payload["updated_checkpoint"]["new_status"] == "approved"
    finally:
        cleanup_run_dir(commit_run_dir)

    reject_run_id = f"mcp-reject-{uuid4().hex}"
    reject_run_dir = create_approval_ready_run(reject_run_id)
    try:
        reject = run_module(
            "-m",
            "scripts.agents.mcp",
            "reject_checkpoint",
            "--run-id",
            reject_run_id,
            "--checkpoint",
            "commit",
            "--note",
            "hold changes",
            "--pretty",
        )
        assert reject.returncode == 0, reject.stderr or reject.stdout
        reject_payload = json.loads(reject.stdout)
        assert reject_payload["tool"] == "reject_checkpoint"
        assert reject_payload["updated_checkpoint"]["id"] == "commit"
        assert reject_payload["updated_checkpoint"]["new_status"] == "rejected"
        assert reject_payload["status"] == "approval_rejected"
    finally:
        cleanup_run_dir(reject_run_dir)


def test_tasks_json_calls_front_door_commands() -> None:
    tasks = read_json(TASKS_PATH)
    labels = {task["label"] for task in tasks["tasks"]}
    assert labels == {
        "Plan task",
        "Start swarm run",
        "Start autonomous swarm run",
        "Continue swarm run",
        "Preview sandbox plan",
        "Build swarm test image",
        "Run dispatcher",
        "Show run status",
        "Show job queue",
        "Show diff preview",
        "Approve run checks",
        "Approve run checks and continue",
        "Approve commit",
        "Approve commit and continue",
        "Approve push and continue",
        "Reject checkpoint",
        "Request commit approval",
        "Request push approval",
    }

    for task in tasks["tasks"]:
        command = task["command"]
        args = task["args"]
        if task["label"] == "Build swarm test image":
            assert command == "docker"
            assert args[:3] == ["build", "-f", "test/docker/swarm-test/Dockerfile"]
            continue
        assert "scripts.agents.mcp" in args
        assert command.endswith(r"venv\Scripts\python.exe")
        if task["label"] in {"Start swarm run", "Start autonomous swarm run", "Continue swarm run"}:
            assert "local_dry_run" not in args
