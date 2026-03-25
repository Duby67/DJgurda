#!/usr/bin/env python3
"""Планирует и опционально выполняет promotion релизов между ветками."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

from typing import Any

from scripts.config import ROOT
from ..rules.versioning import ReleaseVersion, parse_release_version

SRC_INIT = ROOT / "src" / "__init__.py"
VERSION_PATTERN = re.compile(r'(__version__\s*=\s*")([^"]+)(")')


def run_git_command(args: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    """Запускает git-команду в корне репозитория."""
    result = subprocess.run(
        ["git", "-C", str(ROOT), *args],
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if check and result.returncode != 0:
        raise ValueError(result.stderr.strip() or result.stdout.strip() or f"git {' '.join(args)} failed")
    return result


def normalize_ref_name(value: str) -> str:
    """Нормализует имя ветки или remote."""
    return value.strip()


def current_branch_name() -> str:
    """Возвращает текущую локальную ветку."""
    result = run_git_command(["branch", "--show-current"], check=True)
    branch = result.stdout.strip()
    if not branch:
        raise ValueError("Не удалось определить текущую ветку")
    return branch


def ensure_ref_exists(ref: str) -> None:
    """Проверяет существование ref."""
    run_git_command(["rev-parse", "--verify", ref], check=True)


def read_file_from_ref(ref: str, relative_path: str) -> str:
    """Читает файл из указанного git ref."""
    result = run_git_command(["show", f"{ref}:{relative_path}"], check=True)
    return result.stdout


def read_version_from_text(text: str) -> str:
    """Извлекает __version__ из текста src/__init__.py."""
    match = VERSION_PATTERN.search(text)
    if not match:
        raise ValueError("Не удалось найти __version__ в src/__init__.py")
    return match.group(2).strip()


def read_version_from_ref(ref: str) -> ReleaseVersion:
    """Читает release-версию из src/__init__.py для указанного ref."""
    return parse_release_version(read_version_from_text(read_file_from_ref(ref, "src/__init__.py")))


def head_tags(ref: str, prefix: str) -> list[str]:
    """Возвращает tags, которые стоят прямо на HEAD указанного ref."""
    result = run_git_command(["tag", "--points-at", ref, "--list", f"{prefix}*"], check=True)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def find_latest_release_tag(ref: str, prefix: str) -> str | None:
    """Ищет максимальный stable/preview release tag, достижимый из ref."""
    result = run_git_command(["tag", "--merged", ref, "--list", f"{prefix}*"], check=True)
    tags = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    parsed: list[tuple[ReleaseVersion, str]] = []
    for tag in tags:
        try:
            parsed.append((parse_release_version(tag), tag))
        except ValueError:
            continue
    if not parsed:
        return None
    parsed.sort(key=lambda item: item[0].sort_key())
    return parsed[-1][1]


def ahead_behind(left: str, right: str) -> dict[str, int]:
    """Возвращает сколько коммитов left/right расходятся."""
    result = run_git_command(["rev-list", "--left-right", "--count", f"{left}...{right}"], check=True)
    raw = result.stdout.strip().split()
    if len(raw) != 2:
        raise ValueError("Не удалось определить ahead/behind для release-плана")
    return {
        "left_only": int(raw[0]),
        "right_only": int(raw[1]),
    }


def working_tree_is_clean() -> bool:
    """Проверяет, что рабочее дерево чистое."""
    result = run_git_command(["status", "--porcelain"])
    return not result.stdout.strip()


def update_src_version_file(version: str) -> None:
    """Обновляет __version__ в src/__init__.py."""
    text = SRC_INIT.read_text(encoding="utf-8")
    updated, count = VERSION_PATTERN.subn(rf'\g<1>{version}\g<3>', text, count=1)
    if count != 1:
        raise ValueError("Не удалось обновить __version__ в src/__init__.py")
    SRC_INIT.write_text(updated, encoding="utf-8")


def run_release_sync(tag: str, env: str) -> None:
    """Синхронизирует release docs после обновления версии."""
    result = subprocess.run(
        [sys.executable, "-m", "scripts.release.automation.sync", "--tag", tag, "--env", env, "--write"],
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        cwd=str(ROOT),
    )
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or result.stdout.strip() or "release_sync failed")


def checkout_branch(branch: str) -> None:
    """Переключает рабочее дерево на указанную ветку."""
    run_git_command(["checkout", branch], check=True)


def merge_branch(source_branch: str, target_branch: str, next_tag: str) -> dict[str, Any]:
    """Мержит source_branch в target_branch без fast-forward."""
    result = run_git_command(
        [
            "merge",
            "--no-ff",
            source_branch,
            "-m",
            f"release: merge {source_branch} into {target_branch} for {next_tag}",
        ],
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or result.stdout.strip() or "git merge failed")
    return {
        "stdout": result.stdout.strip(),
        "already_up_to_date": "Already up to date." in result.stdout,
    }


def commit_release_bump(target_branch: str, next_version: str) -> str:
    """Коммитит version bump и release docs."""
    run_git_command(
        [
            "add",
            "src/__init__.py",
            "docs/release_notes.md",
            "docs/exec-plans/tech-debt-tracker.md",
        ],
        check=True,
    )
    commit_message = f"release({target_branch}): set version to {next_version}"
    run_git_command(["commit", "-m", commit_message], check=True)
    return commit_message


def create_annotated_tag(tag: str) -> None:
    """Создает annotated git tag."""
    run_git_command(["tag", "-a", tag, "-m", f"Release {tag}"], check=True)


def push_release(remote: str, target_branch: str, tag: str) -> None:
    """Пушит ветку и tag в remote."""
    run_git_command(["push", remote, target_branch], check=True)
    run_git_command(["push", remote, tag], check=True)


def ensure_branch_state_consistent(ref: str, prefix: str, version: ReleaseVersion) -> str | None:
    """Проверяет, что src.__version__ совпадает с последним release tag на ветке."""
    latest_tag = find_latest_release_tag(ref, prefix)
    if latest_tag is None:
        return None
    if parse_release_version(latest_tag).normalized() != version.normalized():
        raise ValueError(
            f"Ветка {ref} несогласована: src.__version__={version.normalized()} но последний release tag={latest_tag}"
        )
    return latest_tag


def infer_target_profile(target_branch: str, target_kind: str | None, release_env: str | None, main_branch: str) -> dict[str, str]:
    """Определяет тип promotion для целевой ветки."""
    if target_kind is None:
        if target_branch == main_branch:
            target_kind = "stable"
        elif target_branch == "dev":
            target_kind = "preview"
        else:
            raise ValueError(
                "Для нестандартной target-ветки укажите --target-kind stable|preview, "
                "чтобы promotion был однозначным"
            )

    if release_env is None:
        if target_kind == "stable":
            release_env = "prod" if target_branch == main_branch else target_branch
        else:
            release_env = "dev" if target_branch == "dev" else target_branch

    return {
        "target_kind": target_kind,
        "release_env": release_env,
    }


def compute_next_preview_version(
    remote_main_version: ReleaseVersion,
    remote_target_version: ReleaseVersion,
) -> tuple[ReleaseVersion, str]:
    """Определяет следующий preview tag для dev-like ветки."""
    expected_base = remote_main_version.next_stable()
    if remote_target_version.is_preview and remote_target_version.stable().normalized() == expected_base.normalized():
        return (
            remote_target_version.next_preview(),
            "continue current preview cycle by incrementing preview suffix",
        )
    return (
        expected_base.start_preview_cycle(),
        "start new preview cycle from next stable version after main",
    )


def compute_next_stable_version(
    source_branch: str,
    source_version: ReleaseVersion,
    remote_target_version: ReleaseVersion,
    main_branch: str,
    warnings: list[str],
) -> tuple[ReleaseVersion, str]:
    """Определяет следующий stable tag для main-like ветки."""
    expected_next = remote_target_version.next_stable()

    if source_version.is_preview:
        promoted = source_version.stable()
        if promoted.normalized() != expected_next.normalized():
            raise ValueError(
                f"Preview-ветка {source_branch} готовит {promoted.normalized()}, "
                f"но следующий stable release для target должен быть {expected_next.normalized()}"
            )
        if source_branch != "dev":
            warnings.append("preview_source_outside_dev_branch")
        return promoted, "promote preview release to stable by stripping preview suffix"

    if source_branch != "dev":
        warnings.append("direct_non_dev_promotion_to_main")
    if source_branch != main_branch:
        warnings.append("stable_release_bypasses_preview_branch")
    return expected_next, "promote directly to next stable version from target branch baseline"


def recompute_next_release_tag(
    *,
    source_branch: str,
    target_branch: str,
    target_kind: str,
    main_branch: str,
    remote: str,
    prefix: str,
) -> str:
    """Пересчитывает ожидаемый release tag по текущему git-состоянию."""
    source_version = read_version_from_ref(source_branch)
    remote_target_version = read_version_from_ref(f"{remote}/{target_branch}")
    remote_main_version = read_version_from_ref(f"{remote}/{main_branch}")

    if target_kind == "preview":
        next_version, _ = compute_next_preview_version(remote_main_version, remote_target_version)
    else:
        warnings: list[str] = []
        next_version, _ = compute_next_stable_version(
            source_branch=source_branch,
            source_version=source_version,
            remote_target_version=remote_target_version,
            main_branch=main_branch,
            warnings=warnings,
        )
    return next_version.tag(prefix)


def build_execution_preflight(
    *,
    source_branch: str,
    target_branch: str,
    target_kind: str,
    main_branch: str,
    remote: str,
    prefix: str,
    planned_tag: str,
) -> dict[str, Any]:
    """Строит preflight-проверки перед execute-стадией promotion."""
    checks: list[dict[str, Any]] = []
    missing_refs: list[str] = []
    for ref in (
        f"refs/heads/{source_branch}",
        f"refs/heads/{target_branch}",
        f"refs/remotes/{remote}/{target_branch}",
        f"refs/heads/{main_branch}",
        f"refs/remotes/{remote}/{main_branch}",
    ):
        try:
            ensure_ref_exists(ref)
        except ValueError:
            missing_refs.append(ref)

    checks.append(
        {
            "id": "working_tree_clean",
            "status": "passed" if working_tree_is_clean() else "failed",
            "details": "execute mutates the repo root and requires a clean working tree",
        }
    )
    checks.append(
        {
            "id": "required_refs_exist",
            "status": "passed" if not missing_refs else "failed",
            "details": "all local and remote refs required for promotion are present",
            "missing_refs": missing_refs,
        }
    )

    if not missing_refs:
        target_sync = ahead_behind(target_branch, f"{remote}/{target_branch}")
        checks.append(
            {
                "id": "target_can_fast_forward_to_remote",
                "status": "passed" if target_sync["left_only"] == 0 else "failed",
                "details": f"local {target_branch} must not contain commits missing from {remote}/{target_branch}",
                "divergence": target_sync,
            }
        )

        source_gap = ahead_behind(f"{remote}/{target_branch}", source_branch)
        checks.append(
            {
                "id": "source_ahead_of_remote_target",
                "status": "passed" if source_gap["right_only"] > 0 else "failed",
                "details": f"{source_branch} should still be ahead of {remote}/{target_branch} when execute starts",
                "divergence": source_gap,
            }
        )

        recomputed_tag = recompute_next_release_tag(
            source_branch=source_branch,
            target_branch=target_branch,
            target_kind=target_kind,
            main_branch=main_branch,
            remote=remote,
            prefix=prefix,
        )
        checks.append(
            {
                "id": "planned_release_still_matches_remote_state",
                "status": "passed" if recomputed_tag == planned_tag else "failed",
                "details": "the planned next release tag still matches current remote state",
                "planned_tag": planned_tag,
                "recomputed_tag": recomputed_tag,
            }
        )

    failed_checks = [check["id"] for check in checks if check["status"] != "passed"]
    return {
        "ready": not failed_checks,
        "failed_checks": failed_checks,
        "checks": checks,
    }


def build_release_plan(
    *,
    source_branch: str,
    target_branch: str,
    target_kind: str | None,
    release_env: str | None,
    main_branch: str,
    remote: str,
    prefix: str,
) -> dict[str, Any]:
    """Строит branch-aware release-план без модификации git-состояния."""
    ensure_ref_exists(f"refs/heads/{source_branch}")
    ensure_ref_exists(f"refs/heads/{target_branch}")
    ensure_ref_exists(f"refs/remotes/{remote}/{target_branch}")
    ensure_ref_exists(f"refs/heads/{main_branch}")
    ensure_ref_exists(f"refs/remotes/{remote}/{main_branch}")

    if source_branch == target_branch:
        raise ValueError("source и target branch не должны совпадать")

    profile = infer_target_profile(target_branch, target_kind, release_env, main_branch)
    warnings: list[str] = []

    source_src_version = read_version_from_ref(source_branch)
    target_src_version = read_version_from_ref(target_branch)
    remote_target_src_version = read_version_from_ref(f"{remote}/{target_branch}")
    main_src_version = read_version_from_ref(main_branch)
    remote_main_src_version = read_version_from_ref(f"{remote}/{main_branch}")

    source_latest_tag = ensure_branch_state_consistent(source_branch, prefix, source_src_version)
    target_latest_tag = ensure_branch_state_consistent(target_branch, prefix, target_src_version)
    remote_target_latest_tag = ensure_branch_state_consistent(f"{remote}/{target_branch}", prefix, remote_target_src_version)
    main_latest_tag = ensure_branch_state_consistent(main_branch, prefix, main_src_version)
    remote_main_latest_tag = ensure_branch_state_consistent(f"{remote}/{main_branch}", prefix, remote_main_src_version)

    if remote_main_src_version.normalized() != main_src_version.normalized():
        warnings.append("local_main_differs_from_remote_main")
    if remote_target_src_version.normalized() != target_src_version.normalized():
        warnings.append("local_target_differs_from_remote_target")

    if profile["target_kind"] == "preview":
        next_version, decision_rule = compute_next_preview_version(remote_main_src_version, remote_target_src_version)
    else:
        next_version, decision_rule = compute_next_stable_version(
            source_branch=source_branch,
            source_version=source_src_version,
            remote_target_version=remote_target_src_version,
            main_branch=main_branch,
            warnings=warnings,
        )

    next_tag = next_version.tag(prefix)
    divergence = ahead_behind(target_branch, source_branch)
    remote_divergence = ahead_behind(f"{remote}/{target_branch}", source_branch)
    if remote_divergence["right_only"] == 0:
        warnings.append("source_branch_not_ahead_of_target")

    planned_steps = [
        f"checkout {target_branch}",
        f"fast-forward {target_branch} to {remote}/{target_branch}",
        f"merge --no-ff {source_branch} into {target_branch}",
        f"update src/__init__.py to {next_version.normalized()}",
        f"run python -m scripts.release.automation.sync --tag {next_tag} --env {profile['release_env']} --write",
        f"commit release bump as 'release({target_branch}): set version to {next_version.normalized()}'",
        f"create annotated tag {next_tag}",
        f"optional push: git push {remote} {target_branch} && git push {remote} {next_tag}",
    ]

    strategy = "promote_to_preview" if profile["target_kind"] == "preview" else "promote_to_stable"
    preflight = build_execution_preflight(
        source_branch=source_branch,
        target_branch=target_branch,
        target_kind=profile["target_kind"],
        main_branch=main_branch,
        remote=remote,
        prefix=prefix,
        planned_tag=next_tag,
    )
    return {
        "strategy": strategy,
        "source_branch": source_branch,
        "target_branch": target_branch,
        "target_kind": profile["target_kind"],
        "release_env": profile["release_env"],
        "main_branch": main_branch,
        "remote": remote,
        "tag_prefix": prefix,
        "working_tree_clean": working_tree_is_clean(),
        "current_branch": current_branch_name(),
        "warnings": warnings,
        "source_state": {
            "src_version": source_src_version.normalized(),
            "head_tags": head_tags(source_branch, prefix),
            "latest_release_tag": source_latest_tag,
        },
        "target_state": {
            "local_src_version": target_src_version.normalized(),
            "remote_src_version": remote_target_src_version.normalized(),
            "local_head_tags": head_tags(target_branch, prefix),
            "local_latest_release_tag": target_latest_tag,
            "remote_latest_release_tag": remote_target_latest_tag,
        },
        "main_state": {
            "local_src_version": main_src_version.normalized(),
            "remote_src_version": remote_main_src_version.normalized(),
            "local_latest_release_tag": main_latest_tag,
            "remote_latest_release_tag": remote_main_latest_tag,
        },
        "next_release": {
            "version": next_version.normalized(),
            "tag": next_tag,
            "decision_rule": decision_rule,
        },
        "execution_preflight": preflight,
        "divergence": {
            "target_vs_source": divergence,
            "remote_target_vs_source": remote_divergence,
        },
        "planned_steps": planned_steps,
    }


def execute_release(
    *,
    plan: dict[str, Any],
    push: bool,
) -> dict[str, Any]:
    """Выполняет release-операции локально и опционально пушит их в remote."""
    source_branch = plan["source_branch"]
    target_branch = plan["target_branch"]
    remote = plan["remote"]
    main_branch = plan["main_branch"]
    target_kind = plan["target_kind"]
    prefix = plan["tag_prefix"]
    release_env = plan["release_env"]
    next_version = plan["next_release"]["version"]
    next_tag = plan["next_release"]["tag"]
    preflight = build_execution_preflight(
        source_branch=source_branch,
        target_branch=target_branch,
        target_kind=target_kind,
        main_branch=main_branch,
        remote=remote,
        prefix=prefix,
        planned_tag=next_tag,
    )
    if not preflight["ready"]:
        failed = ", ".join(preflight["failed_checks"])
        raise ValueError(f"Execution preflight failed: {failed}")

    checkout_branch(target_branch)
    sync_result = run_git_command(["merge", "--ff-only", f"{remote}/{target_branch}"], check=False)
    if sync_result.returncode != 0:
        raise ValueError(
            sync_result.stderr.strip()
            or sync_result.stdout.strip()
            or f"Не удалось fast-forward локальную ветку {target_branch} до {remote}/{target_branch}",
        )

    merge_result = merge_branch(source_branch, target_branch, next_tag)
    update_src_version_file(next_version)
    run_release_sync(next_tag, release_env)
    commit_message = commit_release_bump(target_branch, next_version)
    create_annotated_tag(next_tag)

    if push:
        push_release(remote, target_branch, next_tag)

    return {
        "execution_preflight": preflight,
        "checked_out_branch": target_branch,
        "merge": merge_result,
        "version_updated_to": next_version,
        "release_tag_created": next_tag,
        "release_bump_commit_message": commit_message,
        "release_env": release_env,
        "pushed": push,
    }


def render_human_plan(plan: dict[str, Any], execution: dict[str, Any] | None) -> str:
    """Рендерит короткий человекочитаемый статус release plan."""
    preflight = plan.get("execution_preflight", {})
    lines = [
        f"Strategy: {plan['strategy']}",
        f"Source branch: {plan['source_branch']}",
        f"Target branch: {plan['target_branch']} ({plan['target_kind']})",
        f"Release env: {plan['release_env']}",
        f"Main branch baseline: {plan['main_branch']}",
        f"Remote: {plan['remote']}",
        f"Current branch: {plan['current_branch']}",
        f"Working tree clean: {'yes' if plan['working_tree_clean'] else 'no'}",
        f"Current release on {plan['remote']}/{plan['target_branch']}: "
        f"{plan['target_state']['remote_latest_release_tag'] or plan['target_state']['remote_src_version']}",
        f"Next release: {plan['next_release']['tag']} ({plan['next_release']['version']})",
        f"Decision rule: {plan['next_release']['decision_rule']}",
        f"Execution preflight ready: {'yes' if preflight.get('ready') else 'no'}",
    ]
    if preflight.get("checks"):
        lines.append("Execution preflight:")
        for check in preflight["checks"]:
            lines.append(f"- {check['id']}: {check['status']}")
    if plan["warnings"]:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in plan["warnings"])
    lines.append("Planned steps:")
    lines.extend(f"- {step}" for step in plan["planned_steps"])

    if execution is not None:
        lines.extend(
            [
                "Execution:",
                f"- checked out: {execution['checked_out_branch']}",
                f"- merge already up to date: {'yes' if execution['merge']['already_up_to_date'] else 'no'}",
                f"- version updated to: {execution['version_updated_to']}",
                f"- release env synced: {execution['release_env']}",
                f"- tag created: {execution['release_tag_created']}",
                f"- pushed: {'yes' if execution['pushed'] else 'no'}",
            ]
        )
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Парсит аргументы CLI."""
    parser = argparse.ArgumentParser(
        description="Планирование и выполнение promotion-релизов между dev/main и другими target-ветками.",
    )
    parser.add_argument("--source-branch", help="Ветка-источник. По умолчанию используется текущая.")
    parser.add_argument("--target-branch", required=True, help="Целевая ветка promotion.")
    parser.add_argument(
        "--target-kind",
        choices=("stable", "preview"),
        help="Тип целевой ветки. Для main/dev можно не указывать, для остальных веток обязателен.",
    )
    parser.add_argument(
        "--release-env",
        help="env для scripts.release.automation.sync. По умолчанию подбирается по target-ветке.",
    )
    parser.add_argument(
        "--main-branch",
        default="main",
        help="Базовая stable-ветка, от которой считается следующая версия. По умолчанию: main.",
    )
    parser.add_argument("--remote", default="origin", help="Remote для release-операций. По умолчанию: origin.")
    parser.add_argument("--tag-prefix", default="v", help="Префикс release tag. По умолчанию: v.")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Реально выполнить checkout/merge/version bump/tag. Без флага работает только dry-run.",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="После --execute дополнительно выполнить git push ветки и тега.",
    )
    parser.add_argument(
        "--human",
        action="store_true",
        help="Печатать короткий человекочитаемый план вместо JSON.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Печатать JSON с отступами.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Точка входа CLI."""
    args = parse_args(argv)
    try:
        if args.push and not args.execute:
            raise ValueError("--push можно использовать только вместе с --execute")

        source_branch = normalize_ref_name(args.source_branch) if args.source_branch else current_branch_name()
        target_branch = normalize_ref_name(args.target_branch)
        main_branch = normalize_ref_name(args.main_branch)
        remote = normalize_ref_name(args.remote)
        prefix = args.tag_prefix

        plan = build_release_plan(
            source_branch=source_branch,
            target_branch=target_branch,
            target_kind=args.target_kind,
            release_env=args.release_env,
            main_branch=main_branch,
            remote=remote,
            prefix=prefix,
        )
        execution = execute_release(plan=plan, push=args.push) if args.execute else None
        result = {
            "mode": "execute" if args.execute else "dry_run",
            "plan": plan,
            "execution": execution,
        }
    except ValueError as exc:
        if args.human:
            sys.stdout.write(f"Error: {exc}\n")
        else:
            json.dump(
                {"error": str(exc)},
                sys.stdout,
                ensure_ascii=False,
                indent=2 if args.pretty else None,
            )
            if args.pretty:
                sys.stdout.write("\n")
        return 1

    if args.human:
        sys.stdout.write(render_human_plan(plan, execution))
        return 0

    json.dump(
        result,
        sys.stdout,
        ensure_ascii=False,
        indent=2 if args.pretty else None,
    )
    if args.pretty:
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
