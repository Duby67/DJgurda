#!/usr/bin/env python3
"""Совместимая обертка для preview promotion в dev."""

from __future__ import annotations

import sys

try:
    from release_promote import main as promote_main
except ImportError:  # pragma: no cover - fallback for module execution
    from scripts.release_promote import main as promote_main


def ensure_target_is_dev(args: list[str]) -> None:
    """Проверяет, что wrapper не перенаправляют в другую target-ветку."""
    if "--target-branch" not in args:
        return
    index = args.index("--target-branch")
    if index + 1 >= len(args):
        raise ValueError("--target-branch требует значение")
    if args[index + 1] != "dev":
        raise ValueError("scripts/release_dev.py поддерживает только --target-branch dev")


def main(argv: list[str] | None = None) -> int:
    """Проксирует вызов в release_promote.py с target=dev."""
    args = list(argv if argv is not None else sys.argv[1:])
    ensure_target_is_dev(args)
    if "--target-branch" not in args:
        args = ["--target-branch", "dev", *args]
    if "--target-kind" not in args:
        args = ["--target-kind", "preview", *args]
    return promote_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
