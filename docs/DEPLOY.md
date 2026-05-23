# Production deploy

The scripts in [`../deploy/`](../deploy/) install a systemd unit for the API and an nginx vhost that static-serves the built frontend. They were authored for a specific Ubuntu box (OCI Cloud VM with a wildcard Let's Encrypt cert at `/etc/letsencrypt/live/ocialwaysfree.site/`) but the patterns are straightforward to adapt.

## Read these before running anything

- `deploy/infradocs-v6-api.service` — the systemd unit. Reads `.env` from the repo root. Runs `uvicorn` as user `msinha`. Change the user/paths if your box differs.
- `deploy/infra.ocialwaysfree.site.conf` — the nginx vhost. Listens on 80 (→ 301 to 443) and 443. SSL cert paths hard-code `/etc/letsencrypt/live/ocialwaysfree.site/`. Change to your own cert location.
- `deploy/install_nginx.sh` — copies the vhost into `/etc/nginx/sites-available/`, symlinks it into `sites-enabled/`, runs `nginx -t`, reloads on success. Rolls back the symlink if validation fails. **Does not touch any other site config.**
- `deploy/install_service.sh` — installs the systemd unit, enables it at boot, starts it, smoke-checks `/api/health`. Kills any stray `uvicorn` first so two processes don't fight for `:8004`.
- `deploy/uninstall_nginx.sh`, `deploy/uninstall_service.sh` — symmetric removal. Pulled the vhost/symlink/unit, ran `nginx -t` / `daemon-reload`, no leftovers.

## Step by step

```bash
# 0. Have a populated .env (with a strong INFRADOCS_API_PASSWORD for prod!)
$EDITOR .env

# 1. Build the frontend
cd frontend
npm install
npm run build      # outputs to frontend/dist/
cd ..

# 2. Install the systemd unit (starts the API on :8004)
deploy/install_service.sh

# 3. Install the nginx vhost (serves frontend/dist + proxies /api/)
deploy/install_nginx.sh

# 4. Verify
curl -sk https://infra.ocialwaysfree.site/api/health
```

## To remove cleanly

```bash
deploy/uninstall_nginx.sh
deploy/uninstall_service.sh
```

Other nginx sites are untouched, the systemd unit is fully removed, no orphan files left behind.

## Cert / DNS notes

- The reference vhost uses a wildcard LE cert (`*.ocialwaysfree.site`). If you don't have a wildcard, swap in a per-host cert (`/etc/letsencrypt/live/<your-host>/`) or run `certbot --nginx -d <your-host>` first.
- DNS: the host needs an A/AAAA record (or Cloudflare CNAME) pointing at your machine. The reference setup uses Cloudflare with the `*.ocialwaysfree.site` zone — Cloudflare terminates SSL at the edge and re-encrypts to origin.

## Hardening checklist (not done yet, Phase 8)

- Change `dev_password` in `config.yml` and set a strong `INFRADOCS_API_PASSWORD` in `.env`.
- Tighten the systemd unit's sandboxing (`ProtectSystem=strict`, `ProtectHome=read-only` after confirming the agent still works).
- Tighten the nginx CORS — V6 currently sends `Access-Control-Allow-Origin: *` (gated by auth, but still loose).
- Add log rotation for `logs/api.service.log`.
- Consider running the API behind a forwardauth / OIDC proxy if you want SSO instead of HTTP Basic.
