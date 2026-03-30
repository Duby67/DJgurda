#!/usr/bin/env python3
from __future__ import annotations

import os
import random
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import urlparse, urlunparse

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service

LOG_FILE = Path(os.getenv("REFRESH_INTERNAL_LOG", "/tmp/firefox-refresh.log"))


def ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_url(url: str) -> str:
    try:
        parsed = urlparse(url.strip())
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
    except Exception:
        return url


def log(message: str) -> None:
    line = f"[{ts()}] [container] {message}"
    print(line, flush=True)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def warn(message: str) -> None:
    log(f"WARN: {message}")


def die(message: str) -> int:
    log(f"ERROR: {message}")
    return 1


def get_env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def parse_positive_int(name: str, raw_value: str, default_value: int) -> int:
    value = raw_value.strip() if raw_value else ""
    if not value:
        return default_value
    if not value.isdigit() or int(value) <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return int(value)


def resolve_duration_bounds() -> Tuple[int, int]:
    fixed_raw = get_env("REFRESH_DURATION_SECONDS")
    min_raw = get_env("REFRESH_URL_DURATION_MIN")
    max_raw = get_env("REFRESH_URL_DURATION_MAX")

    if fixed_raw:
        fixed = parse_positive_int("REFRESH_DURATION_SECONDS", fixed_raw, 0)
        if not min_raw:
            min_raw = str(fixed)
        if not max_raw:
            max_raw = str(fixed)

    min_value = parse_positive_int("REFRESH_URL_DURATION_MIN", min_raw, 30)
    max_value = parse_positive_int("REFRESH_URL_DURATION_MAX", max_raw, 60)

    if min_value > max_value:
        raise ValueError("REFRESH_URL_DURATION_MIN cannot be greater than REFRESH_URL_DURATION_MAX")

    return min_value, max_value


def parse_targets(raw_targets: str) -> List[str]:
    targets: List[str] = []
    for item in raw_targets.split(","):
        target = item.strip()
        if not target:
            continue
        if not (target.startswith("http://") or target.startswith("https://")):
            raise ValueError(f"Invalid target URL: {target}")
        targets.append(target)
    return targets


def extract_host(url: str) -> str:
    parsed = urlparse(url)
    return parsed.hostname or ""


def build_cookie_domains(targets: List[str]) -> List[str]:
    seen = set()
    result: List[str] = []

    for target in targets:
        host = extract_host(target)
        if host and host not in seen:
            seen.add(host)
            result.append(host)

        if host.endswith("youtube.com") and "google.com" not in seen:
            seen.add("google.com")
            result.append("google.com")

    return result


def format_epoch(epoch_seconds: int | None) -> str:
    if not epoch_seconds:
        return "n/a"
    try:
        return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return "n/a"


