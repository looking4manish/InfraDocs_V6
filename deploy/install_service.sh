#!/usr/bin/env bash
# Install the systemd unit for the InfraDocs V6 API.
#
# Safe-by-design: kills any stray uvicorn on :8004 first (so we don't end
# up with two processes fighting for the port), then installs the unit,
# then enables + starts it.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UNIT_NAME=infradocs-v6-api.service
SRC="$REPO_ROOT/deploy/$UNIT_NAME"
DEST=/etc/systemd/system/$UNIT_NAME

if [[ ! -f "$SRC" ]]; then
  echo "missing unit source: $SRC" >&2
  exit 1
fi

# 1. Stop any stray nohup uvicorn on :8004
if pgrep -f "uvicorn app.api.main" >/dev/null 2>&1; then
  echo "→ stopping existing uvicorn process(es)"
  pkill -f "uvicorn app.api.main" || true
  sleep 1
fi

# 2. Install unit
echo "→ installing $DEST"
sudo cp "$SRC" "$DEST"
sudo chmod 644 "$DEST"

# 3. Reload + enable + start
sudo systemctl daemon-reload
sudo systemctl enable "$UNIT_NAME"
sudo systemctl restart "$UNIT_NAME"

sleep 2
sudo systemctl --no-pager --lines=5 status "$UNIT_NAME" || true

# 4. Smoke check
echo "→ smoke checking /api/health"
if curl -sf http://127.0.0.1:8004/api/health >/dev/null; then
  echo "✓ API is up under systemd"
else
  echo "✗ API not responding — check logs:" >&2
  echo "  journalctl -u $UNIT_NAME -n 50" >&2
  exit 1
fi
