#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

TOKEN_RE = re.compile(r"(\w+)=([^\s]+)")


def parse_tokens(line: str) -> dict[str, str]:
    return {key: value for key, value in TOKEN_RE.findall(line)}


def find_last(lines: list[str], marker: str) -> str | None:
    for line in reversed(lines):
        if "[container]" in line and marker in line:
            return line
    return None


def main() -> int:
    if len(sys.argv) != 2:
        print("smoke_check_result=fail reason=usage", flush=True)
        return 2

    log_path = Path(sys.argv[1])
    if not log_path.is_file():
        print(f"smoke_check_result=fail reason=log_not_found log_file={log_path}", flush=True)
        return 2

    lines = log_path.read_text(encoding="utf-8").splitlines()

    health_line = find_last(lines, "health_verdict=")
    auth_line = find_last(lines, "auth_verdict=")
    youtube_auth_line = find_last(lines, "youtube_auth_cookies_after")
    youtube_compare_line = find_last(lines, "cookies_compare domain=youtube.com")

    if not health_line or not auth_line or not youtube_auth_line or not youtube_compare_line:
        print(
            "smoke_check_result=fail reason=markers_missing "
            f"health_line={bool(health_line)} auth_line={bool(auth_line)} "
            f"youtube_auth_line={bool(youtube_auth_line)} youtube_compare_line={bool(youtube_compare_line)}",
            flush=True,
        )
        return 1

    health = parse_tokens(health_line)
    auth = parse_tokens(auth_line)
    youtube_auth = parse_tokens(youtube_auth_line)
    youtube_compare = parse_tokens(youtube_compare_line)

    checks = {
        "health_ok": health.get("health_verdict") == "healthy",
        "auth_ok": auth.get("auth_verdict") == "authenticated",
        "youtube_auth_cookie_dump_ok": youtube_auth.get("status") == "ok" and int(youtube_auth.get("count", "0")) > 0,
        "youtube_cookie_changed": youtube_compare.get("status") == "changed",
    }

    print(
        "smoke_check_summary "
        f"health_verdict={health.get('health_verdict', 'missing')} "
        f"health_reason={health.get('reason', 'missing')} "
        f"auth_verdict={auth.get('auth_verdict', 'missing')} "
        f"auth_reason={auth.get('reason', 'missing')} "
        f"youtube_auth_cookie_count={youtube_auth.get('count', 'missing')} "
        f"youtube_cookie_compare_status={youtube_compare.get('status', 'missing')}",
        flush=True,
    )

    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        print(
            "smoke_check_result=fail "
            f"failed_checks={','.join(failed)}",
            flush=True,
        )
        return 1

    print("smoke_check_result=pass", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
