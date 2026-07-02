#!/usr/bin/env bash
#
# InfraDocs uninstaller — remove everything install.sh set up, and say honestly what
# it actually found and removed (a re-run over an already-clean box reports "nothing
# to remove", it does not pretend).
#
# There are TWO checkouts this can be responsible for and it removes BOTH:
#   • the deploy dir  $INFRADOCS_DIR (default ~/infradocs), where install.sh re-clones
#     main and the Docker stack runs; and
#   • the OUTER clone the operator ran the installer/uninstaller from (auto-detected
#     from this script's own resolved location) — but ONLY if it's really an InfraDocs
#     checkout, so it can never nuke an unrelated parent directory.
# It never deletes its own current working directory from within it: it cds to a safe
# location first and removes by absolute path, then VERIFIES each path is gone and fails
# loudly (with the exact command to finish the job) if any remains.
#
# By DEFAULT it removes the InfraDocs app: the Docker stack (containers, named volumes
# incl. Mongo data, network), the built images, the Tailscale serve URL, the host data
# dir, and the checkout(s). Docker and Tailscale THEMSELVES stay put.
#
# For a TOTAL wipe of everything the installer pulled in — including the Docker engine
# and the Tailscale package — pass --all. That is destructive to ALL Docker on the host,
# so it is opt-in.
#
#   bash ~/infradocs/uninstall.sh                 # app only, asks once
#   bash ~/infradocs/uninstall.sh --all --yes     # nuke everything, no prompt
#
# Flags:
#   -y, --yes           don't prompt for confirmation
#   --all               --purge-images --remove-docker --remove-tailscale
#   --purge-images      also remove the pulled base images (mongo/cloudflared/tailscale)
#   --remove-docker     uninstall the Docker engine + wipe /var/lib/docker, /etc/docker
#   --remove-tailscale  uninstall the Tailscale package + wipe its state
#   --keep-repo         leave the checkout(s) in place
#   --keep-config       keep deploy/docker/.env (only meaningful with --keep-repo)
#   --keep-data         leave the host data dir ($INFRADOCS_DATA_ROOT) in place
#
# Env: INFRADOCS_DIR (default $HOME/infradocs), INFRADOCS_DATA_ROOT (default /data/infradocs).
set -euo pipefail

DEPLOY_DIR="${INFRADOCS_DIR:-$HOME/infradocs}"
DATA_ROOT="${INFRADOCS_DATA_ROOT:-/data/infradocs}"
COMPOSE_DIR="$DEPLOY_DIR/deploy/docker"

ASSUME_YES=""; KEEP_REPO=""; KEEP_CONFIG=""; KEEP_DATA=""
PURGE_IMAGES=""; REMOVE_DOCKER=""; REMOVE_TAILSCALE=""
for arg in "$@"; do
  case "$arg" in
    -y|--yes)           ASSUME_YES=1 ;;
    --all)              PURGE_IMAGES=1; REMOVE_DOCKER=1; REMOVE_TAILSCALE=1 ;;
    --purge-images)     PURGE_IMAGES=1 ;;
    --remove-docker)    REMOVE_DOCKER=1 ;;
    --remove-tailscale) REMOVE_TAILSCALE=1 ;;
    --keep-repo)        KEEP_REPO=1 ;;
    --keep-config)      KEEP_CONFIG=1 ;;
    --keep-data)        KEEP_DATA=1 ;;
    -h|--help)          sed -n '2,38p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg (see --help)" >&2; exit 1 ;;
  esac
done

_ts()  { date -u +%Y-%m-%dT%H:%M:%SZ; }
step() { printf "\n\033[1;36m== %s ==\033[0m\n" "$1"; }
ok()   { printf "\033[1;32m  ✓ %s\033[0m\n" "$1"; }
info() { printf "\033[0;37m  · %s\033[0m\n" "$1"; }
warn() { printf "\033[1;33m  ! %s\033[0m\n" "$1"; }
err()  { printf "\033[1;31m  ✗ %s\033[0m\n" "$1" >&2; }
die()  { err "$1"; exit 1; }

