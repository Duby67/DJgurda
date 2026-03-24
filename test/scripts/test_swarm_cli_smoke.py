from __future__ import annotations

import json
import shutil
import subprocess
import sys

from pathlib import Path
from uuid import uuid4

import pytest

from scripts.agents.knowledge import load_verification_profiles, parse_markdown_risks
from scripts.agents.lifecycle.execute import (
    build_output as build_execute_output,
    detect_loaded_policy_conflicts,
)
from scripts.agents.lifecycle.verify import (
    build_output as build_verify_output,
    validate_against_profile,
)
from scripts.agents.routing.plan import build_plan_output
from scripts.agents.routing.route import (
    CLASSIFIER_PATH,
    ROUTING_PATH,
    build_output as build_route_output,
    load_json as load_route_json,
)


ROOT = Path(__file__).resolve().parents[2]


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


def create_run_bundle(
    *,
    context_pack: dict[str, object],
    routing_diagnostics: dict[str, object] | None = None,
    task_type_id: str = "docs_only_change",
    task_type_label: str = "Docs-Only Change",
    changed_paths: list[str] | None = None,
    plan_steps: list[dict[str, object]] | None = None,
    status: str = "planned",
    next_action: str = "load_context_and_implement",
    approval: dict[str, object] | None = None,
    artifacts: dict[str, str] | None = None,
    write_execution_state: bool = False,
) -> Path:
    run_dir = ROOT / "runs" / f"test-context-{uuid4().hex}"
    run_dir.mkdir(parents=True, exist_ok=False)

    plan_payload = {
        "plan": plan_steps or [
            {"id": "classify_task", "status": "completed"},
            {"id": "load_context", "status": "pending"},
            {"id": "implement_change", "status": "pending"},
        ]
    }
    run_summary = {
        "run_id": run_dir.name,
        "status": status,
        "next_action": next_action,
        "task_type": {"id": task_type_id, "label": task_type_label},
        "changed_paths": changed_paths or ["docs/swarm-usage.md"],
        "routing_diagnostics": routing_diagnostics or {},
        "artifacts": artifacts or {},
        "approval": approval or {
            "needs_manual_review": False,
            "escalation_reasons": [],
            "checkpoints": [
                {
                    "id": "run_checks",
                    "required": True,
                    "status": "awaiting_approval",
                    "reason": "tests exist",
                },
                {
                    "id": "commit",
                    "required": True,
                    "status": "awaiting_approval",
                    "reason": "commit approval required",
                },
                {
                    "id": "push",
                    "required": True,
                    "status": "awaiting_approval",
                    "reason": "push approval required",
                },
            ],
        },
    }

    (run_dir / "plan.json").write_text(json.dumps(plan_payload), encoding="utf-8")
    (run_dir / "context-pack.json").write_text(json.dumps(context_pack), encoding="utf-8")
    (run_dir / "run-summary.json").write_text(json.dumps(run_summary), encoding="utf-8")
    if write_execution_state:
        execution_state = {
            "version": 1,
            "run_id": run_dir.name,
            "phase": "changes_applied",
            "status": status,
            "next_action": next_action,
        }
        (run_dir / "execution-state.json").write_text(json.dumps(execution_state), encoding="utf-8")
    return run_dir


def test_route_module_smoke_for_release_docs() -> None:
    result = run_module(
        "-m",
        "scripts.agents.routing.route",
        "--prompt",
        "Обновить release flow документацию",
        "--path",
        "docs/release-flow.md",
        "--pretty",
    )

    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert payload["task_type"]["id"] == "docs_only_change"
    assert "tracked-docs-relevant-to-scope" in payload["context_pack"]["docs"]
    assert "only-the-code-needed-to-verify-behavior" in payload["context_pack"]["code"]


def test_release_promote_preview_dry_run_smoke() -> None:
    result = run_module(
        "-m",
        "scripts.release.automation.promote",
        "--source-branch",
        "swarm-dev",
        "--target-branch",
        "dev",
        "--target-kind",
        "preview",
        "--pretty",
    )

    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert payload["mode"] == "dry_run"
    assert payload["plan"]["target_branch"] == "dev"
    assert payload["plan"]["target_kind"] == "preview"
    assert payload["plan"]["next_release"]["tag"].startswith("v")


