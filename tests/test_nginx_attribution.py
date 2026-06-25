"""nginx blocks attribute to projects by served root (not just the domain map)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.project_detector import ProjectDetector
from app.scanners.nginx import NginxScanner


def test_static_site_attributed_by_root(tmp_path):
    proj = tmp_path / "mdb-discovery"
    proj.mkdir()
    pd = ProjectDetector(projects_root=str(tmp_path))
    sc = NginxScanner("oci", pd)

    block = f"""
    server {{
        listen 443 ssl;
        server_name discovery.mdbdemo.in;
        root {proj}/dist;
        index index.html;
    }}
    """
    asset = sc._parse_block(block, Path("/etc/nginx/sites-enabled/discovery.mdbdemo.in"))
    assert asset is not None
    assert asset["project"] == "mdb-discovery"        # NOT "System"
    assert asset["metadata"]["root"] == f"{proj}/dist"


def test_unknown_domain_no_root_stays_system(tmp_path):
    pd = ProjectDetector(projects_root=str(tmp_path))
    sc = NginxScanner("oci", pd)
    block = """
    server {
        listen 443 ssl;
        server_name random.example.com;
        proxy_pass http://127.0.0.1:9999;
    }
    """
    asset = sc._parse_block(block, Path("/etc/nginx/sites-enabled/random"))
    assert asset["project"] == "System"
