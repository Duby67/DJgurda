"""Validate exported YouTube cookie files in Netscape cookies.txt format."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    from .config import load_config
except ImportError:
    from config import load_config


@dataclass
class ValidationResult:
    ok: bool
    total_rows: int
    matched_rows: int
    message: str


def _domain_matches(cookie_domain: str, target_domain: str) -> bool:
    normalized_cookie = cookie_domain.lower().lstrip(".")
    normalized_target = target_domain.lower().lstrip(".")
    return normalized_cookie == normalized_target or normalized_cookie.endswith(
        f".{normalized_target}"
    )


def validate_cookie_file(cookie_file: Path, domain: str, min_cookies: int = 1) -> ValidationResult:
    if not cookie_file.exists():
        return ValidationResult(
            ok=False,
            total_rows=0,
            matched_rows=0,
            message=f"Cookie file not found: {cookie_file}",
        )

    text = cookie_file.read_text(encoding="utf-8", errors="replace")
    lines = [line.rstrip("\n") for line in text.splitlines()]

    if not lines:
        return ValidationResult(False, 0, 0, "Cookie file is empty")

    header = next((line for line in lines if line.strip()), "")
    if "Netscape HTTP Cookie File" not in header:
        return ValidationResult(
            False,
            0,
            0,
            "Invalid format: missing Netscape cookie header",
        )

    total_rows = 0
    matched_rows = 0

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split("\t")
        if len(parts) != 7:
            return ValidationResult(
                False,
                total_rows,
                matched_rows,
                "Invalid format: each cookie line must contain 7 tab-separated fields",
            )

        total_rows += 1
        cookie_domain = parts[0]
        if _domain_matches(cookie_domain, domain):
            matched_rows += 1

    if total_rows == 0:
        return ValidationResult(False, 0, 0, "No cookie rows found in cookie file")

    if matched_rows < min_cookies:
        return ValidationResult(
            False,
            total_rows,
            matched_rows,
            f"Not enough cookies for domain '{domain}': {matched_rows} < {min_cookies}",
        )

    return ValidationResult(
        True,
        total_rows,
        matched_rows,
        f"Cookie file is valid. matched={matched_rows}, total={total_rows}",
    )


def parse_args() -> argparse.Namespace:
    cfg = load_config()
    parser = argparse.ArgumentParser(description="Validate YouTube cookie file.")
    parser.add_argument(
        "--cookie-file",
        default=str(cfg.output_path),
        help=f"Path to cookie file. Default: {cfg.output_path}",
    )
    parser.add_argument(
        "--domain",
        default=cfg.domain,
        help=f"Domain to validate. Default: {cfg.domain}",
    )
    parser.add_argument(
        "--min-cookies",
        type=int,
        default=cfg.min_cookies,
        help=f"Minimum matched cookies required. Default: {cfg.min_cookies}",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = validate_cookie_file(
        cookie_file=Path(args.cookie_file),
        domain=args.domain,
        min_cookies=args.min_cookies,
    )

    print(result.message)
    print(f"total_rows={result.total_rows}")
    print(f"matched_rows={result.matched_rows}")

    if not result.ok:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
