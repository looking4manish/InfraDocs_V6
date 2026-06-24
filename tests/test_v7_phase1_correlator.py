"""V7 Phase 1 correlator tests — links[], containers_detail, nginx_detail,
hygiene, resilience.

Self-contained: builds synthetic assets inline; independent of phase-5 fixtures.
"""

from app.correlator import correlate


def _asset(category, name, project, metadata=None, health_indicators=None, status=None):
    a = {
        "category": category,
        "name": name,
        "project": project,
        "metadata": metadata or {},
    }
    if health_indicators is not None:
        a["health_indicators"] = health_indicators
    if status is not None:
        a["status"] = status
    return a


def _by_name(apps):
    return {a["name"]: a for a in apps}


def _run(assets, tmp_path, projects=("web",)):
    for p in projects:
        (tmp_path / p).mkdir(exist_ok=True)
    return _by_name(
        correlate(assets, server_id="test", projects_root=str(tmp_path))
    )


def test_container_link_via_compose_label(tmp_path):
    assets = [
        _asset(
            "docker_container", "web-app", "web",
            {"compose_project": "web", "running": True},
        )
    ]
    apps = _run(assets, tmp_path)
    links = apps["web"]["links"]
    assert {
        "src_kind": "docker_container", "src": "web-app",
        "dst_kind": "application", "dst": "web",
        "via": "compose_label", "pass": 2,
    } in links


def test_cert_links_to_app_via_nginx_domain(tmp_path):
    """A TLS cert is linked to the app whose nginx block serves its domain."""
    assets = [
        _asset("nginx_server_block", "web.example.com", "web",
               {"server_name": "web.example.com", "url": "https://web.example.com"}),
        _asset("tls_certificate", "web.example.com", "System",
               {"domains": ["web.example.com"],
                "cert_path": "/etc/letsencrypt/live/web.example.com/fullchain.pem",
                "not_after": "Aug 21 16:57:06 2099 GMT",
                "days_until_expiry": 200, "issuer": "LE"},
               status="valid"),
    ]
    apps = _run(assets, tmp_path)
    web = apps["web"]
    assert "web.example.com" in web["certificates"]
    assert any(c["name"] == "web.example.com" for c in web["certificates_detail"])
    assert {
        "src_kind": "tls_certificate", "src": "web.example.com",
        "dst_kind": "application", "dst": "web",
        "via": "nginx_domain", "pass": 6,
    } in web["links"]


def test_domain_matches_wildcard_rules():
    from app.correlator import _domain_matches
    assert _domain_matches("foo.example.com", "foo.example.com")
    assert _domain_matches("*.example.com", "foo.example.com")
    assert not _domain_matches("*.example.com", "example.com")     # apex not covered
    assert not _domain_matches("*.example.com", "a.b.example.com")  # only one label
    assert not _domain_matches("foo.example.com", "bar.example.com")


def test_shared_cert_file_links_to_all_using_apps(tmp_path):
    """Two apps' nginx blocks point at the SAME cert file -> cert linked to both
    (so a wildcard cert used across apps is flagged shared and never killed)."""
    cert_file = "/etc/letsencrypt/live/ocialwaysfree.site/fullchain.pem"
    assets = [
        _asset("nginx_server_block", "a.example.com", "web",
               {"server_name": "a.example.com", "ssl_certificate": cert_file}),
        _asset("nginx_server_block", "b.example.com", "api",
               {"server_name": "b.example.com", "ssl_certificate": cert_file}),
        _asset("tls_certificate", "ocialwaysfree.site", "System",
               {"domains": ["*.example.com"], "cert_path": cert_file}, status="valid"),
    ]
    apps = _run(assets, tmp_path, projects=("web", "api"))
    assert "ocialwaysfree.site" in apps["web"]["certificates"]
    assert "ocialwaysfree.site" in apps["api"]["certificates"]


def test_wildcard_san_fallback_when_no_cert_file(tmp_path):
    """No ssl_certificate file to match -> wildcard SAN matches the subdomain."""
    assets = [
        _asset("nginx_server_block", "foo.example.com", "web",
               {"server_name": "foo.example.com"}),
        _asset("tls_certificate", "wild", "System", {"domains": ["*.example.com"]}),
    ]
    apps = _run(assets, tmp_path)
    assert "wild" in apps["web"]["certificates"]


def test_container_link_via_project_dir_when_no_label(tmp_path):
    assets = [_asset("docker_container", "solo", "web", {"running": True})]
    apps = _run(assets, tmp_path)
    vias = {l["via"] for l in apps["web"]["links"]}
    assert "project_dir" in vias


