#!/usr/bin/env python3
"""Repo-local swarm front door for planning, orchestration, and job control."""

from __future__ import annotations

import argparse
import json
import sys

from pathlib import Path
from typing import Any

from scripts.config import ROOT
from scripts.agents.executor import (
    complete_external_job,
    claim_job,
    fail_external_job,
    start_or_continue_run,
)
from scripts.agents.lifecycle.approve import build_output as build_approval_action_output
from scripts.agents.lifecycle.request_approval import build_output as build_request_approval_output
from scripts.agents.lifecycle.status import build_status as build_run_status, render_human_status
from scripts.agents.mcp.dispatcher import (
    build_diff_preview as build_dispatcher_diff_preview,
    dispatch_next_job,
    ensure_dispatch_record,
    mark_dispatch_terminal,
    run_autonomous_cycle,
    run_dispatcher_loop,
    submit_role_result,
    show_job_queue as build_dispatcher_job_queue,
)
from scripts.agents.routing.plan import build_plan_output, write_artifacts as write_plan_artifacts
from scripts.agents.routing.run import build_run_bundle, generate_run_id, normalize_runs_dir
from scripts.agents.routing.route import (
    CLASSIFIER_PATH,
    ROUTING_PATH,
    build_output as build_route_output,
    load_json as load_route_json,
    read_paths,
    read_prompt,
)
from scripts.agents.sandbox_adapters import (
    DOCKER_ADAPTER,
    GITHUB_ACTIONS_ADAPTER,
    LOCAL_DRY_RUN_ADAPTER,
)


