"""uninstall.sh — directory-removal correctness + honest reporting (end-to-end, stubbed).

Runs a COPY of the real uninstall.sh from inside a throwaway sandbox checkout — NEVER the
repo's own uninstall.sh targeting the repo — against stub docker/tailscale/sudo/apt-get on
PATH (sudo runs its args WITHOUT privilege, so real system paths can never be removed).
The two checkout trees (deploy dir + the outer clone the operator ran from) live under
tmp_path; INFRADOCS_DATA_ROOT too.
"""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REAL_UNINSTALL = ROOT / "uninstall.sh"


def _write_exe(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _make_checkout(path: Path) -> None:
    (path / "deploy" / "docker").mkdir(parents=True, exist_ok=True)
    (path / "deploy" / "docker" / ".env").write_text("ADMIN_PASSWORD=secret\nAPI_PORT=8090\n")
    (path / "deploy" / "docker" / "docker-compose.yml").write_text("services: {}\n")
    (path / "app").mkdir(exist_ok=True)
    (path / "app" / "marker.py").write_text("# app file\n")
    (path / "config.yml").write_text("paths: {}\n")
    (path / "install.sh").write_text("#!/usr/bin/env bash\necho installer\n")
    shutil.copy(REAL_UNINSTALL, path / "uninstall.sh")
    (path / "uninstall.sh").chmod(0o755)


@pytest.fixture
def sandbox(tmp_path):
    if not shutil.which("bash"):
        pytest.skip("bash not available")

    outer = tmp_path / "projects" / "infradocs"
    outer.mkdir(parents=True)
    _make_checkout(outer)
    deploy = tmp_path / "infradocs"
    deploy.mkdir()
    _make_checkout(deploy)
    data = tmp_path / "data_infradocs"
    (data / "mongo").mkdir(parents=True)

    bindir = tmp_path / "bin"
    bindir.mkdir()
    calls = tmp_path / "calls.log"

    def log_stub(name):
        _write_exe(bindir / name,
                   "#!/usr/bin/env bash\n" f'printf "{name} %s\\n" "$*" >> "{calls}"\nexit 0\n')

    for n in ("docker", "systemctl", "groupdel", "tailscale", "apt-get"):
        log_stub(n)
    _write_exe(bindir / "sudo", '#!/usr/bin/env bash\nexec "$@"\n')

    env = dict(os.environ)
    env["PATH"] = f"{bindir}:{env['PATH']}"
    env["HOME"] = str(tmp_path)
    env["INFRADOCS_DIR"] = str(deploy)
    env["INFRADOCS_DATA_ROOT"] = str(data)
    standalone = tmp_path / "uninstall_standalone.sh"
    shutil.copy(REAL_UNINSTALL, standalone)
    standalone.chmod(0o755)
    return {"env": env, "outer": outer, "deploy": deploy, "data": data, "calls": calls,
            "bin": bindir, "standalone": standalone, "tmp": tmp_path}


def _run(sandbox, *args, cwd=None, script=None, extra_env=None, stdin=""):
    env = dict(sandbox["env"])
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", str(script or (sandbox["outer"] / "uninstall.sh")), *args],
        cwd=str(cwd or sandbox["outer"]),
        env=env, input=stdin, capture_output=True, text=True, timeout=60,
    )


def _calls(sandbox):
    return sandbox["calls"].read_text() if sandbox["calls"].exists() else ""


def test_run_from_inside_outer_clone_removes_both_trees(sandbox):
    r = _run(sandbox, "--yes")
    out = r.stdout + r.stderr
    assert r.returncode == 0, out
    assert not sandbox["outer"].exists(), "the outer clone (CWD) must be gone — the reported bug"
    assert not sandbox["deploy"].exists(), "the deploy dir must be gone too"
    assert not sandbox["data"].exists()
    assert "clean" in out and "uninstalled" in out


def test_stack_teardown_runs_and_assets_swept(sandbox):
    r = _run(sandbox, "--yes")
    assert r.returncode == 0
    calls = _calls(sandbox)
    assert "compose" in calls and "down" in calls and "-v" in calls and "--remove-orphans" in calls
    assert "rmi" in calls and "infradocs-api:latest" in calls
    assert "volume rm" in calls and "docker_mongo_data" in calls


