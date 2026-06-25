#!/usr/bin/env bash
# InfraDocs teardown. Run on the server:
#   bash deploy/docker/remove.sh
# Removes containers, volumes, the built images, and the Tailscale wizard URL.
# Docker + Tailscale themselves stay installed. Re-runnable / safe if already gone.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"
say() { printf "\n\033[1;36m> %s\033[0m\n" "$1"; }

# Use sudo for docker only if this shell can't reach the daemon directly.
if docker info >/dev/null 2>&1; then SUDO=""; else SUDO="sudo"; fi
ENVFILE=(); [[ -f .env ]] && ENVFILE=(--env-file .env)

say "Stopping + removing containers, volumes, network..."
$SUDO docker compose "${ENVFILE[@]}" --profile cloudflare --profile tailscale \
  down -v --remove-orphans 2>/dev/null || true

say "Removing built images..."
$SUDO docker rmi -f infradocs-api:latest infradocs-web:latest infradocs-api:poc 2>/dev/null || true

say "Resetting Tailscale serve (if it was used)..."
sudo tailscale serve reset 2>/dev/null || true

read -rp "Also delete deploy/docker/.env (your saved config)? [y/N]: " d
[[ "${d:-N}" =~ ^[Yy] ]] && rm -f .env && echo "  .env removed."

say "Done - InfraDocs containers, volumes, and images are gone."
echo "  Verify:        docker ps -a | grep infradocs   # (nothing)"
echo "  Delete repo:   cd ~ && rm -rf \"$(cd ../.. && pwd)\""
