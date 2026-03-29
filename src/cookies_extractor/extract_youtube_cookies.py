"""Extract platform cookies from a browser profile into Netscape cookies.txt format."""

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


def _parse_domains(raw: str) -> tuple[str, ...]:
    domains = tuple(token.strip().lower() for token in raw.split(",") if token.strip())
    if not domains:
        raise RuntimeError("Domain list is empty")
    return domains


def parse_args() -> argparse.Namespace:
    cfg = load_config()
    parser = argparse.ArgumentParser(
        description=(
            "Extract fresh cookies from a browser profile and save them in "
            "Netscape cookies.txt format."
        )
    )
    parser.add_argument(
        "--browser",
        default=cfg.browser,
        help="Browser name for yt-dlp cookies extraction (example: firefox, chrome).",
    )
    parser.add_argument(
        "--browser-profile",
        default=cfg.browser_profile,
        help="Browser profile name/path.",
    )
    parser.add_argument(
        "--domains",
        default="youtube.com,google.com,youtu.be,googlevideo.com",
        help="Comma-separated domain list to export.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(cfg.output_dir / "YouTube"),
        help=f"Directory for output cookie file. Default: {cfg.output_dir / 'YouTube'}",
    )
    parser.add_argument(
        "--output-file",
        default="www.youtube.com_cookies.txt",
        help="Output file name.",
    )
    return parser.parse_args()


def _domain_matches(cookie_domain: str, target_domains: tuple[str, ...]) -> bool:
    normalized_cookie = cookie_domain.lower().lstrip(".")
    for domain in target_domains:
        normalized_target = domain.lower().lstrip(".")
        if normalized_cookie == normalized_target or normalized_cookie.endswith(
            f".{normalized_target}"
        ):
            return True
    return False


def export_cookies_for_domains(
    browser: str,
    browser_profile: str | None,
    domains: tuple[str, ...],
    output_path: Path,
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
        if _domain_matches(cookie.domain, domains):
            filtered_jar.set_cookie(cookie)
            exported += 1

    if exported == 0:
        domains_text = ", ".join(domains)
        raise RuntimeError(
            f"No cookies found for domains: {domains_text}. Check browser/profile and login state."
        )

    filtered_jar.save(ignore_discard=True, ignore_expires=True)
    return exported


def export_youtube_cookies(
    browser: str, browser_profile: str | None, domain: str, output_path: Path
) -> int:
    return export_cookies_for_domains(
        browser=browser,
        browser_profile=browser_profile,
        domains=(domain,),
        output_path=output_path,
    )


def main() -> int:
    args = parse_args()
    output_path = Path(args.output_dir) / args.output_file
    domains = _parse_domains(args.domains)

    try:
        exported_count = export_cookies_for_domains(
            browser=args.browser,
            browser_profile=args.browser_profile,
            domains=domains,
            output_path=output_path,
        )
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Cookie file saved: {output_path}")
    print(f"Exported cookies: {exported_count}")
    print(f"Domain filter: {', '.join(domains)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
