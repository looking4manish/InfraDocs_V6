#!/usr/bin/env bash
#
# InfraDocs uninstaller — reverse everything install.sh set up, leaving no orphans.
#
# By DEFAULT it removes the InfraDocs app only: the Docker stack (containers, named
# volumes incl. Mongo data, network), the locally-built images, the Tailscale serve
# URL, the host data dir, and the checkout. Docker and Tailscale THEMSELVES stay put,
# because on most boxes they predate/outlive InfraDocs.
#
# For a TOTAL wipe of everything the installer pulled in — including the Docker engine
# and Tailscale packages — pass --all (or the individual --remove-docker /
# --remove-tailscale). This is destructive to the whole host's Docker, so it's opt-in.
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
    -y|--yes)          ASSUME_YES=1 ;;
    --all)             PURGE_IMAGES=1; REMOVE_DOCKER=1; REMOVE_TAILSCALE=1 ;;
    --purge-images)    PURGE_IMAGES=1 ;;
    --remove-docker)   REMOVE_DOCKER=1 ;;
    --remove-tailscale) REMOVE_TAILSCALE=1 ;;
    --keep-repo)       KEEP_REPO=1 ;;
    --keep-config)     KEEP_CONFIG=1 ;;
    --keep-data)       KEEP_DATA=1 ;;
    -h|--help)         sed -n '2,29p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg (see --help)" >&2; exit 1 ;;
  esac
done

