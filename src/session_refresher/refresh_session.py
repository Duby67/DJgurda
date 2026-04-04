#!/usr/bin/env python3
from __future__ import annotations

import os
import random
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import urlparse, urlunparse

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service

LOG_FILE = Path(os.getenv("REFRESH_INTERNAL_LOG", "/tmp/firefox-refresh.log"))
HUMAN_ACTION_SCRIPT = """
const action = arguments[0];
const x = Math.max(
  0,
  Math.min(arguments[1], Math.max(document.documentElement.clientWidth - 1, 0)),
);
const y = Math.max(
  0,
  Math.min(arguments[2], Math.max(document.documentElement.clientHeight - 1, 0)),
);

if (action === "scroll") {
  window.scrollBy({ top: arguments[3], left: 0, behavior: "smooth" });
  return {
    action,
    scrollY: Math.round(window.scrollY || 0),
    innerHeight: Math.round(window.innerHeight || 0),
    docHeight: Math.round(document.documentElement.scrollHeight || 0),
  };
}

const target = document.elementFromPoint(x, y) || document.body || document.documentElement;
if (!target) {
  return { action: "hover", x, y, element: "n/a" };
}

target.dispatchEvent(
  new MouseEvent("mousemove", {
    bubbles: true,
    cancelable: true,
    clientX: x,
    clientY: y,
    view: window,
  }),
);

return {
  action: "hover",
  x,
  y,
  element: target.tagName ? target.tagName.toLowerCase() : "n/a",
};
"""


@dataclass
class RunHealth:
    pages_total: int
    pages_loaded: int = 0
    page_load_warnings: int = 0
    human_action_warnings: int = 0
    extra_windows_closed: int = 0
    snapshot_warnings: int = 0
    cookie_domains_changed: int = 0
    cookie_domains_total: int = 0


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
    max_value = parse_positive_int("REFRESH_URL_DURATION_MAX", max_raw, 45)

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


def capture_snapshot(
    label: str, db_path: Path, domains: List[str], health: RunHealth
) -> Dict[str, str]:
    snapshot: Dict[str, str] = {}
    for domain in domains:
        stats = query_cookie_stats(db_path, domain)
        snapshot[domain] = stats
        if stats.startswith("query_error:") or stats == "db_missing":
            health.snapshot_warnings += 1
        log(f"cookies_{label} domain={domain} stats={stats}")

    all_stats = query_cookie_stats(db_path, None)
    snapshot["__all__"] = all_stats
    if all_stats.startswith("query_error:") or all_stats == "db_missing":
        health.snapshot_warnings += 1
    log(f"cookies_{label} domain=__all__ stats={all_stats}")
    return snapshot


def compare_snapshots(before: Dict[str, str], after: Dict[str, str], domains: List[str]) -> int:
    changed_total = 0
    for domain in [*domains, "__all__"]:
        b = before.get(domain, "n/a")
        a = after.get(domain, "n/a")
        status = "changed" if b != a else "unchanged"
        if status == "changed":
            changed_total += 1
        log(f"cookies_compare domain={domain} status={status} before={b} after={a}")
    return changed_total


def enforce_single_window(driver: webdriver.Firefox, preferred_handle: str | None, health: RunHealth) -> str:
    handles = driver.window_handles
    log(
        "window_handles_check "
        f"handles_count={len(handles)} "
        f"preferred_found={preferred_handle in handles if preferred_handle else False}"
    )
    if not handles:
        raise WebDriverException("Firefox returned zero window handles")

    active_handle = preferred_handle if preferred_handle in handles else handles[0]
    for handle in handles:
        if handle == active_handle:
            continue
        driver.switch_to.window(handle)
        driver.close()
        health.extra_windows_closed += 1
        log("extra_window_closed")

    driver.switch_to.window(active_handle)
    return active_handle


