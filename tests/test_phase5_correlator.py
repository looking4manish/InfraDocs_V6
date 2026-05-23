"""Phase 5 — correlator unit + integration tests.

Unit tests use synthetic asset fixtures so we can drive every code path
deterministically; integration tests at the bottom run a real scan against
OCI and check that the correlation actually links real data together.
"""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.correlator import correlate


def _container(
    *,
    name,
    project="System",
    compose_project=None,
    host_ports=None,
    bind_sources=None,
    env_keys=None,
):
    return {
        "category": "docker_container",
        "asset_id": f"oci:container:{name}",
        "name": name,
        "status": "running",
        "project": project,
        "metadata": {
            "container_id": name[:12],
            "compose_project": compose_project,
            "host_ports": host_ports or [],
            "ports": [
                {"container_port": "8080/tcp", "host_port": str(hp), "host_ip": "0.0.0.0"}
                for hp in (host_ports or [])
            ],
            "bind_mount_sources": bind_sources or [],
            "env_keys": env_keys or [],
        },
    }


def _compose(*, dir_name):
    path = f"/home/msinha/projects/{dir_name}/docker-compose.yml"
    return {
        "category": "docker_compose",
        "asset_id": f"oci:compose:{path}",
        "name": dir_name,
        "status": "configured",
        "project": dir_name,
        "metadata": {"file_path": path, "services": [dir_name]},
    }


def _nginx(*, name, upstream_host="localhost", upstream_port=None, has_443=True, cf=False):
    return {
        "category": "nginx_server_block",
        "asset_id": f"oci:nginx:test:{name}:443",
        "name": name,
        "status": "configured",
        "project": "System",
        "metadata": {
            "config_file": f"/etc/nginx/sites-enabled/{name}",
            "server_names": [name],
            "listen": ["443 ssl" if has_443 else "80"],
            "listen_ports": [443] if has_443 else [80],
            "upstream": f"{upstream_host}:{upstream_port}" if upstream_port else "",
            "upstream_host": upstream_host,
            "upstream_port": upstream_port,
            "has_ssl": has_443,
            "ssl_certificate": "/etc/letsencrypt/live/x/fullchain.pem" if has_443 else None,
            "cloudflare_origin": cf,
            "internet_exposed": has_443,
            "url": f"https://{name}" if has_443 else None,
        },
    }


def _systemd(*, name, project, exec_start=""):
    return {
        "category": "systemd_service",
        "asset_id": f"oci:service:{name}",
        "name": name,
        "status": "active",
        "project": project,
        "metadata": {"unit_type": "service", "exec_start": exec_start, "environment_keys": []},
    }


def _volume(*, name, project="System", compose_project=None, size=1024):
    return {
        "category": "docker_volume",
        "asset_id": f"oci:volume:{name}",
        "name": name,
        "status": "in_use",
        "project": project,
        "metadata": {
            "mountpoint": f"/var/lib/docker/volumes/{name}/_data",
            "size_bytes": size,
            "compose_project": compose_project,
            "labels": {},
        },
    }


def _port(*, port, project="System"):
    return {
        "category": "network_port",
        "asset_id": f"oci:port:tcp:{port}",
        "name": f"{port}/tcp",
        "status": "listening",
        "project": project,
        "metadata": {"port": port, "protocol": "tcp", "process": "x", "pid": 1},
    }


# ----------------------------- unit tests -----------------------------------


def test_compose_seeds_an_app(tmp_path):
    assets = [_compose(dir_name="openwebui")]
    apps = correlate(assets, server_id="oci", projects_root=str(tmp_path))
    assert len(apps) == 1
    assert apps[0]["name"] == "openwebui"
    assert apps[0]["compose_file"].endswith("docker-compose.yml")
    assert apps[0]["type"] == "compose"


