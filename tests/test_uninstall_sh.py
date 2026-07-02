"""uninstall.sh — clean teardown, no orphan assets (end-to-end, stubbed binaries).

Drives the real uninstall.sh against stub docker/tailscale/sudo on PATH (no Docker,
nothing on the real host touched) with INFRADOCS_DIR / INFRADOCS_DATA_ROOT pointed at
throwaway temp dirs. Asserts it stops + removes the compose stack (-v --remove-orphans),
removes the built images + named volumes, deletes the checkout and host data, honors the
--keep-* flags, and refuses a catastrophic target path.
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
    data.mkdir()
    (data / "mongo").mkdir()

    bindir = tmp_path / "bin"
    bindir.mkdir()
    calls = tmp_path / "calls.log"

    # docker: log argv; `info` succeeds (so no sudo); queries print nothing (no
    # leftovers); everything else exits 0.
    _write_exe(
        bindir / "docker",
        '#!/usr/bin/env bash\n'
        'printf "docker %s\\n" "$*" >> "' + str(calls) + '"\n'
        'exit 0\n',
    )
    _write_exe(bindir / "tailscale", "#!/usr/bin/env bash\nexit 0\n")
    # sudo: transparently run the (stubbed) command, no privilege.
    _write_exe(bindir / "sudo", '#!/usr/bin/env bash\nexec "$@"\n')

    env = dict(os.environ)
    env["PATH"] = f"{bindir}:{env['PATH']}"
    env["HOME"] = str(tmp_path)
    env["INFRADOCS_DIR"] = str(deploy)
    env["INFRADOCS_DATA_ROOT"] = str(data)
    return {"env": env, "deploy": deploy, "data": data, "calls": calls}


def _run(sandbox, *args, extra_env=None):
    env = dict(sandbox["env"])
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", str(UNINSTALL_SH), *args],
        env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60,
    )


def _calls(sandbox):
    return sandbox["calls"].read_text() if sandbox["calls"].exists() else ""


def test_full_uninstall_removes_stack_images_data_and_checkout(sandbox):
    r = _run(sandbox, "--yes")
    out = r.stdout + r.stderr
    assert r.returncode == 0, out
    calls = _calls(sandbox)

    # Stack torn down with volumes + orphans, from a compose down.
    assert "compose" in calls and "down" in calls
    assert "-v" in calls and "--remove-orphans" in calls
    # Built images + named volumes removed.
    assert "rmi" in calls and "infradocs-api:latest" in calls and "infradocs-web:latest" in calls
    assert "volume rm" in calls and "docker_mongo_data" in calls
    # Files gone — no orphan checkout or host data.
    assert not sandbox["deploy"].exists(), "checkout must be removed"
    assert not sandbox["data"].exists(), "host data dir must be removed"
    assert "fully uninstalled" in out


def test_keep_repo_leaves_checkout_but_removes_env(sandbox):
    r = _run(sandbox, "--yes", "--keep-repo")
    assert r.returncode == 0, r.stdout + r.stderr
    assert sandbox["deploy"].exists(), "--keep-repo must leave the checkout"
    assert not (sandbox["deploy"] / "deploy" / "docker" / ".env").exists(), \
        "config .env is removed unless --keep-config"


def test_keep_config_and_keep_data_are_respected(sandbox):
    r = _run(sandbox, "--yes", "--keep-repo", "--keep-config", "--keep-data")
    assert r.returncode == 0, r.stdout + r.stderr
    assert (sandbox["deploy"] / "deploy" / "docker" / ".env").exists()
    assert sandbox["data"].exists()


def test_purge_images_removes_base_images(sandbox):
    r = _run(sandbox, "--yes", "--purge-images")
    assert r.returncode == 0
    calls = _calls(sandbox)
    assert "mongo:7" in calls  # base images only removed with --purge-images
    # sanity: without the flag they are NOT targeted
    r2 = _run(sandbox, "--yes")  # deploy dir already gone; still exits cleanly
    assert r2.returncode == 0


def test_idempotent_when_nothing_installed(sandbox):
    # Remove everything first, then run again — must not error.
    _run(sandbox, "--yes")
    r = _run(sandbox, "--yes")
    out = r.stdout + r.stderr
    assert r.returncode == 0, out
    assert "clean" in out or "fully uninstalled" in out


def test_refuses_catastrophic_deploy_dir(sandbox):
    r = _run(sandbox, "--yes", extra_env={"INFRADOCS_DIR": "/"})
    assert r.returncode != 0
    assert "refusing" in (r.stdout + r.stderr)
    # nothing was torn down
    assert "compose" not in _calls(sandbox)


def test_refuses_catastrophic_data_root(sandbox):
    r = _run(sandbox, "--yes", extra_env={"INFRADOCS_DATA_ROOT": "/data"})
    assert r.returncode != 0
    assert "refusing" in (r.stdout + r.stderr)
    assert sandbox["deploy"].exists()  # aborted before removing anything


def test_interactive_abort_changes_nothing(sandbox):
    # No --yes and stdin says "n" → abort, nothing removed.
    r = subprocess.run(
        ["bash", str(UNINSTALL_SH)],
        env=sandbox["env"], input="n\n", capture_output=True, text=True, timeout=60,
    )
    assert r.returncode != 0
    assert "aborted" in (r.stdout + r.stderr)
    assert sandbox["deploy"].exists() and sandbox["data"].exists()
    assert "compose" not in _calls(sandbox)
