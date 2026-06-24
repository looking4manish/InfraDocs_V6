"""Phase 2 scanner smoke tests against the real OCI host.

These tests run the actual scanners against this machine — they're
integration tests, not unit tests. They assert shape and the absence of
crashes, not specific counts (since infrastructure changes over time).
"""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.project_detector import ProjectDetector
from app.scanners.compose import ComposeScanner
from app.scanners.docker import DockerScanner
from app.scanners.nginx import NginxScanner
from app.scanners.port import PortScanner
from app.scanners.registry import SCANNERS
from app.scanners.storage import StorageScanner
from app.scanners.systemd import SystemdScanner


@pytest.fixture
def pd():
    return ProjectDetector(projects_root="/home/msinha/projects")


def _assert_asset_shape(asset, expected_category_prefix=None):
    for key in [
        "server_id",
        "category",
        "asset_id",
        "name",
        "status",
        "project",
        "metadata",
        "scanner",
        "discovered_at",
    ]:
        assert key in asset, f"missing {key} in {asset}"
    assert asset["server_id"] == "oci"
    if expected_category_prefix:
        assert asset["category"].startswith(expected_category_prefix)


def test_registry_has_all_scanners():
    assert set(SCANNERS.keys()) == {
        "systemd",
        "docker",
        "compose",
        "nginx",
        "port",
        "storage",
        "cron",
        "certs",
    }


def test_systemd_scanner_runs(pd):
    sc = SystemdScanner(server_id="oci", project_detector=pd)
    result = sc.execute()
    assert result["status"] in {"success", "partial_success"}
    assert result["assets_found"] > 10, "OCI should have plenty of systemd units"
    for asset in result["assets"][:5]:
        _assert_asset_shape(asset, "systemd_")
    # The whole point of ProjectDetector: no false projects from name prefixes
    services = [a for a in result["assets"] if a["category"] == "systemd_service"]
    bad = [
        a
        for a in services
        if a["project"] in {"Cloud", "Apport", "Cockpit"} and a["name"].startswith(
            ("cloud-init", "apport", "cockpit")
        )
    ]
    assert not bad, f"false projects from service names regressed: {bad[:3]}"


def test_docker_scanner_runs(pd):
    sc = DockerScanner(server_id="oci", project_detector=pd)
    result = sc.execute()
    # Docker may not be running, but the scanner must not crash either way
    assert result["status"] in {"success", "partial_success", "failed"}
    if result["assets_found"]:
        for asset in result["assets"][:3]:
            _assert_asset_shape(asset, "docker_")


def test_compose_scanner_runs(pd):
    sc = ComposeScanner(server_id="oci", project_detector=pd)
    result = sc.execute()
    assert result["status"] in {"success", "partial_success"}
    for asset in result["assets"]:
        _assert_asset_shape(asset, "docker_compose")
        assert asset["metadata"]["file_path"].endswith(
            ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")
        )


def test_nginx_scanner_runs(pd):
    sc = NginxScanner(server_id="oci", project_detector=pd)
    result = sc.execute()
    assert result["status"] in {"success", "partial_success"}
    # If nginx is installed, we should find at least one server block
    import shutil

    if shutil.which("nginx"):
        # Not guaranteed to have configs, but shouldn't crash
        for asset in result["assets"][:3]:
            _assert_asset_shape(asset, "nginx_")


def test_port_scanner_runs(pd):
    sc = PortScanner(server_id="oci", project_detector=pd)
    result = sc.execute()
    assert result["status"] in {"success", "partial_success"}
    # We always have at least sshd or mongod listening
    assert result["assets_found"] > 0
    for asset in result["assets"][:3]:
        _assert_asset_shape(asset, "network_port")
        assert isinstance(asset["metadata"]["port"], int)


def test_port_scanner_no_false_projects_from_process_name(pd):
    """Regression: PIDs not under /home/msinha/projects/* must tag as 'System'."""
    sc = PortScanner(server_id="oci", project_detector=pd)
    result = sc.execute()
    # Any port whose process is mongod/sshd/systemd must be System
    for a in result["assets"]:
        proc = (a["metadata"].get("process") or "").lower()
        if any(p in proc for p in ("mongod", "sshd", "systemd-resolved")):
            assert a["project"] == "System", (
                f"system process {proc} got tagged with project={a['project']}"
            )


def test_storage_scanner_runs(pd):
    sc = StorageScanner(server_id="oci", project_detector=pd)
    result = sc.execute()
    assert result["status"] in {"success", "partial_success"}
    assert result["assets_found"] >= 1  # at least / mount
    has_root = any(a["name"] == "/" for a in result["assets"])
    assert has_root, "did not see / mountpoint"


def test_nginx_brace_aware_parsing(pd, tmp_path, monkeypatch):
    """Verify nested location { } blocks don't confuse the parser."""
    fake = tmp_path / "site.conf"
    fake.write_text(
        """
        server {
            listen 443 ssl;
            server_name infra.ocialwaysfree.site;
            ssl_certificate /etc/ssl/cert.pem;
            location / {
                proxy_pass http://localhost:8004;
                if ($host = "x") { return 444; }
            }
            location /api/ {
                proxy_pass http://localhost:8004/api/;
            }
        }
        server {
            listen 80;
            server_name chat.ocialwaysfree.site;
            location / { proxy_pass http://localhost:8080; }
        }
        """
    )
    sc = NginxScanner(server_id="oci", project_detector=pd)
    # Bypass nginx-installed check for this isolated test
    monkeypatch.setattr("shutil.which", lambda _: "/usr/sbin/nginx")
    assets = sc._parse_file(fake)
    names = sorted(a["name"] for a in assets)
    assert names == ["chat.ocialwaysfree.site", "infra.ocialwaysfree.site"]


@pytest.mark.skipif(
    not os.environ.get("INFRADOCS_MONGO_URI"),
    reason="MongoDB URI not configured",
)
def test_end_to_end_scan_writes_to_db(pd):
    """Full agent run hits MongoDB and writes assets."""
    from app.core.config_loader import load_config
    from app.core.db_manager import DBManager

    cfg = load_config(str(ROOT / "config.yml"))
    test_db = "infradocs_phase2_e2e"
    db = DBManager(uri=cfg.mongodb.uri, database=test_db)
    try:
        # Run a couple scanners and persist
        for sc_cls in (StorageScanner, SystemdScanner):
            sc = sc_cls(server_id="oci", project_detector=pd)
            result = sc.execute()
            for a in result["assets"]:
                db.upsert_asset(a)

        stats = db.get_stats()
        assert stats["assets_count"] > 5
        # And we can query by category
        systemd_assets = db.get_assets(category="systemd_service")
        assert len(systemd_assets) > 0
    finally:
        db.client.drop_database(test_db)
        db.close()
