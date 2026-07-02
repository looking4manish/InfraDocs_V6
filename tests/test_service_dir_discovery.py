"""A systemd-tracked app under a non-marker path (e.g. /home/data/project/<app>) must
surface as a project — its WorkingDirectory is proof it's a real app, even without a
.git/docker-compose marker and even outside the direct roots. Regression for the UAT
miss where such a folder never showed up.
"""

from app.correlator import correlate
from app.core.project_detector import ProjectDetector
from app.scanners.systemd import SystemdScanner


# ---- detector.register_project_from_dir ----

def _pd():
    # No filesystem walk (scan_roots empty); mirror the prod exclusion set.
    return ProjectDetector(
        projects_root="/nonexistent", scan_roots=[], direct_roots=[],
        exclude_paths=["/proc", "/sys", "/usr/lib", "/var/lib/docker", "/var/cache"],
    )


def test_register_promotes_app_under_arbitrary_top_level_dir():
    pd = _pd()
    assert pd.register_project_from_dir("/home/data/project/mdb-discovery") == "mdb-discovery"
    assert pd.project_paths()["mdb-discovery"] == "/home/data/project/mdb-discovery"
    # and now assets under it attribute correctly
    assert pd.get_project_from_path("/home/data/project/mdb-discovery/db") == "mdb-discovery"


def test_register_rejects_reserved_and_excluded_paths():
    pd = _pd()
    assert pd.register_project_from_dir("/") == "System"
    assert pd.register_project_from_dir("/opt") == "System"          # bare top-level dir
    assert pd.register_project_from_dir("/usr/lib/python3/x") == "System"  # system top
    assert pd.register_project_from_dir("/var/lib/docker/x") == "System"   # excluded tree
    assert pd.register_project_from_dir("relative/path") == "System"
    assert pd.list_projects() == []


def test_register_allows_opt_and_srv_children():
    pd = _pd()
    assert pd.register_project_from_dir("/opt/grafana") == "grafana"
    assert pd.register_project_from_dir("/srv/gitea") == "gitea"


# ---- systemd scanner uses it ----

def _unit_asset(pd, unit, show):
    sc = SystemdScanner(server_id="oci", project_detector=pd)
    sc._is_enabled = lambda n: True  # avoid a real `systemctl is-enabled` subprocess
    return sc._build_unit_asset(
        "service", "systemd_service", unit,
        load_state="loaded", active_state="active", sub_state="running", show=show,
    )


def test_systemd_service_workingdir_promotes_new_project():
    pd = _pd()
    asset = _unit_asset(pd, "mdb-discovery.service", {
        "FragmentPath": "/etc/systemd/system/mdb-discovery.service",  # unit file in /etc → System
        "WorkingDirectory": "/home/data/project/mdb-discovery",       # …but the app lives here
        "ExecStart": "", "UnitFileState": "enabled",
    })
    assert asset["project"] == "mdb-discovery"
    assert pd.project_paths().get("mdb-discovery") == "/home/data/project/mdb-discovery"


def test_systemd_system_service_stays_system():
    pd = _pd()
    # A real OS service: unit in /lib/systemd, working dir under a system tree.
    asset = _unit_asset(pd, "cloud-init.service", {
        "FragmentPath": "/lib/systemd/system/cloud-init.service",
        "WorkingDirectory": "/var/lib/cloud", "ExecStart": "/usr/bin/cloud-init",
    })
    assert asset["project"] == "System"
    assert "cloud" not in pd.list_projects() and "cloud-init.service" not in pd.list_projects()


def test_systemd_service_execstart_promotes_stripping_bin_venv():
    # No WorkingDirectory; the app dir is inferred from the ExecStart binary path,
    # walking past the venv/bin wrappers.
    pd = _pd()
    asset = _unit_asset(pd, "mdb-discovery.service", {
        "FragmentPath": "/etc/systemd/system/mdb-discovery.service",
        "WorkingDirectory": "",
        "ExecStart": "{ path=/home/data/project/mdb-discovery/venv/bin/python ; argv[]=... }",
    })
    assert asset["project"] == "mdb-discovery"
    assert pd.project_paths().get("mdb-discovery") == "/home/data/project/mdb-discovery"


def test_promoted_service_dir_becomes_a_correlator_bucket():
    pd = _pd()
    asset = _unit_asset(pd, "mdb-discovery.service", {
        "FragmentPath": "/etc/systemd/system/mdb-discovery.service",
        "WorkingDirectory": "/home/data/project/mdb-discovery", "ExecStart": "",
    })
    apps = {a["name"]: a for a in correlate(
        [asset], server_id="oci", projects_root="/nonexistent",
        project_dirs=pd.project_paths(),   # includes the just-registered dir
    )}
    assert "mdb-discovery" in apps
    assert apps["mdb-discovery"]["source"] == "/home/data/project/mdb-discovery"
    assert "mdb-discovery.service" in apps["mdb-discovery"]["systemd_units"]
