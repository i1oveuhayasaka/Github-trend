#!/usr/bin/env bash
set -euo pipefail

# Install Mihomo config from a local Clash YAML (e.g. exported from Clash Verge).
# Usage:
#   sudo scripts/setup_mihomo_linux.sh /path/to/profile.yaml

if [ "${EUID:-$(id -u)}" -ne 0 ]; then
  echo "Run as root: sudo $0 <profile.yaml>"
  exit 1
fi

if [ "$#" -ne 1 ] || [ ! -f "$1" ]; then
  echo "Usage: sudo $0 /path/to/profile.yaml"
  exit 1
fi

SRC_CONFIG="$1"
DEST_DIR="/etc/mihomo"
DEST_CONFIG="$DEST_DIR/config.yaml"
PROXY_PORT="${MIHOMO_PROXY_PORT:-7890}"

mkdir -p "$DEST_DIR"
cp "$SRC_CONFIG" "$DEST_CONFIG"
chmod 600 "$DEST_CONFIG"

python3 - "$DEST_CONFIG" "$PROXY_PORT" <<'PY'
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

config_path = Path(sys.argv[1])
proxy_port = int(sys.argv[2])
text = config_path.read_text(encoding="utf-8")

if yaml is None:
    # Minimal fallback when PyYAML is unavailable.
    lines = text.splitlines()
    out: list[str] = []
    has_mixed = any(line.startswith("mixed-port:") for line in lines)
    has_allow_lan = any(line.startswith("allow-lan:") for line in lines)
    for line in lines:
        if line.startswith("mixed-port:"):
            out.append(f"mixed-port: {proxy_port}")
        elif line.startswith("allow-lan:"):
            out.append("allow-lan: false")
        else:
            out.append(line)
    if not has_mixed:
        out.insert(0, f"mixed-port: {proxy_port}")
    if not has_allow_lan:
        out.insert(1, "allow-lan: false")
    config_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    raise SystemExit(0)

data = yaml.safe_load(text) or {}
data["mixed-port"] = proxy_port
data["allow-lan"] = False
if not data.get("mode"):
    data["mode"] = "rule"
config_path.write_text(
    yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
    encoding="utf-8",
)
PY

GEODATA_MIRROR="${GEODATA_MIRROR:-https://ghfast.top/https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest}"
for geofile in geoip.metadb geosite.dat; do
  if [ ! -s "$DEST_DIR/$geofile" ]; then
    echo "Downloading $geofile ..."
    curl -fsSL --connect-timeout 20 --max-time 120 \
      -o "$DEST_DIR/$geofile" "$GEODATA_MIRROR/$geofile"
  fi
done

cat > /etc/systemd/system/mihomo.service <<'UNIT'
[Unit]
Description=Mihomo (Clash Meta) Proxy
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/mihomo -d /etc/mihomo
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

SUDOERS_FILE="/etc/sudoers.d/mihomo-media-digest"
cat > "$SUDOERS_FILE" <<'SUDOERS'
ubuntu ALL=(root) NOPASSWD: /bin/systemctl start mihomo, /bin/systemctl stop mihomo, /bin/systemctl is-active mihomo
SUDOERS
chmod 440 "$SUDOERS_FILE"
visudo -cf "$SUDOERS_FILE"

systemctl daemon-reload
systemctl disable mihomo
systemctl restart mihomo

sleep 5
if ! systemctl is-active --quiet mihomo; then
  echo "mihomo failed to start. Recent logs:"
  journalctl -u mihomo -n 30 --no-pager || true
  exit 1
fi

if curl -sS -I --max-time 15 -x "http://127.0.0.1:${PROXY_PORT}" https://github.com >/dev/null; then
  echo "OK   mihomo test passed via 127.0.0.1:${PROXY_PORT}"
else
  echo "WARN mihomo is running but github.com test failed. Check nodes in config.yaml"
  journalctl -u mihomo -n 20 --no-pager || true
  exit 1
fi

systemctl stop mihomo
echo "OK   mihomo disabled on boot; it will start only when media-digest runs"
