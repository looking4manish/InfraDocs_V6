"""install.sh — onboarding fork + failure-class behaviour (end-to-end, stubbed binaries).

The terminal installer shares one bring-up, then forks at onboarding (UI wizard vs CLI:
primary / secondary / standalone). These tests drive the WHOLE script against stub
git/docker/curl/python/sleep on PATH — no network, no Docker, no real repo touched — and
assert the behaviour the live UAT exposed:

  * UI path stands the stack up + emits the wizard URL, no CLI prompts.
  * STANDALONE skips the reachable-address requirement, the peer/token prompts, and the
    reachability checks, and still configures the node.
  * An empty reachable address in primary/secondary mode RE-PROMPTS (it does not abort).
  * Quitting onboarding after a healthy bring-up leaves the stack UP (no teardown) and
    prints how to finish later.
  * A BRING-UP failure (stack never healthy) still tears the half-built stack down.

The pure config/validation logic is unit-tested in test_cli_install.py; the stub for the
`complete` / `check-*` subcommands here just lets us exercise install.sh's control flow.
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
    """A self-contained checkout + a PATH of stub binaries that record their calls.

    The python3 stub records argv then short-circuits the API-driven subcommands
    (`complete` -> OK, `check-*` -> rc from STUB_CHECK_*_RC) so no real API is needed;
    `render-env` still runs for real to write the .env. `sleep` is a no-op so the health
    wait-loops run instantly. `curl` health probes return STUB_HTTP_CODE (default 200).
    """
    if not shutil.which("bash"):
        pytest.skip("bash not available")

    deploy_dir = tmp_path / "infradocs"
    (deploy_dir / "app").mkdir(parents=True)
    (deploy_dir / "deploy" / "docker").mkdir(parents=True)
    (deploy_dir / ".git").mkdir()  # so install.sh takes the "update existing checkout" path
    shutil.copy(ROOT / "app" / "__init__.py", deploy_dir / "app" / "__init__.py")
    shutil.copy(ROOT / "app" / "cli_install.py", deploy_dir / "app" / "cli_install.py")
    shutil.copy(ROOT / "deploy" / "docker" / "deploy.sh", deploy_dir / "deploy" / "docker" / "deploy.sh")
    (deploy_dir / "deploy" / "docker" / "docker-compose.yml").write_text("services: {}\n")

    bindir = tmp_path / "bin"
    bindir.mkdir()
    calls = tmp_path / "calls.log"

    _write_exe(bindir / "git", "#!/usr/bin/env bash\nexit 0\n")
    _write_exe(bindir / "sleep", "#!/usr/bin/env bash\nexit 0\n")
    _write_exe(
        bindir / "docker",
        '#!/usr/bin/env bash\nprintf "docker %s\\n" "$*" >> "' + str(calls) + '"\nexit 0\n',
    )
    _write_exe(
        bindir / "curl",
        "#!/usr/bin/env bash\n"
        'for a in "$@"; do case "$a" in *http_code*) echo "${STUB_HTTP_CODE:-200}"; exit 0;; esac; done\n'
        "echo 203.0.113.9\nexit 0\n",
    )
    _write_exe(
        bindir / "python3",
        "#!/usr/bin/env bash\n"
        'args="$*"\n'
        'printf "python %s\\n" "$args" >> "' + str(calls) + '"\n'
        'case " $args " in\n'
        '  *" complete "*)       echo OK; exit 0 ;;\n'
        '  *" check-primary "*)  exit "${STUB_CHECK_PRIMARY_RC:-0}" ;;\n'
        '  *" check-priority "*) exit "${STUB_CHECK_PRIORITY_RC:-0}" ;;\n'
        "esac\n"
        'exec "' + sys.executable + '" "$@"\n',
    )

    env = dict(os.environ)
    env["PATH"] = f"{bindir}:{env['PATH']}"
    env["HOME"] = str(tmp_path)
    env["INFRADOCS_DIR"] = str(deploy_dir)
    env["INFRADOCS_SERVER_ID"] = "ci-node"  # deterministic; avoids the node-id prompt
    return {"env": env, "deploy_dir": deploy_dir, "calls": calls}


def _run(sandbox, *args, stdin_text="", extra_env=None):
    env = dict(sandbox["env"])
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", str(INSTALL_SH), *args],
        env=env,
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _calls(sandbox):
    return sandbox["calls"].read_text() if sandbox["calls"].exists() else ""


def _stack_up(out):
    assert "stack is up and healthy (API + Mongo + web)" in out


def _no_teardown(sandbox):
    assert "down" not in _calls(sandbox), "a healthy stack must NOT be torn down"


# ----------------------- UI path (unchanged) --------------------------------


def test_ui_path_brings_stack_up_and_emits_url_without_cli_prompts(sandbox):
    r = _run(sandbox, "--onboard=ui")
    out = r.stdout + r.stderr
    assert r.returncode == 0, f"installer failed:\n{out}"
    calls = _calls(sandbox)

    assert "render-env" in calls, "the .env was never rendered (shared bring-up skipped)"
    assert (sandbox["deploy_dir"] / "deploy" / "docker" / ".env").exists()
    assert "compose" in calls and " up" in calls, "the Docker stack was never started"

    assert "OPEN THE SETUP WIZARD" in out
    assert "http://localhost:8081" in out
    assert "UI" in out and "NOT yet configured" in out

    assert "complete" not in calls, "UI path must not enroll via the CLI"
    assert "check-primary" not in calls and "check-priority" not in calls


# ----------------------- FIX 1: standalone ----------------------------------


def test_standalone_skips_address_and_reachability_and_completes(sandbox):
    # No stdin at all: standalone needs no reachable address, no peers, no checks.
    r = _run(sandbox, "--onboard=cli", "--role=standalone")
    out = r.stdout + r.stderr
    assert r.returncode == 0, f"standalone install failed:\n{out}"
    calls = _calls(sandbox)

    _stack_up(out)
    assert "standalone node configured" in out and "no cluster" in out
    assert "standalone node ready" in out
    # It enrolled as standalone...
    assert "complete" in calls and "standalone" in calls
    # ...without ANY reachability/priority checks or a required-input prompt.
    assert "check-primary" not in calls and "check-priority" not in calls
    assert "or 'q' to finish later" not in out, "standalone must not prompt for onboarding input"
    _no_teardown(sandbox)


# ----------------------- FIX 2: recoverable onboarding errors ---------------


def test_empty_address_reprompts_instead_of_aborting(sandbox):
    # primary mode: first answer is an empty line, then a real address.
    r = _run(sandbox, "--onboard=cli", "--role=primary",
             stdin_text="\nhttp://node-a:8081\n")
    out = r.stdout + r.stderr
    assert r.returncode == 0, f"expected re-prompt + success, got:\n{out}"
    calls = _calls(sandbox)

    _stack_up(out)
    assert "this can't be empty" in out, "an empty address must RE-PROMPT"
    assert "node configured + joined" in out
    assert "complete" in calls
    _no_teardown(sandbox)  # the fat-fingered prompt cost a re-ask, never a rebuild


def test_quit_after_healthy_bringup_leaves_stack_up_with_resume_instructions(sandbox):
    # Operator types 'q' at the reachable-address prompt to bail out.
    r = _run(sandbox, "--onboard=cli", "--role=primary", stdin_text="q\n")
    out = r.stdout + r.stderr
    assert r.returncode == 0, f"quitting onboarding should exit cleanly, got:\n{out}"
    calls = _calls(sandbox)

    _stack_up(out)
    assert "finish onboarding later" in out.lower()
    assert "the stack is UP" in out
    # Resume instructions for BOTH paths.
    assert "install.sh --onboard=cli" in out
    assert "setup wizard" in out and "http://localhost:8081" in out
    # Bailing did not enroll and did not tear the stack down.
    assert "complete" not in calls
    _no_teardown(sandbox)


def test_bringup_failure_still_tears_down_half_built_stack(sandbox):
    # Stack never reports healthy -> this is a BRING-UP failure, teardown is correct.
    r = _run(sandbox, "--onboard=cli", "--role=standalone",
             extra_env={"STUB_HTTP_CODE": "000"})
    out = r.stdout + r.stderr
    assert r.returncode != 0, "an unhealthy bring-up must fail"
    assert "never became healthy" in out or "never became reachable" in out
    assert "down" in _calls(sandbox), "a half-built stack should be torn down"


# ----------------------- override validation --------------------------------


def test_bad_onboard_value_is_rejected_before_building(sandbox):
    r = _run(sandbox, "--onboard=bogus")
    assert r.returncode != 0
    assert "invalid --onboard" in (r.stdout + r.stderr)
    assert "compose" not in _calls(sandbox)


def test_bad_role_value_is_rejected_before_building(sandbox):
    r = _run(sandbox, "--onboard=cli", "--role=bogus")
    assert r.returncode != 0
    assert "invalid --role" in (r.stdout + r.stderr)
    assert "compose" not in _calls(sandbox)
