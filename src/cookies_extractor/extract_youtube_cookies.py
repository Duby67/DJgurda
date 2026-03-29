"""Extract YouTube cookies from a local browser into Netscape cookies.txt format."""

from __future__ import annotations

import argparse
import sys
from http.cookiejar import MozillaCookieJar
from pathlib import Path

try:
    from .config import load_config
except ImportError:
    from config import load_config


class _SilentLogger:
    def debug(self, _message: str) -> None:
        return

    def info(self, _message: str) -> None:
        return

    def warning(self, _message: str) -> None:
        return

    def error(self, _message: str) -> None:
        return


def parse_args() -> argparse.Namespace:
    cfg = load_config()
    parser = argparse.ArgumentParser(
        description=(
            "Extract fresh cookies for youtube.com from a local browser profile "
            "and save them to /cookies_extractor/cookies/www.youtube.com_cookies.txt."
        )
    )
    parser.add_argument(
        "--browser",
        default=cfg.browser,
        help="Browser name for yt-dlp cookies extraction (example: chrome, firefox).",
    )
    parser.add_argument(
        "--browser-profile",
        default=cfg.browser_profile,
        help="Optional browser profile name/path (if needed by yt-dlp).",
    )
    parser.add_argument(
        "--domain",
        default=cfg.domain,
        help=f"Cookie domain to export. Default: {cfg.domain}",
    )
    parser.add_argument(
        "--output-dir",
        default=str(cfg.output_dir),
        help=f"Directory for output cookie file. Default: {cfg.output_dir}",
    )
    parser.add_argument(
        "--output-file",
        default=cfg.output_file,
        help=f"Output file name. Default: {cfg.output_file}",
    )
    return parser.parse_args()


def _domain_matches(cookie_domain: str, target_domain: str) -> bool:
    normalized_cookie = cookie_domain.lower().lstrip(".")
    normalized_target = target_domain.lower().lstrip(".")
    return normalized_cookie == normalized_target or normalized_cookie.endswith(
        f".{normalized_target}"
    )


def export_youtube_cookies(
    browser: str, browser_profile: str | None, domain: str, output_path: Path
) -> int:
    try:
        from yt_dlp.cookies import extract_cookies_from_browser
    except ImportError as exc:
        raise RuntimeError(
            "yt-dlp is not installed. Install dependencies from requirements-cookies.txt first."
        ) from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        source_jar = extract_cookies_from_browser(browser, browser_profile, _SilentLogger())
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"Failed to load cookies from browser '{browser}'. "
            "Check browser availability and profile path."
        ) from exc

    filtered_jar = MozillaCookieJar(str(output_path))
    exported = 0

    for cookie in source_jar:
        if _domain_matches(cookie.domain, domain):
            filtered_jar.set_cookie(cookie)
            exported += 1

    if exported == 0:
        raise RuntimeError(
            f"No cookies found for domain '{domain}'. Check browser/profile and login state."
        )

    filtered_jar.save(ignore_discard=True, ignore_expires=True)
    return exported


def main() -> int:
    args = parse_args()
    output_path = Path(args.output_dir) / args.output_file

    try:
        exported_count = export_youtube_cookies(
            browser=args.browser,
            browser_profile=args.browser_profile,
            domain=args.domain,
            output_path=output_path,
        )
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Cookie file saved: {output_path}")
    print(f"Exported cookies: {exported_count}")
    print(f"Domain filter: {args.domain}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
