#!/usr/bin/env bash
#
# InfraDocs terminal installer — stand a node up, then onboard it your way.
#
#   curl -fsSL https://raw.githubusercontent.com/looking4manish/InfraDocs_V6/main/install.sh -o install.sh
#   bash install.sh
#
# (or just `bash install.sh` from inside an existing checkout). ONE installer with a
# shared bring-up and a fork at the very end:
#   shared  — preflight, clone/pull, render the node config, build + bring up the Docker
#             stack (API + Mongo + web), wait until it's healthy.
#   onboard — you choose HOW to finish:
#     • CLI: answer the prompts here (role / priority / this node's reachable address /
#       — for a secondary — the primary's address + join token). It runs the SAME
#       priority-uniqueness + bidirectional reachability checks the browser wizard does
#       (by driving the API), writes config, and enrolls the node.
#     • UI:  no terminal prompts — it prints the URL you open to finish setup in the
#       browser wizard, and exits leaving the node running-but-unconfigured. The wizard
#       collects the SAME fields and calls the SAME enroll/validation APIs — one config
#       format, both paths converge.
#
# Pick non-interactively with --onboard=cli|ui (or INFRADOCS_ONBOARD=cli|ui) so scripted
# installs work. Mesh-agnostic: it never installs or assumes Tailscale/any VPN; the node
# is reachable at the ADDRESS you supply (CLI prompt) or fill into the wizard (UI).
set -euo pipefail

REPO_URL="${INFRADOCS_REPO_URL:-https://github.com/looking4manish/InfraDocs_V6.git}"
DEPLOY_DIR="${INFRADOCS_DIR:-$HOME/infradocs}"
BRANCH="${INFRADOCS_BRANCH:-main}"

# How to onboard once the stack is up: cli | ui | "" (ask). Flag wins over env.
ONBOARD="${INFRADOCS_ONBOARD:-}"
for arg in "$@"; do
  case "$arg" in
    --onboard=*) ONBOARD="${arg#*=}" ;;
    --onboard)   echo "use --onboard=cli or --onboard=ui" >&2; exit 1 ;;
  esac
done

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

# Normalise --onboard early so a typo fails before we build anything.
case "$ONBOARD" in
  ""|cli|ui) : ;;
  *) die "invalid --onboard='$ONBOARD' (use cli or ui)" ;;
esac

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

# --- 3. node identity (all that bring-up needs) --------------------------
# Just the node's short id — enough to render the .env and stand the stack up. The
# onboarding details (role / priority / reachable address / join) come later, and
# only on the path you choose. Defaults to the hostname for fully-scripted installs.
step "Node identity"
SERVER_ID="${INFRADOCS_SERVER_ID:-$(ask "Short node id (e.g. oci, n150)" "$(hostname -s 2>/dev/null || echo node)")}"
[[ -n "$SERVER_ID" ]] || die "a node id is required"
ok "node id = $SERVER_ID"

# --- 4. write the node config -------------------------------------------
step "Write node config"
export INSTALL_SERVER_ID="$SERVER_ID" INSTALL_SERVER_NAME="$SERVER_ID"
"${HELP[@]}" render-env --out "$DEPLOY_DIR/deploy/docker/.env" || die "failed to write deploy/docker/.env"
chmod 600 "$DEPLOY_DIR/deploy/docker/.env"
ok "wrote deploy/docker/.env"

# --- 5. bring up the stack (shared by both onboarding paths) ------------
step "Deploy the Docker stack"
INFRADOCS_NONINTERACTIVE=1 bash "$DEPLOY_DIR/deploy/docker/deploy.sh" || die "docker deploy failed"
DEPLOYED=1
API_PORT="$(grep -E '^API_PORT=' deploy/docker/.env | cut -d= -f2-)"; API_PORT="${API_PORT:-8090}"
WEB_PORT="$(grep -E '^WEB_PORT=' deploy/docker/.env | cut -d= -f2-)"; WEB_PORT="${WEB_PORT:-8081}"
ADMIN_PW="$(grep -E '^ADMIN_PASSWORD=' deploy/docker/.env | cut -d= -f2-)"; ADMIN_PW="${ADMIN_PW:-Changeme001}"
LOCAL_API="http://localhost:${API_PORT}"
LOCAL_WEB="http://localhost:${WEB_PORT}"
printf "  waiting for the local API"
for _ in $(seq 1 45); do
  [[ "$(curl -s -o /dev/null -w '%{http_code}' "$LOCAL_API/api/health" 2>/dev/null)" == "200" ]] && { echo; break; }
  printf "."; sleep 2