def test_nginx_link_records_upstream_port_evidence(tmp_path):
    assets = [
        _asset(
            "docker_container", "web-app", "web",
            {
                "compose_project": "web", "running": True,
                "ports": [{"host_port": 8080, "container_port": "80/tcp"}],
            },
        ),
        _asset(
            "nginx_server_block", "web.example.com", "System",
            {"upstream_port": 8080, "url": "https://web.example.com"},
        ),
    ]
    apps = _run(assets, tmp_path)
    ng_links = [
        l for l in apps["web"]["links"]
        if l["src_kind"] == "nginx_server_block"
    ]
    assert len(ng_links) == 1
    assert ng_links[0]["via"] == "upstream_port:8080"
    assert ng_links[0]["pass"] == 6


def test_no_links_recorded_to_system_bucket(tmp_path):
    assets = [
        _asset("docker_container", "orphan", "System", {"running": True}),
        _asset("network_port", "22", "System", {"port": 22}),
        _asset("storage_mount", "/", "System", {}),
    ]
    apps = _run(assets, tmp_path)
    sys_app = apps["System"]
    app_links = [l for l in sys_app["links"] if l["dst_kind"] == "application"]
    assert app_links == []
    assert sys_app["containers"] == ["orphan"]


def test_container_to_port_link_emitted(tmp_path):
    assets = [
        _asset(
            "docker_container", "web-app", "web",
            {
                "compose_project": "web", "running": True,
                "ports": [{"host_port": 3000, "container_port": "8080/tcp"}],
            },
        )
    ]
    apps = _run(assets, tmp_path)
    assert {
        "src_kind": "docker_container", "src": "web-app",
        "dst_kind": "network_port", "dst": "3000",
        "via": "port_mapping", "pass": 2,
    } in apps["web"]["links"]


def test_links_deduped(tmp_path):
    pm = {"host_port": 3000, "container_port": "8080/tcp"}
    assets = [
        _asset(
            "docker_container", "web-app", "web",
            {"compose_project": "web", "running": True, "ports": [pm, pm]},
        )
    ]
    apps = _run(assets, tmp_path)
    port_links = [
        l for l in apps["web"]["links"] if l["dst_kind"] == "network_port"
    ]
    assert len(port_links) == 1


def test_containers_detail_populated(tmp_path):
    assets = [
        _asset(
            "docker_container", "web-app", "web",
            {
                "compose_project": "web",
                "compose_service": "app",
                "image": "nginx:1.25",
                "running": True,
                "restarts": 2,
                "restart_policy": "unless-stopped",
                "has_health_check": True,
                "started_at": "2026-06-01T00:00:00Z",
                "host_ports": [8080],
            },
        )
    ]
    apps = _run(assets, tmp_path)
    detail = apps["web"]["containers_detail"]
    assert len(detail) == 1
    d = detail[0]
    assert d["name"] == "web-app"
    assert d["image"] == "nginx:1.25"
    assert d["running"] is True
    assert d["restarts"] == 2
    assert d["restart_policy"] == "unless-stopped"
    assert d["has_health_check"] is True
    assert d["host_ports"] == [8080]
    assert d["compose_service"] == "app"


def test_restart_policy_dict_form_handled(tmp_path):
    assets = [
        _asset(
            "docker_container", "web-app", "web",
            {
                "compose_project": "web", "running": True,
                "restart_policy": {"Name": "always", "MaximumRetryCount": 0},
            },
        )
    ]
    apps = _run(assets, tmp_path)
    assert apps["web"]["containers_detail"][0]["restart_policy"] == "always"


def test_nginx_detail_populated(tmp_path):
    assets = [
        _asset(
            "docker_container", "web-app", "web",
            {
                "compose_project": "web", "running": True,
                "ports": [{"host_port": 8080, "container_port": "80/tcp"}],
            },
        ),
        _asset(
            "nginx_server_block", "web.example.com", "System",
            {
                "config_file": "/etc/nginx/sites-enabled/web.conf",
                "listen_ports": [443],
                "upstream_host": "localhost",
                "upstream_port": 8080,
                "has_ssl": True,
                "ssl_issuer": "Let's Encrypt",
                "ssl_not_after": "2026-09-01T00:00:00Z",
                "cloudflare_origin": False,
                "internet_exposed": True,
                "url": "https://web.example.com",
            },
        ),
    ]
    apps = _run(assets, tmp_path)
    detail = apps["web"]["nginx_detail"]
    assert len(detail) == 1
    d = detail[0]
    assert d["server_name"] == "web.example.com"
    assert d["listen_ports"] == [443]
    assert d["upstream_port"] == 8080
    assert d["has_ssl"] is True
    assert d["ssl_issuer"] == "Let's Encrypt"
    assert d["ssl_not_after"] == "2026-09-01T00:00:00Z"
    assert d["internet_exposed"] is True
    assert apps["web"]["internet_exposed"] is True