def load_json(path: Path) -> dict[str, Any]:
    """Reads a JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def load_optional_json(path: Path) -> dict[str, Any] | None:
    """Reads a JSON file if it exists."""
    if not path.is_file():
        return None
    return load_json(path)


def normalize_rel_path(value: str) -> str:
    """Normalizes a repository-relative path."""
    return value.strip().replace("\\", "/").lstrip("./")


def resolve_run_dir(*, run_dir: str | None, run_id: str | None, runs_dir: str) -> Path:
    """Resolves a run directory from CLI arguments."""
    if run_dir and run_id:
        raise ValueError("Нельзя одновременно использовать --run-dir и --run-id")
    if run_dir:
        return ROOT / normalize_rel_path(run_dir)
    if run_id:
        return (ROOT / normalize_rel_path(runs_dir)) / run_id.strip()
    raise ValueError("Нужно указать либо --run-dir, либо --run-id")


def write_view(run_dir: Path, filename: str, content: str) -> str:
    """Writes a generated human-readable view into the run bundle."""
    view_path = run_dir / filename
    view_path.write_text(content, encoding="utf-8")
    return str(view_path.relative_to(ROOT)).replace("\\", "/")


def command_inputs(args: argparse.Namespace) -> argparse.Namespace:
    """Builds a route-compatible namespace for prompt/path parsing."""
    return argparse.Namespace(prompt=args.prompt, prompt_file=args.prompt_file, path=args.path, paths_file=args.paths_file)


def build_plan_task(args: argparse.Namespace) -> dict[str, Any]:
    """Builds planning output without mutating run artifacts."""
    prompt = read_prompt(command_inputs(args))
    paths = read_paths(command_inputs(args))
    classifier = load_route_json(CLASSIFIER_PATH)
    routing = load_route_json(ROUTING_PATH)
    route_result = build_route_output(classifier=classifier, routing=routing, prompt=prompt, paths=paths)
    plan_output = build_plan_output(route_result)

    result = {
        "tool": "plan_task",
        "route": route_result,
        "plan": plan_output,
    }

    if args.output_dir:
        output_dir = ROOT / normalize_rel_path(args.output_dir)
        result["artifacts"] = write_plan_artifacts(output_dir, route_result, plan_output)

    return result


def build_start_swarm_run(args: argparse.Namespace) -> dict[str, Any]:
    """Builds a run bundle and starts orchestration until the next stop boundary."""
    prompt = read_prompt(command_inputs(args))
    paths = read_paths(command_inputs(args))
    run_id = normalize_rel_path(args.run_id) if args.run_id else generate_run_id("swarm")
    runs_dir = ROOT / normalize_runs_dir(args.runs_dir)
    run_dir = runs_dir / run_id

    bundle = build_run_bundle(prompt=prompt, paths=paths, run_id=run_id, run_dir=run_dir)
    orchestration = start_or_continue_run(run_dir, sandbox_adapter=args.sandbox_adapter)
    status_payload = build_run_status(run_dir)

    return {
        "tool": "start_swarm_run",
        "run_id": run_id,
        "run_dir": str(run_dir.relative_to(ROOT)).replace("\\", "/"),
        "bundle": {
            "task_type": bundle["summary"]["task_type"],
            "status": bundle["summary"]["status"],
            "next_action": bundle["summary"]["next_action"],
        },
        "orchestration": orchestration,
        "status": status_payload,
    }


def build_continue_swarm_run(args: argparse.Namespace) -> dict[str, Any]:
    """Continues orchestration for an existing run bundle."""
    run_dir = resolve_run_dir(run_dir=args.run_dir, run_id=args.run_id, runs_dir=args.runs_dir)
    orchestration = start_or_continue_run(run_dir, sandbox_adapter=args.sandbox_adapter)
    status_payload = build_run_status(run_dir)

    return {
        "tool": "continue_swarm_run",
        "run_id": run_dir.name,
        "run_dir": str(run_dir.relative_to(ROOT)).replace("\\", "/"),
        "orchestration": orchestration,
        "status": status_payload,
    }


def show_run_status(args: argparse.Namespace) -> dict[str, Any]:
    """Shows run status, optionally rendered as human-readable text."""
    run_dir = resolve_run_dir(run_dir=args.run_dir, run_id=args.run_id, runs_dir=args.runs_dir)
    status_payload = build_run_status(run_dir)

    if args.human:
        human = render_human_status(status_payload)
        return {
            "tool": "show_run_status",
            "run_dir": status_payload["run_dir"],
            "human": human,
            "view": write_view(run_dir, "run-status.md", human),
        }

    return {
        "tool": "show_run_status",
        **status_payload,
    }


def build_commit_or_push_request(args: argparse.Namespace, *, checkpoint: str) -> dict[str, Any]:
    """Builds an approval request for commit or push."""
    run_dir = resolve_run_dir(run_dir=args.run_dir, run_id=args.run_id, runs_dir=args.runs_dir)
    result = build_request_approval_output(
        run_dir,
        requested_by=args.requested_by,
        summary_text=args.summary,
        requested_checkpoints=[checkpoint],
    )
    return {
        "tool": f"request_{checkpoint}_approval",
        **result,
    }


def parse_result_payload(args: argparse.Namespace) -> dict[str, Any] | None:
    """Parses optional result payload JSON from CLI arguments."""
    if args.result_json and args.result_file:
        raise ValueError("Нельзя одновременно использовать --result-json и --result-file")
    if args.result_file:
        return json.loads(Path(args.result_file).read_text(encoding="utf-8"))
    if args.result_json:
        return json.loads(args.result_json)
    return None


def build_show_job_queue(args: argparse.Namespace) -> dict[str, Any]:
    """Shows a compact queue summary for role jobs."""
    run_dir = resolve_run_dir(run_dir=args.run_dir, run_id=args.run_id, runs_dir=args.runs_dir)
    output = build_dispatcher_job_queue(run_dir)
    if args.human:
        return {
            "tool": "show_job_queue",
            "run_id": run_dir.name,
            "run_dir": str(run_dir.relative_to(ROOT)).replace("\\", "/"),
            "human": output["human"],
            "view": output["job_queue_markdown"],
        }
    return {
        "tool": "show_job_queue",
        "run_id": run_dir.name,
        "run_dir": str(run_dir.relative_to(ROOT)).replace("\\", "/"),
        **output,
    }


def build_show_diff_preview(args: argparse.Namespace) -> dict[str, Any]:
    """Shows a workspace diff preview or changed-files fallback."""
    run_dir = resolve_run_dir(run_dir=args.run_dir, run_id=args.run_id, runs_dir=args.runs_dir)
    output = build_dispatcher_diff_preview(
        run_dir,
        explicit_paths=[item.strip() for item in args.path] if getattr(args, "path", None) else None,
    )
    if args.human:
        return {
            "tool": "show_diff_preview",
            "run_id": run_dir.name,
            "run_dir": str(run_dir.relative_to(ROOT)).replace("\\", "/"),
            "human": output["human"],
            "view": output["diff_preview_markdown"],
        }
    return {
        "tool": "show_diff_preview",
        "run_id": run_dir.name,
        "run_dir": str(run_dir.relative_to(ROOT)).replace("\\", "/"),
        **output,
    }


def render_sandbox_plan_human(payload: dict[str, Any]) -> str:
    """Renders a compact sandbox plan preview."""
    lines = [
        f"Run: {payload.get('run_id', 'unknown')}",
        f"Adapter: {payload.get('adapter_id', 'unknown')}",
        f"Risk level: {payload.get('risk_level', 'unknown')}",
        f"Commands: {len(payload.get('commands', []))}",
        f"Checks: {len(payload.get('checks', []))}",
    ]
    for command in payload.get("commands", [])[:10]:
        lines.append(f"- {command.get('id', '')}: {command.get('command', '')}")
    return "\n".join(lines) + "\n"


def build_preview_sandbox_plan(args: argparse.Namespace) -> dict[str, Any]:
    """Shows an existing sandbox plan or derives a preview from the verification plan."""
    run_dir = resolve_run_dir(run_dir=args.run_dir, run_id=args.run_id, runs_dir=args.runs_dir)
    sandbox_plan_path = run_dir / "sandbox-plan.json"
    verification_plan_path = run_dir / "verification-plan.json"
    sandbox_plan = load_optional_json(sandbox_plan_path)

    if sandbox_plan is not None:
        output = {
            "tool": "preview_sandbox_plan",
            "run_id": run_dir.name,
            "run_dir": str(run_dir.relative_to(ROOT)).replace("\\", "/"),
            "source": "sandbox-plan.json",
            "artifact": str(sandbox_plan_path.relative_to(ROOT)).replace("\\", "/"),
            **sandbox_plan,
        }
    else:
        verification_plan = load_optional_json(verification_plan_path)
        if verification_plan is not None:
            output = {
                "tool": "preview_sandbox_plan",
                "run_id": run_dir.name,
                "run_dir": str(run_dir.relative_to(ROOT)).replace("\\", "/"),
                "source": "verification-plan.json",
                "artifact": str(verification_plan_path.relative_to(ROOT)).replace("\\", "/"),
                "adapter_id": verification_plan.get("adapter_id", ""),
                "workspace_ref": verification_plan.get("workspace_ref", {}),
                "risk_level": verification_plan.get("risk_level", "unknown"),
                "commands": verification_plan.get("commands", []),
                "checks": verification_plan.get("checks", []),
                "notes": verification_plan.get("notes", []),
            }
        else:
            run_summary = load_json(run_dir / "run-summary.json")
            profile = run_summary.get("verification_profile", {})
            if not profile:
                raise FileNotFoundError(
                    f"Не найден sandbox preview ни в {sandbox_plan_path}, ни в {verification_plan_path}",
                )
            output = {
                "tool": "preview_sandbox_plan",
                "run_id": run_dir.name,
                "run_dir": str(run_dir.relative_to(ROOT)).replace("\\", "/"),
                "source": "run-summary.json",
                "artifact": str((run_dir / 'run-summary.json').relative_to(ROOT)).replace("\\", "/"),
                "adapter_id": run_summary.get("sandbox", {}).get("selected_adapter", ""),
                "workspace_ref": load_optional_json(run_dir / "workspace.json") or {},
                "risk_level": profile.get("risk_level", "unknown"),
                "commands": [
                    {"id": f"command_{index + 1}", "command": command}
                    for index, command in enumerate(profile.get("allowed_commands", []))
                ],
                "checks": [
                    {"id": check_id, "required": True}
                    for check_id in profile.get("required_checks", [])
                ] + [
                    {"id": check_id, "required": False}
                    for check_id in profile.get("optional_checks", [])
                ],
                "notes": profile.get("notes", []),
            }

    if args.human:
        return {
            "tool": "preview_sandbox_plan",
            "run_dir": output["run_dir"],
            "human": render_sandbox_plan_human(output),
        }
    return output


def build_checkpoint_action(
    args: argparse.Namespace,
    *,
    checkpoint: str,
    action: str,
    tool_name: str,
) -> dict[str, Any]:
    """Applies an approval action through the existing lifecycle approval contract."""
    run_dir = resolve_run_dir(run_dir=args.run_dir, run_id=args.run_id, runs_dir=args.runs_dir)
    result = build_approval_action_output(
        run_dir,
        checkpoint_id=checkpoint,
        action=action,
        note=getattr(args, "note", ""),
    )
    return {
        "tool": tool_name,
        **result,
    }


def build_run_dispatcher(args: argparse.Namespace) -> dict[str, Any]:
    """Claims or surfaces the next external job as a Codex-oriented work item."""
    run_dir = resolve_run_dir(run_dir=args.run_dir, run_id=args.run_id, runs_dir=args.runs_dir)
    result = dispatch_next_job(
        run_dir,
        runtime_target=args.runtime_target,
        claimed_by=args.claimed_by,
    )
    return {
        "tool": "run_dispatcher",
        "run_id": run_dir.name,
        "run_dir": str(run_dir.relative_to(ROOT)).replace("\\", "/"),
        **result,
    }


def build_run_dispatcher_loop(args: argparse.Namespace) -> dict[str, Any]:
    """Runs the dispatcher loop over completion inbox artifacts and next dispatch."""
    run_dir = resolve_run_dir(run_dir=args.run_dir, run_id=args.run_id, runs_dir=args.runs_dir)
    result = run_dispatcher_loop(
        run_dir,
        runtime_target=args.runtime_target,
        claimed_by=args.claimed_by,
        sandbox_adapter=args.sandbox_adapter or "",
        max_cycles=args.max_cycles,
    )
    return {
        "tool": "run_dispatcher_loop",
        "run_id": run_dir.name,
        "run_dir": str(run_dir.relative_to(ROOT)).replace("\\", "/"),
        **result,
    }


def build_run_autonomous_cycle(args: argparse.Namespace) -> dict[str, Any]:
    """Runs a unified autonomous orchestration cycle for an existing run."""
    run_dir = resolve_run_dir(run_dir=args.run_dir, run_id=args.run_id, runs_dir=args.runs_dir)
    result = run_autonomous_cycle(
        run_dir,
        runtime_target=args.runtime_target,
        claimed_by=args.claimed_by,
        sandbox_adapter=args.sandbox_adapter or "",
        max_cycles=args.max_cycles,
    )
    return {
        "tool": "run_autonomous_cycle",
        "run_id": run_dir.name,
        "run_dir": str(run_dir.relative_to(ROOT)).replace("\\", "/"),
        **result,
    }


def build_claim_role_job(args: argparse.Namespace) -> dict[str, Any]:
    """Claims an external role job."""
    run_dir = resolve_run_dir(run_dir=args.run_dir, run_id=args.run_id, runs_dir=args.runs_dir)
    result = claim_job(run_dir, job_id=args.job_id, claimed_by=args.claimed_by)
    dispatch = ensure_dispatch_record(run_dir, job_id=args.job_id, runtime_target=args.claimed_by)
    return {
        "tool": "claim_role_job",
        **result,
        "dispatch": dispatch,
    }


def build_complete_role_job(args: argparse.Namespace) -> dict[str, Any]:
    """Completes an external role job and resumes orchestration."""
    run_dir = resolve_run_dir(run_dir=args.run_dir, run_id=args.run_id, runs_dir=args.runs_dir)
    result = complete_external_job(
        run_dir,
        job_id=args.job_id,
        summary=args.summary,
        result_payload=parse_result_payload(args),
        sandbox_adapter=args.sandbox_adapter,
    )
    dispatch = mark_dispatch_terminal(run_dir, job_id=args.job_id, dispatch_status="completed")
    return {
        "tool": "complete_role_job",
        **result,
        "dispatch": dispatch,
    }


def build_fail_role_job(args: argparse.Namespace) -> dict[str, Any]:
    """Marks an external role job as failed."""
    run_dir = resolve_run_dir(run_dir=args.run_dir, run_id=args.run_id, runs_dir=args.runs_dir)
    result = fail_external_job(
        run_dir,
        job_id=args.job_id,
        summary=args.summary,
        reason=args.reason,
    )
    dispatch = mark_dispatch_terminal(run_dir, job_id=args.job_id, dispatch_status="failed")
    return {
        "tool": "fail_role_job",
        **result,
        "dispatch": dispatch,
    }


def build_submit_role_result(args: argparse.Namespace) -> dict[str, Any]:
    """Writes a completion inbox artifact for an external role job and optionally consumes it."""
    run_dir = resolve_run_dir(run_dir=args.run_dir, run_id=args.run_id, runs_dir=args.runs_dir)
    payload = parse_result_payload(args) or {}
    if args.summary and not payload.get("summary"):
        payload["summary"] = args.summary
    if args.status and not payload.get("status"):
        payload["status"] = args.status
    result = submit_role_result(
        run_dir,
        job_id=args.job_id,
        payload=payload,
        runtime_target=args.runtime_target,
        sandbox_adapter=args.sandbox_adapter or "",
        auto_consume=not args.no_consume,
    )
    return {
        "tool": "submit_role_result",
        **result,
    }


def handle_tool(command: str, args: argparse.Namespace) -> dict[str, Any]:
    """Dispatches a tool name to the corresponding handler."""
    if command == "plan_task":
        return build_plan_task(args)
    if command == "start_swarm_run":
        return build_start_swarm_run(args)
    if command == "continue_swarm_run":
        return build_continue_swarm_run(args)
    if command == "show_run_status":
        return show_run_status(args)
    if command == "show_job_queue":
        return build_show_job_queue(args)
    if command == "show_diff_preview":
        return build_show_diff_preview(args)
    if command == "preview_sandbox_plan":
        return build_preview_sandbox_plan(args)
    if command == "approve_run_checks":
        return build_checkpoint_action(args, checkpoint="run_checks", action="approve", tool_name="approve_run_checks")
    if command == "approve_commit":
        return build_checkpoint_action(args, checkpoint="commit", action="approve", tool_name="approve_commit")
    if command == "reject_checkpoint":
        return build_checkpoint_action(args, checkpoint=args.checkpoint, action="reject", tool_name="reject_checkpoint")
    if command == "request_commit_approval":
        return build_commit_or_push_request(args, checkpoint="commit")
    if command == "request_push_approval":
        return build_commit_or_push_request(args, checkpoint="push")
    if command == "run_dispatcher":
        return build_run_dispatcher(args)
    if command == "run_dispatcher_loop":
        return build_run_dispatcher_loop(args)
    if command == "run_autonomous_cycle":
        return build_run_autonomous_cycle(args)
    if command == "claim_role_job":
        return build_claim_role_job(args)
    if command == "complete_role_job":
        return build_complete_role_job(args)
    if command == "fail_role_job":
        return build_fail_role_job(args)
    if command == "submit_role_result":
        return build_submit_role_result(args)
    raise ValueError(f"Unsupported command: {command}")


def serve_stdio() -> int:
    """Serves newline-delimited JSON requests over stdio."""
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            command = str(request.get("tool", "")).strip()
            arguments = request.get("arguments", {})
            namespace = argparse.Namespace(**arguments)
            result = handle_tool(command, namespace)
        except Exception as exc:  # noqa: BLE001
            result = {
                "error": str(exc),
            }
        sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    return 0


def parse_args() -> argparse.Namespace:
    """Parses CLI arguments."""
    parser = argparse.ArgumentParser(description="Repo-local swarm front door.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_pretty_flag(command_parser: argparse.ArgumentParser) -> None:
        command_parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")

    def add_prompt_paths(parent: argparse.ArgumentParser) -> None:
        parent.add_argument("--prompt", default="", help="Task prompt.")
        parent.add_argument("--prompt-file", help="Path to a file with the prompt.")
        parent.add_argument("--path", action="append", help="Changed path. Can be repeated.")
        parent.add_argument("--paths-file", help="Path to a newline-separated list of changed paths.")

    plan_parser = subparsers.add_parser("plan_task", help="Build a task plan.")
    add_prompt_paths(plan_parser)
    add_pretty_flag(plan_parser)
    plan_parser.add_argument("--output-dir", help="Optional output dir for plan artifacts.")

    start_parser = subparsers.add_parser("start_swarm_run", help="Build a run bundle and start orchestration.")
    add_prompt_paths(start_parser)
    add_pretty_flag(start_parser)
    start_parser.add_argument("--run-id", help="Optional explicit run id.")
    start_parser.add_argument(
        "--runs-dir",
        default=str(normalize_runs_dir("runs")),
        help="Base directory for runs (default: runs).",
    )
    start_parser.add_argument(
        "--sandbox-adapter",
        default=None,
        choices=[LOCAL_DRY_RUN_ADAPTER, DOCKER_ADAPTER, GITHUB_ACTIONS_ADAPTER],
        help="Optional sandbox adapter override for automated verification steps.",
    )

    continue_parser = subparsers.add_parser("continue_swarm_run", help="Continue orchestration for an existing run.")
    add_pretty_flag(continue_parser)
    continue_parser.add_argument("--run-dir", help="Path to a run bundle.")
    continue_parser.add_argument("--run-id", help="Run id inside runs-dir.")
    continue_parser.add_argument(
        "--runs-dir",
        default=str(normalize_runs_dir("runs")),
        help="Base directory for runs (default: runs).",
    )
    continue_parser.add_argument(
        "--sandbox-adapter",
        default=None,
        choices=[LOCAL_DRY_RUN_ADAPTER, DOCKER_ADAPTER, GITHUB_ACTIONS_ADAPTER],
        help="Optional sandbox adapter override for resumed local orchestration steps.",
    )

    status_parser = subparsers.add_parser("show_run_status", help="Show a run status.")
    add_pretty_flag(status_parser)
    status_parser.add_argument("--run-dir", help="Path to a run bundle.")
    status_parser.add_argument("--run-id", help="Run id inside runs-dir.")
    status_parser.add_argument(
        "--runs-dir",
        default=str(normalize_runs_dir("runs")),
        help="Base directory for runs (default: runs).",
    )
    status_parser.add_argument("--human", action="store_true", help="Render compact human-readable status.")

    job_queue_parser = subparsers.add_parser("show_job_queue", help="Show a compact role job queue summary.")
    add_pretty_flag(job_queue_parser)
    job_queue_parser.add_argument("--run-dir", help="Path to a run bundle.")
    job_queue_parser.add_argument("--run-id", help="Run id inside runs-dir.")
    job_queue_parser.add_argument(
        "--runs-dir",
        default=str(normalize_runs_dir("runs")),
        help="Base directory for runs (default: runs).",
    )
    job_queue_parser.add_argument("--human", action="store_true", help="Render compact human-readable queue output.")

    diff_parser = subparsers.add_parser("show_diff_preview", help="Show a workspace diff preview.")
    add_pretty_flag(diff_parser)
    diff_parser.add_argument("--run-dir", help="Path to a run bundle.")
    diff_parser.add_argument("--run-id", help="Run id inside runs-dir.")
    diff_parser.add_argument(
        "--runs-dir",
        default=str(normalize_runs_dir("runs")),
        help="Base directory for runs (default: runs).",
    )
    diff_parser.add_argument("--path", action="append", help="Optional path to preview. Can be repeated.")
    diff_parser.add_argument("--human", action="store_true", help="Render compact human-readable diff output.")
    diff_parser.add_argument("--max-lines", type=int, default=80, help="Maximum preview lines to render.")

    sandbox_preview_parser = subparsers.add_parser("preview_sandbox_plan", help="Show sandbox plan preview for a run.")
    add_pretty_flag(sandbox_preview_parser)
    sandbox_preview_parser.add_argument("--run-dir", help="Path to a run bundle.")
    sandbox_preview_parser.add_argument("--run-id", help="Run id inside runs-dir.")
    sandbox_preview_parser.add_argument(
        "--runs-dir",
        default=str(normalize_runs_dir("runs")),
        help="Base directory for runs (default: runs).",
    )
    sandbox_preview_parser.add_argument("--human", action="store_true", help="Render compact human-readable plan output.")

    approve_run_checks_parser = subparsers.add_parser("approve_run_checks", help="Approve run_checks checkpoint.")
    add_pretty_flag(approve_run_checks_parser)
    approve_run_checks_parser.add_argument("--run-dir", help="Path to a run bundle.")
    approve_run_checks_parser.add_argument("--run-id", help="Run id inside runs-dir.")
    approve_run_checks_parser.add_argument(
        "--runs-dir",
        default=str(normalize_runs_dir("runs")),
        help="Base directory for runs (default: runs).",
    )
    approve_run_checks_parser.add_argument("--note", default="", help="Optional approval note.")

    approve_commit_parser = subparsers.add_parser("approve_commit", help="Approve commit checkpoint.")
    add_pretty_flag(approve_commit_parser)
    approve_commit_parser.add_argument("--run-dir", help="Path to a run bundle.")
    approve_commit_parser.add_argument("--run-id", help="Run id inside runs-dir.")
    approve_commit_parser.add_argument(
        "--runs-dir",
        default=str(normalize_runs_dir("runs")),
        help="Base directory for runs (default: runs).",
    )
    approve_commit_parser.add_argument("--note", default="", help="Optional approval note.")

    reject_parser = subparsers.add_parser("reject_checkpoint", help="Reject a lifecycle checkpoint.")
    add_pretty_flag(reject_parser)
    reject_parser.add_argument("--run-dir", help="Path to a run bundle.")
    reject_parser.add_argument("--run-id", help="Run id inside runs-dir.")
    reject_parser.add_argument(
        "--runs-dir",
        default=str(normalize_runs_dir("runs")),
        help="Base directory for runs (default: runs).",
    )
    reject_parser.add_argument(
        "--checkpoint",
        required=True,
        choices=["run_checks", "commit", "push"],
        help="Checkpoint to reject.",
    )
    reject_parser.add_argument("--note", default="", help="Optional rejection note.")

    commit_parser = subparsers.add_parser("request_commit_approval", help="Request commit approval.")
    add_pretty_flag(commit_parser)
    commit_parser.add_argument("--run-dir", help="Path to a run bundle.")
    commit_parser.add_argument("--run-id", help="Run id inside runs-dir.")
    commit_parser.add_argument(
        "--runs-dir",
        default=str(normalize_runs_dir("runs")),
        help="Base directory for runs (default: runs).",
    )
    commit_parser.add_argument("--summary", default="", help="Approval summary.")
    commit_parser.add_argument("--requested-by", default="release_manager", help="Requester identity.")

    push_parser = subparsers.add_parser("request_push_approval", help="Request push approval.")
    add_pretty_flag(push_parser)
    push_parser.add_argument("--run-dir", help="Path to a run bundle.")
    push_parser.add_argument("--run-id", help="Run id inside runs-dir.")
    push_parser.add_argument(
        "--runs-dir",
        default=str(normalize_runs_dir("runs")),
        help="Base directory for runs (default: runs).",
    )
    push_parser.add_argument("--summary", default="", help="Approval summary.")
    push_parser.add_argument("--requested-by", default="release_manager", help="Requester identity.")

    dispatcher_parser = subparsers.add_parser("run_dispatcher", help="Claim or surface the next external role job.")
    add_pretty_flag(dispatcher_parser)
    dispatcher_parser.add_argument("--run-dir", help="Path to a run bundle.")
    dispatcher_parser.add_argument("--run-id", help="Run id inside runs-dir.")
    dispatcher_parser.add_argument(
        "--runs-dir",
        default=str(normalize_runs_dir("runs")),
        help="Base directory for runs (default: runs).",
    )
    dispatcher_parser.add_argument("--claimed-by", default="ux_dispatcher", help="Identity used for claim operations.")
    dispatcher_parser.add_argument("--runtime-target", default="codex", help="External runtime target label.")

    dispatcher_loop_parser = subparsers.add_parser(
        "run_dispatcher_loop",
        help="Consume external completion inbox artifacts and dispatch the next job.",
    )
    add_pretty_flag(dispatcher_loop_parser)
    dispatcher_loop_parser.add_argument("--run-dir", help="Path to a run bundle.")
    dispatcher_loop_parser.add_argument("--run-id", help="Run id inside runs-dir.")
    dispatcher_loop_parser.add_argument(
        "--runs-dir",
        default=str(normalize_runs_dir("runs")),
        help="Base directory for runs (default: runs).",
    )
    dispatcher_loop_parser.add_argument("--claimed-by", default="ux_dispatcher", help="Identity used for claim operations.")
    dispatcher_loop_parser.add_argument("--runtime-target", default="codex", help="External runtime target label.")
    dispatcher_loop_parser.add_argument(
        "--sandbox-adapter",
        default=None,
        choices=[LOCAL_DRY_RUN_ADAPTER, DOCKER_ADAPTER, GITHUB_ACTIONS_ADAPTER],
        help="Optional sandbox adapter override when consuming coder completion artifacts.",
    )
    dispatcher_loop_parser.add_argument("--max-cycles", type=int, default=8, help="Maximum loop iterations per invocation.")

    autonomous_cycle_parser = subparsers.add_parser(
        "run_autonomous_cycle",
        help="Run local orchestration plus dispatcher loop until the next stable boundary.",
    )
    add_pretty_flag(autonomous_cycle_parser)
    autonomous_cycle_parser.add_argument("--run-dir", help="Path to a run bundle.")
    autonomous_cycle_parser.add_argument("--run-id", help="Run id inside runs-dir.")
    autonomous_cycle_parser.add_argument(
        "--runs-dir",
        default=str(normalize_runs_dir("runs")),
        help="Base directory for runs (default: runs).",
    )
    autonomous_cycle_parser.add_argument("--claimed-by", default="ux_dispatcher", help="Identity used for claim operations.")
    autonomous_cycle_parser.add_argument("--runtime-target", default="codex", help="External runtime target label.")
    autonomous_cycle_parser.add_argument(
        "--sandbox-adapter",
        default=None,
        choices=[LOCAL_DRY_RUN_ADAPTER, DOCKER_ADAPTER, GITHUB_ACTIONS_ADAPTER],
        help="Optional sandbox adapter override when autonomous cycle resumes local orchestration.",
    )
    autonomous_cycle_parser.add_argument("--max-cycles", type=int, default=8, help="Maximum autonomous iterations per invocation.")

    for command_name in ("claim_role_job", "complete_role_job", "fail_role_job"):
        job_parser = subparsers.add_parser(command_name, help=f"{command_name.replace('_', ' ').title()}.")
        add_pretty_flag(job_parser)
        job_parser.add_argument("--run-dir", help="Path to a run bundle.")
        job_parser.add_argument("--run-id", help="Run id inside runs-dir.")
        job_parser.add_argument(
            "--runs-dir",
            default=str(normalize_runs_dir("runs")),
            help="Base directory for runs (default: runs).",
        )
        job_parser.add_argument("--job-id", required=True, help="Role job id.")
        job_parser.add_argument("--claimed-by", default="external_runtime", help="Job owner for claim operations.")
        job_parser.add_argument("--runtime-target", default="codex", help="External runtime target label.")
        job_parser.add_argument("--summary", default="", help="Job summary or result note.")
        job_parser.add_argument(
            "--status",
            default="completed",
            choices=["completed", "failed", "blocked"],
            help="Submission status for submit_role_result.",
        )
        job_parser.add_argument("--reason", default="", help="Failure reason.")
        job_parser.add_argument("--result-json", help="Inline JSON payload for complete_role_job.")
        job_parser.add_argument("--result-file", help="Path to a JSON payload for complete_role_job.")
        job_parser.add_argument(
            "--sandbox-adapter",
            default=None,
            choices=[LOCAL_DRY_RUN_ADAPTER, DOCKER_ADAPTER, GITHUB_ACTIONS_ADAPTER],
            help="Optional sandbox adapter override for resumed local orchestration after external completion.",
        )

    submit_parser = subparsers.add_parser("submit_role_result", help="Submit an external role result to the completion inbox.")
    add_pretty_flag(submit_parser)
    submit_parser.add_argument("--run-dir", help="Path to a run bundle.")
    submit_parser.add_argument("--run-id", help="Run id inside runs-dir.")
    submit_parser.add_argument(
        "--runs-dir",
        default=str(normalize_runs_dir("runs")),
        help="Base directory for runs (default: runs).",
    )
    submit_parser.add_argument("--job-id", required=True, help="Role job id.")
    submit_parser.add_argument("--runtime-target", default="codex", help="External runtime target label.")
    submit_parser.add_argument("--summary", default="", help="Job summary or result note.")
    submit_parser.add_argument(
        "--status",
        default="completed",
        choices=["completed", "failed", "blocked"],
        help="Submission status for submit_role_result.",
    )
    submit_parser.add_argument("--result-json", help="Inline JSON payload for submit_role_result.")
    submit_parser.add_argument("--result-file", help="Path to a JSON payload for submit_role_result.")
    submit_parser.add_argument(
        "--sandbox-adapter",
        default=None,
        choices=[LOCAL_DRY_RUN_ADAPTER, DOCKER_ADAPTER, GITHUB_ACTIONS_ADAPTER],
        help="Optional sandbox adapter override for resumed local orchestration after external completion.",
    )
    submit_parser.add_argument(
        "--no-consume",
        action="store_true",
        help="Write completion artifact without immediately running dispatcher loop.",
    )

    stdio_parser = subparsers.add_parser("serve_stdio", help="Serve newline-delimited JSON requests over stdio.")
    add_pretty_flag(stdio_parser)
    stdio_parser.add_argument("--unused", default="", help=argparse.SUPPRESS)

    return parser.parse_args()


def main() -> int:
    """CLI entrypoint."""
    args = parse_args()
    try:
        if args.command == "serve_stdio":
            return serve_stdio()
        result = handle_tool(args.command, args)
    except (FileNotFoundError, ValueError, json.JSONDecodeError, KeyError) as exc:
        json.dump(
            {"error": str(exc), "command": args.command},
            sys.stdout,
            ensure_ascii=False,
            indent=2 if args.pretty else None,
        )
        if args.pretty:
            sys.stdout.write("\n")
        return 1

    json.dump(result, sys.stdout, ensure_ascii=False, indent=2 if args.pretty else None)
    if args.pretty:
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
