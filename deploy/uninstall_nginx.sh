#!/usr/bin/env bash
# Cleanly remove the InfraDocs V6 nginx vhost.
# Leaves every other site untouched.

set -euo pipefail

VHOST_NAME=infra.ocialwaysfree.site
AVAIL=/etc/nginx/sites-available/$VHOST_NAME
ENABLED=/etc/nginx/sites-enabled/$VHOST_NAME

if [[ -L "$ENABLED" ]]; then
  echo "→ disabling $VHOST_NAME"
  sudo rm "$ENABLED"
fi
if [[ -f "$AVAIL" ]]; then
  echo "→ removing $AVAIL"
  sudo rm "$AVAIL"
fi

if ! sudo nginx -t; then
  echo "✗ nginx config test failed after removal — abort reload" >&2
  exit 1
fi
sudo systemctl reload nginx
echo "✓ uninstalled. Other sites unchanged."
