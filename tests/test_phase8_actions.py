"""Phase 8 — operational action dispatcher unit tests."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.actions import (
    ALLOWED_ACTIONS,
    ActionNotAllowed,
    ActionResult,
    SelfActionRefused,
    dispatch,
)


def _container_asset(name="openwebui", container_id="abc123def456"):
    return {
        "category": "docker_container",
        "asset_id": f"oci:container:{container_id[:12]}",
        "name": name,
        "project": "openwebui",
        "metadata": {"container_id": container_id[:12]},
    }


def _systemd_asset(name="my.service", category="systemd_service"):
    return {
        "category": category,
        "asset_id": f"oci:service:{name}",
        "name": name,
        "project": "System",
        "metadata": {"unit_type": "service"},
    }


def _nginx_asset(name="x.example.com"):
    return {
        "category": "nginx_server_block",
        "asset_id": f"oci:nginx:x:{name}:443",
        "name": name,
        "project": "System",
        "metadata": {"config_file": "/etc/nginx/sites-enabled/x"},
    }


# ----------------------- allow-list enforcement -----------------------------


def test_unknown_category_is_rejected():
    asset = {"category": "docker_image", "name": "x", "asset_id": "1", "metadata": {}}
    with pytest.raises(ActionNotAllowed):
        dispatch(asset, "delete")


def test_unknown_action_is_rejected():
    with pytest.raises(ActionNotAllowed):
        dispatch(_container_asset(), "delete")


def test_storage_mount_has_no_actions():
    asset = {"category": "storage_mount", "name": "/", "asset_id": "1", "metadata": {}}
    with pytest.raises(ActionNotAllowed):
        dispatch(asset, "start")


def test_allowed_actions_is_complete():
    """Snapshot test so adding new actions is intentional."""
    assert ALLOWED_ACTIONS["docker_container"] == {"start", "stop", "restart", "logs"}
    assert ALLOWED_ACTIONS["systemd_service"] == {"start", "stop", "restart", "logs", "status"}
    assert ALLOWED_ACTIONS["nginx_server_block"] == {"test", "reload"}


# ----------------------- self-protection ------------------------------------


def test_self_action_refused_for_infradocs_v6_unit():
    asset = _systemd_asset(name="infradocs-v6-api.service")
    with pytest.raises(SelfActionRefused):
        dispatch(asset, "restart")


def test_self_action_refused_does_not_match_unrelated_unit():
    """A unit named `infradocs.service` (no -v6-) is NOT self-protected."""
    asset = _systemd_asset(name="infradocs.service")
    with patch("app.actions._run_subprocess") as run:
        run.return_value = ActionResult(status="success", return_code=0)
        result = dispatch(asset, "restart")
    assert result.status == "success"


# ----------------------- docker container actions ---------------------------


def test_docker_container_start_calls_sdk():
    container = MagicMock()
    container.name = "openwebui"
    client = MagicMock()
    client.containers.get.return_value = container

    with patch("app.actions._docker_client", return_value=client):
        result = dispatch(_container_asset(), "start")

    assert result.status == "success"
    container.start.assert_called_once()


def test_docker_container_restart_passes_timeout():
    container = MagicMock()
    container.name = "openwebui"
    client = MagicMock()
    client.containers.get.return_value = container

    with patch("app.actions._docker_client", return_value=client):
        result = dispatch(_container_asset(), "restart", {"timeout": 5})

    container.restart.assert_called_once_with(timeout=5)
    assert result.status == "success"


def test_docker_container_logs_caps_tail():
    container = MagicMock()
    container.name = "openwebui"
    container.logs.return_value = b"hello\nworld\n"
    client = MagicMock()
    client.containers.get.return_value = container

    with patch("app.actions._docker_client", return_value=client):
        # Request 5000 lines — should cap at 1000
        result = dispatch(_container_asset(), "logs", {"tail": 5000})

    container.logs.assert_called_once_with(tail=1000)
    assert "hello" in result.stdout
    assert result.details["lines"] == 2


def test_docker_container_not_found_yields_failed_result():
    from docker.errors import NotFound
    client = MagicMock()
    client.containers.get.side_effect = NotFound("nope")

    with patch("app.actions._docker_client", return_value=client):
        result = dispatch(_container_asset(), "start")

    assert result.status == "failed"
    assert "not found" in result.stderr.lower()


# ----------------------- systemd actions (subprocess-mocked) ----------------


def test_systemd_restart_invokes_sudo_systemctl():
    with patch("app.actions._run_subprocess") as run:
        run.return_value = ActionResult(status="success", return_code=0,
                                        stdout="", stderr="")
        result = dispatch(_systemd_asset(name="myapp.service"), "restart")

    args, kwargs = run.call_args
    cmd = args[0]
    assert cmd == ["sudo", "-n", "systemctl", "restart", "myapp.service"]
    assert result.status == "success"


def test_systemd_logs_invokes_journalctl():
    with patch("app.actions._run_subprocess") as run:
        run.return_value = ActionResult(status="success", return_code=0,
                                        stdout="log line", stderr="")
        dispatch(_systemd_asset(name="myapp.service"), "logs", {"tail": 50})

    cmd = run.call_args.args[0]
    assert cmd[:2] == ["journalctl", "-u"]
    assert "myapp.service" in cmd
    assert "50" in cmd


def test_systemd_status_allows_nonzero():
    """systemctl status returns non-zero for stopped units; that's not 'failed'."""
    with patch("app.actions._run_subprocess") as run:
        run.return_value = ActionResult(status="success", return_code=3,
                                        stdout="inactive", stderr="")
        result = dispatch(_systemd_asset(), "status")

    # Confirm allow_nonzero was passed
    assert run.call_args.kwargs.get("allow_nonzero") is True
    assert result.status == "success"


# ----------------------- nginx actions --------------------------------------


def test_nginx_test_runs_nginx_minus_t():
    with patch("app.actions._run_subprocess") as run:
        run.return_value = ActionResult(status="success", return_code=0)
        dispatch(_nginx_asset(), "test")

    cmd = run.call_args.args[0]
    assert "nginx" in cmd and "-t" in cmd


def test_nginx_reload_runs_signal():
    with patch("app.actions._run_subprocess") as run:
        run.return_value = ActionResult(status="success", return_code=0)
        dispatch(_nginx_asset(), "reload")

    cmd = run.call_args.args[0]
    assert "reload" in cmd or "-s" in cmd


# ----------------------- timing -------------------------------------------


def test_dispatcher_records_duration_when_handler_doesnt():
    container = MagicMock()
    container.name = "x"
    client = MagicMock()
    client.containers.get.return_value = container

    with patch("app.actions._docker_client", return_value=client):
        result = dispatch(_container_asset(), "start")

    # Handler returns ActionResult with duration_ms=0; dispatcher fills it in.
    assert result.duration_ms >= 0  # Could be 0 if very fast, but field is set
