#!/usr/bin/env bash
# Install the InfraDocs V6 nginx vhost.
#
# Safe-by-design:
#   1) Backs up any existing /etc/nginx/sites-available/infra.ocialwaysfree.site
#   2) Copies the vhost from deploy/
#   3) Symlinks into sites-enabled IF and only IF `nginx -t` passes
#   4) Reload (NEVER restart) nginx
#
# Does NOT touch any other site config.

set -euo pipefail

VHOST_NAME=infra.ocialwaysfree.site
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$REPO_ROOT/deploy/$VHOST_NAME.conf"
AVAIL=/etc/nginx/sites-available/$VHOST_NAME
ENABLED=/etc/nginx/sites-enabled/$VHOST_NAME

if [[ ! -f "$SRC" ]]; then
  echo "missing vhost source: $SRC" >&2
  exit 1
fi

# 1. Back up an existing copy (defensive — sites-available shouldn't have
#    anything for this name yet, but never overwrite blindly).
if [[ -f "$AVAIL" ]]; then
  BACKUP="$AVAIL.bak.$(date -u +%Y%m%dT%H%M%SZ)"
  echo "→ backing up existing $AVAIL to $BACKUP"
  sudo cp "$AVAIL" "$BACKUP"
fi

# 2. Copy fresh vhost
echo "→ installing $AVAIL"
sudo cp "$SRC" "$AVAIL"

# 3. Symlink into sites-enabled (idempotent)
if [[ ! -L "$ENABLED" ]]; then
  echo "→ enabling $VHOST_NAME"
  sudo ln -s "$AVAIL" "$ENABLED"
fi

# 4. Validate before reload
echo "→ nginx -t"
if ! sudo nginx -t; then
  echo "✗ nginx config test FAILED — rolling back symlink"
  sudo rm -f "$ENABLED"
  exit 1
fi

# 5. Reload (NOT restart)
echo "→ reloading nginx"
sudo systemctl reload nginx

echo "✓ done. Hit https://$VHOST_NAME/"
