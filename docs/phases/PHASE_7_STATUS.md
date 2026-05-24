# Phase 7 — Project/System linkage + Ports registry + Storage registry: STATUS

**Status:** Complete
**Date:** 2026-05-24
**Tests:** 38 new (12 correlator updated + 12 ports + 9 storage + 17 API/audit) → 89/89 cumulative

## Scope

Make the data model complete enough that the UI can show any view of any
asset without needing more scans. Specifically:

- **A.** Every asset must link to either a `~/projects/<name>` subfolder or
  the single `System` catch-all. No orphans, no third bucket, no
  `null` project fields.
- **B.** A first-class **ports registry** (hybrid model) that captures
  every port we have evidence of (listening, compose-declared, nginx
  upstream, systemd `--port` flag) with owner attribution and an
  on-demand live-probe endpoint.
- **C.** A first-class **storage registry** that unifies mounts, docker
  volumes, project trees, and bind mounts into one collection — each
  row back-linked to a project or System.
- **D.** Tests and docs.

Out of scope for Phase 7: any UI changes. Frontend continues to show
what it already shows; Phase 9 will surface the new collections.

## A. Ownership invariant

| Change | Where |
|---|---|
| Correlator pre-seeds one app per `~/projects/<name>` + a single `System` app, then routes every asset (containers, images, volumes, networks, nginx blocks, systemd units, ports, mounts) via a single `_route()` helper. | `app/correlator.py` |
| `_empty_app.type` simplified to `"project"` or `"system"`. Dropped `"compose"`, `"systemd"`, `"project_dir"`, `"standalone-container"`. | `app/correlator.py` |
| `_empty_app` now carries first-class `images` and `storage_mounts` lists in addition to the prior fields. | `app/correlator.py` |
| `ProjectDetector.get_project_from_container` extended with `bind_mounts` and `container_name` fallbacks — so a container launched via `docker run` (no compose label, working_dir not a host path) still attributes when its bind mounts live under `~/projects/<X>` or its name exactly matches a project folder. | `app/core/project_detector.py` |
| Docker scanner passes bind-mount sources + container name into the detector; volumes inherit project from any using container. | `app/scanners/docker.py` |
| Agent runs `audit_ownership()` after every scan; reports missing/unknown project counts, writes them to the scan log, and surfaces them in the `--summary` output. | `app/agent.py` |

Validated against live OCI: **258 assets, 0 missing, 0 unknown**, 8
application docs (7 project folders + System).

## B. Ports registry (hybrid model)

| Component | Purpose |
|---|---|
| `app/ports_registry.py::build_ports_registry()` | Walks the asset stream once; collapses (port, proto) into one row each; stacks evidence sources. |
| `app/ports_registry.py::probe()` | Live `ss` snapshot for an arbitrary range; not persisted. Pads with `state="free"` rows so the caller sees a complete range view. |
| `db.replace_ports()` / `db.get_ports()` | Mongo collection `ports`, unique on `port_id`, indexed on port/owner_project/state. |
| `GET /api/ports/` | Filters: `state`, `project`, `port_min`, `port_max`. |
| `GET /api/ports/summary` | Counts by state + by owner. |
| `GET /api/ports/probe?range=X-Y&proto=tcp\|udp` | On-demand probe; cap 5000 ports/call. |

Each row schema:

```jsonc
{
  "port_id": "oci:port:tcp:3000",
  "port": 3000,
  "protocol": "tcp",
  "state": "in_use",            // or "declared"
  "process": "python",          // when state=in_use
  "pid": 1604714,
  "local_address": "0.0.0.0:3000",
  "owner_project": "openwebui",
  "owner_app_id": "oci:app:openwebui",
  "evidence_sources": [
    {"kind": "listening", "source": "python"},
    {"kind": "container", "source": "openwebui:8080/tcp"},
    {"kind": "nginx_upstream", "source": "chat.ocialwaysfree.site"}
  ]
}
```

Evidence kinds: `listening` (ss), `container` (compose port mapping),
`nginx_upstream` (proxy_pass), `nginx_listen` (vhost listen directive),
`systemd_exec` (--port flag in ExecStart).

**Bug caught and fixed during build:** the original systemd port parser
regex `(?:--port[= ]|:)(\d{2,5})\b` matched timestamp fragments out of
systemctl-show's rendering (`start_time=[Sun 2026-05-24 16:07:36 UTC]`
→ phantom ports 7, 36, 16). Tightened to `--port`/`-p` only; pinned by
`test_systemd_regex_does_not_match_timestamps`. Live OCI registry
shrank from 40 phantom rows to 23 real ones.

**Live OCI registry:** 23 rows — 22 in_use + 1 declared.

