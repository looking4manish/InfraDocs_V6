#!/usr/bin/env bash
# InfraDocs one-shot deploy. Run it on the server:
#   bash deploy/docker/deploy.sh
# It installs Docker if needed, writes a minimal deploy/docker/.env, builds +
# starts the stack, and tells you how to reach the first-run WIZARD (where you
# fill in everything else). Re-runnable. Defaults are fine for a first test.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

say()  { printf "\n\033[1;36m▶ %s\033[0m\n" "$1"; }
warn() { printf "\033[1;33m! %s\033[0m\n" "$1"; }
ask()  { local p="$1" d="$2" v; read -rp "$p [$d]: " v; printf '%s' "${v:-$d}"; }

# --- 1. Docker -----------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
  warn "Docker is not installed."
  read -rp "Install Docker now (needs sudo)? [Y/n]: " a
  if [[ "${a:-Y}" =~ ^[Yy] ]]; then
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker "$USER" || true
    warn "Docker installed — if the build asks for sudo, the group isn't active"
    warn "yet; log out/in afterwards to run docker without sudo."
  else
    echo "Docker is required. Aborting."; exit 1
  fi
fi
if docker info >/dev/null 2>&1; then DC=(docker compose); else DC=(sudo docker compose); fi
"${DC[@]}" version >/dev/null 2>&1 || { echo "docker compose plugin missing"; exit 1; }

# --- 2. Minimal .env (you configure the rest in the wizard) --------------
if [[ -f .env ]]; then
  say ".env exists — reusing it. (Delete deploy/docker/.env to reconfigure.)"
else
  say "Minimal config — everything else is set in the web wizard after login."
  SERVER_ID=$(ask "Server id (short, e.g. oci-p)" "$(hostname -s 2>/dev/null || echo infradocs)")
  PROJECTS_ROOT=$(ask "Where your apps live (Projects root)" "$HOME/projects")
  {
    printf 'SERVER_ID=%s\n'      "$SERVER_ID"
    printf 'SERVER_NAME=%s\n'    "$SERVER_ID"
    printf 'ADMIN_USER=admin\n'
    printf 'ADMIN_PASSWORD=Changeme001\n'   # forced-changed on first login
    printf 'PROJECTS_ROOT=%s\n'  "$PROJECTS_ROOT"
    printf 'DOMAIN=:80\n'        # plain HTTP on WEB_PORT; pick real exposure in the wizard
    printf 'COMPOSE_PROFILES=\n'
    printf 'CF_TUNNEL_TOKEN=\n'
    printf 'TS_AUTHKEY=\n'
    printf 'WEB_PORT=8081\n'
    printf 'WEB_TLS_PORT=8443\n'
    printf 'API_PORT=8090\n'
    printf 'MONGO_PORT=27018\n'
  } > .env
  chmod 600 .env
  say ".env written (mode 600)."
fi

# --- 3. Build + start ----------------------------------------------------
say "Building + starting (first run pulls images + builds the UI — a few minutes)…"
"${DC[@]}" --env-file .env up -d --build

# --- 4. Wait for health --------------------------------------------------
get() { grep -E "^$1=" .env | cut -d= -f2-; }
API_PORT="$(get API_PORT)"; API_PORT="${API_PORT:-8090}"
WEB_PORT="$(get WEB_PORT)"; WEB_PORT="${WEB_PORT:-8081}"
say "Waiting for the API…"
ok=""
for _ in $(seq 1 40); do
  [[ "$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:${API_PORT}/api/health" || true)" == "200" ]] && { ok=1; break; }
  sleep 2
done
"${DC[@]}" --env-file .env ps
[[ -n "$ok" ]] && say "InfraDocs is up. 🎉" || warn "API not ready — check: ${DC[*]} --env-file .env logs api"

# --- 5. How to reach the wizard -----------------------------------------
HOSTIP="$(hostname -I 2>/dev/null | awk '{print $1}')"
cat <<EOF

────────────────────────────────────────────────────────────────────
 OPEN THE SETUP WIZARD
────────────────────────────────────────────────────────────────────
 This box is headless, so reach the UI one of these ways:

 1) SSH tunnel from YOUR laptop (simplest — nothing to open on the server):
      ssh -L ${WEB_PORT}:localhost:${WEB_PORT} ${USER}@${HOSTIP:-<server-ip>}
    then browse:  http://localhost:${WEB_PORT}

 2) Tailscale (if this box is on your tailnet):
      sudo tailscale serve --bg ${WEB_PORT}
      tailscale serve status     # prints the https://<host>.ts.net URL

 First login:  admin / Changeme001   → you'll set a new password, then the wizard.
 Manage:       ${DC[*]} --env-file .env  ps | logs -f | down
────────────────────────────────────────────────────────────────────
EOF
