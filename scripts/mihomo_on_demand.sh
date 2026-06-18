#!/usr/bin/env bash

# Start/stop Mihomo only while media-digest runs.
# Requires passwordless sudo for systemctl (configured by setup_mihomo_linux.sh).

MIHOMO_PROXY_PORT="${MIHOMO_PROXY_PORT:-7890}"
MIHOMO_CONFIG="/etc/mihomo/config.yaml"
MIHOMO_STARTED_BY_SCRIPT=0

_mihomo_port_ready() {
  ss -tln 2>/dev/null | grep -q "127.0.0.1:${MIHOMO_PROXY_PORT} "
}

mihomo_start_if_needed() {
  [ -f "$MIHOMO_CONFIG" ] || return 0

  if systemctl is-active --quiet mihomo 2>/dev/null; then
    _mihomo_port_ready || {
      echo "mihomo service is active but port ${MIHOMO_PROXY_PORT} is not ready" >&2
      return 1
    }
    return 0
  fi

  sudo systemctl start mihomo
  MIHOMO_STARTED_BY_SCRIPT=1

  for _ in $(seq 1 30); do
    if _mihomo_port_ready; then
      return 0
    fi
    sleep 1
  done

  echo "mihomo failed to start within 30s" >&2
  journalctl -u mihomo -n 20 --no-pager >&2 || true
  return 1
}

mihomo_stop_if_started() {
  if [ "$MIHOMO_STARTED_BY_SCRIPT" -eq 1 ]; then
    sudo systemctl stop mihomo >/dev/null 2>&1 || true
    MIHOMO_STARTED_BY_SCRIPT=0
  fi
}

mihomo_export_proxy() {
  export http_proxy="${HTTP_PROXY:-http://127.0.0.1:${MIHOMO_PROXY_PORT}}"
  export https_proxy="${HTTPS_PROXY:-http://127.0.0.1:${MIHOMO_PROXY_PORT}}"
  export no_proxy="${NO_PROXY:-127.0.0.1,localhost}"
}
