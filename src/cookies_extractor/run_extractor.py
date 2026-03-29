"""Run extraction + validation with atomic cookie file update."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from .config import load_config
    from .extract_youtube_cookies import export_youtube_cookies
    from .validate_youtube_cookies import validate_cookie_file
except ImportError:
    from config import load_config
    from extract_youtube_cookies import export_youtube_cookies
    from validate_youtube_cookies import validate_cookie_file


def parse_args() -> argparse.Namespace:
    cfg = load_config()
    parser = argparse.ArgumentParser(
        description="Extract and validate YouTube cookies with atomic file replacement."
    )
    parser.add_argument("--browser", default=cfg.browser)
    parser.add_argument("--browser-profile", default=cfg.browser_profile)
    parser.add_argument("--domain", default=cfg.domain)
    parser.add_argument("--output-dir", default=str(cfg.output_dir))
    parser.add_argument("--output-file", default=cfg.output_file)
    parser.add_argument("--min-cookies", type=int, default=cfg.min_cookies)
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    output_path = Path(args.output_dir) / args.output_file
    temp_path = output_path.with_suffix(output_path.suffix + ".tmp")

    try:
        exported_count = export_youtube_cookies(
            browser=args.browser,
            browser_profile=args.browser_profile,
            domain=args.domain,
            output_path=temp_path,
        )
    except RuntimeError as exc:
        print(f"Extraction failed: {exc}", file=sys.stderr)
        return 1

    validation = validate_cookie_file(
        cookie_file=temp_path,
        domain=args.domain,
        min_cookies=args.min_cookies,
    )

    if not validation.ok:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        print(f"Validation failed: {validation.message}", file=sys.stderr)
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path.replace(output_path)

    print(f"Cookie file updated: {output_path}")
    print(f"Exported cookies: {exported_count}")
    print(f"Validated cookies: {validation.matched_rows}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
