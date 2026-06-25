"""Scattered-project discovery — multi-root, marker scan, docker dirs, full paths."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.project_detector import ProjectDetector, attach_root_paths


def test_dedicated_root_direct_subfolders(tmp_path):
    (tmp_path / "app1").mkdir()
    (tmp_path / "app2").mkdir()
    pd = ProjectDetector(projects_root=str(tmp_path))
    assert {"app1", "app2"}.issubset(set(pd.list_projects()))


def test_scan_roots_are_marker_only(tmp_path):
    # A broad root with random folders + one real (nested) compose project.
    (tmp_path / "Downloads").mkdir()
    proj = tmp_path / "stuff" / "myapp"
    proj.mkdir(parents=True)
    (proj / "docker-compose.yml").write_text("services: {}")

    pd = ProjectDetector(
        projects_root=str(tmp_path / "nonexistent"),
        scan_roots=[str(tmp_path)],
        scan_depth=3,
    )
    projs = pd.list_projects()
    assert "myapp" in projs            # marker-bearing dir discovered
    assert "Downloads" not in projs    # a random subfolder is NOT a project
    assert pd.project_paths()["myapp"].endswith("/stuff/myapp")
    assert pd.get_project_from_path(str(proj / "data" / "x")) == "myapp"


def test_discovered_docker_dirs_and_longest_prefix(tmp_path):
    d = tmp_path / "scattered" / "dockerapp"
    d.mkdir(parents=True)
    pd = ProjectDetector(
        projects_root=str(tmp_path / "none"),
        discovered={"dockerapp": str(d)},
    )
    assert "dockerapp" in pd.list_projects()
    assert pd.get_project_from_path(str(d / "sub" / "y")) == "dockerapp"
    assert pd.get_project_from_path("/etc/nginx") == "System"


def test_attach_root_paths():
    apps = [{"name": "app1"}, {"name": "System"}]
    attach_root_paths(apps, {"app1": "/data/app1"})
    assert apps[0]["root_path"] == "/data/app1"
    assert "root_path" not in apps[1]


def test_host_root_translation(tmp_path, monkeypatch):
    # Simulate a container: host root mounted at tmp/host, real project at /srv/app.
    host = tmp_path / "host"
    (host / "srv" / "app").mkdir(parents=True)
    (host / "srv" / "app" / "docker-compose.yml").write_text("services: {}")
    monkeypatch.setattr("app.core.project_detector._HOST_ROOT", str(host))

    pd = ProjectDetector(projects_root="/nonexistent", scan_roots=["/srv"], scan_depth=3)
    assert "app" in pd.list_projects()
    # stored as the REAL host path, not the /host-prefixed one
    assert pd.project_paths()["app"] == "/srv/app"
    assert pd.get_project_from_path("/srv/app/data") == "app"


def test_path_component_fallback_for_relocated_app(tmp_path):
    # mxh discovered at <data>/mxh, but its nginx root is /home/x/mxh/dist.
    (tmp_path / "data" / "mxh").mkdir(parents=True)
    pd = ProjectDetector(projects_root=str(tmp_path / "data"))
    assert "mxh" in pd.list_projects()
    assert pd.get_project_from_path("/home/msinha/mxh/frontend/dist") == "mxh"
    assert pd.get_project_from_path("/var/www/other/dist") == "System"
