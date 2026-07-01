"""Phase 1 smoke tests — imports, config load, ProjectDetector, MongoDB connectivity."""

import os
import sys
from pathlib import Path

import pytest

# Ensure project root is on sys.path so `app` is importable
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_imports():
    from app.core import config_loader, db_manager, logger, project_detector  # noqa: F401


def test_config_loads():
    from app.core.config_loader import load_config

    cfg = load_config(str(ROOT / "config.yml"))
    assert cfg.server.id == "oci"
    assert cfg.server.api_port == 8004
    assert cfg.mongodb.database == "infradocs"
    assert cfg.mongodb.uri_env == "INFRADOCS_MONGO_URI"
    assert "docker" in cfg.scanning.enabled_scanners
    assert cfg.auth.username == "msinha"


def test_mongodb_uri_resolves_from_env(monkeypatch):
    from app.core.config_loader import load_config

    monkeypatch.setenv("INFRADOCS_MONGO_URI", "mongodb://test:test@example:27017/")
    cfg = load_config(str(ROOT / "config.yml"))
    assert cfg.mongodb.uri.startswith("mongodb://")


def test_mongodb_uri_missing_raises(tmp_path, monkeypatch):
    """When the env var is unset, accessing the URI must error loudly."""
    from app.core.config_loader import load_config

    # Use an isolated config in tmp_path so the project-root .env isn't loaded.
    isolated_cfg = tmp_path / "config.yml"
    isolated_cfg.write_text(
        (ROOT / "config.yml").read_text()
    )

    monkeypatch.delenv("INFRADOCS_MONGO_URI", raising=False)
    cfg = load_config(str(isolated_cfg))
    with pytest.raises(RuntimeError, match="MongoDB URI not set"):
        _ = cfg.mongodb.uri


def test_logger_setup(tmp_path):
    from app.core.logger import setup_logger

    log_file = tmp_path / "test.log"
    log = setup_logger("phase1.test", log_file=str(log_file), level="INFO")
    log.info("hello world")
    assert log_file.exists()
    content = log_file.read_text()
    assert "hello world" in content


# These tests build a CONTROLLED projects_root under tmp_path rather than
# asserting against the live /home/msinha/projects tree — that tree drifts (it
# was nearly emptied by a folder deletion, and the checkout here is `infradocs`,
# not `InfraDocs_V6`), which made the old versions flaky-by-environment. They now
# test detector LOGIC deterministically. See tests/test_project_discovery.py for
# the multi-root / full-disk discovery + exclusion-guard coverage.
def test_project_detector_scans_projects(tmp_path):
    from app.core.project_detector import ProjectDetector

    (tmp_path / "InfraDocs_V6").mkdir()
    (tmp_path / "otherapp").mkdir()
    pd = ProjectDetector(projects_root=str(tmp_path))
    projects = pd.list_projects()
    assert "InfraDocs_V6" in projects
    assert len(projects) >= 2


def test_project_detector_path_resolution(tmp_path):
    from app.core.project_detector import ProjectDetector

    (tmp_path / "InfraDocs_V6").mkdir()
    pd = ProjectDetector(projects_root=str(tmp_path))
    # Inside a discovered project dir
    assert pd.get_project_from_path(str(tmp_path / "InfraDocs_V6" / "foo" / "bar")) == "InfraDocs_V6"
    # Outside any project root
    assert pd.get_project_from_path("/etc/nginx/nginx.conf") == "System"
    # Empty path
    assert pd.get_project_from_path("") == "System"


def test_project_detector_rejects_service_name_inference(tmp_path):
    """V5 regression: cloud-init.service must NOT become 'Cloud' project."""
    from app.core.project_detector import ProjectDetector

    proj = tmp_path / "InfraDocs_V6"
    (proj / "deploy").mkdir(parents=True)
    pd = ProjectDetector(projects_root=str(tmp_path))
    assert pd.get_project_from_service_name("cloud-init.service") == "System"
    assert pd.get_project_from_service_name("apport-autoreport.service") == "System"
    # With unit file path inside a project, it should resolve
    assert (
        pd.get_project_from_service_name(
            "infradocs.service",
            unit_file_path=str(proj / "deploy" / "infradocs.service"),
        )
        == "InfraDocs_V6"
    )


