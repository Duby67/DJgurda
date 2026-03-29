"""Validate exported cookie files in Netscape cookies.txt format."""

from __future__ import annotations

import argparse
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


def _parse_domains(raw: str) -> tuple[str, ...]:
    domains = tuple(token.strip().lower() for token in raw.split(",") if token.strip())
    if not domains:
        raise ValueError("Domain list is empty")
    return domains


def _domain_matches(cookie_domain: str, target_domains: tuple[str, ...]) -> bool:
    normalized_cookie = cookie_domain.lower().lstrip(".")
    for target_domain in target_domains:
        normalized_target = target_domain.lower().lstrip(".")
        if normalized_cookie == normalized_target or normalized_cookie.endswith(
            f".{normalized_target}"
        ):
            return True
    return False


def validate_cookie_file(
    cookie_file: Path,
    domains: tuple[str, ...],
    min_cookies: int = 1,
) -> ValidationResult:
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
        if _domain_matches(cookie_domain, domains):
            matched_rows += 1

    if total_rows == 0:
        return ValidationResult(False, 0, 0, "No cookie rows found in cookie file")

    if matched_rows < min_cookies:
        domains_text = ", ".join(domains)
        return ValidationResult(
            False,
            total_rows,
            matched_rows,
            f"Not enough cookies for domains ({domains_text}): {matched_rows} < {min_cookies}",
        )

    return ValidationResult(
        True,
        total_rows,
        matched_rows,
        f"Cookie file is valid. matched={matched_rows}, total={total_rows}",
    )


def parse_args() -> argparse.Namespace:
    cfg = load_config()
    parser = argparse.ArgumentParser(description="Validate cookie file.")
    parser.add_argument(
        "--cookie-file",
        default=str(cfg.output_dir / "YouTube" / "www.youtube.com_cookies.txt"),
        help="Path to cookie file.",
    )
    parser.add_argument(
        "--domains",
        default="youtube.com,google.com,youtu.be,googlevideo.com",
        help="Comma-separated domain list.",
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
    domains = _parse_domains(args.domains)
    result = validate_cookie_file(
        cookie_file=Path(args.cookie_file),
        domains=domains,
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
