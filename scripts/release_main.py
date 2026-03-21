#!/usr/bin/env python3
"""Готовит и опционально публикует release в main с semver bump и tag."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SRC_INIT = ROOT / "src" / "__init__.py"
RELEASE_SYNC = ROOT / "scripts" / "release_sync.py"
VERSION_PATTERN = re.compile(r'(__version__\s*=\s*")([^"]+)(")')


@dataclass(frozen=True)
class SemVer:
    major: int
    minor: int
    patch: int

    def normalized(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    def tag(self, prefix: str = "v") -> str:
        return f"{prefix}{self.normalized()}"

    def next_release(self) -> "SemVer":
        if self.patch < 9:
            return SemVer(self.major, self.minor, self.patch + 1)
        return SemVer(self.major, self.minor + 1, 0)


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


def parse_semver(value: str) -> SemVer:
    """Парсит строку вида 1.2.3 или v1.2.3."""
    normalized = value.strip()
    if normalized.startswith("refs/tags/"):
        normalized = normalized[len("refs/tags/") :]
    if normalized.startswith("v"):
        normalized = normalized[1:]

    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", normalized)
    if not match:
        raise ValueError(f"Неподдерживаемая версия: '{value}'")
    return SemVer(int(match.group(1)), int(match.group(2)), int(match.group(3)))


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


def read_version_from_ref(ref: str) -> str:
    """Читает версию из src/__init__.py для указанного ref."""
    return read_version_from_text(read_file_from_ref(ref, "src/__init__.py"))


def find_latest_release_tag(ref: str, prefix: str) -> str | None:
    """Ищет максимальный semver-tag, достижимый из ref."""
    result = run_git_command(["tag", "--merged", ref, "--list", f"{prefix}*"], check=True)
    tags = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    parsed: list[tuple[SemVer, str]] = []
    for tag in tags:
        try:
            parsed.append((parse_semver(tag), tag))
        except ValueError:
            continue
    if not parsed:
        return None
    parsed.sort(key=lambda item: (item[0].major, item[0].minor, item[0].patch))
    return parsed[-1][1]


def head_tags(ref: str, prefix: str) -> list[str]:
    """Возвращает tags, которые стоят прямо на HEAD указанного ref."""
    result = run_git_command(["tag", "--points-at", ref, "--list", f"{prefix}*"], check=True)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


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


def run_release_sync(tag: str) -> None:
    """Синхронизирует release docs после обновления версии."""
    result = subprocess.run(
        [sys.executable, str(RELEASE_SYNC), "--tag", tag, "--write"],
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


def commit_release_bump(next_version: str) -> str:
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
    commit_message = f"release: bump version to {next_version}"
    run_git_command(["commit", "-m", commit_message], check=True)
    return commit_message


def create_annotated_tag(tag: str) -> None:
    """Создает annotated git tag."""
    run_git_command(["tag", "-a", tag, "-m", f"Release {tag}"], check=True)


def push_release(remote: str, target_branch: str, tag: str) -> None:
    """Пушит main и tag в remote."""
    run_git_command(["push", remote, target_branch], check=True)
    run_git_command(["push", remote, tag], check=True)


def build_release_plan(
    *,
    source_branch: str,
    target_branch: str,
    remote: str,
    prefix: str,
) -> dict[str, Any]:
    """Строит release-план без модификации git-состояния."""
    ensure_ref_exists(f"refs/heads/{source_branch}")
    ensure_ref_exists(f"refs/heads/{target_branch}")
    ensure_ref_exists(f"refs/remotes/{remote}/{target_branch}")

    target_src_version = parse_semver(read_version_from_ref(target_branch))
    remote_target_src_version = parse_semver(read_version_from_ref(f"{remote}/{target_branch}"))
    latest_tag = find_latest_release_tag(target_branch, prefix)
    remote_latest_tag = find_latest_release_tag(f"{remote}/{target_branch}", prefix)
    head_release_tags = head_tags(target_branch, prefix)

    if latest_tag is not None and parse_semver(latest_tag) != target_src_version:
        raise ValueError(
            f"Локальная ветка {target_branch} несогласована: src.__version__={target_src_version.normalized()} "
            f"но последний release tag={latest_tag}"
        )
    if remote_latest_tag is not None and parse_semver(remote_latest_tag) != remote_target_src_version:
        raise ValueError(
            f"Remote ветка {remote}/{target_branch} несогласована: src.__version__={remote_target_src_version.normalized()} "
            f"но последний release tag={remote_latest_tag}"
        )

    base_version = remote_target_src_version
    next_version = base_version.next_release()
    next_tag = next_version.tag(prefix)

    divergence = ahead_behind(target_branch, source_branch)
    remote_divergence = ahead_behind(f"{remote}/{target_branch}", source_branch)

    return {
        "source_branch": source_branch,
        "target_branch": target_branch,
        "remote": remote,
        "working_tree_clean": working_tree_is_clean(),
        "current_branch": current_branch_name(),
        "target_state": {
            "local_src_version": target_src_version.normalized(),
            "remote_src_version": remote_target_src_version.normalized(),
            "local_head_tags": head_release_tags,
            "local_latest_release_tag": latest_tag,
            "remote_latest_release_tag": remote_latest_tag,
        },
        "next_release": {
            "version": next_version.normalized(),
            "tag": next_tag,
            "bump_rule": "patch +1; when patch reaches 9, next release increments minor and resets patch to 0",
        },
        "divergence": {
            "target_vs_source": divergence,
            "remote_target_vs_source": remote_divergence,
        },
        "planned_steps": [
            f"checkout {target_branch}",
            f"merge --no-ff {source_branch} into {target_branch}",
            f"update src/__init__.py to {next_version.normalized()}",
            f"run scripts/release_sync.py --tag {next_tag} --write",
            f"commit release bump as 'release: bump version to {next_version.normalized()}'",
            f"create annotated tag {next_tag}",
            f"optional push: git push {remote} {target_branch} && git push {remote} {next_tag}",
        ],
    }


def execute_release(
    *,
    plan: dict[str, Any],
    prefix: str,
    push: bool,
) -> dict[str, Any]:
    """Выполняет release-операции локально и опционально пушит их в remote."""
    if not plan["working_tree_clean"]:
        raise ValueError("Для --execute требуется чистое рабочее дерево")

    source_branch = plan["source_branch"]
    target_branch = plan["target_branch"]
    remote = plan["remote"]
    next_version = plan["next_release"]["version"]
    next_tag = plan["next_release"]["tag"]

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
    run_release_sync(next_tag)
    commit_message = commit_release_bump(next_version)
    create_annotated_tag(next_tag)

    if push:
        push_release(remote, target_branch, next_tag)

    return {
        "checked_out_branch": target_branch,
        "merge": merge_result,
        "version_updated_to": next_version,
        "release_tag_created": next_tag,
        "release_bump_commit_message": commit_message,
        "pushed": push,
    }


def render_human_plan(plan: dict[str, Any], execution: dict[str, Any] | None) -> str:
    """Рендерит короткий человекочитаемый статус release plan."""
    lines = [
        f"Source branch: {plan['source_branch']}",
        f"Target branch: {plan['target_branch']}",
        f"Remote: {plan['remote']}",
        f"Current branch: {plan['current_branch']}",
        f"Working tree clean: {'yes' if plan['working_tree_clean'] else 'no'}",
        f"Current release on {plan['remote']}/{plan['target_branch']}: "
        f"{plan['target_state']['remote_latest_release_tag'] or plan['target_state']['remote_src_version']}",
        f"Next release: {plan['next_release']['tag']} ({plan['next_release']['version']})",
        "Planned steps:",
    ]
    lines.extend(f"- {step}" for step in plan["planned_steps"])

    if execution is not None:
        lines.extend(
            [
                "Execution:",
                f"- checked out: {execution['checked_out_branch']}",
                f"- merge already up to date: {'yes' if execution['merge']['already_up_to_date'] else 'no'}",
                f"- version updated to: {execution['version_updated_to']}",
                f"- tag created: {execution['release_tag_created']}",
                f"- pushed: {'yes' if execution['pushed'] else 'no'}",
            ]
        )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    """Парсит аргументы CLI."""
    parser = argparse.ArgumentParser(
        description="Подготовка release в main с автоинкрементом версии и tag.",
    )
    parser.add_argument("--source-branch", help="Ветка-источник релиза. По умолчанию используется текущая.")
    parser.add_argument("--target-branch", default="main", help="Целевая release-ветка. По умолчанию: main.")
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
    return parser.parse_args()


def main() -> int:
    """Точка входа CLI."""
    args = parse_args()
    try:
        if args.push and not args.execute:
            raise ValueError("--push можно использовать только вместе с --execute")

        source_branch = normalize_ref_name(args.source_branch) if args.source_branch else current_branch_name()
        target_branch = normalize_ref_name(args.target_branch)
        remote = normalize_ref_name(args.remote)
        prefix = args.tag_prefix

        plan = build_release_plan(
            source_branch=source_branch,
            target_branch=target_branch,
            remote=remote,
            prefix=prefix,
        )
        execution = execute_release(plan=plan, prefix=prefix, push=args.push) if args.execute else None
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
