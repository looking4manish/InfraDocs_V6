"""Blast-radius computation — shared + data-loss flagging."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.blast_radius import compute_blast_radius


def _app(name, **kw):
    base = {
        "name": name, "type": "project", "containers": [], "images": [],
        "volumes": [], "nginx_sites": [], "certificates": [], "systemd_units": [],
        "links": [{"via": "x"}],
    }
    base.update(kw)
    return base


def test_flags_shared_image_and_cert():
    web = _app("web", images=["nginx:latest"], certificates=["web.example.com"])
    api = _app("api", images=["nginx:latest"])  # shares the image
    plan = compute_blast_radius(web, [web, api])

    img = next(i for i in plan["items"] if i["category"] == "docker_image")
    assert img["shared"] is True and "api" in img["shared_with"]
    cert = next(i for i in plan["items"] if i["category"] == "tls_certificate")
    assert cert["shared"] is False  # cert not in api
    assert plan["summary"]["shared"] == 1
    assert any("SHARED" in w for w in plan["warnings"])


def test_flags_data_loss_items():
    web = _app(
        "web", volumes=[{"name": "web_data"}],
        project_dir="/home/x/projects/web", project_dir_size_bytes=1234,
    )
    plan = compute_blast_radius(web, [web])
    cats = {i["category"]: i for i in plan["items"]}
    assert cats["docker_volume"]["data_loss"] is True
    assert cats["project_directory"]["data_loss"] is True
    assert plan["summary"]["data_loss"] == 2


def test_self_protection_and_incompleteness_warning():
    sysapp = _app(
        "System", type="system", systemd_units=["infradocs-v6-api.service"],
    )
    plan = compute_blast_radius(sysapp, [sysapp])
    assert "infradocs-v6-api.service" in plan["protected"]

    bare = _app("ghost", links=[])  # no evidence at all
    plan2 = compute_blast_radius(bare, [bare])
    assert any("incomplete" in w for w in plan2["warnings"])
