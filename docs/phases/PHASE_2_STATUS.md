# Phase 2 — Scanners: STATUS

**Status:** Complete
**Date:** 2026-05-23
**Tests:** 23/23 passing (Phase 1 + Phase 2)

## Scope

Port V5's six scanners to V6 with a consistent interface, route every project-detection decision through `ProjectDetector`, fix the latent V5 bugs caught during the port, and ship an agent that orchestrates scanners and writes assets to MongoDB.

## Deliverables

| File | Purpose |
|---|---|
| `app/scanners/base.py` | `BaseScanner` abstract class, asset factory, error capture, `execute()` wrapper |
| `app/scanners/systemd.py` | `systemd_service` + `systemd_timer` discovery |
| `app/scanners/docker.py` | `docker_container/image/volume/network` discovery via docker SDK |
| `app/scanners/compose.py` | `docker_compose` files under `projects_root` with skip-list for noise dirs |
| `app/scanners/nginx.py` | `nginx_server_block` discovery with brace-aware parser |
| `app/scanners/port.py` | `network_port` discovery from `ss -tulpnH` |
| `app/scanners/storage.py` | `storage_mount` discovery from `df` |
| `app/scanners/registry.py` | Name → class registry consumed by the agent |
| `app/agent.py` | CLI entry point: `scan` (full / `--incremental`), `status` |
| `tests/test_phase2_scanners.py` | 10 integration tests against the real OCI host |
| `tests/conftest.py` | Loads `.env` before any test inspects environment |

## Real scan against OCI

```
✓ loaded 6 scanners: ['docker', 'compose', 'systemd', 'port', 'nginx', 'storage']
📊 scan complete in 9.75s
  scanners: 6
  assets discovered: 245
  assets written: 245
  status: success

📋 by category:
  • docker_compose: 1
  • docker_container: 1
  • docker_image: 5
  • docker_network: 1
  • docker_volume: 1
  • network_port: 27
  • nginx_server_block: 8
  • storage_mount: 4
  • systemd_service: 183
  • systemd_timer: 14

📋 by project:
  • System: 234
  • openwebui: 4
  • OCI_Dashboard: 4
  • raveuploader_rws: 3
```

DB row count after scan: **245** (matches "written" — no asset_id collisions).

## V5 bugs fixed during the port

1. **systemd_scanner broken super().__init__** — V5's `SystemdScanner.__init__` called `super().__init__(config, db_manager)` but `BaseScanner` expected `(server_id, config)`, silently writing the wrong server_id onto every asset. V6 has one consistent constructor signature across all scanners.
2. **nginx regex breaks on nested braces** — V5 used `server\s*\{([^}]+)\}` which matches up to the first `}`, so real configs with nested `location { ... }` blocks lose all data after the first closing brace. V6 uses a proper brace-balanced extractor. Test: `test_nginx_brace_aware_parsing`.
3. **port_scanner falls back to `process_name.title()`** — exact same false-project anti-pattern V5 fought elsewhere ("Cloud" project from `cloud-init.service`). V6 reads `/proc/<pid>/cwd` and runs it through `ProjectDetector`, so a port only gets a project name if its process actually runs from inside a project dir. Test: `test_port_scanner_no_false_projects_from_process_name`.
4. **compose_scanner used `.title()` on dir names** — `openwebui` became "Openwebui". V6 uses `ProjectDetector.get_project_from_path()`, preserving real dir-name casing.
5. **NginxScanner had its own DOMAIN_PROJECT_MAP** divergent from `ProjectDetector.DOMAIN_MAPPING`. Removed; nginx now uses ProjectDetector exclusively.
6. **rglob over `projects_root` traversed `node_modules/.git/venv`** in V5's compose scanner. V6 uses an explicit `iterdir` walker that skips `node_modules`, `venv`, `.venv`, `.git`, `dist`, `build`, `__pycache__`, and any dotdir.
7. **storage_scanner substring-matched `openwebui` in mount paths** — coincidental matches anywhere in the path produced false projects. V6 uses `ProjectDetector.get_project_from_path()` and skips snap mountpoints + tmpfs.

## Bugs found & fixed during Phase 2 testing

1. **Dual-stack port collision** — `asset_id = port:{proto}:{port}` collided when both `0.0.0.0:80` and `[::]:80` listened on the same port. Fixed by including `local_address` in the id (13 collisions eliminated).
2. **Nginx same-site HTTP+HTTPS collision** — a single config file commonly has two `server` blocks for the same `server_name` (one `listen 80` redirect, one `listen 443 ssl`). Fixed by including the listen port in the asset_id (4 collisions eliminated). DB count now matches written count exactly.

## Schema notes

- Every asset includes `server_id: "oci"` as a constant. When distributed scanning returns post-V6, no schema migration required.
- `asset_id` format: `{server_id}:{kind}:{unique_key}` (kind is scanner-specific; unique_key includes whatever's needed for distinctness — confirmed via dedupe pass).
- Each asset has `category`, `status`, `project`, `metadata`, `health_indicators`, `discovered_at`, `scanner`, plus `created_at` / `updated_at` injected by `DBManager`.

## Open items / notes

- Docker container project tagging missed the running container (`InfraDocs_V6` not in project counts). Reason: the running container has no compose label *and* its `WorkingDir` likely isn't a project dir. Either fine (it's noise) or the docker scanner could inspect mount sources — defer to Phase 5 or later.
- `agent.log` written under `logs/` for every run (gitignored).
- The OCI host shows 234 "System" assets vs 11 project-tagged. That's the expected ratio — most systemd services and storage mounts are genuinely system-level.

## Next: Phase 3 — API

FastAPI on :8004 with routers for assets, projects, and scans. Basic auth via `INFRADOCS_API_PASSWORD`. No `servers` router (single host).
