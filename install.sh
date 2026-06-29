#!/usr/bin/env bash
#
# InfraDocs terminal installer — onboard a server with no browser required.
#
#   curl -fsSL https://raw.githubusercontent.com/looking4manish/InfraDocs_V6/main/install.sh -o install.sh
#   bash install.sh
#
# (or just `bash install.sh` from inside an existing checkout). It clones/updates the
# repo, preflight-checks, prompts for this node's role/priority/address (+ the primary's
# address & token for a secondary), writes the node config, deploys the Docker stack, and
# onboards the node — running the SAME priority-uniqueness + bidirectional reachability
# checks the browser wizard does (by driving the API). Mesh-agnostic: it never installs or
# assumes Tailscale/any VPN; the node is reachable at the ADDRESS you supply.
set -euo pipefail

REPO_URL="${INFRADOCS_REPO_URL:-https://github.com/looking4manish/InfraDocs_V6.git}"
DEPLOY_DIR="${INFRADOCS_DIR:-$HOME/infradocs}"
BRANCH="${INFRADOCS_BRANCH:-main}"

step() { printf "\n\033[1;36m== %s ==\033[0m\n" "$1"; }
ok()   { printf "\033[1;32m  ✓ %s\033[0m\n" "$1"; }
warn() { printf "\033[1;33m  ! %s\033[0m\n" "$1"; }
err()  { printf "\033[1;31m  ✗ %s\033[0m\n" "$1" >&2; }
ask()  { local p="$1" d="${2:-}" v; if [[ -n "$d" ]]; then read -rp "  $p [$d]: " v; printf '%s' "${v:-$d}"; else read -rp "  $p: " v; printf '%s' "$v"; fi; }
askyn(){ local v; read -rp "  $1 [y/N]: " v; [[ "$v" =~ ^[Yy] ]]; }

DEPLOYED=""   # set once the stack is up so we know to tear it down on failure
cleanup() {
  if [[ -n "$DEPLOYED" && -f "$DEPLOY_DIR/deploy/docker/.env" ]]; then
    warn "tearing down the half-installed stack so the box is left clean…"
    (cd "$DEPLOY_DIR/deploy/docker" && docker compose --env-file .env down -v >/dev/null 2>&1) || true
  fi
}
die() { err "$1"; echo "" >&2; err "Installation stopped — no changes left behind."; cleanup; exit 1; }

# --- 1. preflight --------------------------------------------------------
step "Preflight checks"
for tool in git curl docker; do
  command -v "$tool" >/dev/null 2>&1 || die "missing required tool: $tool — install it and re-run"
done
docker compose version >/dev/null 2>&1 || die "the 'docker compose' plugin is missing"
docker info >/dev/null 2>&1 || die "cannot talk to the Docker daemon (is it running? are you in the 'docker' group?)"
ok "git, curl, docker + compose present; Docker daemon reachable"

# --- 2. fetch the repo ---------------------------------------------------
step "Fetch InfraDocs ($BRANCH)"
if [[ -d "$DEPLOY_DIR/.git" ]]; then
  git -C "$DEPLOY_DIR" fetch --depth 1 origin "$BRANCH" >/dev/null 2>&1 \
    && git -C "$DEPLOY_DIR" checkout -q "$BRANCH" \
    && git -C "$DEPLOY_DIR" reset --hard -q "origin/$BRANCH" \
    || die "failed to update the existing checkout at $DEPLOY_DIR"
  ok "updated $DEPLOY_DIR"
else
  git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$DEPLOY_DIR" >/dev/null 2>&1 \
    || die "git clone failed ($REPO_URL)"
  ok "cloned to $DEPLOY_DIR"
fi
cd "$DEPLOY_DIR"
PY="python3"; [[ -x "$DEPLOY_DIR/venv/bin/python" ]] && PY="$DEPLOY_DIR/venv/bin/python"
HELP=( env "PYTHONPATH=$DEPLOY_DIR" "$PY" -m app.cli_install )

# --- 3. prompts ----------------------------------------------------------
step "Node configuration"
SERVER_ID="$(ask "Short node id (e.g. oci, n150)" "$(hostname -s 2>/dev/null || echo node)")"
ADVERTISE_URL="$(ask "This node's reachable address — what other nodes + browsers use (e.g. http://HOST-OR-IP:8081)")"
[[ -n "$ADVERTISE_URL" ]] || die "a reachable address is required"

ROLE="secondary"; PRIORITY=""; PRIMARY_URL=""; JOIN_TOKEN=""
if askyn "Is this the FIRST node (the cluster primary)?"; then
  ROLE="primary"; PRIORITY=1
  ok "role = primary · priority = 1"
