"""install.sh — UI onboarding path (end-to-end, with stubbed binaries).

The terminal installer forks at onboarding: CLI (prompts + enroll here) or UI (hand
off to the browser wizard). This drives the WHOLE script with `--onboard=ui` against
stub git/docker/curl/python on PATH (no network, no Docker, no real repo touched) and
asserts the UI path:
  - runs the SHARED bring-up — renders the .env and stands the Docker stack up, and
  - emits the wizard URL the operator opens, and
  - does NOT run any CLI onboarding prompt / enroll (no `complete`, no `check-*`).

The CLI path's own logic is covered by test_cli_install.py; this guards the fork.
"""

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INSTALL_SH = ROOT / "install.sh"


def _write_exe(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


@pytest.fixture
def sandbox(tmp_path):
    """A self-contained checkout + a PATH of stub binaries that record their calls."""
    if not shutil.which("bash"):
        pytest.skip("bash not available")

    deploy_dir = tmp_path / "infradocs"
    (deploy_dir / "app").mkdir(parents=True)
    (deploy_dir / "deploy" / "docker").mkdir(parents=True)
    (deploy_dir / ".git").mkdir()  # so install.sh takes the "update existing checkout" path
    # Minimal app package so `python -m app.cli_install render-env` runs for real.
    shutil.copy(ROOT / "app" / "__init__.py", deploy_dir / "app" / "__init__.py")
    shutil.copy(ROOT / "app" / "cli_install.py", deploy_dir / "app" / "cli_install.py")
    shutil.copy(ROOT / "deploy" / "docker" / "deploy.sh", deploy_dir / "deploy" / "docker" / "deploy.sh")
    # docker-compose.yml is only consumed by the (stubbed) docker CLI; a placeholder is fine.
    (deploy_dir / "deploy" / "docker" / "docker-compose.yml").write_text("services: {}\n")

    bindir = tmp_path / "bin"
    bindir.mkdir()
    calls = tmp_path / "calls.log"

    # git: no-op success (fetch/checkout/reset against the fake .git do nothing).
    _write_exe(bindir / "git", "#!/usr/bin/env bash\nexit 0\n")
    # docker: record the subcommand, succeed at everything (info, compose version/up/ps/down).
    _write_exe(
        bindir / "docker",
        f'#!/usr/bin/env bash\nprintf "docker %s\\n" "$*" >> "{calls}"\nexit 0\n',
    )
    # curl: health probes pass (-w '%{{http_code}}' -> 200); other calls return a placeholder.
    _write_exe(
        bindir / "curl",
        '#!/usr/bin/env bash\n'
        'for a in "$@"; do case "$a" in *http_code*) echo 200; exit 0;; esac; done\n'
        'echo 203.0.113.9\nexit 0\n',
    )
    # python3: record argv (so we can assert which subcommands ran), then exec the real one.
    _write_exe(
        bindir / "python3",
        f'#!/usr/bin/env bash\nprintf "python %s\\n" "$*" >> "{calls}"\n'
        f'exec "{sys.executable}" "$@"\n',
    )

    env = dict(os.environ)
    env["PATH"] = f"{bindir}:{env['PATH']}"
    env["HOME"] = str(tmp_path)
    env["INFRADOCS_DIR"] = str(deploy_dir)
    env["INFRADOCS_SERVER_ID"] = "ci-node"  # deterministic; avoids the node-id prompt
    return {"env": env, "deploy_dir": deploy_dir, "calls": calls}


def _run(sandbox, *args):
    return subprocess.run(
        ["bash", str(INSTALL_SH), *args],
        env=sandbox["env"],
        stdin=subprocess.DEVNULL,  # closed stdin: a stray onboarding prompt would EOF, not hang
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_ui_path_brings_stack_up_and_emits_url_without_cli_prompts(sandbox):
    r = _run(sandbox, "--onboard=ui")
    out = r.stdout + r.stderr
    assert r.returncode == 0, f"installer failed:\n{out}"

    calls = sandbox["calls"].read_text()

    # SHARED bring-up actually happened: config rendered + stack stood up.
    assert "render-env" in calls, "the .env was never rendered (shared bring-up skipped)"
    assert (sandbox["deploy_dir"] / "deploy" / "docker" / ".env").exists()
    assert "compose" in calls and " up" in calls, "the Docker stack was never started"

    # UI hand-off: the wizard URL is printed and the chosen path is named.
    assert "OPEN THE SETUP WIZARD" in out
    assert "http://localhost:8081" in out
    assert "UI" in out and "NOT yet configured" in out

    # The fork held: NO CLI onboarding ran — no enroll, no live primary/priority checks.
    assert "complete" not in calls, "UI path must not enroll via the CLI"
    assert "check-primary" not in calls and "check-priority" not in calls, \
        "UI path must not run the CLI's live checks"


def test_bad_onboard_value_is_rejected_before_building(sandbox):
    r = _run(sandbox, "--onboard=bogus")
    assert r.returncode != 0
    assert "invalid --onboard" in (r.stdout + r.stderr)
    # failed before standing anything up
    assert not sandbox["calls"].exists() or "compose" not in sandbox["calls"].read_text()
