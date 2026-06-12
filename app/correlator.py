"""Application correlator.

Takes the flat `assets` collection (which the scanners produce) and joins
related assets into `application` documents.

**Ownership invariant (Phase 7):** every application is either
  - a project bucket — one per subdirectory of `projects_root`, OR
  - the single `System` bucket — everything that can't be tied to a project.

Every asset emitted by the scanners is routed to exactly one of those
buckets; nothing is silently dropped. The `System` app is therefore the
catch-all that surfaces docker images, host-level mounts, host-level
listening ports, and any container/service that doesn't live in a project
directory.

**V7 additions (Phase 1, additive):**
  - `links[]` — every pass records *why* it joined an asset to an app:
    {src_kind, src, dst_kind, dst, via, pass}. Evidence, not inference.
  - `containers_detail[]` / `nginx_detail[]` — denormalized component
    state so the UI renders topology from a single application fetch.
  - `hygiene{}` — dangling/unused images, orphaned volumes,
    exited-with-restart=always containers.
  - `resilience{}` — would this app survive a reboot?
All existing fields and their shapes are unchanged.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from app.scanners.docker import _dir_size_bytes

logger = logging.getLogger(__name__)


SYSTEM_BUCKET = "System"


def _empty_app(name: str, *, source: Optional[str], type_: str) -> Dict[str, Any]:
    """Empty application document. `type_` is "project" or "system"."""
    return {
        "name": name,
        "type": type_,
        "source": source,
        "containers": [],
        "images": [],
        "compose_file": None,
        "compose_files": [],
        "systemd_units": [],
        "nginx_sites": [],
        "urls": [],
        "port_mappings": [],
        "listening_ports": [],
        "volumes": [],
        "networks": [],
        "storage_paths": [],
        "storage_mounts": [],
        "project_dir": None,
        "project_dir_size_bytes": 0,
        "total_size_bytes": 0,
        "internet_exposed": False,
        "cloudflare": False,
        "env_keys": [],
        "components_count": 0,
        "links": [],
        "containers_detail": [],
        "nginx_detail": [],
        "hygiene": {
            "exited_restart_always": [],
            "dangling_images": [],
            "unused_images": [],
            "orphaned_volumes": [],
        },
        "resilience": {
            "reboot_safe": True,
            "issues": [],
        },
    }


def _group(assets: Iterable[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for a in assets:
        out[a["category"]].append(a)
    return out


def _project_dirs(projects_root: str) -> Set[str]:
    root = Path(projects_root)
    if not root.exists():
        return set()
    return {
        p.name
        for p in root.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    }


def _link(
    app: Dict[str, Any],
    src_kind: str,
    src: str,
    dst_kind: str,
    dst: str,
    via: str,
    pass_no: int,
) -> None:
    """Record linking evidence on the app document.

    Convention: links to the System bucket are NOT recorded — System is the
    absence of evidence, and an app-level `links == []` with assets present
    is itself the signal the UI surfaces ("no linking evidence found").
    Container→port links are the exception kind whose dst is not an app.
    """
    if dst_kind == "application" and dst == SYSTEM_BUCKET:
        return
    app["links"].append(
        {
            "src_kind": src_kind,
            "src": src,
            "dst_kind": dst_kind,
            "dst": dst,
            "via": via,
            "pass": pass_no,
        }
    )


def _restart_policy_name(rp: Any) -> Optional[str]:
    """Scanner may emit the policy as a string or a docker {"Name": ...} dict."""
    if isinstance(rp, dict):
        return rp.get("Name") or None
    if isinstance(rp, str):
        return rp or None
    return None


def correlate(
    assets: List[Dict[str, Any]],
    *,
    server_id: str,
    projects_root: str,
) -> List[Dict[str, Any]]:
    """Run correlation and return one app document per project + one System app."""
    by_cat = _group(assets)
    apps: Dict[str, Dict[str, Any]] = {}

    project_names = _project_dirs(projects_root)
    for pname in project_names:
        apps[pname] = _empty_app(
            pname,
            source=str(Path(projects_root) / pname),
            type_="project",
        )
    for a in assets:
        proj = a.get("project")
        if proj and proj != SYSTEM_BUCKET and proj not in apps:
            apps[proj] = _empty_app(proj, source=None, type_="project")
    apps[SYSTEM_BUCKET] = _empty_app(SYSTEM_BUCKET, source=None, type_="system")

    def _route(project_tag: str, compose_proj: Optional[str] = None) -> str:
        """Decide app name from (project_tag, compose_project). Falls back to System."""
        if compose_proj and compose_proj in apps and compose_proj != SYSTEM_BUCKET:
            return compose_proj
        if project_tag and project_tag in apps and project_tag != SYSTEM_BUCKET:
            return project_tag
        return SYSTEM_BUCKET

    # ---- Pass 1: compose files --------------------------------------------
    for compose in by_cat.get("docker_compose", []):
        path = compose["metadata"]["file_path"]
        compose_dir = Path(path).parent.name
        app_name = _route(compose["project"], compose_proj=compose_dir)
        app = apps[app_name]
        if app["compose_file"] is None:
            app["compose_file"] = path
        if path not in app["compose_files"]:
            app["compose_files"].append(path)
        _link(
            app, "docker_compose", path, "application", app_name,
            "compose_dir" if app_name == compose_dir else "project_tag", 1,
        )

    # ---- Pass 2: containers + host-port index -----------------------------
    host_port_to_app: Dict[int, str] = {}
    container_to_app: Dict[str, str] = {}

    for c in by_cat.get("docker_container", []):
        meta = c["metadata"]
        compose_proj = meta.get("compose_project")
        app_name = _route(c["project"], compose_proj=compose_proj)
        container_to_app[c["name"]] = app_name
        app = apps[app_name]
        app["containers"].append(c["name"])

        if compose_proj and app_name == compose_proj:
            via = "compose_label"
        else:
            via = "project_dir"
        _link(app, "docker_container", c["name"], "application", app_name, via, 2)

        rp_name = _restart_policy_name(meta.get("restart_policy"))
        app["containers_detail"].append(
            {
                "name": c["name"],
                "image": meta.get("image"),
                "running": bool(meta.get("running")),
                "restarts": meta.get("restarts", 0),
                "restart_policy": rp_name,
                "has_health_check": bool(
                    meta.get("has_health_check") or meta.get("healthcheck_defined")
                ),
                "started_at": meta.get("started_at"),
                "host_ports": meta.get("host_ports") or [],
                "compose_service": meta.get("compose_service"),
            }
        )

        if not meta.get("running") and rp_name in ("always", "unless-stopped"):
            app["hygiene"]["exited_restart_always"].append(c["name"])

        seen_mappings = {
            (pm["host_port"], pm["container"], pm["container_port"])
            for pm in app["port_mappings"]
        }
        for pm in meta.get("ports") or []:
            hp = pm.get("host_port")
            try:
                hp_int = int(hp) if hp is not None else None
            except (TypeError, ValueError):
                hp_int = None
            if hp_int is not None:
                host_port_to_app.setdefault(hp_int, app_name)
                key = (hp_int, c["name"], pm.get("container_port"))
                if key not in seen_mappings:
                    app["port_mappings"].append(
                        {
                            "host_port": hp_int,
                            "container": c["name"],
                            "container_port": pm.get("container_port"),
                        }
                    )
                    seen_mappings.add(key)
                _link(
                    app, "docker_container", c["name"],
                    "network_port", str(hp_int), "port_mapping", 2,
                )

        for src in meta.get("bind_mount_sources") or []:
            app["storage_paths"].append(src)
        for k in meta.get("env_keys") or []:
            if k not in app["env_keys"]:
                app["env_keys"].append(k)

    # Extend host_port index from project-tagged listening ports so nginx
    # can link to non-Docker apps (e.g. an OCI_Dashboard service on :8080).
    for p in by_cat.get("network_port", []):
        if p["project"] != SYSTEM_BUCKET and p["project"] in apps:
            port = p["metadata"].get("port")
            if isinstance(port, int):
                host_port_to_app.setdefault(port, p["project"])

    # ---- Pass 3: images attach to the apps whose containers use them ------
    image_to_apps: Dict[str, Set[str]] = defaultdict(set)
    for c in by_cat.get("docker_container", []):
        img = c["metadata"].get("image")
        if img:
            image_to_apps[img].add(container_to_app[c["name"]])

    for img in by_cat.get("docker_image", []):
        candidates: Set[str] = set()
        for tag in (img["metadata"].get("tags") or []) + [img["name"]]:
            candidates |= image_to_apps.get(tag, set())
        target_apps = candidates or {SYSTEM_BUCKET}
        for app_name in target_apps:
            if img["name"] not in apps[app_name]["images"]:
                apps[app_name]["images"].append(img["name"])
            if candidates:
                _link(
                    apps[app_name], "docker_image", img["name"],
                    "application", app_name, "image_tag", 3,
                )

        meta = img["metadata"]
        owner = sorted(target_apps)[0]
        if meta.get("is_dangling"):
            apps[owner]["hygiene"]["dangling_images"].append(img["name"])
        elif meta.get("in_use") is False:
            apps[owner]["hygiene"]["unused_images"].append(img["name"])

    # ---- Pass 4: volumes --------------------------------------------------
    for v in by_cat.get("docker_volume", []):
        meta = v["metadata"]
        compose_proj = meta.get("compose_project")
        app_name = _route(v["project"], compose_proj=compose_proj)
        apps[app_name]["volumes"].append(
            {
                "name": v["name"],
                "mountpoint": meta.get("mountpoint"),
                "size_bytes": meta.get("size_bytes", 0),
            }
        )
        _link(
            apps[app_name], "docker_volume", v["name"], "application", app_name,
            "compose_label" if compose_proj and app_name == compose_proj
            else "project_tag", 4,
        )
        if (v.get("health_indicators") or {}).get("in_use") is False:
            apps[app_name]["hygiene"]["orphaned_volumes"].append(v["name"])

    # ---- Pass 5: networks --------------------------------------------------
    for n in by_cat.get("docker_network", []):
        labels = n["metadata"].get("labels") or {}
        compose_proj = labels.get("com.docker.compose.project")
        app_name = _route(n["project"], compose_proj=compose_proj)
        apps[app_name]["networks"].append(n["name"])
        _link(
            apps[app_name], "docker_network", n["name"], "application", app_name,
            "compose_label" if compose_proj and app_name == compose_proj
            else "project_tag", 5,
        )

    # ---- Pass 6: nginx blocks ---------------------------------------------
    for ng in by_cat.get("nginx_server_block", []):
        meta = ng["metadata"]
        upstream_port = meta.get("upstream_port")
        if upstream_port and upstream_port in host_port_to_app:
            app_name = host_port_to_app[upstream_port]
            via = f"upstream_port:{upstream_port}"
        else:
            app_name = _route(ng["project"])
            via = "project_tag"
        app = apps[app_name]
        app["nginx_sites"].append(ng["name"])
        _link(app, "nginx_server_block", ng["name"], "application", app_name, via, 6)
        app["nginx_detail"].append(
            {
                "server_name": ng["name"],
                "config_file": meta.get("config_file"),
                "listen_ports": meta.get("listen_ports") or [],
                "upstream_host": meta.get("upstream_host"),
                "upstream_port": upstream_port,
                "has_ssl": bool(meta.get("has_ssl")),
                "ssl_issuer": meta.get("ssl_issuer"),
                "ssl_not_after": meta.get("ssl_not_after"),
                "cloudflare_origin": bool(meta.get("cloudflare_origin")),
                "internet_exposed": bool(meta.get("internet_exposed")),
                "url": meta.get("url"),
            }
        )
        url = meta.get("url")
        if url and url not in app["urls"]:
            app["urls"].append(url)
        if meta.get("internet_exposed"):
            app["internet_exposed"] = True
        if meta.get("cloudflare_origin"):
            app["cloudflare"] = True

    # ---- Pass 7: systemd services + timers --------------------------------
    for s in by_cat.get("systemd_service", []) + by_cat.get("systemd_timer", []):
        app_name = _route(s["project"])
        apps[app_name]["systemd_units"].append(s["name"])
        _link(
            apps[app_name], s["category"], s["name"],
            "application", app_name, "unit_path", 7,
        )
        unit_state = s["metadata"].get("unit_file_state")
        if (
            app_name != SYSTEM_BUCKET
            and unit_state
            and unit_state not in ("enabled", "enabled-runtime", "static")
        ):
            apps[app_name]["resilience"]["issues"].append(
                f"unit {s['name']} is {unit_state} (won't start on boot)"
            )
        for k in s["metadata"].get("environment_keys") or []:
            if k not in apps[app_name]["env_keys"]:
                apps[app_name]["env_keys"].append(k)

    # ---- Pass 8: listening ports ------------------------------------------
    for p in by_cat.get("network_port", []):
        port = p["metadata"].get("port")
        if not isinstance(port, int):
            continue
        if port in host_port_to_app:
            app_name = host_port_to_app[port]
            via = "host_port_index"
        else:
            app_name = _route(p["project"])
            via = "process_cwd"
        if port not in apps[app_name]["listening_ports"]:
            apps[app_name]["listening_ports"].append(port)
        _link(
            apps[app_name], "network_port", str(port),
            "application", app_name, via, 8,
        )

    # ---- Pass 9: storage mounts -------------------------------------------
    for m in by_cat.get("storage_mount", []):
        app_name = _route(m["project"])
        apps[app_name]["storage_mounts"].append(m["name"])
        _link(
            apps[app_name], "storage_mount", m["name"],
            "application", app_name, "project_tag", 9,
        )

    # ---- Pass 10: project_dir size for project apps -----------------------
    for app_name, app in apps.items():
        if app["type"] != "project":
            continue
        proj_dir = Path(projects_root) / app_name
        if proj_dir.is_dir():
            app["project_dir"] = str(proj_dir)
            app["project_dir_size_bytes"] = _dir_size_bytes(str(proj_dir))
            if str(proj_dir) not in app["storage_paths"]:
                app["storage_paths"].insert(0, str(proj_dir))

    # ---- Pass 11: totals + dedup + resilience ------------------------------
    for app in apps.values():
        total = app["project_dir_size_bytes"]
        for v in app["volumes"]:
            total += v.get("size_bytes") or 0
        for src in app["storage_paths"]:
            if not src.startswith(projects_root):
                total += _dir_size_bytes(src)
        app["total_size_bytes"] = total

        for k in (
            "containers",
            "images",
            "compose_files",
            "nginx_sites",
            "urls",
            "systemd_units",
            "networks",
            "storage_paths",
            "storage_mounts",
            "env_keys",
            "listening_ports",
        ):
            if isinstance(app.get(k), list):
                app[k] = sorted(set(app[k]), key=str)

        seen_links: Set[tuple] = set()
        deduped: List[Dict[str, Any]] = []
        for ln in app["links"]:
            key = (ln["src_kind"], ln["src"], ln["dst_kind"], ln["dst"], ln["via"])
            if key not in seen_links:
                seen_links.add(key)
                deduped.append(ln)
        app["links"] = deduped

        if app["type"] == "project":
            for cd in app["containers_detail"]:
                if cd["restart_policy"] in (None, "no"):
                    app["resilience"]["issues"].append(
                        f"container {cd['name']} has no restart policy"
                    )
        app["resilience"]["reboot_safe"] = not app["resilience"]["issues"]

        app["components_count"] = (
            len(app["containers"])
            + len(app["nginx_sites"])
            + len(app["systemd_units"])
            + len(app["volumes"])
        )

    result = []
    for name in sorted(apps.keys()):
        app = apps[name]
        app["application_id"] = f"{server_id}:app:{name}"
        result.append(app)
    return result
