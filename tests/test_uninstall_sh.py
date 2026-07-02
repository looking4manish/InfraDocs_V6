"""uninstall.sh — clean teardown, no orphan assets (end-to-end, stubbed binaries).

Drives the real uninstall.sh against stub docker/tailscale/sudo/apt-get/systemctl on
PATH (no Docker, nothing on the real host touched — `sudo` is stubbed to run its args
WITHOUT privilege, so system paths can never actually be removed) with INFRADOCS_DIR /
INFRADOCS_DATA_ROOT pointed at throwaway temp dirs.
"""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
UNINSTALL_SH = ROOT / "uninstall.sh"


def _write_exe(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


@pytest.fixture
def sandbox(tmp_path):
    if not shutil.which("bash"):
        pytest.skip("bash not available")

    deploy = tmp_path / "infradocs"
    (deploy / "deploy" / "docker").mkdir(parents=True)
    (deploy / "deploy" / "docker" / ".env").write_text("ADMIN_PASSWORD=secret\nAPI_PORT=8090\n")
    (deploy / "deploy" / "docker" / "docker-compose.yml").write_text("services: {}\n")
    (deploy / "app").mkdir()
    (deploy / "app" / "marker.py").write_text("# app file\n")
    data = tmp_path / "data_infradocs"
    (data / "mongo").mkdir(parents=True)

    bindir = tmp_path / "bin"
    bindir.mkdir()
    calls = tmp_path / "calls.log"

    def log_stub(name, extra=""):
        _write_exe(
            bindir / name,
            "#!/usr/bin/env bash\n"
            f'printf "{name} %s\\n" "$*" >> "{calls}"\n' + extra + "exit 0\n",
        )

    # docker: log; `info` succeeds (no sudo); queries print nothing (no leftovers).
    log_stub("docker")
    log_stub("systemctl")
    log_stub("groupdel")
    log_stub("tailscale")
    log_stub("apt-get")  # log only — never touch real packages
    # sudo: run the (stubbed) command WITHOUT privilege — real system paths survive.
    _write_exe(bindir / "sudo", '#!/usr/bin/env bash\nexec "$@"\n')

    env = dict(os.environ)
    env["PATH"] = f"{bindir}:{env['PATH']}"
    env["HOME"] = str(tmp_path)
    env["INFRADOCS_DIR"] = str(deploy)
    env["INFRADOCS_DATA_ROOT"] = str(data)
    return {"env": env, "deploy": deploy, "data": data, "calls": calls, "bin": bindir}


def _run(sandbox, *args, extra_env=None, script=None):
    env = dict(sandbox["env"])
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", str(script or UNINSTALL_SH), *args],
        env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60,
    )


def _calls(sandbox):
    return sandbox["calls"].read_text() if sandbox["calls"].exists() else ""


def test_default_uninstall_removes_stack_images_data_and_checkout(sandbox):
    r = _run(sandbox, "--yes")
    out = r.stdout + r.stderr
    assert r.returncode == 0, out
    calls = _calls(sandbox)

    assert "compose" in calls and "down" in calls and "-v" in calls and "--remove-orphans" in calls
    assert "rmi" in calls and "infradocs-api:latest" in calls and "infradocs-web:latest" in calls
    assert "volume rm" in calls and "docker_mongo_data" in calls
    assert not sandbox["deploy"].exists(), "checkout must be removed"
    assert not sandbox["data"].exists(), "host data dir must be removed"
    assert "uninstalled" in out and "clean" in out
    # default keeps Docker: no engine purge
    assert "apt-get" not in calls


def test_all_flag_attempts_docker_and_tailscale_engine_removal(sandbox):
    r = _run(sandbox, "--all", "--yes")
    calls = _calls(sandbox)
    # Docker engine purge attempted (both package sets), daemon stopped, group dropped.
    assert "apt-get purge" in calls and "docker-ce" in calls and "docker.io" in calls
    assert "systemctl" in calls and "docker" in calls
    # Tailscale package removal attempted.
    assert "tailscale down" in calls or "apt-get purge" in calls
    assert "purge" in calls and "tailscale" in calls
    # base images targeted (--all implies --purge-images)
    assert "mongo:7" in calls
    # files still removed regardless
    assert not sandbox["deploy"].exists()
    assert not sandbox["data"].exists()


def test_reexec_from_inside_checkout_still_removes_it(sandbox):
    # Run the script FROM INSIDE the dir it will delete — it must copy itself out
    # (re-exec) and still remove the checkout completely.
    inside = sandbox["deploy"] / "uninstall.sh"
    shutil.copy(UNINSTALL_SH, inside)
    inside.chmod(0o755)
    r = _run(sandbox, "--yes", script=inside)
    out = r.stdout + r.stderr
    assert r.returncode == 0, out
    assert not sandbox["deploy"].exists(), "checkout must be fully removed even when run from inside it"


def test_keep_repo_leaves_checkout_but_removes_env(sandbox):
    r = _run(sandbox, "--yes", "--keep-repo")
    assert r.returncode == 0, r.stdout + r.stderr
    assert sandbox["deploy"].exists()
    assert not (sandbox["deploy"] / "deploy" / "docker" / ".env").exists()


def test_keep_config_and_keep_data_are_respected(sandbox):
    r = _run(sandbox, "--yes", "--keep-repo", "--keep-config", "--keep-data")
    assert r.returncode == 0, r.stdout + r.stderr
    assert (sandbox["deploy"] / "deploy" / "docker" / ".env").exists()
    assert sandbox["data"].exists()


def test_idempotent_when_nothing_installed(sandbox):
    _run(sandbox, "--yes")            # first pass removes everything
    r = _run(sandbox, "--yes")        # second pass: honestly reports nothing to do
    out = r.stdout + r.stderr
    assert r.returncode == 0, out
    assert "not installed here" in out and "nothing to remove" in out
    # it must NOT claim to have removed things that weren't there
    assert "removed built images" not in out


def test_refuses_catastrophic_deploy_dir(sandbox):
    r = _run(sandbox, "--yes", extra_env={"INFRADOCS_DIR": "/"})
    assert r.returncode != 0
    assert "refusing" in (r.stdout + r.stderr)
    assert "compose" not in _calls(sandbox)


def test_refuses_catastrophic_data_root(sandbox):
    r = _run(sandbox, "--yes", extra_env={"INFRADOCS_DATA_ROOT": "/data"})
    assert r.returncode != 0
    assert "refusing" in (r.stdout + r.stderr)
    assert sandbox["deploy"].exists()


def test_interactive_abort_changes_nothing(sandbox):
    r = subprocess.run(
        ["bash", str(UNINSTALL_SH)],
        env=sandbox["env"], input="n\n", capture_output=True, text=True, timeout=60,
    )
    assert r.returncode != 0
    assert "aborted" in (r.stdout + r.stderr)
    assert sandbox["deploy"].exists() and sandbox["data"].exists()
    assert "compose" not in _calls(sandbox)
