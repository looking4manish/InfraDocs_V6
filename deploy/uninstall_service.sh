#!/usr/bin/env bash
# Cleanly stop and remove the InfraDocs V6 systemd unit.

set -euo pipefail

UNIT_NAME=infradocs-v6-api.service
DEST=/etc/systemd/system/$UNIT_NAME

if systemctl list-unit-files | grep -q "^$UNIT_NAME"; then
  echo "→ stopping + disabling $UNIT_NAME"
  sudo systemctl stop "$UNIT_NAME" || true
  sudo systemctl disable "$UNIT_NAME" || true
fi
if [[ -f "$DEST" ]]; then
  echo "→ removing $DEST"
  sudo rm "$DEST"
fi
sudo systemctl daemon-reload
echo "✓ uninstalled."
