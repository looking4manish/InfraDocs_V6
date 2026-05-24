"""Phase 7B — ports registry tests.

Unit tests use synthetic asset fixtures so we can drive every code path
deterministically.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ports_registry import build_ports_registry, probe


def _container(name, *, project="System", compose_project=None, host_ports=(), status="running"):
    return {
        "category": "docker_container",
        "asset_id": f"oci:container:{name}",
        "name": name,
        "status": status,
        "project": project,
        "metadata": {
            "compose_project": compose_project,
            "ports": [
                {"container_port": "8080/tcp", "host_port": str(hp), "host_ip": "0.0.0.0"}
                for hp in host_ports
            ],
        },
    }


def _port(port, *, proto="tcp", process="x", pid=1, project="System"):
    return {
        "category": "network_port",
        "asset_id": f"oci:port:{proto}:{port}",
        "name": f"{port}/{proto}",
        "status": "listening",
        "project": project,
        "metadata": {
            "port": port,
            "protocol": proto,
            "process": process,
            "pid": pid,
            "local_address": f"0.0.0.0:{port}",
        },
    }


def _nginx(name, *, listen_ports=(443, 80), upstream_port=None, url=None):
    return {
        "category": "nginx_server_block",
        "asset_id": f"oci:nginx:test:{name}:443",
        "name": name,
        "status": "configured",
        "project": "System",
        "metadata": {
            "listen_ports": list(listen_ports),
            "upstream_port": upstream_port,
            "url": url,
        },
    }


def _systemd(name, *, exec_start, project="System"):
    return {
        "category": "systemd_service",
        "asset_id": f"oci:service:{name}",
        "name": name,
        "status": "active",
        "project": project,
        "metadata": {
            "unit_type": "service",
            "exec_start": exec_start,
            "environment_keys": [],
        },
    }


VALID = ["System", "openwebui", "OCI_Dashboard", "raveuploader_rws", "InfraDocs_V6"]


def test_listening_port_is_in_use():
    """A `ss`-discovered port marks the row state=in_use."""
    rows = build_ports_registry(
        [_port(8000, process="python", pid=42, project="OCI_Dashboard")],
        server_id="oci",
        valid_projects=VALID,
    )
    assert len(rows) == 1
    r = rows[0]
    assert r["port"] == 8000
    assert r["state"] == "in_use"
    assert r["process"] == "python"
    assert r["pid"] == 42
    assert r["owner_project"] == "OCI_Dashboard"
    assert r["owner_app_id"] == "oci:app:OCI_Dashboard"
    assert {"kind": "listening", "source": "python"} in r["evidence_sources"]


def test_container_port_without_listening_is_declared():
    """Container port mapping with the container stopped → state=declared."""
    rows = build_ports_registry(
        [_container("openwebui", project="openwebui", host_ports=[3000], status="exited")],
        server_id="oci",
        valid_projects=VALID,
    )
    assert len(rows) == 1
    assert rows[0]["state"] == "declared"
    assert rows[0]["owner_project"] == "openwebui"


def test_running_container_marks_port_in_use():
    rows = build_ports_registry(
        [_container("openwebui", project="openwebui", host_ports=[3000], status="running")],
        server_id="oci",
        valid_projects=VALID,
    )
    assert rows[0]["state"] == "in_use"


def test_multi_evidence_dedupes_into_one_row():
    """Listener + container + nginx upstream for the same port = 1 row, 3 sources."""
    assets = [
        _port(3000, process="python"),
        _container("openwebui", project="openwebui", host_ports=[3000]),
        _nginx("chat.x.com", listen_ports=[443, 80], upstream_port=3000),
    ]
    rows = build_ports_registry(assets, server_id="oci", valid_projects=VALID)
    by_port = {(r["port"], r["protocol"]): r for r in rows}
    three_thousand = by_port[(3000, "tcp")]
    assert three_thousand["state"] == "in_use"
    kinds = {e["kind"] for e in three_thousand["evidence_sources"]}
    assert kinds == {"listening", "container", "nginx_upstream"}


def test_nginx_listen_ports_are_declared_at_minimum():
    """nginx listening on 80/443 adds those as registry rows."""
    rows = build_ports_registry(
        [_nginx("infra.x.com", listen_ports=[80, 443], upstream_port=8004)],
        server_id="oci",
        valid_projects=VALID,
    )
    by_port = {r["port"] for r in rows}
    assert {80, 443, 8004} <= by_port


def test_systemd_exec_start_picks_up_port_flag():
    """A systemd unit with --port 8004 in ExecStart contributes evidence."""
    rows = build_ports_registry(
        [_systemd(
            "infradocs-v6-api.service",
            exec_start="/usr/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8004",
            project="InfraDocs_V6",
        )],
        server_id="oci",
        valid_projects=VALID,
    )
    assert any(r["port"] == 8004 for r in rows)
    r = next(r for r in rows if r["port"] == 8004)
    assert r["owner_project"] == "InfraDocs_V6"
    assert {"kind": "systemd_exec", "source": "infradocs-v6-api.service"} in r["evidence_sources"]


def test_systemd_regex_does_not_match_timestamps():
    """The real bug we hit on live OCI: systemctl-show's start_time field
    contains :07, :36, etc. The regex must skip those."""
    exec_start = (
        "{ path=/usr/bin/python ; argv[]=/usr/bin/python -m foo ; "
        "ignore_errors=no ; start_time=[Sun 2026-05-24 16:07:36 UTC] ; "
        "stop_time=[n/a] ; pid=1234 ; code=(null) ; status=0/0 }"
    )
    rows = build_ports_registry(
        [_systemd("noisy.service", exec_start=exec_start)],
        server_id="oci",
        valid_projects=VALID,
    )
    # No real port flag → no rows
    assert rows == []


def test_port_id_is_stable_and_unique():
    """Same (port, proto) collapses into one row no matter how many sources."""
    assets = [_port(80), _port(80), _nginx("a", listen_ports=[80]), _nginx("b", listen_ports=[80])]
    rows = build_ports_registry(assets, server_id="oci", valid_projects=VALID)
    eighty = [r for r in rows if r["port"] == 80]
    assert len(eighty) == 1
    assert eighty[0]["port_id"] == "oci:port:tcp:80"


def test_owner_fallback_to_system_when_unknown_project():
    """A port tagged with a project that no longer exists falls back to System."""
    rows = build_ports_registry(
        [_port(9000, project="DeletedProject")],
        server_id="oci",
        valid_projects=VALID,  # DeletedProject not in this list
    )
    assert rows[0]["owner_project"] == "System"


def test_compose_project_takes_priority_over_asset_project_tag():
    """Container with compose_project=X but project=System routes to X."""
    rows = build_ports_registry(
        [_container("svc", project="System", compose_project="openwebui", host_ports=[7777])],
        server_id="oci",
        valid_projects=VALID,
    )
    assert rows[0]["owner_project"] == "openwebui"


# --------------------------- probe smoke tests ------------------------------


def test_probe_returns_full_range_with_states():
    """probe(8000, 8005) returns 6 rows even if nothing's listening."""
    rows = probe(8000, 8005, proto="tcp")
    assert len(rows) == 6
    for r in rows:
        assert r["port"] in range(8000, 8006)
        assert r["state"] in {"in_use", "free"}


def test_probe_marks_known_listener_in_use():
    """The API itself is listening on 8004 — probe should catch it."""
    rows = probe(8003, 8005, proto="tcp")
    by_port = {r["port"]: r for r in rows}
    # In any environment running the InfraDocs API on 8004, that port should
    # show as in_use. If the API is not running, this test will skip itself.
    if by_port[8004]["state"] == "free":
        import pytest
        pytest.skip("InfraDocs API not running on :8004 in this env")
    assert by_port[8004]["state"] == "in_use"
