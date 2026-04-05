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
from urllib3.exceptions import ReadTimeoutError

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
YOUTUBE_AUTH_STATE_SCRIPT = """
const ytcfgLoggedIn = Boolean(
  window.ytcfg && (
    (typeof window.ytcfg.get === "function" && window.ytcfg.get("LOGGED_IN")) ||
    (window.ytcfg.data_ && window.ytcfg.data_.LOGGED_IN)
  ),
);
const hasTopbarButtons = Boolean(
  document.querySelector(
    'ytd-topbar-menu-button-renderer #button, ytd-notification-topbar-button-renderer',
  ),
);
return {
  loggedInConfig: ytcfgLoggedIn,
  hasAvatarButton: Boolean(
    document.querySelector(
      '#avatar-btn, button#avatar-btn, ytd-topbar-menu-button-renderer #avatar-btn',
    ),
  ),
  hasNotificationButton: Boolean(
    document.querySelector('ytd-notification-topbar-button-renderer'),
  ),
  hasCreateButton: Boolean(
    document.querySelector('ytd-topbar-menu-button-renderer, button[aria-label*="Create"]'),
  ),
  hasTopbarButtons,
  hasSignInButton: Boolean(
    document.querySelector(
      'a[href*="ServiceLogin"], a[href*="/signin"], a[aria-label*="Sign in"]',
    ),
  ),
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
    auth_warnings: int = 0
    youtube_targets_present: bool = False
    youtube_auth_confirmed: bool = False
    youtube_auth_cookie_present: bool = False
    youtube_auth_cookie_refreshed: bool = False


YOUTUBE_AUTH_COOKIE_NAMES: tuple[str, ...] = (
    "SID",
    "HSID",
    "SSID",
    "APISID",
    "SAPISID",
    "LOGIN_INFO",
    "__Secure-1PSID",
    "__Secure-3PSID",
)


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


def normalize_url_for_match(url: str) -> tuple[str, str]:
    parsed = urlparse((url or "").strip())
    host = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/") or "/"
    return host, path


def navigation_matches(target: str, current_url: str) -> bool:
    target_host, target_path = normalize_url_for_match(target)
    current_host, current_path = normalize_url_for_match(current_url)
    return target_host == current_host and target_path == current_path


def build_cookie_domains(targets: List[str]) -> List[str]:
    seen = set()
    result: List[str] = []

    def add_domain(domain: str) -> None:
        if domain and domain not in seen:
            seen.add(domain)
            result.append(domain)

    for target in targets:
        host = extract_host(target)
        add_domain(host)

        if host.endswith("youtube.com"):
            add_domain("youtube.com")
            add_domain("google.com")
        elif host.endswith("google.com"):
            add_domain("google.com")

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


def query_named_cookie_summary(
    db_path: Path,
    names: tuple[str, ...],
    host_suffixes: tuple[str, ...],
) -> Dict[str, object]:
    if not db_path.exists():
        return {"status": "db_missing", "names": [], "last_access": "n/a"}

    try:
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        return {"status": f"query_error:{exc.__class__.__name__}", "names": [], "last_access": "n/a"}

    try:
        cursor = conn.cursor()
        name_placeholders = ",".join("?" for _ in names)
        host_clause = " OR ".join("host LIKE ?" for _ in host_suffixes)
        params = [*names, *[f"%{suffix}" for suffix in host_suffixes]]
        cursor.execute(
            f"""
            SELECT DISTINCT name
            FROM moz_cookies
            WHERE name IN ({name_placeholders})
              AND ({host_clause})
            ORDER BY name
            """,
            params,
        )
        found_names = [str(row[0]) for row in cursor.fetchall()]
        cursor.execute(
            f"""
            SELECT max(lastAccessed)
            FROM moz_cookies
            WHERE name IN ({name_placeholders})
              AND ({host_clause})
            """,
            params,
        )
        last_accessed = cursor.fetchone()
        max_last_accessed = last_accessed[0] if last_accessed else None
        return {
            "status": "ok",
            "names": found_names,
            "last_access": format_access_micro(max_last_accessed),
        }
    except sqlite3.Error as exc:
        return {"status": f"query_error:{exc.__class__.__name__}", "names": [], "last_access": "n/a"}
    finally:
        conn.close()


def capture_youtube_auth_cookie_summary(
    label: str,
    db_path: Path,
    health: RunHealth,
) -> Dict[str, object]:
    summary = query_named_cookie_summary(
        db_path=db_path,
        names=YOUTUBE_AUTH_COOKIE_NAMES,
        host_suffixes=("youtube.com", "google.com"),
    )
    status = str(summary.get("status", "unknown"))
    if status != "ok":
        health.snapshot_warnings += 1

    names = list(summary.get("names", []))
    names_text = ",".join(names) if names else "n/a"
    log(
        f"youtube_auth_cookies_{label} status={status} "
        f"count={len(names)} names={names_text} "
        f"last_access={summary.get('last_access', 'n/a')}"
    )
    return summary


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


def stop_page_loading(driver: webdriver.Firefox, target_safe: str, health: RunHealth) -> str:
    try:
        ready_state = driver.execute_script(
            "window.stop(); return document.readyState || 'n/a';"
        )
        ready_state = str(ready_state or "n/a")
        log(
            f"page_load_stop_done target={target_safe} "
            f"ready_state={ready_state}"
        )
        return ready_state
    except (TimeoutException, WebDriverException, ReadTimeoutError) as exc:
        health.page_load_warnings += 1
        warn(
            f"page_load_stop_failed target={target_safe} "
            f"error={exc.__class__.__name__}"
        )
        return "n/a"


def probe_auth_state(driver: webdriver.Firefox, target_safe: str) -> str:
    target_host = extract_host(target_safe)
    if not target_host.endswith("youtube.com"):
        return "n/a"

    try:
        auth_probe = driver.execute_script(YOUTUBE_AUTH_STATE_SCRIPT) or {}
    except (TimeoutException, WebDriverException, ReadTimeoutError) as exc:
        warn(
            f"auth_probe_failed target={target_safe} "
            f"error={exc.__class__.__name__}"
        )
        return "unknown"

    logged_in_config = bool(auth_probe.get("loggedInConfig"))
    has_avatar = bool(auth_probe.get("hasAvatarButton"))
    has_sign_in = bool(auth_probe.get("hasSignInButton"))
    has_notification = bool(auth_probe.get("hasNotificationButton"))
    has_create = bool(auth_probe.get("hasCreateButton"))
    has_topbar_buttons = bool(auth_probe.get("hasTopbarButtons"))

    has_signed_in_ui = has_avatar or logged_in_config or (
        has_notification and (has_create or has_topbar_buttons)
    )

    if has_signed_in_ui and not has_sign_in:
        auth_state = "signed_in"
    elif has_sign_in and not has_signed_in_ui:
        auth_state = "signed_out"
    elif has_signed_in_ui and has_sign_in:
        auth_state = "mixed"
    else:
        auth_state = "unknown"

    log(
        f"auth_probe target={target_safe} auth_state={auth_state} "
        f"logged_in_config={logged_in_config} "
        f"has_avatar={has_avatar} has_sign_in={has_sign_in} "
        f"has_notification={has_notification} has_create={has_create} "
        f"has_topbar_buttons={has_topbar_buttons}"
    )
    return auth_state


def perform_human_action(driver: webdriver.Firefox, target_safe: str, health: RunHealth) -> None:
    action = random.choice(["scroll", "scroll", "hover", "pause"])
    if action == "pause":
        return

    try:
        viewport_width = max(driver.execute_script("return window.innerWidth || 0;") or 0, 1)
        viewport_height = max(driver.execute_script("return window.innerHeight || 0;") or 0, 1)
        x = random.randint(0, max(viewport_width - 1, 0))
        y = random.randint(0, max(viewport_height - 1, 0))
        scroll_delta = random.randint(-260, 520)
        result = driver.execute_script(HUMAN_ACTION_SCRIPT, action, x, y, scroll_delta) or {}
    except (TimeoutException, WebDriverException, ReadTimeoutError) as exc:
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
        except (WebDriverException, ReadTimeoutError) as exc:
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
    elif health.youtube_targets_present and not health.youtube_auth_confirmed and not health.youtube_auth_cookie_present:
        verdict = "degraded"
        reason = "youtube_auth_not_confirmed"
    elif health.youtube_targets_present and not health.youtube_auth_cookie_refreshed:
        verdict = "degraded"
        reason = "youtube_auth_cookies_not_refreshed"
    elif health.page_load_warnings or health.human_action_warnings or health.snapshot_warnings:
        verdict = "degraded"
        reason = (
            f"page_load_warnings={health.page_load_warnings} "
            f"human_action_warnings={health.human_action_warnings} "
            f"snapshot_warnings={health.snapshot_warnings} "
            f"auth_warnings={health.auth_warnings}"
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
        f"snapshot_warnings={health.snapshot_warnings} "
        f"auth_warnings={health.auth_warnings} "
        f"youtube_auth_confirmed={health.youtube_auth_confirmed} "
        f"youtube_auth_cookie_present={health.youtube_auth_cookie_present} "
        f"youtube_auth_cookie_refreshed={health.youtube_auth_cookie_refreshed}"
    )


def configure_firefox_options(options: Options, profile_dir: Path, firefox_bin: str) -> None:
    options.binary_location = firefox_bin
    options.page_load_strategy = "eager"
    options.add_argument("-profile")
    options.add_argument(str(profile_dir))

    options.set_preference("accessibility.force_disabled", 1)
    options.set_preference("browser.shell.checkDefaultBrowser", False)
    options.set_preference("browser.startup.homepage", "about:blank")
    options.set_preference("browser.startup.homepage_override.mstone", "ignore")
    options.set_preference("browser.startup.page", 0)
    options.set_preference("browser.sessionstore.resume_from_crash", False)
    options.set_preference("browser.sessionstore.restore_on_demand", False)
    options.set_preference("browser.sessionstore.restore_tabs_lazily", False)
    options.set_preference("browser.sessionstore.max_resumed_crashes", 0)

    # Keep the container runtime lightweight and avoid GPU/WebGL/media crashes.
    options.set_preference("gfx.webrender.all", False)
    options.set_preference("gfx.webrender.enabled", False)
    options.set_preference("layers.acceleration.disabled", True)
    options.set_preference("media.autoplay.default", 5)
    options.set_preference("media.autoplay.allow-muted", False)
    options.set_preference("media.eme.enabled", False)
    options.set_preference("media.ffmpeg.vaapi.enabled", False)
    options.set_preference("media.hardware-video-decoding.enabled", False)
    options.set_preference("media.mp4.enabled", False)
    options.set_preference("media.webm.enabled", False)
    options.set_preference("webgl.disabled", True)


def start_webdriver(
    profile_dir: Path,
    firefox_bin: str,
    geckodriver_bin: str,
    gecko_log_path: str,
    page_load_timeout: int,
    script_timeout: int,
    health: RunHealth,
) -> tuple[webdriver.Firefox, str]:
    options = Options()
    configure_firefox_options(options, profile_dir, firefox_bin)
    service = Service(executable_path=geckodriver_bin, log_output=gecko_log_path)

    log(
        "webdriver_starting "
        f"profile={profile_dir} firefox_bin={firefox_bin} "
        f"geckodriver_bin={geckodriver_bin} geckodriver_log={gecko_log_path} "
        "page_load_strategy=eager session_restore_disabled=true "
        "webgl_disabled=true media_decode_disabled=true"
    )
    webdriver_start_monotonic = time.monotonic()
    driver = webdriver.Firefox(service=service, options=options)
    log(
        "webdriver_created "
        f"startup_elapsed_seconds={time.monotonic() - webdriver_start_monotonic:.3f}"
    )
    driver.set_page_load_timeout(page_load_timeout)
    log(f"page_load_timeout_set seconds={page_load_timeout}")
    driver.set_script_timeout(script_timeout)
    log(f"script_timeout_set seconds={script_timeout}")
    log("single_window_enforce_start stage=initial")
    active_handle = enforce_single_window(driver, driver.current_window_handle, health)
    log(
        "webdriver_started single_process=true single_window=true "
        f"active_handle={active_handle}"
    )
    return driver, active_handle


def stop_webdriver(driver: webdriver.Firefox | None) -> None:
    if driver is None:
        return

    try:
        driver.quit()
        log("webdriver_quit_ok")
    except Exception as exc:  # noqa: BLE001
        warn(f"webdriver_quit_failed error={exc.__class__.__name__}: {exc}")


def restart_webdriver(
    driver: webdriver.Firefox | None,
    profile_dir: Path,
    firefox_bin: str,
    geckodriver_bin: str,
    gecko_log_path: str,
    page_load_timeout: int,
    script_timeout: int,
    health: RunHealth,
    reason: str,
) -> tuple[webdriver.Firefox, str]:
    warn(f"webdriver_restart_start reason={reason}")
    stop_webdriver(driver)
    restarted_driver, active_handle = start_webdriver(
        profile_dir=profile_dir,
        firefox_bin=firefox_bin,
        geckodriver_bin=geckodriver_bin,
        gecko_log_path=gecko_log_path,
        page_load_timeout=page_load_timeout,
        script_timeout=script_timeout,
        health=health,
    )
    log(f"webdriver_restart_done active_handle={active_handle}")
    return restarted_driver, active_handle


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
        script_timeout = parse_positive_int(
            "REFRESH_SCRIPT_TIMEOUT_SECONDS", get_env("REFRESH_SCRIPT_TIMEOUT_SECONDS"), 15
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
        f"heartbeat_seconds={heartbeat_seconds} page_load_timeout={page_load_timeout} "
        f"script_timeout={script_timeout}"
    )
    domains = build_cookie_domains(targets)
    for domain in domains:
        log(f"cookie_domain_watch={domain}")

    cookies_db = profile_dir / "cookies.sqlite"
    health = RunHealth(pages_total=len(targets), cookie_domains_total=len(domains) + 1)
    health.youtube_targets_present = any(extract_host(target).endswith("youtube.com") for target in targets)
    before = capture_snapshot("before", cookies_db, domains, health)
    youtube_auth_before = capture_youtube_auth_cookie_summary("before", cookies_db, health)

    driver: webdriver.Firefox | None = None
    active_handle: str | None = None
    fatal_error: str | None = None
    exit_code = 0
    gecko_log_path = os.getenv("REFRESH_GECKODRIVER_LOG", "/tmp/geckodriver.log")
    try:
        driver, active_handle = start_webdriver(
            profile_dir=profile_dir,
            firefox_bin=firefox_bin,
            geckodriver_bin=geckodriver_bin,
            gecko_log_path=gecko_log_path,
            page_load_timeout=page_load_timeout,
            script_timeout=script_timeout,
            health=health,
        )

        total_steps = len(targets)
        for index, target in enumerate(targets, start=1):
            duration = random.randint(duration_min, duration_max)
            step_reached = False
            page_load_timed_out = False
            stop_ready_state = "n/a"
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
                step_reached = True
                log(
                    f"webdriver_get_done index={index}/{total_steps} target={target_safe} "
                    f"elapsed_seconds={time.monotonic() - page_get_monotonic:.3f}"
                )
            except TimeoutException:
                step_reached = True
                page_load_timed_out = True
                stop_ready_state = stop_page_loading(driver, target_safe, health)
            except (WebDriverException, ReadTimeoutError) as exc:
                health.page_load_warnings += 1
                warn(f"webdriver_get_error target={target_safe} error={exc.__class__.__name__}")
                driver, active_handle = restart_webdriver(
                    driver=driver,
                    profile_dir=profile_dir,
                    firefox_bin=firefox_bin,
                    geckodriver_bin=geckodriver_bin,
                    gecko_log_path=gecko_log_path,
                    page_load_timeout=page_load_timeout,
                    script_timeout=script_timeout,
                    health=health,
                    reason=f"webdriver_get_error:{exc.__class__.__name__}",
                )
                log(
                    f"step_skipped index={index}/{total_steps} "
                    f"target={target_safe} reason=webdriver_restarted"
                )
                continue

            if active_handle is not None:
                try:
                    active_handle = enforce_single_window(driver, active_handle, health)
                except (WebDriverException, ReadTimeoutError) as exc:
                    health.page_load_warnings += 1
                    warn(
                        f"single_window_enforce_failed target={target_safe} "
                        f"error={exc.__class__.__name__}"
                    )

            try:
                current_url_raw = driver.current_url or ""
                current_url = safe_url(current_url_raw) if current_url_raw else "n/a"
                current_ready_state = str(
                    driver.execute_script("return document.readyState || 'n/a';") or "n/a"
                )
                title = (driver.title or "").replace("\n", " ").strip()
                if len(title) > 120:
                    title = title[:117] + "..."
                navigation_match = navigation_matches(target, current_url_raw)
                auth_state = probe_auth_state(driver, target_safe)
                if auth_state == "signed_in":
                    health.youtube_auth_confirmed = True
                elif auth_state in {"signed_out", "mixed", "unknown"} and extract_host(target).endswith("youtube.com"):
                    health.auth_warnings += 1
                if page_load_timed_out:
                    effective_ready_state = (
                        stop_ready_state
                        if stop_ready_state != "n/a"
                        else current_ready_state
                    )
                    if navigation_match and effective_ready_state in {"interactive", "complete"}:
                        log(
                            f"page_load_timeout_soft index={index}/{total_steps} "
                            f"target={target_safe} current_url={current_url} "
                            f"ready_state={effective_ready_state}"
                        )
                    else:
                        health.page_load_warnings += 1
                        warn(
                            f"page_load_timeout_hard index={index}/{total_steps} "
                            f"target={target_safe} current_url={current_url} "
                            f"ready_state={effective_ready_state} "
                            f"navigation_match={navigation_match}"
                        )
                elif not navigation_match:
                    health.page_load_warnings += 1
                    warn(
                        f"navigation_mismatch index={index}/{total_steps} "
                        f"target={target_safe} current_url={current_url} "
                        f"ready_state={current_ready_state}"
                    )

                if step_reached:
                    health.pages_loaded += 1
                log(
                    f"step_loaded index={index}/{total_steps} "
                    f"current_url={current_url} title={title or 'n/a'} "
                    f"ready_state={current_ready_state} "
                    f"navigation_match={navigation_match} auth_state={auth_state}"
                )
            except (WebDriverException, ReadTimeoutError) as exc:
                health.page_load_warnings += 1
                warn(
                    f"step_metadata_failed index={index}/{total_steps} "
                    f"target={target_safe} error={exc.__class__.__name__}"
                )

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
                    f"page_transition_stop_start index={index}/{total_steps} "
                    f"target={target_safe}"
                )
                stop_page_loading(driver, target_safe, health)

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
        stop_webdriver(driver)

    after = capture_snapshot("after", cookies_db, domains, health)
    youtube_auth_after = capture_youtube_auth_cookie_summary("after", cookies_db, health)
    health.cookie_domains_changed = compare_snapshots(before, after, domains)
    health.youtube_auth_cookie_present = bool(youtube_auth_after.get("names"))
    health.youtube_auth_cookie_refreshed = (
        youtube_auth_before.get("status") == "ok"
        and youtube_auth_after.get("status") == "ok"
        and (
            youtube_auth_before.get("names") != youtube_auth_after.get("names")
            or youtube_auth_before.get("last_access") != youtube_auth_after.get("last_access")
        )
    )
    emit_health_verdict(health, fatal_error)

    log("Session refresh completed")
    return exit_code


if __name__ == "__main__":
    sys.exit(run())
