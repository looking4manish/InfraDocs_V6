#!/usr/bin/env bash
#
# InfraDocs uninstaller — remove everything install.sh set up, and say honestly what
# it actually found and removed (a re-run over an already-clean box reports "nothing
# to remove", it does not pretend).
#
# By DEFAULT it removes the InfraDocs app: the Docker stack (containers, named volumes
# incl. Mongo data, network), the built images, the Tailscale serve URL, the host data
# dir, and the checkout. Docker and Tailscale THEMSELVES stay put.
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
#   --keep-repo         leave the checkout ($INFRADOCS_DIR) in place
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
    -h|--help)          sed -n '2,29p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg (see --help)" >&2; exit 1 ;;
  esac
done

step() { printf "\n\033[1;36m== %s ==\033[0m\n" "$1"; }
ok()   { printf "\033[1;32m  ✓ %s\033[0m\n" "$1"; }
info() { printf "\033[0;37m  · %s\033[0m\n" "$1"; }
warn() { printf "\033[1;33m  ! %s\033[0m\n" "$1"; }
err()  { printf "\033[1;31m  ✗ %s\033[0m\n" "$1" >&2; }
die()  { err "$1"; exit 1; }

# --- safety rails: never rm -rf something catastrophic ------------------
case "$DEPLOY_DIR" in
  ""|"/"|"$HOME"|"/root"|"/home") die "refusing to treat '$DEPLOY_DIR' as the InfraDocs dir (set INFRADOCS_DIR)" ;;
esac
case "$DATA_ROOT" in
  ""|"/"|"/data"|"/var"|"/home"|"$HOME") die "refusing to treat '$DATA_ROOT' as the data dir (set INFRADOCS_DATA_ROOT)" ;;
esac

# --- re-exec from /tmp if we're running from inside the dir we'll delete ---
SELF="$(readlink -f "$0" 2>/dev/null || echo "$0")"
if [[ -z "${INFRADOCS_UNINSTALL_REEXEC:-}" && "$SELF" == "$DEPLOY_DIR"/* ]]; then
  _tmp="$(mktemp "${TMPDIR:-/tmp}/infradocs-uninstall.XXXXXX.sh")"
  cp "$SELF" "$_tmp"
  INFRADOCS_UNINSTALL_REEXEC=1 exec bash "$_tmp" "$@"
fi

_rm_rf() {
  [[ -e "$1" || -L "$1" ]] || return 0
  rm -rf "$1" 2>/dev/null && [[ ! -e "$1" ]] && return 0
  if command -v sudo >/dev/null 2>&1; then sudo rm -rf "$1" 2>/dev/null; fi
  [[ ! -e "$1" ]] && return 0
  warn "could not fully remove $1 (permission or busy mount?)"; return 1
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
have_repo="";    [[ -d "$DEPLOY_DIR" ]] && have_repo=1
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
echo "  Target: $DEPLOY_DIR"
if [[ ${#DC[@]} -eq 0 ]]; then
  info "docker not installed — no containers/images/volumes to remove"
elif [[ -n "$have_assets" ]]; then
  echo "    • Docker stack: $n_c container(s), $n_i built image(s), $n_v named volume(s), network"; todo=1
  [[ -n "$PURGE_IMAGES" ]] && echo "    • base images (mongo/cloudflared/tailscale) if unused"
else
  info "no InfraDocs Docker stack found"
fi
if [[ -n "$have_repo" ]]; then
  if [[ -z "$KEEP_REPO" ]]; then echo "    • checkout: $DEPLOY_DIR"; todo=1
  elif [[ -z "$KEEP_CONFIG" && -f "$COMPOSE_DIR/.env" ]]; then echo "    • config: $COMPOSE_DIR/.env"; todo=1; fi
else
  info "checkout $DEPLOY_DIR not present"
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

# --- 1. stop + remove the Docker stack (only if there is one) ------------
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

# --- 4. config / checkout ------------------------------------------------
if [[ -n "$have_repo" ]]; then
  if [[ -z "$KEEP_REPO" ]]; then
    step "Remove the checkout"
    cd /
    _rm_rf "$DEPLOY_DIR" && ok "removed $DEPLOY_DIR"
  elif [[ -z "$KEEP_CONFIG" && -f "$COMPOSE_DIR/.env" ]]; then
    step "Remove saved config"
    _rm_rf "$COMPOSE_DIR/.env" && ok "removed $COMPOSE_DIR/.env"
  fi
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

# --- 6. verify: no orphans left ------------------------------------------
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
[[ -z "$KEEP_REPO" && -d "$DEPLOY_DIR" ]] && { warn "checkout still present: $DEPLOY_DIR"; remaining=1; }
[[ -z "$KEEP_DATA" && -e "$DATA_ROOT" ]] && { warn "host data still present: $DATA_ROOT"; remaining=1; }
if [[ "$remaining" == 0 ]]; then
  ok "clean — no InfraDocs assets remain"
  echo ""
  [[ -n "$REMOVE_DOCKER" ]] && echo "  InfraDocs is fully uninstalled, including the Docker engine." \
    || echo "  InfraDocs is uninstalled. Docker was left installed (use --all to purge it too)."
else
  die "some assets could not be removed (see above) — re-run with sudo / --all, or remove by hand"
fi
