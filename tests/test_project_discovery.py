"""Scattered-project discovery — multi-root, marker scan, docker dirs, full paths."""

import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core import project_detector as pdmod
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


# ---- full-disk multi-root discovery -------------------------------------------------

def test_direct_roots_each_child_is_an_app(tmp_path):
    """direct_roots behave like projects_root: every direct child is an app,
    even a plain install dir with no compose/.git marker (e.g. /opt/<app>)."""
    opt = tmp_path / "opt"
    srv = tmp_path / "srv"
    (opt / "grafana").mkdir(parents=True)      # plain install, no marker
    (srv / "gitea").mkdir(parents=True)
    pd = ProjectDetector(
        projects_root=str(tmp_path / "home_projects"),  # absent
        direct_roots=[str(opt), str(srv)],
    )
    projs = pd.list_projects()
    assert "grafana" in projs and "gitea" in projs
    assert pd.project_paths()["grafana"].endswith("/opt/grafana")
    assert pd.get_project_from_path(str(opt / "grafana" / "conf")) == "grafana"


def test_scan_roots_do_not_promote_home_users_to_apps(tmp_path):
    """A broad marker-hunt root (like /home) must NOT turn every subfolder into an
    app — only marker-bearing dirs surface."""
    home = tmp_path / "home"
    (home / "alice").mkdir(parents=True)                 # a user, not an app
    proj = home / "bob" / "coolapp"
    proj.mkdir(parents=True)
    (proj / ".git").mkdir()                              # a real project marker
    pd = ProjectDetector(
        projects_root=str(tmp_path / "none"),
        scan_roots=[str(home)],
        scan_depth=3,
    )
    projs = pd.list_projects()
    assert "coolapp" in projs
    assert "alice" not in projs and "bob" not in projs


def test_discovery_roots_dedup_and_order(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    pd = ProjectDetector(
        projects_root=str(a),
        direct_roots=[str(b)],
        scan_roots=[str(a), str(b)],   # dupes of the above
    )
    roots = [str(r) for r in pd.discovery_roots()]
    assert roots == [str(a), str(b)]   # deduped, order preserved


# ---- exclusion / traversal guards ---------------------------------------------------

def test_noise_dirs_are_not_descended(tmp_path):
    """A marker buried inside node_modules/venv/.git must be ignored — those hide
    thousands of stub markers that aren't real deployments."""
    buried = tmp_path / "repo" / "node_modules" / "pkg"
    buried.mkdir(parents=True)
    (buried / "docker-compose.yml").write_text("services: {}")
    pd = ProjectDetector(
        projects_root=str(tmp_path / "none"),
        scan_roots=[str(tmp_path)],
        scan_depth=5,
    )
    assert "pkg" not in pd.list_projects()


def test_skipped_mount_is_not_descended(tmp_path, monkeypatch):
    """A dir whose mountpoint fstype is network/tmpfs/etc is not traversed."""
    mnt = tmp_path / "mnt" / "nfsshare"
    proj = mnt / "app"
    proj.mkdir(parents=True)
    (proj / "docker-compose.yml").write_text("services: {}")
    # Pretend /…/mnt/nfsshare is an NFS mount the traversal must skip.
    monkeypatch.setattr(pdmod, "_skip_mountpoints", lambda: {str(mnt)})
    pd = ProjectDetector(
        projects_root=str(tmp_path / "none"),
        scan_roots=[str(tmp_path)],
        scan_depth=5,
    )
    assert "app" not in pd.list_projects()


def test_marker_scan_respects_depth_bound(tmp_path):
    """A marker deeper than scan_depth is not found (bounded traversal)."""
    deep = tmp_path / "l1" / "l2" / "l3" / "l4" / "app"
    deep.mkdir(parents=True)
    (deep / "docker-compose.yml").write_text("services: {}")
    shallow = ProjectDetector(
        projects_root=str(tmp_path / "none"), scan_roots=[str(tmp_path)], scan_depth=2
    )
    assert "app" not in shallow.list_projects()
    deeper = ProjectDetector(
        projects_root=str(tmp_path / "none"), scan_roots=[str(tmp_path)], scan_depth=6
    )
    assert "app" in deeper.list_projects()


def test_deadline_guard_triggers_and_flags_truncation(tmp_path):
    (tmp_path / "app1").mkdir()
    pd = ProjectDetector(projects_root=str(tmp_path))
    # Deadline already in the past → the budget is exhausted, truncation flagged.
    pd._deadline = time.monotonic() - 1
    assert pd._budget_exhausted() is True
    assert pd._truncated is True


def test_zero_timeout_disables_wall_clock_cap(tmp_path):
    (tmp_path / "app1").mkdir()
    pd = ProjectDetector(projects_root=str(tmp_path), scan_timeout_seconds=0)
    assert pd._deadline is None
    assert "app1" in pd.list_projects()


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses filesystem permissions")
def test_unreadable_root_logs_loudly_without_crashing(tmp_path, caplog):
    """A configured root that exists but can't be read is logged LOUDLY (named
    reason) and does not crash or abort discovery of the readable roots."""
    good = tmp_path / "good"
    (good / "app_ok").mkdir(parents=True)
    locked = tmp_path / "locked"
    locked.mkdir()
    os.chmod(locked, 0o000)
    try:
        with caplog.at_level("WARNING", logger="app.core.project_detector"):
            pd = ProjectDetector(
                projects_root=str(good),
                direct_roots=[str(locked)],
            )
        assert "app_ok" in pd.list_projects()          # readable root still scanned
        assert any(
            "UNREADABLE" in r.getMessage() and str(locked) in r.getMessage()
            for r in caplog.records
        )
    finally:
        os.chmod(locked, 0o755)


def test_absent_root_is_skipped_quietly(tmp_path, caplog):
    """A root that simply doesn't exist on this box is normal — info, not a crash."""
    with caplog.at_level("INFO", logger="app.core.project_detector"):
        pd = ProjectDetector(
            projects_root=str(tmp_path / "does_not_exist"),
            scan_roots=[str(tmp_path / "also_missing")],
        )
    assert pd.list_projects() == []
    assert not any(r.levelname == "WARNING" for r in caplog.records)