def perform_human_action(driver: webdriver.Firefox, target_safe: str, health: RunHealth) -> None:
    action = random.choice(["scroll", "scroll", "hover", "pause"])
    if action == "pause":
        return

    viewport_width = max(driver.execute_script("return window.innerWidth || 0;") or 0, 1)
    viewport_height = max(driver.execute_script("return window.innerHeight || 0;") or 0, 1)
    x = random.randint(0, max(viewport_width - 1, 0))
    y = random.randint(0, max(viewport_height - 1, 0))
    scroll_delta = random.randint(-260, 520)

    try:
        result = driver.execute_script(HUMAN_ACTION_SCRIPT, action, x, y, scroll_delta) or {}
    except WebDriverException as exc:
        health.human_action_warnings += 1
        warn(
            f"human_action_failed target={target_safe} "
            f"action={action} error={exc.__class__.__name__}"
        )
        return

    if action == "scroll":
        log(
            f"human_action target={target_safe} action=scroll "
            f"delta={scroll_delta} scroll_y={result.get('scrollY', 'n/a')} "
            f"doc_height={result.get('docHeight', 'n/a')}"
        )
        return

    log(
        f"human_action target={target_safe} action=hover "
        f"x={result.get('x', x)} y={result.get('y', y)} "
        f"element={result.get('element', 'n/a')}"
    )


def keep_page_alive(
    driver: webdriver.Firefox,
    target_safe: str,
    index: int,
    total_steps: int,
    duration: int,
    heartbeat_seconds: int,
    active_handle: str,
    health: RunHealth,
) -> str:
    deadline = time.monotonic() + duration
    next_heartbeat = time.monotonic() + heartbeat_seconds

    while True:
        now = time.monotonic()
        remaining = int(round(deadline - now))
        if remaining <= 0:
            break

        try:
            active_handle = enforce_single_window(driver, active_handle, health)
            perform_human_action(driver, target_safe, health)
        except WebDriverException as exc:
            health.human_action_warnings += 1
            warn(
                f"human_activity_loop_failed target={target_safe} "
                f"error={exc.__class__.__name__}"
            )

        if now >= next_heartbeat:
            log(
                f"step_progress index={index}/{total_steps} "
                f"target={target_safe} remaining={max(remaining, 0)}s"
            )
            next_heartbeat = now + heartbeat_seconds

        time.sleep(min(random.uniform(2.0, 5.0), max(deadline - time.monotonic(), 0.2)))

    log(f"step_progress index={index}/{total_steps} target={target_safe} remaining=0s")
    return active_handle