done
[[ "$(curl -s -o /dev/null -w '%{http_code}' "$LOCAL_API/api/health" 2>/dev/null)" == "200" ]] \
  || die "the local API never became healthy on $LOCAL_API"
ok "API + Mongo healthy"
printf "  waiting for the web UI"
for _ in $(seq 1 45); do
  code="$(curl -s -o /dev/null -w '%{http_code}' "$LOCAL_WEB/" 2>/dev/null)"
  [[ "$code" =~ ^(200|301|302|304)$ ]] && { echo; break; }
  printf "."; sleep 2
done
code="$(curl -s -o /dev/null -w '%{http_code}' "$LOCAL_WEB/" 2>/dev/null)"
[[ "$code" =~ ^(200|301|302|304)$ ]] \
  || die "the web UI never became reachable on $LOCAL_WEB"
ok "stack is up and healthy (API + Mongo + web)"

# --- 6. choose the onboarding method ------------------------------------
step "Onboarding method"
if [[ -z "$ONBOARD" ]]; then
  while [[ "$ONBOARD" != "cli" && "$ONBOARD" != "ui" ]]; do
    a="$(ask "Onboard this node via [C]LI prompts here, or [U]I wizard in a browser?" "C")"
    case "$a" in
      C|c|cli|CLI) ONBOARD="cli" ;;
      U|u|ui|UI)   ONBOARD="ui" ;;
      *)           err "answer C or U" ;;
    esac
  done
fi
ok "onboarding via: $ONBOARD"

# --- 7. FORK: onboard via CLI here, or hand off to the UI wizard --------
if [[ "$ONBOARD" == "cli" ]]; then
  # ---- CLI path: interactive prompts + live checks + enroll (unchanged behaviour)
  step "Onboard via CLI"
  ADVERTISE_URL="$(ask "This node's reachable address — what other nodes + browsers use (e.g. http://HOST-OR-IP:${WEB_PORT})")"
  [[ -n "$ADVERTISE_URL" ]] || die "a reachable address is required"

  ROLE="secondary"; PRIORITY=""; PRIMARY_URL=""; JOIN_TOKEN=""
  if askyn "Is this the FIRST node (the cluster primary)?"; then
    ROLE="primary"; PRIORITY=1
    ok "role = primary · priority = 1"
  else
    PRIMARY_URL="$(ask "The primary's reachable address (e.g. http://PRIMARY-HOST:${WEB_PORT})")"
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

  step "Enroll this node"
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

  step "Installed — node configured + joined (CLI)"
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
else
  # ---- UI path: no terminal prompts. Stack is already up; print the wizard URL and exit.
  # The operator fills in the SAME fields (role / priority / reachable address / join) in
  # the browser wizard, which calls the SAME /api/setup/complete enroll + validation APIs.
  step "Onboard via UI wizard"
  ok "node is running — finish setup in the browser (no terminal prompts)"
  # The address other machines use is operator-supplied; here we only know the local URL.
  WIZ_URL="${INFRADOCS_ADVERTISE_URL:-$LOCAL_WEB}"
  CONFIGURED_LINE=""
  [[ -n "${INFRADOCS_ADVERTISE_URL:-}" ]] && CONFIGURED_LINE="   Configured:      $INFRADOCS_ADVERTISE_URL"
  cat <<EOF

  ====================================================================
   OPEN THE SETUP WIZARD
  ====================================================================
   On this host:    $LOCAL_WEB
   From elsewhere:  http://<this node's reachable address>:${WEB_PORT}
${CONFIGURED_LINE:+$CONFIGURED_LINE
}
   Login: admin / $ADMIN_PW  (change it), then the wizard collects role /
   priority / this node's reachable address / (secondary: primary address +
   join token) and enrolls the node — the SAME fields and APIs the CLI path
   uses. The node stays running but UNCONFIGURED until you finish there.
  ====================================================================
EOF

  step "Stack up — open the URL above to finish setup (UI)"
  echo "  onboarding:  UI wizard (node is up but NOT yet configured)"
  echo "  open:        $WIZ_URL"
  echo "  next:        log in, complete the wizard — it enrolls the node"
  echo "  Manage: (cd $DEPLOY_DIR/deploy/docker && docker compose --env-file .env ps|logs -f|down)"
fi
