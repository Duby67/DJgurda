"""Run extraction + validation for all configured targets with atomic updates."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    from .config import load_config
    from .extract_youtube_cookies import export_cookies_for_domains
    from .targets import CookieTarget, parse_targets
    from .validate_youtube_cookies import validate_cookie_file
except ImportError:
    from config import load_config
    from extract_youtube_cookies import export_cookies_for_domains
    from targets import CookieTarget, parse_targets
    from validate_youtube_cookies import validate_cookie_file


@dataclass
class TargetRunResult:
    target: CookieTarget
    output_path: Path
    exported_count: int
    matched_count: int


def parse_args() -> argparse.Namespace:
    cfg = load_config()
    parser = argparse.ArgumentParser(
        description="Extract and validate cookies for all configured targets."
    )
    parser.add_argument("--browser", default=cfg.browser)
    parser.add_argument("--browser-profile", default=cfg.browser_profile)
    parser.add_argument("--output-dir", default=str(cfg.output_dir))
    parser.add_argument("--targets", default=cfg.targets)
    parser.add_argument("--min-cookies", type=int, default=cfg.min_cookies)
    return parser.parse_args()


def _process_target(
    target: CookieTarget,
    browser: str,
    browser_profile: str | None,
    output_root: Path,
    min_cookies: int,
) -> TargetRunResult:
    target_output_path = output_root / target.folder / target.output_file
    temp_path = target_output_path.with_suffix(target_output_path.suffix + ".tmp")

    exported_count = export_cookies_for_domains(
        browser=browser,
        browser_profile=browser_profile,
        domains=target.domains,
        output_path=temp_path,
    )

    validation = validate_cookie_file(
        cookie_file=temp_path,
        domains=target.domains,
        min_cookies=max(min_cookies, target.min_cookies),
    )

    if not validation.ok:
        temp_path.unlink(missing_ok=True)
        raise RuntimeError(validation.message)

    target_output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path.replace(target_output_path)

    return TargetRunResult(
        target=target,
        output_path=target_output_path,
        exported_count=exported_count,
        matched_count=validation.matched_rows,
    )


def main() -> int:
    args = parse_args()

    try:
        targets = parse_targets(args.targets)
    except ValueError as exc:
        print(f"Target resolution failed: {exc}", file=sys.stderr)
        return 1

    output_root = Path(args.output_dir)
    failures: list[str] = []
    successes: list[TargetRunResult] = []

    for target in targets:
        try:
            result = _process_target(
                target=target,
                browser=args.browser,
                browser_profile=args.browser_profile,
                output_root=output_root,
                min_cookies=args.min_cookies,
            )
            successes.append(result)
            print(
                f"[{target.key}] updated: {result.output_path} "
                f"(exported={result.exported_count}, matched={result.matched_count})"
            )
        except Exception as exc:  # noqa: BLE001
            failures.append(f"[{target.key}] {exc}")
            print(f"[{target.key}] failed: {exc}", file=sys.stderr)

    if failures:
        print("One or more targets failed:", file=sys.stderr)
        for item in failures:
            print(f"- {item}", file=sys.stderr)
        return 1

    print(f"All targets updated successfully: {len(successes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
