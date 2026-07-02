#!/usr/bin/env bash
#
# InfraDocs uninstaller — cleanly reverse everything install.sh set up, leaving no
# orphan assets. It stops + removes the Docker stack (containers, named volumes, the
# network, and the locally-built images), resets the Tailscale wizard URL, deletes the
# host data dir, and removes the checkout. Docker and Tailscale THEMSELVES are left
# installed. Re-runnable and safe if things are already partly gone.
#
#   bash ~/infradocs/uninstall.sh              # interactive — shows a plan, asks once
#   bash ~/infradocs/uninstall.sh --yes        # no prompt (for scripts)
#
# Flags:
#   -y, --yes         don't prompt for confirmation
#   --keep-repo       leave the checkout ($INFRADOCS_DIR) in place
#   --keep-config     keep deploy/docker/.env (only meaningful with --keep-repo)
#   --keep-data       leave the host data dir ($INFRADOCS_DATA_ROOT) in place
#   --purge-images    also remove the pulled base images (mongo, cloudflared, tailscale)
#
# Env: INFRADOCS_DIR (default $HOME/infradocs), INFRADOCS_DATA_ROOT (default /data/infradocs).
set -euo pipefail

DEPLOY_DIR="${INFRADOCS_DIR:-$HOME/infradocs}"
DATA_ROOT="${INFRADOCS_DATA_ROOT:-/data/infradocs}"
COMPOSE_DIR="$DEPLOY_DIR/deploy/docker"

ASSUME_YES=""; KEEP_REPO=""; KEEP_CONFIG=""; KEEP_DATA=""; PURGE_IMAGES=""
for arg in "$@"; do
  case "$arg" in
    -y|--yes)       ASSUME_YES=1 ;;
    --keep-repo)    KEEP_REPO=1 ;;
    --keep-config)  KEEP_CONFIG=1 ;;
    --keep-data)    KEEP_DATA=1 ;;
    --purge-images) PURGE_IMAGES=1 ;;
    -h|--help)      sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
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

# rm that falls back to sudo for root-owned paths (e.g. a root-created /data dir).
_rm_rf() {
  [[ -e "$1" || -L "$1" ]] || return 0
  rm -rf "$1" 2>/dev/null && return 0
  if command -v sudo >/dev/null 2>&1; then sudo rm -rf "$1" 2>/dev/null && return 0; fi
  warn "could not remove $1 (permission denied)"
  return 1
}

# docker CLI: prefer direct, fall back to sudo; empty if docker isn't installed.
DC=()
if command -v docker >/dev/null 2>&1; then
  if docker info >/dev/null 2>&1; then DC=(docker); else DC=(sudo docker); fi
fi

IMAGES_BUILT=(infradocs-api:latest infradocs-web:latest infradocs-api:poc)
IMAGES_BASE=(mongo:7 cloudflare/cloudflared:latest tailscale/tailscale:latest)
# Named volumes: compose project defaults to the compose-dir basename ("docker").
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
command -v tailscale >/dev/null 2>&1 && echo "    • the Tailscale serve URL (reset; Tailscale stays installed)"
[[ -z "$KEEP_DATA" ]] && echo "    • host data dir: $DATA_ROOT"
if [[ -z "$KEEP_REPO" ]]; then echo "    • the checkout: $DEPLOY_DIR"
elif [[ -z "$KEEP_CONFIG" ]]; then echo "    • saved config: $COMPOSE_DIR/.env (checkout kept)"; fi
echo "  Docker + Tailscale themselves are left installed."
if [[ -z "$ASSUME_YES" ]]; then
  read -rp $'\n  Proceed? [y/N]: ' a
  [[ "$a" =~ ^[Yy] ]] || die "aborted — nothing was changed"
fi