# A directory that is catastrophic to rm -rf — never treat one as a target.
_safe_target() {
  case "$1" in
    ""|"/"|"$HOME"|"/root"|"/home"|"/tmp"|"/usr"|"/etc"|"/var"|"/opt"|"/srv"|"/data") return 1 ;;
  esac
  return 0
}

# Is `$1` genuinely an InfraDocs checkout? Guards the auto-detected outer dir so we can
# never delete an unrelated parent that merely happens to be the CWD / script location.
_is_infradocs_checkout() {
  local d="$1"
  [[ -d "$d" && -f "$d/install.sh" && -f "$d/uninstall.sh" ]] || return 1
  [[ -d "$d/app" || -f "$d/config.yml" || -d "$d/deploy/docker" ]] || return 1
  return 0
}

# --- safety rails: never rm -rf something catastrophic ------------------
_safe_target "$DEPLOY_DIR" || die "refusing to treat '$DEPLOY_DIR' as the InfraDocs dir (set INFRADOCS_DIR)"
case "$DATA_ROOT" in
  ""|"/"|"/data"|"/var"|"/home"|"$HOME") die "refusing to treat '$DATA_ROOT' as the data dir (set INFRADOCS_DATA_ROOT)" ;;
esac

# --- resolve the two trees + the invocation context ---------------------
# On re-exec these come from the env (the /tmp copy's own dirname is meaningless), so the
# outer clone we detected before stepping out is preserved.
SELF="$(readlink -f "$0" 2>/dev/null || echo "$0")"
SCRIPT_DIR="${INFRADOCS_SCRIPT_DIR:-$(cd "$(dirname "$SELF")" 2>/dev/null && pwd || true)}"
INVOKED_CWD="${INFRADOCS_INVOKED_CWD:-$PWD}"

OUTER_DIR="${INFRADOCS_OUTER_DIR-__unset__}"
if [[ "$OUTER_DIR" == "__unset__" ]]; then
  OUTER_DIR=""
  for cand in "$SCRIPT_DIR" "$INVOKED_CWD"; do
    if [[ -n "$cand" && "$cand" != "$DEPLOY_DIR" ]] && _safe_target "$cand" && _is_infradocs_checkout "$cand"; then
      OUTER_DIR="$cand"; break
    fi
  done
fi

# The checkout trees to remove (deploy dir + outer clone), de-duplicated.
REMOVE_DIRS=()
if [[ -z "$KEEP_REPO" ]]; then
  [[ -d "$DEPLOY_DIR" ]] && REMOVE_DIRS+=("$DEPLOY_DIR")
  [[ -n "$OUTER_DIR" && -d "$OUTER_DIR" && "$OUTER_DIR" != "$DEPLOY_DIR" ]] && REMOVE_DIRS+=("$OUTER_DIR")
fi

