#!/usr/bin/env bash
# InfraDocs one-shot deploy helper. Run it from anywhere:
#   bash deploy/docker/deploy.sh
# It checks Docker, writes deploy/docker/.env interactively (first run only),
# then builds + starts the stack and prints how to reach it. Re-runnable.
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
    warn "Docker installed. If the next step asks for sudo, that's the group not"
    warn "being active yet — log out/in afterwards to run docker without sudo."
  else
    echo "Docker is required. Aborting."; exit 1
  fi
fi
# Use sudo for compose only if this shell can't talk to the daemon yet.
if docker info >/dev/null 2>&1; then DC=(docker compose); else DC=(sudo docker compose); fi
"${DC[@]}" version >/dev/null 2>&1 || { echo "docker compose plugin missing"; exit 1; }

# --- 2. Config (.env) ----------------------------------------------------
if [[ -f .env ]]; then
  say ".env already exists — reusing it. (Delete deploy/docker/.env to reconfigure.)"
else
  say "Let's configure this deployment."
  SERVER_ID=$(ask "Server id (short, e.g. oci-p)" "$(hostname -s 2>/dev/null || echo infradocs)")
  SERVER_NAME=$(ask "Display name" "$SERVER_ID")
  PROJECTS_ROOT=$(ask "Projects root (where your apps live)" "$HOME/projects")

  while :; do
    read -rsp "Initial admin password (min 8 chars): " ADMIN_PASSWORD; echo
    [[ ${#ADMIN_PASSWORD} -ge 8 ]] && break || warn "too short"
  done

  echo "How will the UI be reached from the internet?"
  echo "  1) localhost / Tailscale  (default — no domain; use 'tailscale serve' after)"
  echo "  2) Domain + Caddy auto-TLS (point your DNS at this box's PUBLIC IP, open 80/443)"
  echo "  3) Cloudflare Tunnel       (works behind NAT/CGNAT)"
  EX=$(ask "Choose 1-3" "1")
  # :80 = serve plain HTTP on the web port (clean for curl / tailscale / cloudflare,
  # which terminate TLS themselves). A real domain → Caddy auto-provisions TLS on 443.
  DOMAIN=":80"; COMPOSE_PROFILES=""; CF_TUNNEL_TOKEN=""
  case "$EX" in
    2) DOMAIN=$(ask "Domain (e.g. infra.you.com)" "infra.example.com") ;;
    3) COMPOSE_PROFILES="cloudflare"
       CF_TUNNEL_TOKEN=$(ask "Cloudflare tunnel token" "") ;;
  esac

  # Write .env with printf so special chars in the password stay literal.
  {
    printf 'SERVER_ID=%s\n'        "$SERVER_ID"
    printf 'SERVER_NAME=%s\n'      "$SERVER_NAME"
    printf 'ADMIN_USER=admin\n'
    printf 'ADMIN_PASSWORD=%s\n'   "$ADMIN_PASSWORD"
    printf 'PROJECTS_ROOT=%s\n'    "$PROJECTS_ROOT"
    printf 'DOMAIN=%s\n'           "$DOMAIN"
    printf 'COMPOSE_PROFILES=%s\n' "$COMPOSE_PROFILES"
    printf 'CF_TUNNEL_TOKEN=%s\n'  "$CF_TUNNEL_TOKEN"
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
say "Building + starting the stack (first run can take a few minutes)…"
"${DC[@]}" --env-file .env up -d --build

# --- 4. Wait for the API + report ---------------------------------------
get() { grep -E "^$1=" .env | cut -d= -f2-; }
API_PORT="$(get API_PORT)"; API_PORT="${API_PORT:-8090}"
WEB_PORT="$(get WEB_PORT)"; WEB_PORT="${WEB_PORT:-8081}"

say "Waiting for the API to come up…"
ok=""
for _ in $(seq 1 40); do
  if [[ "$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:${API_PORT}/api/health" || true)" == "200" ]]; then
    ok=1; break
  fi
  sleep 2
done

"${DC[@]}" --env-file .env ps
if [[ -n "$ok" ]]; then say "InfraDocs is up. 🎉"; else warn "API not healthy yet — check: ${DC[*]} --env-file .env logs api"; fi

cat <<EOF

  Local UI:    http://localhost:${WEB_PORT}/
  First login: admin / Changeme001   (you'll be forced to set a new one)

  Reach it from another device on your tailnet:
     sudo tailscale serve --bg ${WEB_PORT}
     tailscale serve status        # prints the https://<host>.ts.net URL

  Manage:  ${DC[*]} --env-file .env ps | logs -f | down
EOF