def emit_health_verdict(health: RunHealth, fatal_error: str | None) -> None:
    if fatal_error is not None:
        verdict = "failed"
        reason = fatal_error
    elif health.pages_loaded == 0:
        verdict = "failed"
        reason = "no_pages_loaded"
    elif health.page_load_warnings or health.human_action_warnings or health.snapshot_warnings:
        verdict = "degraded"
        reason = (
            f"page_load_warnings={health.page_load_warnings} "
            f"human_action_warnings={health.human_action_warnings} "
            f"snapshot_warnings={health.snapshot_warnings}"
        )
    else:
        verdict = "healthy"
        reason = "all_steps_completed"

    log(
        f"health_verdict={verdict} reason={reason} "
        f"pages_loaded={health.pages_loaded}/{health.pages_total} "
        f"page_load_warnings={health.page_load_warnings} "
        f"human_action_warnings={health.human_action_warnings} "
        f"extra_windows_closed={health.extra_windows_closed} "
        f"cookie_domains_changed={health.cookie_domains_changed}/{health.cookie_domains_total} "
        f"snapshot_warnings={health.snapshot_warnings}"
    )


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
    health = RunHealth(pages_total=len(targets), cookie_domains_total=len(domains) + 1)
    before = capture_snapshot("before", cookies_db, domains, health)

    driver: webdriver.Firefox | None = None
    active_handle: str | None = None
    fatal_error: str | None = None
    exit_code = 0
    try:
        options = Options()
        options.binary_location = firefox_bin
        options.add_argument("-profile")
        options.add_argument(str(profile_dir))
        options.set_preference("browser.shell.checkDefaultBrowser", False)
        options.set_preference("browser.startup.homepage", "about:blank")
        options.set_preference("browser.startup.page", 0)
        options.set_preference("browser.sessionstore.resume_from_crash", False)
        options.set_preference("browser.sessionstore.restore_on_demand", False)
        options.set_preference("browser.sessionstore.restore_tabs_lazily", False)
        options.set_preference("browser.sessionstore.max_resumed_crashes", 0)

        gecko_log_path = os.getenv("REFRESH_GECKODRIVER_LOG", "/tmp/geckodriver.log")
        service = Service(executable_path=geckodriver_bin, log_output=gecko_log_path)

        log(
            "webdriver_starting "
            f"profile={profile_dir} firefox_bin={firefox_bin} "
            f"geckodriver_bin={geckodriver_bin} geckodriver_log={gecko_log_path} "
            "session_restore_disabled=true"
        )
        webdriver_start_monotonic = time.monotonic()
        driver = webdriver.Firefox(service=service, options=options)
        log(
            "webdriver_created "
            f"startup_elapsed_seconds={time.monotonic() - webdriver_start_monotonic:.3f}"
        )
        driver.set_page_load_timeout(page_load_timeout)
        log(f"page_load_timeout_set seconds={page_load_timeout}")
        log("single_window_enforce_start stage=initial")
        active_handle = enforce_single_window(driver, driver.current_window_handle, health)
        log(
            "webdriver_started single_process=true single_window=true "
            f"active_handle={active_handle}"
        )

        total_steps = len(targets)
        for index, target in enumerate(targets, start=1):
            duration = random.randint(duration_min, duration_max)
            target_safe = safe_url(target)
            log(
                f"step_start index={index}/{total_steps} "
                f"target={target_safe} duration_seconds={duration}"
            )

            try:
                if active_handle is not None:
                    log(
                        f"single_window_enforce_start stage=before_get index={index}/{total_steps} "
                        f"target={target_safe}"
                    )
                    active_handle = enforce_single_window(driver, active_handle, health)
                log(f"webdriver_get_start index={index}/{total_steps} target={target_safe}")
                page_get_monotonic = time.monotonic()
                driver.get(target)
                health.pages_loaded += 1
                log(
                    f"webdriver_get_done index={index}/{total_steps} target={target_safe} "
                    f"elapsed_seconds={time.monotonic() - page_get_monotonic:.3f}"
                )
            except TimeoutException:
                health.page_load_warnings += 1
                warn(f"page_load_timeout target={target_safe}")
            except WebDriverException as exc:
                health.page_load_warnings += 1
                warn(f"webdriver_get_error target={target_safe} error={exc.__class__.__name__}")

            if active_handle is not None:
                try:
                    active_handle = enforce_single_window(driver, active_handle, health)
                except WebDriverException as exc:
                    health.page_load_warnings += 1
                    warn(
                        f"single_window_enforce_failed target={target_safe} "
                        f"error={exc.__class__.__name__}"
                    )

            current_url = safe_url(driver.current_url) if driver.current_url else "n/a"
            title = (driver.title or "").replace("\n", " ").strip()
            if len(title) > 120:
                title = title[:117] + "..."
            log(f"step_loaded index={index}/{total_steps} current_url={current_url} title={title or 'n/a'}")

            if active_handle is not None:
                log(
                    f"page_lifetime_start index={index}/{total_steps} "
                    f"target={target_safe} duration_seconds={duration}"
                )
                active_handle = keep_page_alive(
                    driver=driver,
                    target_safe=target_safe,
                    index=index,
                    total_steps=total_steps,
                    duration=duration,
                    heartbeat_seconds=heartbeat_seconds,
                    active_handle=active_handle,
                    health=health,
                )

            log(
                f"step_done index={index}/{total_steps} "
                f"target={target_safe} duration_seconds={duration}"
            )

        log(
            "webdriver_sequence_completed "
            f"pages_loaded={health.pages_loaded}/{health.pages_total} "
            f"extra_windows_closed={health.extra_windows_closed}"
        )
    except Exception as exc:  # noqa: BLE001
        fatal_error = f"webdriver_failed error={exc.__class__.__name__}: {exc}"
        exit_code = die(fatal_error)
    finally:
        if driver is not None:
            try:
                driver.quit()
                log("webdriver_quit_ok")
            except Exception as exc:  # noqa: BLE001
                warn(f"webdriver_quit_failed error={exc.__class__.__name__}: {exc}")

    after = capture_snapshot("after", cookies_db, domains, health)
    health.cookie_domains_changed = compare_snapshots(before, after, domains)
    emit_health_verdict(health, fatal_error)

    log("Session refresh completed")
    return exit_code


if __name__ == "__main__":
    sys.exit(run())
