from __future__ import annotations

import json
import shutil
import subprocess
import sys

from pathlib import Path
from uuid import uuid4

from scripts.agents.lifecycle.execute import build_output as build_execute_output


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


def create_run_bundle(*, context_pack: dict[str, object], routing_diagnostics: dict[str, object] | None = None) -> Path:
    run_dir = ROOT / "runs" / f"test-context-{uuid4().hex}"
    run_dir.mkdir(parents=True, exist_ok=False)

    plan_payload = {
        "plan": [
            {"id": "classify_task", "status": "completed"},
            {"id": "load_context", "status": "pending"},
            {"id": "implement_change", "status": "pending"},
        ]
    }
    run_summary = {
        "run_id": run_dir.name,
        "status": "planned",
        "next_action": "load_context_and_implement",
        "task_type": {"id": "docs_only_change", "label": "Docs-Only Change"},
        "changed_paths": ["docs/swarm-usage.md"],
        "routing_diagnostics": routing_diagnostics or {},
        "artifacts": {},
        "approval": {
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
    assert payload["task_type"]["id"] == "release_or_versioning_change"
    assert "scripts/AGENTS.md" in payload["context_pack"]["agents"]
    assert "scripts/release/automation/promote.py" in payload["context_pack"]["code"]


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
