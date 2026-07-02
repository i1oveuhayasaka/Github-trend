#!/usr/bin/env bash
set -u

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR" || exit 1

ok() { printf "OK   %s\n" "$1"; }
warn() { printf "WARN %s\n" "$1"; }
fail() { printf "FAIL %s\n" "$1"; FAILED=1; }

FAILED=0
if [ -z "${PYTHON_BIN:-}" ]; then
  if [ -x "$PROJECT_DIR/.venv/bin/python" ]; then
    PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
  else
    PYTHON_BIN="$(command -v python3 || true)"
  fi
fi

echo "== Media Digest server environment check =="
echo "Project: $PROJECT_DIR"
echo

echo "== System =="
uname -a || true
if [ -r /etc/os-release ]; then
  . /etc/os-release
  echo "OS: ${PRETTY_NAME:-unknown}"
fi
echo "Date: $(date)"
echo

echo "== Python =="
if [ -z "$PYTHON_BIN" ]; then
  fail "python3 not found. Install Python 3.11+."
else
  echo "python: $PYTHON_BIN"
  "$PYTHON_BIN" --version
  if "$PYTHON_BIN" - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
  then
    ok "Python version is 3.11+"
  else
    fail "Python version is too old. Need 3.11+ because the project uses tomllib."
  fi
fi
echo

echo "== Files =="
[ -f config.toml ] && ok "config.toml exists" || fail "config.toml missing. Copy config.example.toml to config.toml."
[ -f .env ] && ok ".env exists" || fail ".env missing. Copy .env.example to .env and fill secrets."
for dir in data logs outputs; do
  mkdir -p "$dir" 2>/dev/null || true
  if [ -d "$dir" ] && [ -w "$dir" ]; then
    ok "$dir/ is writable"
  else
    fail "$dir/ is not writable"
  fi
done
echo

echo "== Secrets =="
if [ -f .env ]; then
  if grep -Eq '^SERVERCHAN_SENDKEY=.+' .env; then
    ok "SERVERCHAN_SENDKEY is set"
  else
    fail "SERVERCHAN_SENDKEY is missing in .env"
  fi
  if grep -Eq '^BYTECAT_API_KEY=.+' .env; then
    ok "BYTECAT_API_KEY is set"
  else
    warn "BYTECAT_API_KEY is missing in .env; Chinese summaries will fail if config uses it."
  fi
fi
echo

echo "== Config parse =="
if [ -n "$PYTHON_BIN" ] && [ -f config.toml ]; then
  if "$PYTHON_BIN" - <<'PY'
import tomllib
from pathlib import Path
config = tomllib.loads(Path("config.toml").read_text(encoding="utf-8"))
translation = config.get("translation", {})
serverchan = config.get("push", {}).get("serverchan", {})
xiaohongshu = config.get("social", {}).get("xiaohongshu", {})
print("translation.provider =", translation.get("provider"))
print("translation.openai_base_url =", translation.get("openai_base_url"))
print("translation.openai_model =", translation.get("openai_model"))
print("push.serverchan.enabled =", serverchan.get("enabled"))
print("social.xiaohongshu.enabled =", xiaohongshu.get("enabled"))
PY
  then
    ok "config.toml parsed"
  else
    fail "config.toml parse failed"
  fi
fi
echo

echo "== Network =="
if [ -n "$PYTHON_BIN" ]; then
  "$PYTHON_BIN" - <<'PY'
import urllib.error
import urllib.request

urls = [
    "https://github.com/trending?since=daily",
    "https://codecdn.bytecatcode.org",
    "https://sctapi.ftqq.com",
]

failed = False
for url in urls:
    request = urllib.request.Request(url, headers={"User-Agent": "media-digest-env-check"})
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            print(f"OK   reachable: {url} -> HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        print(f"OK   reachable: {url} -> HTTP {exc.code}")
    except Exception as exc:
        failed = True
        print(f"FAIL unreachable: {url} -> {type(exc).__name__}: {exc}")

raise SystemExit(1 if failed else 0)
PY
  [ "$?" -eq 0 ] && ok "network check finished" || fail "network check failed"
fi
echo

echo "== Import check =="
if [ -n "$PYTHON_BIN" ]; then
  if "$PYTHON_BIN" -m media_digest --help >/dev/null; then
    ok "media_digest module can run"
  else
    fail "media_digest module cannot run from this directory"
  fi
  if "$PYTHON_BIN" -c "import chinese_calendar" >/dev/null 2>&1; then
    ok "chinese-calendar is installed"
  else
    fail "chinese-calendar is missing. Install the project dependencies."
  fi
fi
echo

if [ "$FAILED" -eq 0 ]; then
  ok "Server environment looks ready."
  echo "Next test command:"
  echo "  scripts/run_daily_github_trending_linux.sh"
else
  fail "Server environment has issues. Fix FAIL items above first."
fi

exit "$FAILED"
