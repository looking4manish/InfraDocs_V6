"""Application correlator.

Takes the flat `assets` collection (which the scanners produce) and joins
related assets into `application` documents. One application aggregates
everything Manish would need to see at a glance to understand or
decommission a service: containers, compose file, nginx sites, exposed
URLs, ports, volumes, on-disk paths and sizes, systemd units.

The correlation runs in passes (each pass touches a different asset
category). Pass order matters — port-mapping index built in pass 4 is what
nginx server blocks key off in pass 5.
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from app.scanners.docker import _dir_size_bytes

logger = logging.getLogger(__name__)


def _empty_app(name: str, *, source: str, type_: str) -> Dict[str, Any]:
    return {
        "name": name,
        "type": type_,  # compose | systemd | project_dir | standalone-container
        "source": source,
        "containers": [],
        "compose_file": None,
        "systemd_units": [],
        "nginx_sites": [],
        "urls": [],
        "port_mappings": [],  # [{host_port, container, container_port}]
        "listening_ports": [],
        "volumes": [],  # [{name, mountpoint, size_bytes}]
        "networks": [],
        "storage_paths": [],
        "project_dir": None,
        "project_dir_size_bytes": 0,
        "total_size_bytes": 0,
        "internet_exposed": False,
        "cloudflare": False,
        "env_keys": [],  # union of env key names across containers/units
        "components_count": 0,
    }


def _group(assets: Iterable[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for a in assets:
        out[a["category"]].append(a)
    return out


def correlate(
    assets: List[Dict[str, Any]],
    *,
    server_id: str,
    projects_root: str,
) -> List[Dict[str, Any]]:
    """Run the correlation passes and return a list of application documents."""
    by_cat = _group(assets)
    apps: Dict[str, Dict[str, Any]] = {}

    # ---- Pass 1: seed from compose files -----------------------------------
    for compose in by_cat.get("docker_compose", []):
        path = compose["metadata"]["file_path"]
        name = Path(path).parent.name
        app = apps.setdefault(name, _empty_app(name, source=path, type_="compose"))
        app["compose_file"] = path

    # ---- Pass 2: seed from project-tagged systemd units --------------------
    for unit in by_cat.get("systemd_service", []):
        if unit["project"] != "System":
            apps.setdefault(
                unit["project"],
                _empty_app(unit["project"], source=unit["name"], type_="systemd"),
            )

    # ---- Pass 3: seed from any other non-System project tag ----------------
    for asset in assets:
        if asset["project"] != "System" and asset["project"] not in apps:
            apps[asset["project"]] = _empty_app(
                asset["project"], source=None, type_="project_dir"
            )

    # ---- Pass 4: attach containers, build host-port → app index ------------
    host_port_to_app: Dict[int, str] = {}

    def _resolve_container_app(c: Dict[str, Any]) -> str:
        """Decide which app a container belongs to."""
        meta = c["metadata"]
        compose_proj = meta.get("compose_project")
        if compose_proj:
            if compose_proj not in apps:
                apps[compose_proj] = _empty_app(
                    compose_proj, source=None, type_="compose-implied"
                )
            return compose_proj
        if c["project"] != "System":
            return c["project"]  # already seeded in pass 3
        # Standalone container — treat its own name as the app
        if c["name"] not in apps:
            apps[c["name"]] = _empty_app(
                c["name"], source=c["name"], type_="standalone-container"
            )
        return c["name"]

    for c in by_cat.get("docker_container", []):
        meta = c["metadata"]
        app_name = _resolve_container_app(c)
        app = apps[app_name]
        app["containers"].append(c["name"])

        # Port mappings (dedup IPv4 + IPv6 duplicates that point at the same host_port)
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

        # Bind-mount sources count as storage paths the app owns/uses
        for src in meta.get("bind_mount_sources") or []:
            app["storage_paths"].append(src)

        # Env keys union
        for k in meta.get("env_keys") or []:
            if k not in app["env_keys"]:
                app["env_keys"].append(k)

    # ---- Pass 4b: extend host_port_to_app from project-tagged listening ports
    # This catches non-Docker apps (e.g. systemd-run binaries) so nginx blocks
    # proxying to those ports still link back to the right application.
    for p in by_cat.get("network_port", []):
        if p["project"] == "System" or p["project"] not in apps:
            continue
        port = p["metadata"].get("port")
        if isinstance(port, int):
            host_port_to_app.setdefault(port, p["project"])

    # ---- Pass 5: attach docker volumes ------------------------------------
    for v in by_cat.get("docker_volume", []):
        meta = v["metadata"]
        compose_proj = meta.get("compose_project")
        app_name: Optional[str] = None
        if compose_proj and compose_proj in apps:
            app_name = compose_proj
        elif v["project"] != "System" and v["project"] in apps:
            app_name = v["project"]
        if app_name:
            apps[app_name]["volumes"].append(
                {
                    "name": v["name"],
                    "mountpoint": meta.get("mountpoint"),
                    "size_bytes": meta.get("size_bytes", 0),
                }
            )

    # ---- Pass 6: attach docker networks -----------------------------------
    for n in by_cat.get("docker_network", []):
        labels = n["metadata"].get("labels") or {}
        compose_proj = labels.get("com.docker.compose.project")
        if compose_proj and compose_proj in apps:
            apps[compose_proj]["networks"].append(n["name"])
        elif n["project"] != "System" and n["project"] in apps:
            apps[n["project"]]["networks"].append(n["name"])

    # ---- Pass 7: attach nginx server blocks (upstream → host_port → app) --
    for ng in by_cat.get("nginx_server_block", []):
        meta = ng["metadata"]
        upstream_port = meta.get("upstream_port")
        app_name = None
        # Strategy A: upstream port matches a container's host port
        if upstream_port and upstream_port in host_port_to_app:
            app_name = host_port_to_app[upstream_port]
        # Strategy B: subdomain → project via existing DOMAIN_MAPPING
        elif ng["project"] != "System" and ng["project"] in apps:
            app_name = ng["project"]

        if not app_name:
            continue
        app = apps[app_name]
        app["nginx_sites"].append(ng["name"])
        url = meta.get("url")
        if url and url not in app["urls"]:
            app["urls"].append(url)
        if meta.get("internet_exposed"):
            app["internet_exposed"] = True
        if meta.get("cloudflare_origin"):
            app["cloudflare"] = True

    # ---- Pass 8: attach systemd services and timers -----------------------
    for s in by_cat.get("systemd_service", []) + by_cat.get("systemd_timer", []):
        if s["project"] != "System" and s["project"] in apps:
            apps[s["project"]]["systemd_units"].append(s["name"])
            for k in s["metadata"].get("environment_keys") or []:
                if k not in apps[s["project"]]["env_keys"]:
                    apps[s["project"]]["env_keys"].append(k)

    # ---- Pass 9: attach listening ports -----------------------------------
    for p in by_cat.get("network_port", []):
        port = p["metadata"].get("port")
        if not isinstance(port, int):
            continue
        if port in host_port_to_app:
            app_name = host_port_to_app[port]
            if port not in apps[app_name]["listening_ports"]:
                apps[app_name]["listening_ports"].append(port)
        elif p["project"] != "System" and p["project"] in apps:
            if port not in apps[p["project"]]["listening_ports"]:
                apps[p["project"]]["listening_ports"].append(port)

    # ---- Pass 10: attach project directory + size -------------------------
    for app_name, app in apps.items():
        proj_dir = Path(projects_root) / app_name
        if proj_dir.is_dir():
            app["project_dir"] = str(proj_dir)
            app["project_dir_size_bytes"] = _dir_size_bytes(str(proj_dir))
            if str(proj_dir) not in app["storage_paths"]:
                app["storage_paths"].insert(0, str(proj_dir))

    # ---- Pass 11: aggregate total disk + dedup lists ----------------------
    for app in apps.values():
        total = app["project_dir_size_bytes"]
        for v in app["volumes"]:
            total += v.get("size_bytes") or 0
        # Bind-mount sources that aren't under projects_root may add storage too
        for src in app["storage_paths"]:
            if not src.startswith(projects_root):
                total += _dir_size_bytes(src)
        app["total_size_bytes"] = total

        # Dedup the list fields that are simple strings
        for k in (
            "containers",
            "nginx_sites",
            "urls",
            "systemd_units",
            "networks",
            "storage_paths",
            "env_keys",
            "listening_ports",
        ):
            if isinstance(app.get(k), list):
                app[k] = sorted(set(app[k]), key=str)

        # components_count is a rough "how many moving parts" signal
        app["components_count"] = (
            len(app["containers"])
            + len(app["nginx_sites"])
            + len(app["systemd_units"])
            + len(app["volumes"])
        )

    # Return as a list with stable ordering
    result = []
    for name in sorted(apps.keys()):
        app = apps[name]
        app["application_id"] = f"{server_id}:app:{name}"
        result.append(app)
    return result