| Owner | Ports |
|---|---|
| InfraDocs_V6 | 8004 (API) + 1 |
| OCI_Dashboard | 8000, 8001 |
| raveuploader_rws | 8010 |
| System | 18 (22 SSH, 53 DNS, 80, 443, 111 RPC, etc.) |

## C. Storage registry

| Component | Purpose |
|---|---|
| Storage scanner now also runs `df -B1` to capture `size_bytes` / `total_bytes` / `used_bytes` / `free_bytes` alongside the human-readable "12G" strings. | `app/scanners/storage.py` |
| `app/storage_registry.py::build_storage_registry()` | Produces one row per (kind, name) across four kinds. |
| `db.replace_storage()` / `db.get_storage()` | Mongo collection `storage`, unique on `storage_id`. |
| `GET /api/storage/` | Filters: `kind`, `project`. |
| `GET /api/storage/summary` | Counts and bytes-totals by kind + by owner. |

Kinds:

- `mount` — every df-listed filesystem (skips tmpfs/devtmpfs/snap/...).
- `docker_volume` — named volumes with `du`-walked size.
- `project_tree` — one row per `~/projects/<name>`, sized by `du`.
- `bind_mount` — every container bind source, attributed by
  path-under-projects-root first, then by using-container's app.

Each row schema:

```jsonc
{
  "storage_id": "oci:storage:mount:/",
  "kind": "mount",
  "name": "/",
  "path": "/",
  "owner_project": "System",
  "owner_app_id": "oci:app:System",
  "size_bytes": 32874823680,
  "total_bytes": 186020495360,
  "used_bytes": 32874823680,
  "free_bytes": 153145671680,
  "fstype": "ext4",
  "device": "/dev/sda1",
  "usage_percent": 18,
  "evidence_sources": [{"kind": "df", "source": "/"}]
}
```

**Live OCI registry:** 14 entities. Highlights:

| Owner | Total bytes | Detail |
|---|---|---|
| System | ~35.3 GB | 4 mounts (/, /boot, /boot/efi, efivars) |
| openwebui | ~4.4 GB | project_tree + 1 bind_mount |
| RaveUploader | ~461 MB | project_tree |
| InfraDocs_V6 | ~223 MB | project_tree |
| OCI_Dashboard | ~114 MB | project_tree |
| raveuploader_rws | ~108 MB | project_tree |
| carp | ~505 KB | project_tree |
| claude | 0 | project_tree (empty) |

## D. Tests

| File | Coverage |
|---|---|
| `tests/test_phase5_correlator.py` | 12 tests updated to assert the new ownership invariant — System bucket always present, type is "project"/"system", no standalone-container apps. All still pass plus the live-OCI integration test. |
| `tests/test_phase7_ports.py` | 12 unit tests covering each evidence source, dedup, owner fallback, the timestamp-false-positive regression, and probe smoke tests. |
| `tests/test_phase7_storage.py` | 9 unit tests covering each kind, path-based vs container-based attribution, unknown project fallback, storage_id uniqueness. |
| `tests/test_phase7_api.py` | 17 API-level tests using TestClient + dependency override (matches Phase 3 pattern). Covers list/filter/summary/probe for ports and storage + the three `audit_ownership()` branches. |

Cumulative: **89/89 passing**.

## To activate against live OCI

This is the only manual step left:

```bash
sudo systemctl restart infradocs-v6-api.service
```

…so the running API picks up the new `ports` and `storage` routers.
The scan agent's next run will populate both collections automatically;
or trigger one now:

```bash
source venv/bin/activate
python -m app.agent scan --summary
# or via the API:
curl -X POST -u msinha:msinha123 http://127.0.0.1:8004/api/scans/trigger
```

## Decisions worth remembering

- **No standalone-container apps.** A container running on the box but
  not living under a `~/projects/<X>` folder (no compose label, no
  bind-mount inside projects_root, no name match) now lands in the
  System bucket rather than getting its own app. Discoverable via
  `GET /api/applications/System` → `containers[]`.
- **Empty project folders still appear.** `~/projects/claude` and
  `~/projects/RaveUploader` had no live assets to attach but still
  show up as application docs (with `components_count: 0`). The
  dashboard sees the complete project list, not just the active ones.
- **Hybrid ports model.** Registry stores only evidence-based rows;
  live arbitrary-range queries go through `/api/ports/probe` which
  doesn't write to DB.
- **`type` field on applications changed.** Old values
  (`compose`, `systemd`, `project_dir`, `standalone-container`,
  `compose-implied`) collapsed to `"project"` or `"system"`. If any
  external consumer was reading the old types, it will need to update.
  Within the repo nothing else read this field, so the change is
  contained.

## Next: Phase 8 — Operational controls

Container/service start/stop/restart/logs at both asset and application
level. The hard part (data model) is now done; Phase 8 layers action
endpoints on top.
