# Reliability

## Purpose

This file captures runtime reliability expectations, testing posture, and important operational gaps.

## Reliability Rules

- External integrations are unstable by default.
- Stable runtime sources need stricter guarantees than experimental ones.
- Runtime temp storage should be created and cleaned by code, not by assumption.
- Error handling should surface degradation instead of silently masking it.
- Multi-link orchestration should behave deterministically.
- DB failures should be observable and should not silently rewrite business behavior.

## Runtime Reality

- Stable sources:
  - TikTok
  - YouTube
  - Instagram
  - COUB
  - Yandex Music
- Experimental source:
  - VK
- `VK` should stay on an explicit R&D track and not be framed as a stable runtime contract.

## Handler Smoke Tests

- One source should map to one folder in `test/handlers/<Source>/`.
- The local smoke script should be named `test_<source>_handlers_local.py`.
- Links and expected content types should live next to the test in `<Source>_urls.py`.
- Base smoke flow:
  1. `resolve_url`
  2. `ServiceManager.get_handler`
  3. `handler.process(...)`
  4. validate `MediaResult.content_type`
  5. cleanup via `result.iter_cleanup_paths()` in `finally`
- Smoke tests should run with `--timeout 180` where supported.

## Testing Posture

- Prefer targeted checks for the touched subsystem.
- Handler smoke tests are useful but should not redefine architecture policy.
- Environment-sensitive checks should run in isolated or explicitly approved environments.
- Any test execution requires explicit user approval.
- Local Python checks should use the project `venv`.

## Known Gaps

- webhook mode is not implemented;
- command access policy may need tightening;
- external anti-bot behavior remains a continuing source of regressions;
- deploy and local environments differ by OS and tooling assumptions.
