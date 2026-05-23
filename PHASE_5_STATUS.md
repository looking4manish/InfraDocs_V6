# Phase 5 — Scanner enrichment + Application correlation: STATUS

**Status:** Complete
**Date:** 2026-05-23
**Tests:** 12 new (correlator) + 51 cumulative, all passing

## Scope

Pivot from the asset-per-category model to an **application-centric view**: one document per running thing that aggregates everything you'd need to inspect or decommission it — containers, compose file, nginx sites, exposed URLs, port mappings, volumes, on-disk paths and sizes, systemd units, env-var keys.

## What was enriched per scanner

| Scanner | New fields |
|---|---|
| docker (container) | `host_ports` (sorted set of ints), `bind_mount_sources`, `volume_names`, `networks`, `compose_project` / `compose_service` / `compose_working_dir` / `compose_config_files` (from labels), `cmd`, `entrypoint`, `working_dir`, `env_keys` (names only — values dropped to avoid leaking secrets), `restart_policy`, `healthcheck_defined`, `healthcheck_test` |
| docker (volume) | `mountpoint`, `size_bytes` (du-walked), `compose_project` |
| systemd | `exec_start`, `working_directory`, `user`, `group`, `restart`, `unit_file_state`, `description`, `drop_in_paths`, `environment_keys`, `environment_files`. Project resolution now also tries `WorkingDirectory` then `ExecStart` path (catches services whose unit is in `/etc/systemd/system/` but binary lives in a project dir) |
| nginx | `listen_ports` (ints), `upstream_host` / `upstream_port` (parsed), `ssl_issuer`, `ssl_not_after`, `cloudflare_origin`, `internet_exposed`, `url` |
| compose / port / storage | unchanged structurally; correlator pulls from existing fields |

## Correlator (`app/correlator.py`)

11-pass algorithm that joins flat assets into application docs:

```
Pass 1: Seed apps from docker_compose assets (one app per compose dir).
Pass 2: Seed apps from project-tagged systemd_service units.
Pass 3: Seed stub apps for any other non-System project tag.
Pass 4: Attach containers, populate host_port → app index, capture env keys.
Pass 4b: Extend host_port index from project-tagged listening ports
        (so non-Docker apps like OCI_Dashboard catch their nginx via upstream port).
Pass 5: Attach docker volumes via compose label or project tag.
Pass 6: Attach docker networks.
Pass 7: Attach nginx server blocks:
        (a) upstream_port → host_port_to_app (strongest)
        (b) fallback: subdomain → project via existing DOMAIN_MAPPING.
        Propagate internet_exposed / cloudflare flags up to the app.
Pass 8: Attach systemd services + timers by project tag.
Pass 9: Attach listening ports (via host_port match or process project tag).
Pass 10: du the project dir under projects_root/<app>.
Pass 11: Aggregate total_size_bytes, dedup list fields, compute components_count.
```

Output document shape (one per app):

```jsonc
{
  "application_id": "oci:app:openwebui",
  "name": "openwebui",
  "type": "compose" | "systemd" | "project_dir" | "standalone-container" | "compose-implied",
  "source": "/home/msinha/projects/openwebui/docker-compose.yml",
  "containers": ["openwebui"],
  "compose_file": "...",
  "systemd_units": [],
  "nginx_sites": ["chat.ocialwaysfree.site"],
  "urls": ["https://chat.ocialwaysfree.site"],
  "port_mappings": [{"host_port": 3000, "container": "openwebui", "container_port": "8080/tcp"}],
  "listening_ports": [3000],
  "volumes": [{"name": "...", "mountpoint": "...", "size_bytes": ...}],
  "networks": ["bridge"],
  "storage_paths": ["/home/msinha/projects/openwebui", "/home/msinha/projects/openwebui/data"],
  "project_dir": "/home/msinha/projects/openwebui",
  "project_dir_size_bytes": 2206212096,
  "total_size_bytes": 2206212096,
  "internet_exposed": true,
  "cloudflare": false,
  "env_keys": ["PATH", "OPENAI_API_KEY", "WEBUI_AUTH", ...],
  "components_count": 2
}
```

## Real OCI output (4 applications detected)

