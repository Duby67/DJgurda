#!/usr/bin/env python3
"""Проверка и синхронизация версии релиза между tag, src/__init__.py, RELEASE_NOTES.md и IMPROVEMENTS.md."""

from __future__ import annotations

import argparse
import re
import sys

from dataclasses import dataclass
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SRC_INIT = ROOT / "src" / "__init__.py"
RELEASE_NOTES = ROOT / "RELEASE_NOTES.md"
IMPROVEMENTS = ROOT / "IMPROVEMENTS.md"


@dataclass
class SyncResult:
    ok: bool
    messages: list[str]


def normalize_tag(tag: str) -> str:
    tag = tag.strip()
    if tag.startswith("refs/tags/"):
        tag = tag[len("refs/tags/") :]
    if tag.startswith("v"):
        tag = tag[1:]
    return tag


def read_version_from_src() -> str:
    text = SRC_INIT.read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    if not match:
        raise ValueError("Не удалось найти __version__ в src/__init__.py")
    return match.group(1).strip()


def ensure_release_notes_section(tag: str, release_date: str, env: str, write: bool) -> SyncResult:
    text = RELEASE_NOTES.read_text(encoding="utf-8")
    header_re = re.compile(rf"^##\s+\d{{4}}-\d{{2}}-\d{{2}}\s+\|\s+version/tag:\s*{re.escape(tag)}\s+\|\s+env:\s*{re.escape(env)}\s*$", re.MULTILINE)
    if header_re.search(text):
        return SyncResult(True, [f"RELEASE_NOTES: найден раздел для tag '{tag}' и env '{env}'"])

    if not write:
        return SyncResult(False, [f"RELEASE_NOTES: отсутствует раздел для tag '{tag}' и env '{env}'"])

    section = (
        f"## {release_date} | version/tag: {tag} | env: {env}\n"
        "- Что изменилось:\n"
        "  - ...\n"
        "- Важно для деплоя:\n"
        "  - ...\n"
        "- Breaking changes:\n"
        "  - Нет / Да (описание)\n"
        "- Ручные действия после релиза:\n"
        "  - Нет / Да (описание)\n\n"
    )

    lines = text.splitlines(keepends=True)
    insert_at = len(lines)
    for i, line in enumerate(lines):
        if line.startswith("## ") and "Как вести release notes" not in line:
            insert_at = i
            break
    new_text = "".join(lines[:insert_at]) + section + "".join(lines[insert_at:])
    RELEASE_NOTES.write_text(new_text, encoding="utf-8")
    return SyncResult(True, [f"RELEASE_NOTES: добавлен шаблон раздела для tag '{tag}'"])


def ensure_improvements_revision(tag: str, release_date: str, write: bool) -> SyncResult:
    text = IMPROVEMENTS.read_text(encoding="utf-8")
    metadata_header = "## Метаданные backlog"
    revision_prefix = "- Последняя ревизия backlog:"
    new_revision_line = f"{revision_prefix} {release_date} | version/tag: {tag}"

    messages: list[str] = []
    changed = False

    if metadata_header not in text:
        if not write:
            return SyncResult(False, ["IMPROVEMENTS: отсутствует раздел 'Метаданные backlog'"])
        insert_anchor = "## Приоритет P0 (критично)"
        insert_block = f"{metadata_header}\n{new_revision_line}\n\n"
        if insert_anchor in text:
            text = text.replace(insert_anchor, insert_block + insert_anchor, 1)
        else:
            text = text + ("\n" if not text.endswith("\n") else "") + insert_block
        changed = True
        messages.append("IMPROVEMENTS: добавлен раздел 'Метаданные backlog'")

    revision_re = re.compile(rf"^{re.escape(revision_prefix)}\s+.+$", re.MULTILINE)
    match = revision_re.search(text)
    if match:
        current_line = match.group(0).strip()
        if current_line != new_revision_line:
            if not write:
                return SyncResult(False, [f"IMPROVEMENTS: метка ревизии не совпадает. Текущая: '{current_line}'"])
            text = text[: match.start()] + new_revision_line + text[match.end() :]
            changed = True
            messages.append("IMPROVEMENTS: обновлена метка ревизии backlog")
        else:
            messages.append("IMPROVEMENTS: метка ревизии backlog актуальна")
    else:
        if not write:
            return SyncResult(False, ["IMPROVEMENTS: отсутствует строка 'Последняя ревизия backlog'"])
        text = text.replace(metadata_header, f"{metadata_header}\n{new_revision_line}", 1)
        changed = True
        messages.append("IMPROVEMENTS: добавлена строка 'Последняя ревизия backlog'")

    if changed:
        IMPROVEMENTS.write_text(text, encoding="utf-8")
    return SyncResult(True, messages)


def main() -> int:
    parser = argparse.ArgumentParser(description="Синхронизация релизных артефактов по tag")
    parser.add_argument("--tag", required=True, help="Релизный tag (например, v1.2.0 или 1.2.0)")
    parser.add_argument("--env", default="prod", help="Окружение для release notes (по умолчанию: prod)")
    parser.add_argument("--date", default=str(date.today()), help="Дата релиза YYYY-MM-DD")
    parser.add_argument("--write", action="store_true", help="Применить изменения в файлах")
    args = parser.parse_args()

    raw_tag = args.tag.strip()
    norm_tag = normalize_tag(raw_tag)
    src_version = read_version_from_src()

    if src_version != norm_tag:
        print(
            f"ERROR: version mismatch: src.__version__='{src_version}' vs tag='{raw_tag}' (normalized='{norm_tag}')",
            file=sys.stderr,
        )
        return 1

    print(f"OK: src.__version__ == tag ({src_version})")

    notes_result = ensure_release_notes_section(raw_tag, args.date, args.env, args.write)
    for message in notes_result.messages:
        print(message)

    improvements_result = ensure_improvements_revision(raw_tag, args.date, args.write)
    for message in improvements_result.messages:
        print(message)

    if not notes_result.ok or not improvements_result.ok:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