def test_project_detector_container_label(tmp_path):
    from app.core.project_detector import ProjectDetector

    (tmp_path / "openwebui").mkdir()
    pd = ProjectDetector(projects_root=str(tmp_path))
    labels = {"com.docker.compose.project": "openwebui"}
    # Resolves because openwebui exists as a project dir
    assert pd.get_project_from_container(labels, working_dir="") == "openwebui"
    # Unknown compose project with no path evidence → System
    assert pd.get_project_from_container(
        {"com.docker.compose.project": "ghost"}, working_dir=""
    ) == "System"


def test_project_detector_domain_mapping(tmp_path):
    from app.core.project_detector import ProjectDetector

    (tmp_path / "InfraDocs_V6").mkdir()
    pd = ProjectDetector(projects_root=str(tmp_path))
    # infra.* → InfraDocs_V6 (dir exists → mapping resolves)
    assert pd.get_project_from_domain("infra.ocialwaysfree.site") == "InfraDocs_V6"
    # unknown subdomain → System
    assert pd.get_project_from_domain("unknown.example.com") == "System"


def _load_real_config():
    from app.core.config_loader import load_config

    return load_config(str(ROOT / "config.yml"))


def _mongo_available() -> bool:
    cfg = _load_real_config()
    return bool(os.environ.get(cfg.mongodb.uri_env))


@pytest.mark.skipif(
    os.environ.get("SKIP_MONGO_TESTS") == "1" or not _mongo_available(),
    reason="MongoDB URI not configured",
)
def test_mongodb_connection():
    from app.core.db_manager import DBManager

    cfg = _load_real_config()
    test_db_name = "infradocs_phase1_test"
    db = DBManager(uri=cfg.mongodb.uri, database=test_db_name)
    try:
        stats = db.get_stats()
        assert stats["database"] == test_db_name
        assert isinstance(stats["assets_count"], int)
    finally:
        db.client.drop_database(test_db_name)
        db.close()


@pytest.mark.skipif(
    os.environ.get("SKIP_MONGO_TESTS") == "1" or not _mongo_available(),
    reason="MongoDB URI not configured",
)
def test_db_manager_asset_round_trip():
    from app.core.db_manager import DBManager

    cfg = _load_real_config()
    test_db_name = "infradocs_phase1_test"
    db = DBManager(uri=cfg.mongodb.uri, database=test_db_name)
    try:
        db.create_indexes()
        sample = {
            "server_id": "oci",
            "asset_id": "docker_container:test123",
            "name": "test-container",
            "category": "docker_container",
            "status": "running",
            "project": "InfraDocs_V6",
            "metadata": {"image": "test:latest"},
            "health_score": 100,
        }
        assert db.upsert_asset(sample) is True
        results = db.get_assets(category="docker_container")
        assert len(results) == 1
        assert results[0]["asset_id"] == "docker_container:test123"
        assert results[0]["project"] == "InfraDocs_V6"
    finally:
        db.client.drop_database(test_db_name)
        db.close()


@pytest.mark.skipif(
    os.environ.get("SKIP_MONGO_TESTS") == "1" or not _mongo_available(),
    reason="MongoDB URI not configured",
)
def test_replica_set_primary_reachable():
    """Verify we're connected to a true replica-set and a primary is elected."""
    from app.core.db_manager import DBManager

    cfg = _load_real_config()
    db = DBManager(uri=cfg.mongodb.uri, database="infradocs_phase1_test")
    try:
        hello = db.client.admin.command("hello")
        assert hello.get("setName") == "rs0"
        assert hello.get("primary"), "no primary elected"
    finally:
        db.close()