```
openwebui          (compose)   2 components   internet=True
  container: openwebui
  compose file: /home/msinha/projects/openwebui/docker-compose.yml
  nginx: chat.ocialwaysfree.site -> https://chat.ocialwaysfree.site
  port map: container 8080/tcp -> host 3000
  storage: project dir + /data subdir, 2.1 GB total
  env_keys: 34 (PATH, OLLAMA_BASE_URL, etc — values redacted)

OCI_Dashboard      (systemd)   4 components   internet=True
  systemd units: OCI_Dashboard.service, mapup-demo.service
  nginx: dashboard.ocialwaysfree.site, home.ocialwaysfree.site  ← both linked via shared port 8001
  urls: https://dashboard.ocialwaysfree.site, https://home.ocialwaysfree.site
  listening: 8000, 8001
  storage: /home/msinha/projects/OCI_Dashboard, 109 MB

raveuploader_rws   (systemd)   2 components   internet=True
  systemd unit: raveuploader_rws.service
  nginx: rws.ocialwaysfree.site
  url: https://rws.ocialwaysfree.site
  listening: 8010
  storage: 103 MB

InfraDocs_V6       (project_dir) 0 components  internet=False
  listening: 5173 (vite), 8004 (api)
  storage: 223 MB
```

## API additions

- `GET /api/applications/list` — list all apps (filterable by `internet_exposed=true|false`)
- `GET /api/applications/{name}` — single application detail

## DB additions

- New `applications` collection, replace-pattern (wiped + rewritten on every scan so deletions propagate)
- Indexes on `name` (unique), `application_id` (unique), `internet_exposed`

## Bugs found & fixed during Phase 5

1. **systemd `WorkingDirectory=!/root` false-positive** — `!` is systemd's "ignore-errors" prefix on a relative path, not an absolute path. My new "fallback to WorkingDirectory" logic was treating `!/root` as relative-to-CWD and resolving it into `/home/msinha/projects/InfraDocs_V6/!/root`, tagging `emergency.service` as InfraDocs_V6. Fixed by requiring absolute paths (must start with `/`).
2. **Letsencrypt cert read PermissionError** — `_read_cert_info()` exists check threw on root-owned `/etc/letsencrypt/live/*/fullchain.pem`. Wrapped in try/except so the scanner returns empty cert info rather than crashing.
3. **port_mappings IPv4+IPv6 duplicates** — same `host_port:container_port` pair emitted twice (once per stack). Added dedup set keyed by `(host_port, container, container_port)`.
4. **Orphan nginx sites for non-Docker apps** — `home.ocialwaysfree.site` proxies to `localhost:8001` which is `OCI_Dashboard.service`. The host-port index only got populated from container port mappings, so the nginx pass couldn't link them. Added pass 4b that also indexes project-tagged listening ports.

## Sensitive data handling

- Container `Env` → only **key names** stored, values dropped entirely. Skipped per-key matching against `_PASSWORD/TOKEN/SECRET/KEY` regex because dropping all values is simpler and safer.
- Same treatment for systemd `Environment=` properties.
- `EnvironmentFiles=` paths captured (so the operator knows *which* file holds the secrets) but file contents never read.
- No process command-lines beyond the systemd `ExecStart` field. No `/proc/<pid>/environ` reads.

## Open items for later phases

- Cloudflare detection currently flags `False` for all real sites because the certs are root-only readable and `openssl x509` fails. Either: (a) run agent as root, (b) give the agent user a sudoers entry for `openssl x509 -noout -in /etc/letsencrypt/...`, or (c) use a Cloudflare API token. Deferring decision.
- The correlator wipes-and-rewrites the `applications` collection on every scan. Fine for now (it's small), but means we lose history. Could be turned into upsert if useful.
- Bind mount sources outside `projects_root` get du'd at correlation time, which can be slow if mounts point at large dirs (e.g., `/data/openwebui`). Currently 2 GB openwebui dir takes ~0.5s. Watch this if other apps grow large.

## Next: Phase 6 — Nginx exposure

Add `infra.ocialwaysfree.site` vhost serving the built React app + proxying `/api/*` to :8004. No disturbance to existing 4 configs. `nginx -t` before reload.