def test_release_sync_smoke_for_current_prod_tag() -> None:
    result = run_module(
        "-m",
        "scripts.release.automation.sync",
        "--tag",
        "v1.2.4",
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "OK: src.__version__ == tag" in result.stdout


def test_execute_context_loading_keeps_abstract_placeholders_advisory() -> None:
    run_dir = create_run_bundle(
        context_pack={
            "agents": ["AGENTS.md"],
            "docs": ["ARCHITECTURE.md"],
            "code": ["src/handlers/resources/<Source>/"],
            "tests": [],
            "notes": [],
        }
    )

    try:
        payload = build_execute_output(run_dir)
        assert payload["status"] == "context_loaded_pending_run_checks_approval"

        loaded_context = json.loads((run_dir / "loaded-context.json").read_text(encoding="utf-8"))
        assert loaded_context["summary"]["abstract_items"] == 1
        assert loaded_context["summary"]["blocking_unresolved_items"] == 0
        assert loaded_context["summary"]["advisory_unresolved_items"] == 1

        summary_text = (run_dir / "context-summary.md").read_text(encoding="utf-8")
        assert "Blocking Unresolved: 0" in summary_text
        assert "Advisory Unresolved: 1" in summary_text
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_execute_context_loading_blocks_on_missing_concrete_context() -> None:
    run_dir = create_run_bundle(
        context_pack={
            "agents": ["AGENTS.md"],
            "docs": ["docs/does-not-exist.md"],
            "code": [],
            "tests": [],
            "notes": [],
        }
    )

    try:
        payload = build_execute_output(run_dir)
        assert payload["status"] == "context_insufficient"
        assert payload["next_action"] == "resolve_context_gaps"

        loaded_context = json.loads((run_dir / "loaded-context.json").read_text(encoding="utf-8"))
        assert loaded_context["summary"]["missing_items"] == 1
        assert loaded_context["summary"]["blocking_unresolved_items"] == 1
        assert loaded_context["summary"]["advisory_unresolved_items"] == 0
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_plan_output_injects_profiles_and_tracked_risks_for_docs_changes() -> None:
    route_result = {
        "task_type": {"id": "docs_only_change", "label": "Docs-Only Change"},
        "changed_paths": ["docs/swarm-usage.md"],
        "matched_task_types": [{"id": "docs_only_change", "score": 3, "evidence": ["path_prefix:docs/"]}],
        "context_pack": {
            "agents": ["AGENTS.md"],
            "docs": ["ARCHITECTURE.md"],
            "code": [],
            "tests": [],
            "notes": [],
        },
        "escalation": {"needed": False, "reasons": []},
    }

    payload = build_plan_output(route_result)

    assert "tester" in payload["recommended_agents"]
    assert payload["verification_profile"]["profile_id"] == "docs_only_change"
    assert any(item["title"] == "Docs Cleanup After Typed-Runtime Transition" for item in payload["known_risks"])
    assert any(
        item["path"] == "docs/exec-plans/active/agent-first-docs-migration.md"
        for item in payload["active_initiatives"]
    )


def test_detect_loaded_policy_conflicts_ignores_prohibitions_and_flags_permissive_rules() -> None:
    safe_conflicts = detect_loaded_policy_conflicts(
        [
            {
                "path": "docs/policy-safe.md",
                "text": (
                    "- tests не равны source of truth.\n"
                    "- legacy archive материалы не использовать как source of truth.\n"
                    "- Never push without approval.\n"
                ),
            }
        ]
    )
    assert safe_conflicts == []

    risky_conflicts = detect_loaded_policy_conflicts(
        [
            {
                "path": "docs/policy-risky.md",
                "text": (
                    "- tests are source of truth.\n"
                    "- legacy archive notes are source of truth.\n"
                    "- push without approval is allowed.\n"
                ),
            }
        ]
    )
    assert {item["reason"] for item in risky_conflicts} == {
        "tests_marked_as_source_of_truth",
        "legacy_marked_as_source_of_truth",
        "push_without_approval_rule_detected",
    }


def test_verify_output_accepts_normalized_command_variants_and_writes_alias_artifact() -> None:
    run_dir = create_run_bundle(
        context_pack={
            "agents": ["AGENTS.md"],
            "docs": ["ARCHITECTURE.md"],
            "code": [],
            "tests": [],
            "notes": [],
        },
        plan_steps=[
            {"id": "classify_task", "status": "completed"},
            {"id": "load_context", "status": "completed"},
            {"id": "implement_change", "status": "completed"},
            {"id": "verify_change", "status": "pending"},
            {"id": "review_result", "status": "pending"},
        ],
        status="changes_applied_pending_verification",
        next_action="verify_change",
        write_execution_state=True,
    )

    try:
        payload = build_verify_output(
            run_dir,
            conclusion="passed",
            summary_text="profile-compatible verification",
            verified_by="tester",
            checks=[{"id": "docs_code_alignment_review", "status": "passed", "note": ""}],
            commands=[r".\venv\Scripts\python.exe   -m pytest test\scripts\test_swarm_cli_smoke.py -q"],
            log_paths=[],
        )

        assert payload["status"] == "verification_recorded_pending_review"
        assert payload["artifacts"]["test_report"].endswith("test-report.json")

        test_report = json.loads((run_dir / "test-report.json").read_text(encoding="utf-8"))
        assert test_report["verification_profile"]["profile_id"] == "docs_only_change"

        run_summary = json.loads((run_dir / "run-summary.json").read_text(encoding="utf-8"))
        assert run_summary["verification"]["profile_id"] == "docs_only_change"
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_validate_against_profile_returns_structured_error_for_unknown_task_type() -> None:
    with pytest.raises(ValueError, match="Verification profile not found"):
        validate_against_profile(
            task_type_id="missing_task_type",
            conclusion="passed",
            checks=[{"id": "some_check", "status": "passed", "note": ""}],
            commands=[],
        )


def test_parse_markdown_risks_supports_inline_area_and_inline_impact(tmp_path: Path) -> None:
    risk_file = tmp_path / "inline-risk.md"
    risk_file.write_text(
        "\n".join(
            [
                "# Risks",
                "",
                "## High Priority",
                "",
                "### Inline Policy Drift",
                "- Main Area: `scripts/agents/`",
                "- Impact: breaks planner output",
            ]
        ),
        encoding="utf-8",
    )

    parsed = parse_markdown_risks(risk_file, source="test")

    assert parsed == [
        {
            "title": "Inline Policy Drift",
            "priority": "high",
            "source": "test",
            "areas": ["scripts/agents/"],
            "impact": "breaks planner output",
        }
    ]


def test_every_task_type_has_verification_profile() -> None:
    classifier = load_route_json(CLASSIFIER_PATH)
    profile_ids = set(load_verification_profiles()["profiles"])
    task_ids = {item["id"] for item in classifier["task_types"]}

    assert task_ids <= profile_ids


def test_plan_output_builds_profile_context_from_real_route() -> None:
    classifier = load_route_json(CLASSIFIER_PATH)
    routing = load_route_json(ROUTING_PATH)

    route_result = build_route_output(
        classifier=classifier,
        routing=routing,
        prompt="Обновить swarm usage docs и testing policy",
        paths=["docs/swarm-usage.md", "docs/testing-policy.md"],
    )
    plan_output = build_plan_output(route_result)

    assert "tester" in plan_output["recommended_agents"]
    assert plan_output["verification_profile"]["profile_id"] == "swarm_policy_or_planning_change"
    assert any(risk["title"] == "Docs Cleanup After Typed-Runtime Transition" for risk in plan_output["known_risks"])
    assert plan_output["active_initiatives"]
    assert plan_output["active_initiatives"][0]["path"] == "docs/exec-plans/active/agent-first-docs-migration.md"


def test_verify_rejects_missing_required_profile_checks() -> None:
    run_dir = create_run_bundle(
        context_pack={
            "agents": ["AGENTS.md"],
            "docs": ["ARCHITECTURE.md"],
            "code": [],
            "tests": [],
            "notes": [],
        },
        task_type_id="release_or_versioning_change",
        task_type_label="Release Or Versioning Change",
        changed_paths=["docs/release-flow.md"],
        plan_steps=[
            {"id": "classify_task", "status": "completed"},
            {"id": "load_context", "status": "completed"},
            {"id": "implement_change", "status": "completed"},
            {"id": "verify_change", "status": "pending"},
            {"id": "review_result", "status": "pending"},
        ],
        status="changes_applied_pending_verification",
        next_action="verify_change",
        write_execution_state=True,
    )

    try:
        with pytest.raises(ValueError, match="required checks"):
            build_verify_output(
                run_dir,
                conclusion="passed",
                summary_text="Only part of release verification recorded",
                verified_by="tester",
                checks=[{"id": "release_promote_dry_run", "status": "passed", "note": ""}],
                commands=[r".\venv\Scripts\python.exe -m pytest test\scripts\test_swarm_cli_smoke.py"],
                log_paths=[],
            )
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_verify_rejects_passed_conclusion_with_failed_check() -> None:
    run_dir = create_run_bundle(
        context_pack={
            "agents": ["AGENTS.md"],
            "docs": ["ARCHITECTURE.md"],
            "code": [],
            "tests": [],
            "notes": [],
        },
        plan_steps=[
            {"id": "classify_task", "status": "completed"},
            {"id": "load_context", "status": "completed"},
            {"id": "implement_change", "status": "completed"},
            {"id": "verify_change", "status": "pending"},
            {"id": "review_result", "status": "pending"},
        ],
        status="changes_applied_pending_verification",
        next_action="verify_change",
        write_execution_state=True,
    )

    try:
        with pytest.raises(ValueError, match="conclusion='passed'"):
            build_verify_output(
                run_dir,
                conclusion="passed",
                summary_text="Docs verification contradicts failed check",
                verified_by="tester",
                checks=[{"id": "docs_code_alignment_review", "status": "failed", "note": "drift found"}],
                commands=[r".\venv\Scripts\python.exe -m pytest test\scripts\test_swarm_cli_smoke.py"],
                log_paths=[],
            )
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)
