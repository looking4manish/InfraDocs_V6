# Phase 6 — Nginx exposure: STATUS

**Status:** Complete — V6 is live on the internet.
**Date:** 2026-05-23
**URL:** https://infra.ocialwaysfree.site/

## Scope

Expose the V6 frontend + API to the internet via nginx, **without disturbing any existing site config**. Add a proper systemd unit so the API isn't running as a stray `nohup` process. Provide symmetric uninstall scripts so removal leaves nothing orphaned.

## What got installed

| File | Path on box | Purpose |
|---|---|---|
| `infra.ocialwaysfree.site.conf` | `/etc/nginx/sites-available/infra.ocialwaysfree.site` (+ symlink in `sites-enabled/`) | nginx vhost: 80→443 redirect, 443 serves `frontend/dist/` static + proxies `/api/*` to `127.0.0.1:8004` |
| `infradocs-v6-api.service` | `/etc/systemd/system/infradocs-v6-api.service` | systemd unit running `uvicorn app.api.main:app` under user `msinha`. `Restart=on-failure`, enabled at boot. |

Both files live canonically in `deploy/` inside the repo; the install scripts (`install_nginx.sh`, `install_service.sh`) copy them into place. **All four scripts use sudo and never write blindly** — backups before overwriting, `nginx -t` before reload, rollback if validation fails.

## Existing sites left alone

Pre-existing `sites-enabled/`: `chat`, `home`, `dashboard`, `rws`. All four were untouched. Live verification post-install:

```
chat:       200
home:       200
dashboard:  502   (pre-existing — proxies to :3100 which isn't listening; not caused by V6)
rws:        200
infra:      200   (new)
```

The `dashboard` 502 was diagnosed and confirmed pre-existing — its backend on ports 3100/8080 was already not running before any Phase 6 changes.

## SSL / Cloudflare

- Used the existing wildcard cert `/etc/letsencrypt/live/ocialwaysfree.site/fullchain.pem` (SAN `*.ocialwaysfree.site`). No new cert issuance needed.
- `infra.ocialwaysfree.site` DNS resolves to `104.21.95.155` (Cloudflare) — so traffic flows: client → CF edge → OCI box. CF terminates SSL at the edge then re-encrypts to origin.
- Origin cert is the wildcard LE cert, which covers the connection.

## systemd unit details

- Reads `INFRADOCS_MONGO_URI` (and `INFRADOCS_API_PASSWORD` if set) from `EnvironmentFile=/home/msinha/projects/InfraDocs_V6/.env`. `.env` is gitignored; production deploys must populate it before `install_service.sh`.
- Stdout/stderr append to `logs/api.service.log`.
- `Type=exec`, `Restart=on-failure`, `NoNewPrivileges=true`, `PrivateTmp=true`.
- Status post-install: `active (running)` from PID 1119582, memory 51 MB.

## End-to-end verification

```bash
$ curl -o /dev/null -w "%{http_code}\n" http://infra.ocialwaysfree.site/
301
$ curl -o /dev/null -w "%{http_code}\n" https://infra.ocialwaysfree.site/
200
$ curl -s https://infra.ocialwaysfree.site/api/health
{"status":"ok","mongo":{"ok":true}}
$ curl -s -u msinha:msinha123 https://infra.ocialwaysfree.site/api/applications/list \
    | jq '.applications[].name'
"InfraDocs_V6"
"OCI_Dashboard"
"openwebui"
"raveuploader_rws"
```

After a rescan, the `InfraDocs_V6` application document correctly cross-links its own new infrastructure:

```jsonc
{
  "name": "InfraDocs_V6",
  "systemd_units": ["infradocs-v6-api.service"],
  "nginx_sites": ["infra.ocialwaysfree.site"],
  "urls": ["https://infra.ocialwaysfree.site"],
  "listening_ports": [5173, 8004],
  "internet_exposed": true,
  "components_count": 2
}
```

— the scanner picked up the systemd unit we just installed, the correlator linked it to the nginx vhost we just installed, and the URL is now live on the public internet. The application-centric model from Phase 5 just demonstrated itself on a real change.

## Clean removal

Symmetric uninstall scripts so you can wipe V6's footprint without leftovers:

```bash
deploy/uninstall_service.sh   # stop + disable + remove systemd unit
deploy/uninstall_nginx.sh     # remove vhost from sites-enabled + sites-available, reload nginx
```

`nginx -t` is run after removal too, so a broken config aborts before reload.

## Notes for later phases

- The vite dev server (port 5173) is still running from Phase 4 testing. It's harmless but unnecessary now that nginx serves `frontend/dist/`. Will retire it in Phase 8 polish.
- Frontend build is **manual right now** — `npm run build` produces `frontend/dist/`. A `deploy/build.sh` that calls `npm run build` + restarts the API would be a nice-to-have for Phase 8.
- API uses `dev_password` from config because `.env`'s `INFRADOCS_API_PASSWORD` is empty. For real production, generate a strong password and put it in `.env`. The systemd unit will pick it up on next restart.

## Next: Phase 7 — Operational controls

Container/service start/stop/restart/logs endpoints + UI buttons. Now that the API runs under a stable systemd unit and the data model is application-centric, operational actions can target either individual assets ("restart the openwebui container") or whole applications ("restart everything in the Immich app").
