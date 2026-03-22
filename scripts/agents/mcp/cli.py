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
from scripts.agents.lifecycle.request_approval import build_output as build_request_approval_output
from scripts.agents.lifecycle.status import build_status as build_run_status, render_human_status
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
from scripts.agents.sandbox_adapters import DOCKER_ADAPTER, LOCAL_DRY_RUN_ADAPTER


def load_json(path: Path) -> dict[str, Any]:
    """Reads a JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


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
        return {
            "tool": "show_run_status",
            "run_dir": status_payload["run_dir"],
            "human": render_human_status(status_payload),
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


def build_claim_role_job(args: argparse.Namespace) -> dict[str, Any]:
    """Claims an external role job."""
    run_dir = resolve_run_dir(run_dir=args.run_dir, run_id=args.run_id, runs_dir=args.runs_dir)
    result = claim_job(run_dir, job_id=args.job_id, claimed_by=args.claimed_by)
    return {
        "tool": "claim_role_job",
        **result,
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
    return {
        "tool": "complete_role_job",
        **result,
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
    return {
        "tool": "fail_role_job",
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
    if command == "request_commit_approval":
        return build_commit_or_push_request(args, checkpoint="commit")
    if command == "request_push_approval":
        return build_commit_or_push_request(args, checkpoint="push")
    if command == "claim_role_job":
        return build_claim_role_job(args)
    if command == "complete_role_job":
        return build_complete_role_job(args)
    if command == "fail_role_job":
        return build_fail_role_job(args)
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
        default=LOCAL_DRY_RUN_ADAPTER,
        choices=[LOCAL_DRY_RUN_ADAPTER, DOCKER_ADAPTER],
        help="Sandbox adapter for automated verification steps.",
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
        default=LOCAL_DRY_RUN_ADAPTER,
        choices=[LOCAL_DRY_RUN_ADAPTER, DOCKER_ADAPTER],
        help="Sandbox adapter for resumed local orchestration steps.",
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
        job_parser.add_argument("--summary", default="", help="Job summary or result note.")
        job_parser.add_argument("--reason", default="", help="Failure reason.")
        job_parser.add_argument("--result-json", help="Inline JSON payload for complete_role_job.")
        job_parser.add_argument("--result-file", help="Path to a JSON payload for complete_role_job.")
        job_parser.add_argument(
            "--sandbox-adapter",
            default=LOCAL_DRY_RUN_ADAPTER,
            choices=[LOCAL_DRY_RUN_ADAPTER, DOCKER_ADAPTER],
            help="Sandbox adapter for resumed local orchestration after external completion.",
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