def test_exited_restart_always_flagged(tmp_path):
    assets = [
        _asset(
            "docker_container", "dead-app", "web",
            {
                "compose_project": "web",
                "running": False,
                "restart_policy": "always",
            },
        )
    ]
    apps = _run(assets, tmp_path)
    assert apps["web"]["hygiene"]["exited_restart_always"] == ["dead-app"]


def test_running_container_not_flagged(tmp_path):
    assets = [
        _asset(
            "docker_container", "live-app", "web",
            {"compose_project": "web", "running": True,
             "restart_policy": "always"},
        )
    ]
    apps = _run(assets, tmp_path)
    assert apps["web"]["hygiene"]["exited_restart_always"] == []


def test_dangling_and_unused_images_flagged(tmp_path):
    assets = [
        _asset(
            "docker_image", "<none>:<none>", "System",
            {"tags": ["<none>"], "is_dangling": True, "in_use": False},
        ),
        _asset(
            "docker_image", "old:1.0", "System",
            {"tags": ["old:1.0"], "is_dangling": False, "in_use": False},
        ),
    ]
    apps = _run(assets, tmp_path)
    hyg = apps["System"]["hygiene"]
    assert "<none>:<none>" in hyg["dangling_images"]
    assert "old:1.0" in hyg["unused_images"]


def test_orphaned_volume_flagged(tmp_path):
    assets = [
        _asset(
            "docker_volume", "stale_data", "web",
            {"compose_project": "web", "mountpoint": "/var/lib/x",
             "size_bytes": 10},
            health_indicators={"in_use": False},
        ),
        _asset(
            "docker_volume", "live_data", "web",
            {"compose_project": "web", "mountpoint": "/var/lib/y",
             "size_bytes": 10},
            health_indicators={"in_use": True},
        ),
    ]
    apps = _run(assets, tmp_path)
    assert apps["web"]["hygiene"]["orphaned_volumes"] == ["stale_data"]


def test_container_without_restart_policy_breaks_resilience(tmp_path):
    assets = [
        _asset(
            "docker_container", "fragile", "web",
            {"compose_project": "web", "running": True,
             "restart_policy": None},
        )
    ]
    apps = _run(assets, tmp_path)
    res = apps["web"]["resilience"]
    assert res["reboot_safe"] is False
    assert any("fragile" in i for i in res["issues"])


def test_disabled_unit_breaks_resilience(tmp_path):
    assets = [
        _asset(
            "systemd_service", "web-worker.service", "web",
            {"unit_file_state": "disabled"},
        )
    ]
    apps = _run(assets, tmp_path)
    res = apps["web"]["resilience"]
    assert res["reboot_safe"] is False
    assert any("web-worker.service" in i for i in res["issues"])


def test_healthy_app_is_reboot_safe(tmp_path):
    assets = [
        _asset(
            "docker_container", "solid", "web",
            {"compose_project": "web", "running": True,
             "restart_policy": "unless-stopped"},
        ),
        _asset(
            "systemd_service", "web-helper.service", "web",
            {"unit_file_state": "enabled"},
        ),
    ]
    apps = _run(assets, tmp_path)
    assert apps["web"]["resilience"]["reboot_safe"] is True
    assert apps["web"]["resilience"]["issues"] == []


def test_legacy_fields_unchanged_in_shape(tmp_path):
    assets = [
        _asset(
            "docker_container", "web-app", "web",
            {"compose_project": "web", "running": True,
             "ports": [{"host_port": 8080, "container_port": "80/tcp"}]},
        )
    ]
    apps = _run(assets, tmp_path)
    app = apps["web"]
    assert app["containers"] == ["web-app"]
    assert app["port_mappings"] == [
        {"host_port": 8080, "container": "web-app",
         "container_port": "80/tcp"}
    ]
    assert app["application_id"] == "test:app:web"
    assert isinstance(app["components_count"], int)


def test_live_shape_running_via_health_indicators(tmp_path):

    """Live scanner shape: running truth lives in health_indicators + top-level

    status, NOT in metadata. Guards the scanner<->correlator contract so the

    metadata-only read can't silently return (the openwebui exited bug)."""

    assets = [

        _asset(

            "docker_container", "live-app", "web",

            {"compose_project": "web", "restart_policy": "always"},

            health_indicators={"running": True},

            status="running",

        )

    ]

    apps = _run(assets, tmp_path)

    detail = apps["web"]["containers_detail"]

    assert detail[0]["running"] is True

    assert apps["web"]["hygiene"]["exited_restart_always"] == []