def test_all_flag_engine_purge_and_both_trees(sandbox):
    r = _run(sandbox, "--all", "--yes")
    calls = _calls(sandbox)
    assert "apt-get purge" in calls and "docker-ce" in calls and "docker.io" in calls
    assert "purge" in calls and "tailscale" in calls and "mongo:7" in calls
    assert not sandbox["outer"].exists() and not sandbox["deploy"].exists()


def test_outer_dir_not_a_checkout_is_not_removed(sandbox):
    (sandbox["outer"] / "install.sh").unlink()
    (sandbox["outer"] / "app" / "marker.py").unlink()
    (sandbox["outer"] / "app").rmdir()
    (sandbox["outer"] / "config.yml").unlink()
    shutil.rmtree(sandbox["outer"] / "deploy")
    r = _run(sandbox, "--yes")
    out = r.stdout + r.stderr
    assert r.returncode == 0, out
    assert sandbox["outer"].exists(), "a non-InfraDocs parent must NEVER be removed"
    assert not sandbox["deploy"].exists(), "the deploy dir is still removed"


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses directory permissions")
def test_unremovable_target_fails_loud_not_false_success(sandbox):
    locked = sandbox["tmp"] / "locked"
    locked.mkdir()
    dep = locked / "infradocs"
    _make_checkout(dep)
    env = {"INFRADOCS_DIR": str(dep)}
    os.chmod(locked, 0o555)
    try:
        r = _run(sandbox, "--yes", cwd=sandbox["tmp"], script=sandbox["standalone"], extra_env=env)
        out = r.stdout + r.stderr
        assert r.returncode != 0, "must NOT report success when a target survives"
        assert "could NOT remove" in out or "still present" in out
        assert "cd ~ && rm -rf" in out and str(dep) in out
        assert dep.exists()
    finally:
        os.chmod(locked, 0o755)


def test_keep_repo_leaves_both_trees_but_removes_env(sandbox):
    r = _run(sandbox, "--yes", "--keep-repo")
    assert r.returncode == 0, r.stdout + r.stderr
    assert sandbox["outer"].exists() and sandbox["deploy"].exists()
    assert not (sandbox["deploy"] / "deploy" / "docker" / ".env").exists()


def test_keep_config_and_keep_data(sandbox):
    r = _run(sandbox, "--yes", "--keep-repo", "--keep-config", "--keep-data")
    assert r.returncode == 0, r.stdout + r.stderr
    assert (sandbox["deploy"] / "deploy" / "docker" / ".env").exists()
    assert sandbox["data"].exists()


def test_idempotent_second_run_reports_nothing(sandbox):
    _run(sandbox, "--yes")
    r = _run(sandbox, "--yes", cwd=sandbox["tmp"], script=sandbox["standalone"])
    out = r.stdout + r.stderr
    assert r.returncode == 0, out
    assert "not installed here" in out and "nothing to remove" in out
    assert "removed built images" not in out


def test_refuses_catastrophic_deploy_dir(sandbox):
    r = _run(sandbox, "--yes", extra_env={"INFRADOCS_DIR": "/"})
    assert r.returncode != 0
    assert "refusing" in (r.stdout + r.stderr)
    assert sandbox["outer"].exists()


def test_refuses_catastrophic_data_root(sandbox):
    r = _run(sandbox, "--yes", extra_env={"INFRADOCS_DATA_ROOT": "/data"})
    assert r.returncode != 0
    assert "refusing" in (r.stdout + r.stderr)
    assert sandbox["outer"].exists() and sandbox["deploy"].exists()


def test_interactive_abort_changes_nothing(sandbox):
    r = _run(sandbox, stdin="n\n")
    assert r.returncode != 0
    assert "aborted" in (r.stdout + r.stderr)
    assert sandbox["outer"].exists() and sandbox["deploy"].exists() and sandbox["data"].exists()
    assert "compose" not in _calls(sandbox)