def test_compose_app_links_container_via_label(tmp_path):
    """Container with com.docker.compose.project label attaches to that app."""
    assets = [
        _compose(dir_name="immich"),
        _container(
            name="immich-server",
            project="immich",
            compose_project="immich",
            host_ports=[2283],
        ),
        _container(
            name="immich-machine-learning",
            project="immich",
            compose_project="immich",
        ),
        _container(
            name="postgres-immich",
            project="immich",
            compose_project="immich",
        ),
    ]
    apps = {a["name"]: a for a in correlate(assets, server_id="oci", projects_root=str(tmp_path))}
    assert "immich" in apps
    assert len(apps["immich"]["containers"]) == 3
    assert sorted(apps["immich"]["containers"]) == [
        "immich-machine-learning",
        "immich-server",
        "postgres-immich",
    ]


def test_nginx_links_via_upstream_port(tmp_path):
    """proxy_pass http://localhost:8080 -> container that maps host port 8080."""
    assets = [
        _compose(dir_name="openwebui"),
        _container(
            name="openwebui",
            compose_project="openwebui",
            host_ports=[8080],
        ),
        _nginx(name="chat.example.com", upstream_port=8080),
    ]
    apps = {a["name"]: a for a in correlate(assets, server_id="oci", projects_root=str(tmp_path))}
    assert apps["openwebui"]["nginx_sites"] == ["chat.example.com"]
    assert apps["openwebui"]["urls"] == ["https://chat.example.com"]
    assert apps["openwebui"]["internet_exposed"] is True


def test_nginx_links_via_domain_when_no_port_match(tmp_path):
    """Fallback: if upstream port doesn't match any container, use domain → project."""
    # Seed project_dir-style app
    proj = tmp_path / "OCI_Dashboard"
    proj.mkdir()

    assets = [
        # systemd unit tagged with OCI_Dashboard seeds the app
        _systemd(name="OCI_Dashboard.service", project="OCI_Dashboard"),
        # nginx block tagged with OCI_Dashboard project (via DOMAIN_MAPPING)
        {
            "category": "nginx_server_block",
            "asset_id": "oci:nginx:x:dashboard.example.com:443",
            "name": "dashboard.example.com",
            "status": "configured",
            "project": "OCI_Dashboard",
            "metadata": {
                "config_file": "/etc/nginx/sites-enabled/x",
                "listen_ports": [443],
                "upstream": "",
                "upstream_port": None,
                "internet_exposed": True,
                "url": "https://dashboard.example.com",
                "cloudflare_origin": False,
            },
        },
    ]
    apps = {a["name"]: a for a in correlate(assets, server_id="oci", projects_root=str(tmp_path))}
    assert "OCI_Dashboard" in apps
    assert apps["OCI_Dashboard"]["nginx_sites"] == ["dashboard.example.com"]


def test_systemd_seeds_app_for_non_compose_runtime(tmp_path):
    assets = [_systemd(name="raveuploader_rws.service", project="raveuploader_rws")]
    apps = {a["name"]: a for a in correlate(assets, server_id="oci", projects_root=str(tmp_path))}
    assert "raveuploader_rws" in apps
    assert apps["raveuploader_rws"]["systemd_units"] == ["raveuploader_rws.service"]
    assert apps["raveuploader_rws"]["type"] == "systemd"


def test_volume_attaches_via_compose_label(tmp_path):
    assets = [
        _compose(dir_name="openwebui"),
        _volume(name="openwebui_data", compose_project="openwebui", size=5_000_000),
    ]
    apps = {a["name"]: a for a in correlate(assets, server_id="oci", projects_root=str(tmp_path))}
    assert len(apps["openwebui"]["volumes"]) == 1
    assert apps["openwebui"]["volumes"][0]["size_bytes"] == 5_000_000


def test_listening_port_attaches_via_host_port(tmp_path):
    assets = [
        _container(name="openwebui", project="openwebui", host_ports=[8080]),
        _port(port=8080),
    ]
    apps = {a["name"]: a for a in correlate(assets, server_id="oci", projects_root=str(tmp_path))}
    assert 8080 in apps["openwebui"]["listening_ports"]
    assert apps["openwebui"]["port_mappings"][0]["host_port"] == 8080


