#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
LOCK_DIR="$PROJECT_DIR/data/daily-github-trending.lock"

cd "$PROJECT_DIR"
mkdir -p data logs outputs

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "Another media-digest run is already active."
  exit 0
fi

cleanup() {
  # shellcheck source=scripts/mihomo_on_demand.sh
  source "$SCRIPT_DIR/mihomo_on_demand.sh"
  mihomo_stop_if_started
  rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap cleanup EXIT

if [ -z "${PYTHON_BIN:-}" ]; then
  if [ -x "$PROJECT_DIR/.venv/bin/python" ]; then
    PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

# shellcheck source=scripts/mihomo_on_demand.sh
source "$SCRIPT_DIR/mihomo_on_demand.sh"
mihomo_start_if_needed
mihomo_export_proxy

RETRY_INTERVAL_SEC="${RETRY_INTERVAL_SEC:-300}"
RETRY_UNTIL_HOUR="${RETRY_UNTIL_HOUR:-11}"

_retry_deadline_reached() {
  [ "$(TZ=Asia/Shanghai date +%H)" -ge "$RETRY_UNTIL_HOUR" ]
}

_run_digest() {
  "$PYTHON_BIN" -m media_digest \
    --config "$PROJECT_DIR/config.toml" \
    --source github_trending_daily \
    --limit "${DIGEST_LIMIT:-10}"
}

attempt=1
while true; do
  echo "[$(TZ=Asia/Shanghai date '+%F %T %Z')] digest attempt #${attempt}"
  if _run_digest; then
    echo "digest succeeded on attempt #${attempt}"
    exit 0
  fi

  echo "digest failed on attempt #${attempt} (exit $?)" >&2
  if _retry_deadline_reached; then
    echo "giving up: retry window ended at ${RETRY_UNTIL_HOUR}:00 Asia/Shanghai" >&2
    exit 1
  fi

  echo "retrying in ${RETRY_INTERVAL_SEC}s..." >&2
  sleep "$RETRY_INTERVAL_SEC"
  attempt=$((attempt + 1))
done
