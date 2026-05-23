# Architecture

InfraDocs V6 has three layers.

```
┌──────────────────────────────────────────────────────────────────┐
│                     Frontend (React + Vite)                       │
│    Dark-theme SPA, polls API, shows applications & assets         │
└──────────────────────┬───────────────────────────────────────────┘
                       │ HTTP (Basic Auth)
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│                       API (FastAPI, :8004)                        │
│   /api/applications  /api/assets  /api/projects  /api/scans       │
│   /api/scans/trigger runs the agent in a BackgroundTask           │
└────────────────────┬─────────────────────────────────────────────┘
                     │           ▲
              read   │           │  upsert
                     ▼           │
┌──────────────────────────────────────────────────────────────────┐
│                          MongoDB                                  │
│        Collections: assets, applications, scan_logs               │
└────────────────────▲───────────────────────────────────────────▲─┘
                     │                                            │
            upsert   │                                  replace   │
                     │                                            │
┌──────────────────────────────────────────────────────────────────┐
│                       Agent (python -m app.agent scan)            │
│                                                                   │
│   ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌──────────┐   │
│   │  systemd   │  │   docker   │  │  compose   │  │  nginx   │   │
│   └────────────┘  └────────────┘  └────────────┘  └──────────┘   │
│   ┌────────────┐  ┌────────────┐                                  │
│   │    port    │  │  storage   │     ── flat assets ───▶          │
│   └────────────┘  └────────────┘                                  │
│                                                                   │
│   ┌─────────────────────────────────────────────────────────┐    │
│   │     correlator.py — 11 passes — application docs         │    │
│   └─────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
```

## The application-centric model (this is the load-bearing idea)

V5 stored every discovered thing as an "asset" with a `category` (`docker_container`, `nginx_server_block`, `systemd_service`, etc.). That's useful raw data but it scatters the picture: to understand "openwebui", you had to mentally re-join its container with its compose file, its nginx site, its mounted volume, its listening port, and its on-disk storage path.

V6 keeps the flat `assets` collection as raw output, **but adds an `applications` collection that joins everything an app owns** into one document. The correlator (`app/correlator.py`) builds these docs after every scan.

### How correlation links things

The correlator runs 11 deterministic passes. Linking strategies, strongest to weakest:

1. **Docker Compose project label** (`com.docker.compose.project`) on a container, volume, or network — strongest signal; all assets with the same label belong to the same app.
2. **Container's `WorkingDir`** under `/home/<user>/projects/<X>/` — second strongest.
3. **Systemd unit `FragmentPath`** or `WorkingDirectory` or `ExecStart` under a project dir — catches services whose unit file lives in `/etc/systemd/system/` but whose binary lives in a project dir.
4. **Nginx `proxy_pass http://localhost:8080`** → look up host port 8080 in the `host_port → app` index built from container port mappings *and* project-tagged listening ports. This is what links non-Docker apps (like a Python systemd service) to the nginx server block exposing them.
5. **Subdomain → project** via a small `DOMAIN_MAPPING` table in `ProjectDetector` (e.g. `chat.*` → `openwebui`).
6. **Process's `/proc/<pid>/cwd`** — used by the port scanner to tag listening ports.

An app's `application_id` is `{server_id}:app:{name}` for forward-compatibility with multi-host re-introduction. Today `server_id` is always `oci`; documents carry this constant so a future split into per-host server_ids doesn't require schema migration.

## Why the `project_detector` matters more than it looks

A long-standing trap in V5: scanners inferred project names from service-name prefixes (e.g. `cloud-init.service` → "Cloud" project). The result was a wall of false projects. V6's `project_detector` codifies one rule: **only paths under `/home/<user>/projects/<X>/` get a project name; everything else is `"System"`**. Service-name string-matching is explicitly off-limits.

Tests assert this regression doesn't come back (`test_project_detector_rejects_service_name_inference`, `test_port_scanner_no_false_projects_from_process_name`).

## What each scanner captures

| Scanner | Asset kind | Notable enriched fields |
|---|---|---|
| `systemd` | `systemd_service`, `systemd_timer` | `exec_start`, `working_directory`, `user`, `environment_keys` (names only), `restart`, `unit_file_state`, `drop_in_paths` |
| `docker` | `docker_container`, `docker_image`, `docker_volume`, `docker_network` | container: `host_ports`, `bind_mount_sources`, `env_keys`, `cmd`, `entrypoint`, `compose_*` labels, `restart_policy`, `healthcheck_*`; volume: `mountpoint` + walked `size_bytes` |
| `compose` | `docker_compose` | services list, file path, version |
| `nginx` | `nginx_server_block` | `listen_ports` (ints), `upstream_host`/`upstream_port` (parsed), SSL `issuer` + `not_after`, `cloudflare_origin`, `internet_exposed`, `url` |
| `port` | `network_port` | port, protocol, local_address, process name, PID |
| `storage` | `storage_mount` | size/used/avail, fstype, usage_percent |

## Why MongoDB

InfraDocs V5 used MongoDB and V6 inherited the choice. The model fits well: scanner output is loosely-typed and varies by category, application documents have a flat schema but optional/list-heavy fields. A relational schema would mostly mean a big EAV table or 10+ join tables for the same data.

V6 connects via a connection-string URI (replica-set capable) loaded from `INFRADOCS_MONGO_URI` in `.env`. The URI is never committed; `.env` is gitignored.

## Secrets handling

- Container `Env` values are dropped entirely — only key names are stored. This is to avoid stashing API tokens / DB passwords in the documentation database.
- Same for systemd `Environment=` values.
- `EnvironmentFiles=` paths are captured so the operator knows *where* the secrets live, but file contents are never read.
- The Mongo URI itself is the only secret the V6 process needs, and it's read from `.env` (gitignored) into `os.environ`.

## Test strategy

- **Unit tests** for `correlator.py` use synthetic asset fixtures. They cover every pass: compose seeding, compose-project label, upstream-port linking, domain-mapping fallback, systemd-only apps, volume linking, listening-port linking, dir-size accounting, propagation of `internet_exposed`/`cloudflare`.
- **Integration tests** drive the real Mongo + real scanners against the live OCI host. They assert that named apps (`openwebui`, `OCI_Dashboard`, `raveuploader_rws`) exist and have their cross-links populated.
- The frontend has no automated tests yet — that's a Phase 8 polish item.