# --- re-exec from /tmp if we're running from inside ANY tree we'll delete ---
# Otherwise `rm -rf` can't unlink the in-use directory node (contents go, the dir stays)
# and the script would falsely report success. Copying out first guarantees full removal.
_self_inside_target=""
for d in "${REMOVE_DIRS[@]:-}"; do
  [[ -n "$d" && ( "$SELF" == "$d" || "$SELF" == "$d"/* ) ]] && _self_inside_target=1
done
if [[ -z "${INFRADOCS_UNINSTALL_REEXEC:-}" && -n "$_self_inside_target" ]]; then
  _tmp="$(mktemp "${TMPDIR:-/tmp}/infradocs-uninstall.XXXXXX.sh")"
  cp "$SELF" "$_tmp"
  INFRADOCS_UNINSTALL_REEXEC=1 INFRADOCS_SCRIPT_DIR="$SCRIPT_DIR" \
    INFRADOCS_INVOKED_CWD="$INVOKED_CWD" INFRADOCS_OUTER_DIR="$OUTER_DIR" \
    exec bash "$_tmp" "$@"
fi

# Best-effort rm for non-checkout paths (data dir, package state) — verifies removal.
_rm_rf() {
  [[ -e "$1" || -L "$1" ]] || return 0
  rm -rf "$1" 2>/dev/null && [[ ! -e "$1" ]] && return 0
  if command -v sudo >/dev/null 2>&1; then sudo rm -rf "$1" 2>/dev/null; fi
  [[ ! -e "$1" ]] && return 0
  warn "could not fully remove $1 (permission or busy mount?)"; return 1
}

# Remove a checkout TREE by absolute path, from OUTSIDE it. Verifies it is actually gone
# and, if not, prints a loud timestamped named-reason failure + the exact command to
# finish it by hand. Returns non-zero if the path survives.
_remove_tree() {
  local path="$1"
  [[ -d "$path" || -L "$path" ]] || return 0
  cd /tmp 2>/dev/null || cd /               # never delete our own CWD from within it
  rm -rf "$path" 2>/dev/null || true
  if [[ -e "$path" ]] && command -v sudo >/dev/null 2>&1; then sudo rm -rf "$path" 2>/dev/null || true; fi
  if [[ -e "$path" ]]; then
    err "$(_ts) uninstall: could NOT remove $path"
    err "    reason: it is (or contains) the current working directory, or a busy mount."
    err "    finish it from outside the tree:  cd ~ && rm -rf \"$path\""
    return 1
  fi
  ok "removed $path"
  return 0
}

_purge_pkgs() {
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get purge -y "$@" >/dev/null 2>&1 || true
    sudo apt-get autoremove -y >/dev/null 2>&1 || true
  elif command -v dnf >/dev/null 2>&1; then sudo dnf remove -y "$@" >/dev/null 2>&1 || true
  elif command -v yum >/dev/null 2>&1; then sudo yum remove -y "$@" >/dev/null 2>&1 || true
  else warn "no apt/dnf/yum found — remove these packages by hand: $*"; fi
}

DC=()
if command -v docker >/dev/null 2>&1; then
  if docker info >/dev/null 2>&1; then DC=(docker); else DC=(sudo docker); fi
fi

IMAGES_BUILT=(infradocs-api:latest infradocs-web:latest infradocs-api:poc)
IMAGES_BASE=(mongo:7 cloudflare/cloudflared:latest tailscale/tailscale:latest)
VOLUMES=(docker_mongo_data docker_caddy_data docker_tailscale_state)

_count() { grep -c . 2>/dev/null || true; }

# --- discover what actually exists on THIS box ---------------------------
have_data="";    [[ -e "$DATA_ROOT" || -L "$DATA_ROOT" ]] && have_data=1
have_compose=""; [[ -d "$COMPOSE_DIR" ]] && have_compose=1
n_c=0; n_i=0; n_v=0
if [[ ${#DC[@]} -gt 0 ]]; then
  n_c=$("${DC[@]}" ps -aq --filter name=infradocs 2>/dev/null | _count)
  n_i=$("${DC[@]}" images -q --filter=reference='infradocs-*' 2>/dev/null | _count)
  n_v=$("${DC[@]}" volume ls -q 2>/dev/null | grep -Ec 'docker_(mongo_data|caddy_data|tailscale_state)$' 2>/dev/null || true)
fi
have_assets=""; [[ "$n_c" != 0 || "$n_i" != 0 || "$n_v" != 0 || -n "$have_compose" ]] && have_assets=1

# --- plan (only what is actually present / requested) --------------------
step "InfraDocs uninstall — plan"
todo=0
if [[ ${#DC[@]} -eq 0 ]]; then
  info "docker not installed — no containers/images/volumes to remove"
elif [[ -n "$have_assets" ]]; then
  echo "    • Docker stack: $n_c container(s), $n_i built image(s), $n_v named volume(s), network"; todo=1
  [[ -n "$PURGE_IMAGES" ]] && echo "    • base images (mongo/cloudflared/tailscale) if unused"
else
  info "no InfraDocs Docker stack found"
fi
if [[ -n "$KEEP_REPO" ]]; then
  info "checkout(s) kept (--keep-repo)"
  [[ -z "$KEEP_CONFIG" && -f "$COMPOSE_DIR/.env" ]] && { echo "    • config: $COMPOSE_DIR/.env"; todo=1; }
elif [[ ${#REMOVE_DIRS[@]} -gt 0 ]]; then
  for d in "${REMOVE_DIRS[@]}"; do
    if [[ "$d" == "$DEPLOY_DIR" ]]; then echo "    • checkout (deploy dir): $d"
    else echo "    • checkout (outer clone you ran from): $d"; fi
  done
  todo=1
else
  info "no InfraDocs checkout present (deploy dir $DEPLOY_DIR)"
fi
if [[ -n "$have_data" && -z "$KEEP_DATA" ]]; then echo "    • host data: $DATA_ROOT"; todo=1
elif [[ -z "$have_data" ]]; then info "host data $DATA_ROOT not present"; fi
if [[ -n "$REMOVE_DOCKER" ]] && command -v docker >/dev/null 2>&1; then
  echo "    • ⚠ the DOCKER ENGINE (package + /var/lib/docker, /etc/docker) — affects ALL Docker on this host"; todo=1
elif [[ -z "$REMOVE_DOCKER" ]]; then
  info "Docker engine will be KEPT (pass --all or --remove-docker to purge it)"
fi
if [[ -n "$REMOVE_TAILSCALE" ]] && command -v tailscale >/dev/null 2>&1; then
  echo "    • ⚠ the Tailscale package + state — affects this whole host"; todo=1
fi

if [[ "$todo" -eq 0 ]]; then
  step "Nothing to do"
  ok "InfraDocs is not installed here — nothing to remove."
  exit 0
fi
if [[ -z "$ASSUME_YES" ]]; then
  read -rp $'\n  Proceed? [y/N]: ' a
  [[ "$a" =~ ^[Yy] ]] || die "aborted — nothing was changed"
fi

# --- 1. stop + remove the Docker stack (runs regardless of dir outcome) ---
if [[ ${#DC[@]} -gt 0 && -n "$have_assets" ]]; then
  step "Stop + remove the Docker stack"
  if [[ -n "$have_compose" ]]; then
    ENVFILE=(); [[ -f "$COMPOSE_DIR/.env" ]] && ENVFILE=(--env-file .env)
    ( cd "$COMPOSE_DIR"
      ADMIN_PASSWORD="${ADMIN_PASSWORD:-uninstall}" \
        "${DC[@]}" compose "${ENVFILE[@]}" --profile cloudflare --profile tailscale \
          down -v --remove-orphans >/dev/null 2>&1
    ) && ok "compose stack stopped + removed" || warn "compose down had issues — sweeping by name"
  fi
  mapfile -t leftover < <(
    { "${DC[@]}" ps -aq --filter name=infradocs 2>/dev/null
      for img in "${IMAGES_BUILT[@]}"; do "${DC[@]}" ps -aq --filter ancestor="$img" 2>/dev/null; done
    } | sort -u | grep -v '^$' || true
  )
  [[ ${#leftover[@]} -gt 0 ]] && { "${DC[@]}" rm -f "${leftover[@]}" >/dev/null 2>&1 || true; ok "removed ${#leftover[@]} container(s)"; }
  "${DC[@]}" volume rm -f "${VOLUMES[@]}" >/dev/null 2>&1 || true
  "${DC[@]}" rmi -f "${IMAGES_BUILT[@]}" >/dev/null 2>&1 || true
  [[ -n "$PURGE_IMAGES" ]] && { "${DC[@]}" rmi "${IMAGES_BASE[@]}" >/dev/null 2>&1 || true; }
  ok "removed built images + named volumes"
fi

# --- 2. Tailscale: reset serve, or remove the package --------------------
if command -v tailscale >/dev/null 2>&1; then
  if [[ -n "$REMOVE_TAILSCALE" ]]; then
    step "Remove Tailscale"
    sudo tailscale down >/dev/null 2>&1 || true
    sudo systemctl disable --now tailscaled >/dev/null 2>&1 || true
    _purge_pkgs tailscale
    _rm_rf /var/lib/tailscale || true; _rm_rf /var/cache/tailscale || true
    ok "tailscale package + state removed"
  elif [[ -n "$have_assets" ]]; then
    step "Reset Tailscale serve"
    sudo tailscale serve reset >/dev/null 2>&1 || true
    ok "tailscale serve reset (package kept)"
  fi
fi

# --- 3. host data dir ----------------------------------------------------
if [[ -z "$KEEP_DATA" && -n "$have_data" ]]; then
  step "Remove host data"
  _rm_rf "$DATA_ROOT" && ok "removed $DATA_ROOT"
fi

# --- 4. config / checkout(s) ---------------------------------------------
# Track dir-removal failures without aborting (set -e) so verify can report every path.
dir_failed=0
if [[ -n "$KEEP_REPO" ]]; then
  if [[ -z "$KEEP_CONFIG" && -f "$COMPOSE_DIR/.env" ]]; then
    step "Remove saved config"
    _rm_rf "$COMPOSE_DIR/.env" && ok "removed $COMPOSE_DIR/.env"
  fi
elif [[ ${#REMOVE_DIRS[@]} -gt 0 ]]; then
  step "Remove the checkout(s)"
  for d in "${REMOVE_DIRS[@]}"; do
    _remove_tree "$d" || dir_failed=1
  done
fi

# --- 5. Docker engine (opt-in; LAST) -------------------------------------
if [[ -n "$REMOVE_DOCKER" ]] && command -v docker >/dev/null 2>&1; then
  step "Remove the Docker engine"
  sudo systemctl disable --now docker docker.socket containerd >/dev/null 2>&1 || true
  _purge_pkgs docker-ce docker-ce-cli containerd.io docker-buildx-plugin \
              docker-compose-plugin docker-ce-rootless-extras docker.io docker-doc \
              docker-compose podman-docker
  _rm_rf /var/lib/docker || true; _rm_rf /var/lib/containerd || true; _rm_rf /etc/docker || true
  _rm_rf /var/run/docker.sock || true
  sudo groupdel docker >/dev/null 2>&1 || true
  ok "docker engine + data removed"
fi

# --- 6. verify: nothing left, and report the TRUTH -----------------------
step "Verify"
remaining=0
if command -v docker >/dev/null 2>&1; then
  DCV=(docker); docker info >/dev/null 2>&1 || DCV=(sudo docker)
  c=$("${DCV[@]}" ps -aq --filter name=infradocs 2>/dev/null | _count)
  i=$("${DCV[@]}" images -q --filter=reference='infradocs-*' 2>/dev/null | _count)
  v=$("${DCV[@]}" volume ls -q 2>/dev/null | grep -Ec 'docker_(mongo_data|caddy_data|tailscale_state)$' 2>/dev/null || true)
  [[ "$c" != 0 ]] && { warn "$c InfraDocs container(s) still present"; remaining=1; }
  [[ "$i" != 0 ]] && { warn "$i InfraDocs image(s) still present"; remaining=1; }
  [[ "$v" != 0 ]] && { warn "$v InfraDocs volume(s) still present"; remaining=1; }
  [[ -n "$REMOVE_DOCKER" ]] && { warn "docker still on PATH after purge — remove leftover packages by hand"; remaining=1; }
fi
if [[ -z "$KEEP_REPO" ]]; then
  for d in "${REMOVE_DIRS[@]:-}"; do
    [[ -n "$d" && -e "$d" ]] || continue
    err "$(_ts) uninstall: checkout still present: $d"
    err "    run this from your home dir to finish it:  cd ~ && rm -rf \"$d\""
    remaining=1
  done
fi
[[ -z "$KEEP_DATA" && -e "$DATA_ROOT" ]] && { warn "host data still present: $DATA_ROOT"; remaining=1; }

if [[ "$remaining" == 0 && "$dir_failed" == 0 ]]; then
  ok "clean — no InfraDocs assets remain"
  echo ""
  [[ -n "$REMOVE_DOCKER" ]] && echo "  InfraDocs is fully uninstalled, including the Docker engine." \
    || echo "  InfraDocs is uninstalled. Docker was left installed (use --all to purge it too)."
else
  die "$(_ts) uninstall INCOMPLETE — some targets could not be removed (see above). The Docker teardown ran; finish the leftover path(s) with the printed command."
fi
