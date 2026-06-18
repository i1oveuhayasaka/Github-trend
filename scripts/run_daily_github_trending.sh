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

"$PYTHON_BIN" -m media_digest \
  --config "$PROJECT_DIR/config.toml" \
  --source github_trending_daily \
  --limit "${DIGEST_LIMIT:-10}"
