# Deploy

There are two ways to deploy InfraDocs. The **Docker product** is the supported, generic,
multi-server path. The **native systemd + nginx** scripts are how the original live instance
(`infra.ocialwaysfree.site`) runs and are kept for that legacy box.

---

## 1. Docker product (recommended)

A self-contained docker-compose stack — MongoDB + API + Caddy web — driven by an interactive
installer that ends at a browser-reachable setup wizard. Nothing host-specific is hardcoded;
you choose how the UI is exposed during the wizard.

```bash
git clone https://github.com/looking4manish/InfraDocs_V6.git
cd InfraDocs_V6/deploy/docker
./deploy.sh
```

`deploy.sh` builds the images, starts the stack, and prints the wizard URL (it will use a
Tailscale address or public IP when available, so you can reach it from a headless box over
SSH/Cockpit). Then:

1. Open the printed URL.
2. Log in with the seeded `admin` / `Changeme001` (you're forced to change the password).
3. Run the **setup wizard**: server name, role (standalone / primary / secondary), exposure
   mechanism, and optional AI labeling (endpoint / key / model).

Teardown is symmetric and clean:

```bash
./remove.sh
```

### What the stack looks like

- `deploy/docker/docker-compose.yml` — `mongo` + `api` + `web`.
- The **API container** runs with `network_mode: host` and `pid: host`, and mounts the host
  filesystem **read-only at `/host`** (env `INFRADOCS_HOST_ROOT=/host`). That's what lets the
  scanners see real containers, processes, listening ports, and config files. Inside the
  container, read host configs through `app/core/hostpath.py`, never `/etc/...` directly.
- The **web (Caddy) container** also runs on the host network and proxies to the API at
  `localhost:<API_PORT>` (default `:8090`). It runs on the host network deliberately: the
  OCI firewall drops docker-bridge → host traffic, so a bridged proxy couldn't reach the API.
- Optional `cloudflared` and `tailscale` sidecars (compose profiles) provide exposure when
  you don't have a public domain.
- Configuration is driven by `deploy/docker/.env` (created by `deploy.sh`):
  `INFRADOCS_SCAN_ROOTS`, ports, domain/exposure, etc.

### Exposure (you configure this — the product stays generic)

The wizard offers three mechanisms; pick one and wire it up yourself:

- **Domain + DNS:** the wizard detects your public IP and tells you which `A`-record to
  create; point your domain at it (Cloudflare-fronted is fine — terminate TLS at the edge).
  On a cloud VM, also open 80/443 in the security list/firewall.
- **Tailscale:** no domain needed — reachable on your tailnet (Funnel), one-time login link.
- **Cloudflare Tunnel:** paste a tunnel token; no inbound ports required.

### Multi-server

Install the product on each host. Make one host the **primary** in its wizard; on each other
host choose **secondary** and paste the primary URL + a join token minted on the primary
(`POST /api/federation/tokens`). Secondaries push their scans **outbound** to the primary —
no inbound port on the secondary. (Primary → secondary **command dispatch** is on the roadmap,
not yet shipped.)

---

## 2. Native systemd + nginx (legacy — the live OCI box)

This is how `infra.ocialwaysfree.site` runs today: a systemd unit runs the API and host
nginx static-serves the built frontend. The scripts in [`../deploy/`](../deploy/) were
authored for that Ubuntu box (wildcard Let's Encrypt cert at
`/etc/letsencrypt/live/ocialwaysfree.site/`); adapt user/paths/cert for another host.

> ⚠️ Host nginx serves `frontend/dist/` **live**. A bare `npx vite build` in the repo
> instantly changes production. Always build to a throwaway dir
> (`npx vite build --outDir /tmp/ifd-check`) when you only want to test compilation.

Files to read before running anything:

- `deploy/infradocs-v6-api.service` — systemd unit. Reads `.env`, runs `uvicorn` as `msinha`
  on `127.0.0.1:8004`. Change user/paths for your box.
- `deploy/infra.ocialwaysfree.site.conf` — nginx vhost. Serves `frontend/dist/`, proxies
  `/api/` → `:8004`, TLS on 443. Cert paths hardcode `/etc/letsencrypt/live/ocialwaysfree.site/`.
- `deploy/install_service.sh` / `deploy/install_nginx.sh` — installers (the nginx one runs
  `nginx -t` and rolls back the symlink on failure; touches no other site).
- `deploy/uninstall_service.sh` / `deploy/uninstall_nginx.sh` — symmetric clean removal.
- `deploy/sudoers.infradocs` — sudoers rules for the action dispatcher (systemd/nginx actions).

```bash
# 0. Populate .env (strong creds for prod)
$EDITOR .env

# 1. Build the frontend (to dist, since this box serves it live)
cd frontend && npm install && npm run build && cd ..

# 2. API service on :8004
deploy/install_service.sh

# 3. nginx vhost
deploy/install_nginx.sh

# 4. Verify
curl -sk https://infra.ocialwaysfree.site/api/health
```

Remove cleanly:

```bash
deploy/uninstall_nginx.sh
deploy/uninstall_service.sh
```

---

## Cutover plan (native → dockerized fleet)

The intended migration (not yet executed): archive the native InfraDocs folder + its nginx
config on OCI → fresh **dockerized primary** on OCI → onboard OCI-P and N150 as
**secondaries**. The user configures exposure (Cloudflare/nginx/DNS A-record) manually at
install time; keep the product generic. See [`CONTEXT_FOR_LLM.md`](../CONTEXT_FOR_LLM.md).