def test_project_dir_size_picked_up(tmp_path):
    """The correlator du's the project dir if it exists under projects_root."""
    proj = tmp_path / "openwebui"
    proj.mkdir()
    (proj / "f1").write_bytes(b"x" * 1000)
    (proj / "f2").write_bytes(b"y" * 2000)

    assets = [_compose(dir_name="openwebui")]
    # Override the compose path so it lives under tmp_path
    assets[0]["metadata"]["file_path"] = str(proj / "docker-compose.yml")

    apps = correlate(assets, server_id="oci", projects_root=str(tmp_path))
    app = apps[0]
    assert app["project_dir"] == str(proj)
    assert app["project_dir_size_bytes"] >= 3000
    assert app["total_size_bytes"] >= 3000


def test_internet_exposed_propagates(tmp_path):
    assets = [
        _container(name="webapp", project="System", host_ports=[5000]),
        _nginx(name="public.example.com", upstream_port=5000, has_443=True, cf=True),
    ]
    apps = {a["name"]: a for a in correlate(assets, server_id="oci", projects_root=str(tmp_path))}
    # Container name doubles as app name since it's standalone
    app = apps["webapp"]
    assert app["internet_exposed"] is True
    assert app["cloudflare"] is True


def test_components_count_aggregates(tmp_path):
    assets = [
        _compose(dir_name="big_app"),
        _container(name="c1", compose_project="big_app"),
        _container(name="c2", compose_project="big_app"),
        _nginx(name="big.example.com", upstream_port=None),
        _systemd(name="big_app.service", project="big_app"),
        _volume(name="big_app_data", compose_project="big_app"),
    ]
    apps = {a["name"]: a for a in correlate(assets, server_id="oci", projects_root=str(tmp_path))}
    # nginx didn't link via upstream port, so won't attach unless domain matches
    assert apps["big_app"]["components_count"] >= 4  # 2 containers + 1 systemd + 1 volume


def test_application_id_format(tmp_path):
    apps = correlate([_compose(dir_name="x")], server_id="oci", projects_root=str(tmp_path))
    assert apps[0]["application_id"] == "oci:app:x"


# --------------------------- integration test -------------------------------


@pytest.mark.skipif(
    not os.environ.get("INFRADOCS_MONGO_URI"),
    reason="MongoDB URI not configured",
)
def test_integration_correlate_real_oci_scan():
    """Run a real scan + correlate, then sanity-check the openwebui app."""
    from app.core.config_loader import load_config
    from app.core.project_detector import ProjectDetector
    from app.scanners.registry import SCANNERS

    cfg = load_config(str(ROOT / "config.yml"))
    pd = ProjectDetector(projects_root=cfg.paths.projects_root)
    all_assets = []
    for name, cls in SCANNERS.items():
        sc = cls(server_id="oci", project_detector=pd)
        for a in sc.execute()["assets"]:
            all_assets.append(a)

    apps = correlate(
        all_assets,
        server_id="oci",
        projects_root=cfg.paths.projects_root,
    )
    by_name = {a["name"]: a for a in apps}

    # We expect at least openwebui and OCI_Dashboard to be detected
    assert "openwebui" in by_name, (
        f"expected openwebui in apps; saw: {sorted(by_name)}"
    )
    ow = by_name["openwebui"]
    assert ow["containers"], "openwebui app has no containers attached"
    # openwebui maps container 8080 -> host 3000; should show host_port 3000
    assert any(pm["host_port"] in {3000, 8080} for pm in ow["port_mappings"])

    assert "OCI_Dashboard" in by_name, "OCI_Dashboard systemd-driven app missing"
    od = by_name["OCI_Dashboard"]
    assert any(
        "OCI_Dashboard.service" in u for u in od["systemd_units"]
    ), f"OCI_Dashboard.service not linked; got {od['systemd_units']}"

    # raveuploader_rws is also systemd-only
    assert "raveuploader_rws" in by_name, "raveuploader_rws systemd-only app missing"