else
  PRIMARY_URL="$(ask "The primary's reachable address (e.g. http://PRIMARY-HOST:8081)")"
  [[ -n "$PRIMARY_URL" ]] || die "the primary's address is required for a secondary"
  JOIN_TOKEN="$(ask "Join token (mint one on the primary)")"
  [[ -n "$JOIN_TOKEN" ]] || die "a join token is required for a secondary"
  "${HELP[@]}" check-primary --primary-url "$PRIMARY_URL" \
    || die "cannot reach the primary at $PRIMARY_URL (check the address / firewall)"
  ok "primary reachable (secondary → primary)"
  while :; do
    PRIORITY="$(ask "Failover priority 1-99 (1 = highest; must be free)")"
    if "${HELP[@]}" check-priority --primary-url "$PRIMARY_URL" --priority "$PRIORITY"; then
      ok "priority $PRIORITY is valid and free"; break
    fi
    err "choose a different priority"
  done
fi

# --- 4. write the node config -------------------------------------------
step "Write node config"
export INSTALL_SERVER_ID="$SERVER_ID" INSTALL_SERVER_NAME="$SERVER_ID"
"${HELP[@]}" render-env --out "$DEPLOY_DIR/deploy/docker/.env" || die "failed to write deploy/docker/.env"
chmod 600 "$DEPLOY_DIR/deploy/docker/.env"
ok "wrote deploy/docker/.env"

# --- 5. deploy the stack (non-interactive) ------------------------------
step "Deploy the Docker stack"
INFRADOCS_NONINTERACTIVE=1 INFRADOCS_ADVERTISE_URL="$ADVERTISE_URL" \
  bash "$DEPLOY_DIR/deploy/docker/deploy.sh" || die "docker deploy failed"
DEPLOYED=1
API_PORT="$(grep -E '^API_PORT=' deploy/docker/.env | cut -d= -f2-)"; API_PORT="${API_PORT:-8090}"
ADMIN_PW="$(grep -E '^ADMIN_PASSWORD=' deploy/docker/.env | cut -d= -f2-)"; ADMIN_PW="${ADMIN_PW:-Changeme001}"
LOCAL_API="http://localhost:${API_PORT}"
printf "  waiting for the local API"
for _ in $(seq 1 45); do
  [[ "$(curl -s -o /dev/null -w '%{http_code}' "$LOCAL_API/api/health" 2>/dev/null)" == "200" ]] && { echo; break; }
  printf "."; sleep 2
done
[[ "$(curl -s -o /dev/null -w '%{http_code}' "$LOCAL_API/api/health" 2>/dev/null)" == "200" ]] \
  || die "the local API never became healthy on $LOCAL_API"
ok "stack is up and healthy"

# --- 6. onboard (drives priority uniqueness + bidirectional reachability) -
step "Onboard this node"
if [[ "$ROLE" == "secondary" ]]; then
  "${HELP[@]}" complete --api "$LOCAL_API" --user admin --password "$ADMIN_PW" \
    --role secondary --server-name "$SERVER_ID" --advertise-url "$ADVERTISE_URL" \
    --priority "$PRIORITY" --primary-url "$PRIMARY_URL" --join-token "$JOIN_TOKEN" \
    || die "onboarding refused (reason above). The primary must reach this node back at $ADVERTISE_URL"
  ok "enrolled — reachability confirmed both directions"
else
  "${HELP[@]}" complete --api "$LOCAL_API" --user admin --password "$ADMIN_PW" \
    --role primary --server-name "$SERVER_ID" --advertise-url "$ADVERTISE_URL" \
    || die "could not write the primary's config"
  ok "this node is the cluster primary"
fi

# --- 7. summary ----------------------------------------------------------
step "Installed"
echo "  role:      $ROLE"
echo "  priority:  $PRIORITY"
echo "  address:   $ADVERTISE_URL"
[[ "$ROLE" == "secondary" ]] && echo "  primary:   $PRIMARY_URL  (reachable, confirmed both directions)"
echo ""
echo "  Open the dashboard at: $ADVERTISE_URL   (login: admin / $ADMIN_PW — change it)"
if [[ "$ROLE" == "primary" ]]; then
  echo "  Mint a join token for each secondary from the Servers lens (or POST /api/federation/tokens)."
fi
echo "  Manage: (cd $DEPLOY_DIR/deploy/docker && docker compose --env-file .env ps|logs -f|down)"