step() { printf "\n\033[1;36m== %s ==\033[0m\n" "$1"; }
ok()   { printf "\033[1;32m  ✓ %s\033[0m\n" "$1"; }
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
# Otherwise `rm -rf $DEPLOY_DIR` would unlink this very script mid-run and bash
# could fail to read the rest — leaving the folder half-removed. Copying out first
# guarantees the checkout is deleted completely.
SELF="$(readlink -f "$0" 2>/dev/null || echo "$0")"
if [[ -z "${INFRADOCS_UNINSTALL_REEXEC:-}" && "$SELF" == "$DEPLOY_DIR"/* ]]; then
  _tmp="$(mktemp "${TMPDIR:-/tmp}/infradocs-uninstall.XXXXXX.sh")"
  cp "$SELF" "$_tmp"
  INFRADOCS_UNINSTALL_REEXEC=1 exec bash "$_tmp" "$@"
fi

# rm that falls back to sudo for root-owned paths (e.g. a root-created /data dir).
_rm_rf() {
  [[ -e "$1" || -L "$1" ]] || return 0
  rm -rf "$1" 2>/dev/null && [[ ! -e "$1" ]] && return 0
  if command -v sudo >/dev/null 2>&1; then sudo rm -rf "$1" 2>/dev/null; fi
  [[ ! -e "$1" ]] && return 0
  warn "could not fully remove $1 (permission or busy mount?)"
  return 1
}

# Package purge across apt / dnf / yum (best-effort, always via sudo).
_purge_pkgs() {
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get purge -y "$@" >/dev/null 2>&1 || true
    sudo apt-get autoremove -y >/dev/null 2>&1 || true
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf remove -y "$@" >/dev/null 2>&1 || true
  elif command -v yum >/dev/null 2>&1; then
    sudo yum remove -y "$@" >/dev/null 2>&1 || true
  else
    warn "no apt/dnf/yum found — remove these packages by hand: $*"
  fi
}

# docker CLI: prefer direct, fall back to sudo; empty if docker isn't installed.
DC=()
if command -v docker >/dev/null 2>&1; then
  if docker info >/dev/null 2>&1; then DC=(docker); else DC=(sudo docker); fi
fi

IMAGES_BUILT=(infradocs-api:latest infradocs-web:latest infradocs-api:poc)
IMAGES_BASE=(mongo:7 cloudflare/cloudflared:latest tailscale/tailscale:latest)
VOLUMES=(docker_mongo_data docker_caddy_data docker_tailscale_state)

# --- plan + confirm ------------------------------------------------------
step "InfraDocs uninstall — plan"
echo "  This will remove:"
if [[ ${#DC[@]} -gt 0 ]]; then
  echo "    • the Docker stack: containers, named volumes (incl. Mongo data), network"
  echo "    • built images: ${IMAGES_BUILT[*]}"
  [[ -n "$PURGE_IMAGES" ]] && echo "    • base images: ${IMAGES_BASE[*]}"
else
  warn "docker not found — skipping container/volume/image removal"
fi
[[ -z "$KEEP_DATA" ]] && echo "    • host data dir: $DATA_ROOT"
if [[ -z "$KEEP_REPO" ]]; then echo "    • the checkout: $DEPLOY_DIR"
elif [[ -z "$KEEP_CONFIG" ]]; then echo "    • saved config: $COMPOSE_DIR/.env (checkout kept)"; fi
if [[ -n "$REMOVE_DOCKER" ]]; then
  echo "    • the DOCKER ENGINE itself (package + /var/lib/docker, /etc/docker)  ⚠ affects ALL Docker on this host"
else
  echo "    • (Docker engine kept — pass --remove-docker / --all to purge it too)"
fi
[[ -n "$REMOVE_TAILSCALE" ]] && echo "    • the Tailscale package + its state  ⚠ affects this whole host" \
  || { command -v tailscale >/dev/null 2>&1 && echo "    • the Tailscale serve URL is reset (package kept)"; }
if [[ -z "$ASSUME_YES" ]]; then
  read -rp $'\n  Proceed? [y/N]: ' a
  [[ "$a" =~ ^[Yy] ]] || die "aborted — nothing was changed"
fi

# --- 1. stop + remove the Docker stack -----------------------------------
if [[ ${#DC[@]} -gt 0 ]]; then
  step "Stop + remove the Docker stack"
  if [[ -d "$COMPOSE_DIR" ]]; then
    ENVFILE=(); [[ -f "$COMPOSE_DIR/.env" ]] && ENVFILE=(--env-file .env)
    ( cd "$COMPOSE_DIR"
      ADMIN_PASSWORD="${ADMIN_PASSWORD:-uninstall}" \
        "${DC[@]}" compose "${ENVFILE[@]}" --profile cloudflare --profile tailscale \
          down -v --remove-orphans >/dev/null 2>&1
    ) && ok "compose stack stopped + removed (containers, volumes, network)" \
      || warn "compose down reported issues — sweeping leftovers by name next"
  else
    warn "no compose dir at $COMPOSE_DIR — sweeping by name/label instead"
  fi

  mapfile -t leftover < <(
    { "${DC[@]}" ps -aq --filter name=infradocs 2>/dev/null
      for img in "${IMAGES_BUILT[@]}"; do "${DC[@]}" ps -aq --filter ancestor="$img" 2>/dev/null; done
    } | sort -u | grep -v '^$' || true
  )
  if [[ ${#leftover[@]} -gt 0 ]]; then
    "${DC[@]}" rm -f "${leftover[@]}" >/dev/null 2>&1 || true
    ok "removed ${#leftover[@]} leftover container(s)"
  fi

  "${DC[@]}" volume rm -f "${VOLUMES[@]}" >/dev/null 2>&1 || true
  "${DC[@]}" rmi -f "${IMAGES_BUILT[@]}" >/dev/null 2>&1 || true
  [[ -n "$PURGE_IMAGES" ]] && { "${DC[@]}" rmi "${IMAGES_BASE[@]}" >/dev/null 2>&1 || true; }
  ok "removed built images + named volumes"
fi

# --- 2. Tailscale: reset serve, or remove the package entirely -----------
if command -v tailscale >/dev/null 2>&1; then
  if [[ -n "$REMOVE_TAILSCALE" ]]; then
    step "Remove Tailscale"
    sudo tailscale down >/dev/null 2>&1 || true
    sudo systemctl disable --now tailscaled >/dev/null 2>&1 || true
    _purge_pkgs tailscale
    _rm_rf /var/lib/tailscale || true; _rm_rf /var/cache/tailscale || true
    ok "tailscale package + state removed"
  else
    step "Reset Tailscale serve"
    sudo tailscale serve reset >/dev/null 2>&1 || true
    ok "tailscale serve reset (Tailscale itself untouched)"
  fi
fi

# --- 3. host data dir ----------------------------------------------------
if [[ -z "$KEEP_DATA" && ( -e "$DATA_ROOT" || -L "$DATA_ROOT" ) ]]; then
  step "Remove host data"
  _rm_rf "$DATA_ROOT" && ok "removed $DATA_ROOT"
fi

# --- 4. config / checkout ------------------------------------------------
if [[ -z "$KEEP_REPO" ]]; then
  if [[ -d "$DEPLOY_DIR" ]]; then
    step "Remove the checkout"
    cd /
    _rm_rf "$DEPLOY_DIR" && ok "removed $DEPLOY_DIR"
  fi
elif [[ -z "$KEEP_CONFIG" && -f "$COMPOSE_DIR/.env" ]]; then
  step "Remove saved config"
  _rm_rf "$COMPOSE_DIR/.env" && ok "removed $COMPOSE_DIR/.env"
fi

# --- 5. Docker engine (opt-in; LAST, since the stack teardown needed it) --
if [[ -n "$REMOVE_DOCKER" ]]; then
  step "Remove the Docker engine"
  sudo systemctl disable --now docker docker.socket containerd >/dev/null 2>&1 || true
  # Cover both the get.docker.com (docker-ce…) and distro (docker.io) package sets.
  _purge_pkgs docker-ce docker-ce-cli containerd.io docker-buildx-plugin \
              docker-compose-plugin docker-ce-rootless-extras docker.io docker-doc \
              docker-compose podman-docker
  _rm_rf /var/lib/docker || true; _rm_rf /var/lib/containerd || true; _rm_rf /etc/docker || true
  _rm_rf /var/run/docker.sock || true
  sudo groupdel docker >/dev/null 2>&1 || true
  ok "docker engine + data removed (/var/lib/docker, /etc/docker)"
fi

# --- 6. verify: no orphans left ------------------------------------------
step "Verify"
remaining=0
if command -v docker >/dev/null 2>&1 && [[ -z "$REMOVE_DOCKER" ]]; then
  DCV=(docker); docker info >/dev/null 2>&1 || DCV=(sudo docker)
  c=$("${DCV[@]}" ps -aq --filter name=infradocs 2>/dev/null | grep -c . || true)
  i=$("${DCV[@]}" images -q infradocs-api infradocs-web 2>/dev/null | grep -c . || true)
  v=$("${DCV[@]}" volume ls -q 2>/dev/null | grep -Ec 'docker_(mongo_data|caddy_data|tailscale_state)$' || true)
  [[ "$c" != 0 ]] && { warn "$c InfraDocs container(s) still present"; remaining=1; }
  [[ "$i" != 0 ]] && { warn "$i InfraDocs image(s) still present"; remaining=1; }
  [[ "$v" != 0 ]] && { warn "$v InfraDocs volume(s) still present"; remaining=1; }
elif [[ -n "$REMOVE_DOCKER" ]] && command -v docker >/dev/null 2>&1; then
  warn "docker command still on PATH after purge — remove leftover apt/dnf packages by hand"; remaining=1
fi
[[ -z "$KEEP_REPO" && -d "$DEPLOY_DIR" ]] && { warn "checkout still present: $DEPLOY_DIR"; remaining=1; }
[[ -z "$KEEP_DATA" && -e "$DATA_ROOT" ]] && { warn "host data still present: $DATA_ROOT"; remaining=1; }
if [[ "$remaining" == 0 ]]; then
  ok "clean — no InfraDocs assets remain"
  echo ""
  if [[ -n "$REMOVE_DOCKER" ]]; then
    echo "  InfraDocs is fully uninstalled, including the Docker engine."
  else
    echo "  InfraDocs is uninstalled. Docker was left installed (use --all to purge it too)."
  fi
else
  die "some assets could not be removed (see above) — re-run with sudo / --all, or remove by hand"
fi