def format_access_micro(epoch_micro: int | None) -> str:
    if not epoch_micro:
        return "n/a"
    try:
        return datetime.fromtimestamp(epoch_micro / 1_000_000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return "n/a"


def query_cookie_stats(db_path: Path, domain: str | None) -> str:
    if not db_path.exists():
        return "db_missing"

    try:
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        return f"query_error:{exc.__class__.__name__}"

    try:
        cursor = conn.cursor()
        if domain is None:
            cursor.execute(
                "SELECT count(*), max(lastAccessed), max(expiry) FROM moz_cookies"
            )
        else:
            cursor.execute(
                "SELECT count(*), max(lastAccessed), max(expiry) FROM moz_cookies WHERE host LIKE ?",
                (f"%{domain}",),
            )

        row = cursor.fetchone() or (0, None, None)
        count, last_accessed, max_expiry = row
        return f"{count},{format_access_micro(last_accessed)},{format_epoch(max_expiry)}"
    except sqlite3.Error as exc:
        return f"query_error:{exc.__class__.__name__}"
    finally:
        conn.close()


def capture_snapshot(label: str, db_path: Path, domains: List[str]) -> Dict[str, str]:
    snapshot: Dict[str, str] = {}
    for domain in domains:
        stats = query_cookie_stats(db_path, domain)
        snapshot[domain] = stats
        log(f"cookies_{label} domain={domain} stats={stats}")

    all_stats = query_cookie_stats(db_path, None)
    snapshot["__all__"] = all_stats
    log(f"cookies_{label} domain=__all__ stats={all_stats}")
    return snapshot


def compare_snapshots(before: Dict[str, str], after: Dict[str, str], domains: List[str]) -> None:
    for domain in [*domains, "__all__"]:
        b = before.get(domain, "n/a")
        a = after.get(domain, "n/a")
        status = "changed" if b != a else "unchanged"
        log(f"cookies_compare domain={domain} status={status} before={b} after={a}")


def run() -> int:
    profile_dir = Path(get_env("REFRESH_FIREFOX_PROFILE", "/session_refresher/firefox_profile"))
    firefox_bin = get_env("REFRESH_FIREFOX_BIN", "/usr/bin/firefox")
    geckodriver_bin = get_env("REFRESH_GECKODRIVER_BIN", "/usr/local/bin/geckodriver")
    targets_raw = get_env("REFRESH_TARGETS", "https://www.youtube.com")

    try:
        heartbeat_seconds = parse_positive_int(
            "REFRESH_HEARTBEAT_SECONDS", get_env("REFRESH_HEARTBEAT_SECONDS"), 15
        )
        page_load_timeout = parse_positive_int(
            "REFRESH_PAGE_LOAD_TIMEOUT_SECONDS", get_env("REFRESH_PAGE_LOAD_TIMEOUT_SECONDS"), 45
        )
        duration_min, duration_max = resolve_duration_bounds()
        targets = parse_targets(targets_raw)
    except ValueError as exc:
        return die(str(exc))

    if not profile_dir.is_dir():
        return die(f"Firefox profile directory does not exist: {profile_dir}")

    if not Path(firefox_bin).is_file():
        return die(f"Firefox binary not found: {firefox_bin}")

    if not Path(geckodriver_bin).is_file():
        return die(f"Geckodriver binary not found: {geckodriver_bin}")

    if not targets:
        return die("No refresh targets provided")

    log("Starting Selenium Firefox session refresh")
    log(f"profile={profile_dir}")
    log(f"firefox_bin={firefox_bin}")
    log(f"geckodriver_bin={geckodriver_bin}")
    log(f"targets_total={len(targets)}")
    log(
        "duration_mode=random "
        f"url_duration_min={duration_min} url_duration_max={duration_max} "
        f"heartbeat_seconds={heartbeat_seconds} page_load_timeout={page_load_timeout}"
    )
    domains = build_cookie_domains(targets)
    for domain in domains:
        log(f"cookie_domain_watch={domain}")

    cookies_db = profile_dir / "cookies.sqlite"
    before = capture_snapshot("before", cookies_db, domains)

    driver: webdriver.Firefox | None = None
    try:
        options = Options()
        options.binary_location = firefox_bin
        options.add_argument("-profile")
        options.add_argument(str(profile_dir))
        options.set_preference("browser.shell.checkDefaultBrowser", False)
        options.set_preference("browser.startup.homepage", "about:blank")
        options.set_preference("browser.startup.page", 0)

        gecko_log_path = os.getenv("REFRESH_GECKODRIVER_LOG", "/tmp/geckodriver.log")
        service = Service(executable_path=geckodriver_bin, log_output=gecko_log_path)

        driver = webdriver.Firefox(service=service, options=options)
        driver.set_page_load_timeout(page_load_timeout)
        log("webdriver_started single_process=true")

        total_steps = len(targets)
        for index, target in enumerate(targets, start=1):
            duration = random.randint(duration_min, duration_max)
            target_safe = safe_url(target)
            log(
                f"step_start index={index}/{total_steps} "
                f"target={target_safe} duration_seconds={duration}"
            )

            try:
                driver.get(target)
            except TimeoutException:
                warn(f"page_load_timeout target={target_safe}")
            except WebDriverException as exc:
                warn(f"webdriver_get_error target={target_safe} error={exc.__class__.__name__}")

            current_url = safe_url(driver.current_url) if driver.current_url else "n/a"
            title = (driver.title or "").replace("\n", " ").strip()
            if len(title) > 120:
                title = title[:117] + "..."
            log(f"step_loaded index={index}/{total_steps} current_url={current_url} title={title or 'n/a'}")

            remaining = duration
            while remaining > 0:
                step = heartbeat_seconds if heartbeat_seconds < remaining else remaining
                time.sleep(step)
                remaining -= step
                log(
                    f"step_progress index={index}/{total_steps} "
                    f"target={target_safe} remaining={remaining}s"
                )

            log(
                f"step_done index={index}/{total_steps} "
                f"target={target_safe} duration_seconds={duration}"
            )

        log("webdriver_sequence_completed")
    except Exception as exc:  # noqa: BLE001
        return die(f"webdriver_failed error={exc.__class__.__name__}: {exc}")
    finally:
        if driver is not None:
            try:
                driver.quit()
                log("webdriver_quit_ok")
            except Exception as exc:  # noqa: BLE001
                warn(f"webdriver_quit_failed error={exc.__class__.__name__}: {exc}")

    after = capture_snapshot("after", cookies_db, domains)
    compare_snapshots(before, after, domains)

    log("Session refresh completed")
    return 0


if __name__ == "__main__":
    sys.exit(run())
