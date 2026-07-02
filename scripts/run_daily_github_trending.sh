#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
LOCK_DIR="$PROJECT_DIR/data/daily-github-trending.lock"

cd "$PROJECT_DIR"
mkdir -p data logs outputs

if [ -z "${PYTHON_BIN:-}" ]; then
  if [ -x "$PROJECT_DIR/.venv/bin/python" ]; then
    PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

WORKDAY_ARGS=()
if [ -n "${WORKDAY_DATE:-}" ]; then
  WORKDAY_ARGS=(--date "$WORKDAY_DATE")
fi
if "$PYTHON_BIN" -m media_digest.workday "${WORKDAY_ARGS[@]}"; then
  :
else
  workday_status=$?
  if [ "$workday_status" -eq 3 ]; then
    exit 0
  fi
  exit "$workday_status"
fi

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "Another media-digest run is already active."
  exit 0
fi

cleanup() {
  rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap cleanup EXIT

"$PYTHON_BIN" -m media_digest \
  --config "$PROJECT_DIR/config.toml" \
  --source github_trending_daily \
  --limit "${DIGEST_LIMIT:-10}"