# --- 1. stop + remove the Docker stack -----------------------------------
if [[ ${#DC[@]} -gt 0 ]]; then
  step "Stop + remove the Docker stack"
  if [[ -d "$COMPOSE_DIR" ]]; then
    ENVFILE=(); [[ -f "$COMPOSE_DIR/.env" ]] && ENVFILE=(--env-file .env)
    # ADMIN_PASSWORD is a ${VAR:?} in the compose file; give it a value so `down`
    # can interpolate even when .env is already gone.
    ( cd "$COMPOSE_DIR"
      ADMIN_PASSWORD="${ADMIN_PASSWORD:-uninstall}" \
        "${DC[@]}" compose "${ENVFILE[@]}" --profile cloudflare --profile tailscale \
          down -v --remove-orphans >/dev/null 2>&1
    ) && ok "compose stack stopped + removed (containers, volumes, network)" \
      || warn "compose down reported issues — sweeping leftovers by name next"
  else
    warn "no compose dir at $COMPOSE_DIR — sweeping by name/label instead"
  fi

  # Orphan sweep: any container left over (compose metadata missing, renamed, …).
  mapfile -t leftover < <(
    { "${DC[@]}" ps -aq --filter name=infradocs 2>/dev/null
      for img in "${IMAGES_BUILT[@]}"; do "${DC[@]}" ps -aq --filter ancestor="$img" 2>/dev/null; done
    } | sort -u | grep -v '^$' || true
  )
  if [[ ${#leftover[@]} -gt 0 ]]; then
    "${DC[@]}" rm -f "${leftover[@]}" >/dev/null 2>&1 || true
    ok "removed ${#leftover[@]} leftover container(s)"
  fi

  # Named volumes (explicit — covers the case where compose couldn't enumerate them).
  "${DC[@]}" volume rm -f "${VOLUMES[@]}" >/dev/null 2>&1 || true
  # Built images are ours — always remove. `docker rmi` refuses images still in use
  # elsewhere, so base-image removal (opt-in) can't nuke a shared image.
  "${DC[@]}" rmi -f "${IMAGES_BUILT[@]}" >/dev/null 2>&1 || true
  [[ -n "$PURGE_IMAGES" ]] && { "${DC[@]}" rmi "${IMAGES_BASE[@]}" >/dev/null 2>&1 || true; }
  ok "removed built images + named volumes"
fi

# --- 2. reset the Tailscale wizard URL (best-effort) ---------------------
if command -v tailscale >/dev/null 2>&1; then
  step "Reset Tailscale serve"
  sudo tailscale serve reset >/dev/null 2>&1 || true
  ok "tailscale serve reset (Tailscale itself untouched)"
fi

# --- 3. host data dir ----------------------------------------------------
if [[ -z "$KEEP_DATA" && ( -e "$DATA_ROOT" || -L "$DATA_ROOT" ) ]]; then
  step "Remove host data"
  _rm_rf "$DATA_ROOT" && ok "removed $DATA_ROOT"
fi

# --- 4. config / checkout (LAST — this file lives inside the checkout) ---
if [[ -z "$KEEP_REPO" ]]; then
  if [[ -d "$DEPLOY_DIR" ]]; then
    step "Remove the checkout"
    # Deleting the running script's own file is safe on Linux: the open fd keeps the
    # inode alive until this process exits. cd out first so cwd isn't the target.
    cd /
    _rm_rf "$DEPLOY_DIR" && ok "removed $DEPLOY_DIR"
  fi
elif [[ -z "$KEEP_CONFIG" && -f "$COMPOSE_DIR/.env" ]]; then
  step "Remove saved config"
  _rm_rf "$COMPOSE_DIR/.env" && ok "removed $COMPOSE_DIR/.env"
fi

# --- 5. verify: no orphans left ------------------------------------------
step "Verify"
remaining=0
if [[ ${#DC[@]} -gt 0 ]]; then
  c=$("${DC[@]}" ps -aq --filter name=infradocs 2>/dev/null | grep -c . || true)
  i=$("${DC[@]}" images -q infradocs-api infradocs-web 2>/dev/null | grep -c . || true)
  v=$("${DC[@]}" volume ls -q 2>/dev/null | grep -Ec 'docker_(mongo_data|caddy_data|tailscale_state)$' || true)
  [[ "$c" != 0 ]] && { warn "$c InfraDocs container(s) still present"; remaining=1; }
  [[ "$i" != 0 ]] && { warn "$i InfraDocs image(s) still present"; remaining=1; }
  [[ "$v" != 0 ]] && { warn "$v InfraDocs volume(s) still present"; remaining=1; }
fi
[[ -z "$KEEP_REPO" && -d "$DEPLOY_DIR" ]] && { warn "checkout still present: $DEPLOY_DIR"; remaining=1; }
if [[ "$remaining" == 0 ]]; then
  ok "clean — no InfraDocs containers, images, volumes, data, or files remain"
  echo ""
  echo "  InfraDocs is fully uninstalled. Docker + Tailscale were left installed."
else
  warn "some assets could not be removed (see above) — re-run with sudo, or remove them by hand"
fi
