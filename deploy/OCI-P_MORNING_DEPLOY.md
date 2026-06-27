# OCI-P — morning deploy runbook (operator)

Stand up the InfraDocs V6 docker product on **OCI-P** as a federation **secondary**.
Pre-staged overnight: the repo is cloned at `~/infradocs-v6-deploy` (branch `main`,
commit `02355d0`). **Nothing was started.** OCI-P is the production MongoDB-rs primary +
MXH host, so every command below is scoped to InfraDocs only.

---

## ‼ Blocking prerequisite — do this FIRST (on OCI, not OCI-P)

A secondary is useless until the **primary** can receive it. The live OCI API
(`infra.ocialwaysfree.site`) is currently running **old code** — `/api/federation/*`
returns 404, so it cannot mint tokens or ingest pushes yet. Before deploying OCI-P:

1. On OCI, bring the primary onto current `main` and **restart its API** (this is the
   step the overnight agent was forbidden to do):
   ```bash
   cd /home/msinha/projects/InfraDocs_V6 && git checkout main && git pull --ff-only origin main
   cd frontend && npm install && npm run build && cd ..      # rebuilds the LIVE dist (served instantly)
   sudo systemctl restart infradocs-v6-api.service
   curl -sk https://infra.ocialwaysfree.site/api/federation/servers   # must NOT be 404 now
   ```
   ⚠ This restarts production and rebuilds the live frontend — do it deliberately, watch
   the site afterward. (Decide separately whether OCI should run native vs. the docker
   product per the cutover plan in docs/DEPLOY.md.)
2. On OCI, set its role to primary and mint a join token for OCI-P:
   ```bash
   curl -sk -u admin:'<password>' -X POST https://infra.ocialwaysfree.site/api/setup/complete \
        -H 'Content-Type: application/json' -d '{"server_name":"OCI","role":"primary","exposure":"domain"}'
   curl -sk -u admin:'<password>' -X POST https://infra.ocialwaysfree.site/api/federation/tokens \
        -H 'Content-Type: application/json' -d '{"server_id":"oci-p"}'
   # -> copy the returned "token"
   ```

## Pre-flight checklist (on OCI-P)

- [ ] Prereq above done; `…/api/federation/servers` on OCI returns 200 (not 404).
- [ ] You have the **join token** minted on OCI for `server_id=oci-p`.
- [ ] `docker ps` works without sudo; `docker compose version` ≥ v2.
- [ ] Ports free: `for p in 8090 8081 8443 27018; do ss -ltn | grep ":$p " && echo "$p BUSY"; done` (silent = free).
- [ ] Disk: `df -h /` (was 24 G free overnight).
- [ ] **Do not** touch `/data/mxh`, `/etc/letsencrypt/live/mhx.mdbdemo.in`, mongo `:27017`,
      nginx/Caddy/cloudflared. The InfraDocs mongo is `:27018` (separate from the rs `:27017`).

## 1. Configure + stand up the stack

```bash
cd ~/infradocs-v6-deploy/deploy/docker
cat > .env <<'ENV'
SERVER_ID=oci-p
SERVER_NAME=OCI-P
ADMIN_USER=admin
ADMIN_PASSWORD=Changeme001
PROJECTS_ROOT=/home/msinha/projects
DOMAIN=:8081
COMPOSE_PROFILES=
CF_TUNNEL_TOKEN=
TS_AUTHKEY=
WEB_PORT=8081
WEB_TLS_PORT=8443
API_PORT=8090
MONGO_PORT=27018
ENV
chmod 600 .env
docker compose --env-file .env up -d --build     # builds api+web images, starts mongo+api+web
# wait for health:
for _ in $(seq 1 40); do [ "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8090/api/health)" = 200 ] && { echo UP; break; }; sleep 2; done
docker compose --env-file .env ps
```

> The API container runs host-network + host-PID and mounts `/` read-only at `/host` and the
> docker socket — that's how it scans the host. It does **not** write to the rs `:27017`.

## 2. Configure OCI-P as a SECONDARY

Point it at the OCI primary and the token from the prereq:

```bash
curl -s -u admin:Changeme001 -X POST http://localhost:8090/api/setup/complete \
     -H 'Content-Type: application/json' \
     -d '{"server_name":"OCI-P","role":"secondary","exposure":"tailscale",
          "primary_url":"https://infra.ocialwaysfree.site","join_token":"<TOKEN_FROM_OCI>"}'
# verify it took:
curl -s -u admin:Changeme001 http://localhost:8090/api/setup/status   # role=secondary, setup_complete=true
# trigger one scan -> it should push outbound to the primary:
curl -s -u admin:Changeme001 -X POST http://localhost:8090/api/scans/trigger
# then on OCI: curl .../api/federation/servers  -> oci-p should appear with a last_seen
```

## 3. Install the poll timer — ⚠ ARCHITECTURE DECISION REQUIRED

`deploy/systemd/infradocs-fed-poll.timer` runs `…/venv/bin/python -m app.federation_agent
poll` on the **host**. A *docker* deploy has **no host venv**, so the committed unit will not
work as-is. Pick one (both are sound; the overnight agent did **not** improvise this for you):

**Option A (recommended) — run poll inside the API container via a drop-in override:**
```bash
sudo cp ~/infradocs-v6-deploy/deploy/systemd/infradocs-fed-poll.{service,timer} /etc/systemd/system/
sudo mkdir -p /etc/systemd/system/infradocs-fed-poll.service.d
CID_CMD="docker exec \$(cd /home/msinha/infradocs-v6-deploy/deploy/docker && docker compose -p infradocs ps -q api) python -m app.federation_agent poll"
sudo tee /etc/systemd/system/infradocs-fed-poll.service.d/docker.conf >/dev/null <<EOF
[Service]
# docker deploy: poll runs inside the api container (which has the code, the :27018
# settings, docker.sock + /run/systemd to act, and host net to reach the primary).
ExecStart=
ExecStart=/bin/sh -c '$CID_CMD'
User=
WorkingDirectory=
EnvironmentFile=
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now infradocs-fed-poll.timer
```
**Option B — a host venv** pointed at the container mongo: `python3 -m venv ~/ifd-venv &&
~/ifd-venv/bin/pip install -r ~/infradocs-v6-deploy/requirements.txt`, then edit the unit's
`WorkingDirectory`/`ExecStart`/`EnvironmentFile` to that venv with
`INFRADOCS_MONGO_URI=mongodb://localhost:27018/`. Heavier; only if you don't want docker-exec.

> This same decision applies to N150. It should be made once, then the chosen unit committed
> back to `deploy/systemd/` so the repo reflects how poll runs on a docker secondary.

## 4. Verify

```bash
systemctl list-timers --all | grep infradocs-fed       # poll timer registered, next run shown
journalctl -u infradocs-fed-poll.service -n 20 --no-pager   # a clean run logs: executed N command(s)
```

## Rollback / remove (clean, touches only InfraDocs)

```bash
sudo systemctl disable --now infradocs-fed-poll.timer 2>/dev/null || true
sudo rm -f /etc/systemd/system/infradocs-fed-poll.{service,timer}
sudo rm -rf /etc/systemd/system/infradocs-fed-poll.service.d
sudo systemctl daemon-reload
cd ~/infradocs-v6-deploy/deploy/docker && ./remove.sh    # or: docker compose --env-file .env down -v
```
Leaves OCI-P exactly as before (MXH / mongo rs / certs never touched).
