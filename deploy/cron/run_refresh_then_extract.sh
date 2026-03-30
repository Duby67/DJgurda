#!/usr/bin/env bash
set -euo pipefail

EXTRACTOR_ROOT="${EXTRACTOR_ROOT:-$HOME/cookies}"
RUNTIME_DIR="${RUNTIME_DIR:-$EXTRACTOR_ROOT/runtime}"
REFRESH_SCRIPT="${REFRESH_SCRIPT:-$RUNTIME_DIR/run_session_refresher.sh}"
EXTRACT_SCRIPT="${EXTRACT_SCRIPT:-$RUNTIME_DIR/run_cookies_extractor.sh}"
DELAY_SECONDS="${REFRESH_TO_EXTRACT_DELAY_SECONDS:-120}"

if [[ ! -x "$REFRESH_SCRIPT" ]]; then
  echo "Refresh script is missing or not executable: $REFRESH_SCRIPT" >&2
  exit 1
fi

if [[ ! -x "$EXTRACT_SCRIPT" ]]; then
  echo "Extractor script is missing or not executable: $EXTRACT_SCRIPT" >&2
  exit 1
fi

"$REFRESH_SCRIPT"
sleep "$DELAY_SECONDS"
"$EXTRACT_SCRIPT"
