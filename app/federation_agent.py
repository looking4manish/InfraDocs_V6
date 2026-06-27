"""Federation agent — the two scheduled cycles, role-guarded.

Both subcommands read this host's role from the settings doc (_id="app", written
by the setup wizard) and refuse to act on the wrong role. Nothing about the fleet
topology is hardcoded — the same binary ships everywhere and becomes a no-op on a
host that isn't playing the matching part.

Usage:
    python -m app.federation_agent poll      # SECONDARY: claim + run + report dispatched commands
    python -m app.federation_agent reap      # PRIMARY:  expire stale dispatched commands
"""

import argparse
import sys

from app import federation as F
from app.core.config_loader import load_config
from app.core.db_manager import DBManager


def run_poll(args) -> int:
    """Secondary side: claim queued commands, execute via the guarded dispatcher,
    report results back — all outbound, so it works behind NAT/CGNAT."""
    cfg = load_config(args.config)
    db = DBManager(uri=cfg.mongodb.uri, database=cfg.mongodb.database)
    try:
        s = db.db.settings.find_one({"_id": "app"}) or {}
        if s.get("role") != "secondary" or not s.get("primary_url") or not s.get("join_token"):
            print("not configured as a secondary "
                  "(need settings.role=secondary + primary_url + join_token)")
            return 1
        out = F.poll_and_execute(s["primary_url"], s["join_token"], cfg.server.id)
        print(f"executed {out['executed']} command(s): {out['results']}")
        return 0
    finally:
        db.close()


def run_reap(args) -> int:
    """Primary side: close out commands claimed but never reported (cron-friendly).

    Operates on the command queue directly, so it must run on the PRIMARY. Mirrors
    run_poll's role-guard: a non-primary host refuses and reaps nothing.
    """
    cfg = load_config(args.config)
    db = DBManager(uri=cfg.mongodb.uri, database=cfg.mongodb.database)
    try:
        s = db.db.settings.find_one({"_id": "app"}) or {}
        if s.get("role") != "primary":
            print("not configured as the primary "
                  "(need settings.role=primary) — refusing to reap")
            return 1
        from app.api.routers.federation import reap_stale_commands
        n = reap_stale_commands(db)
        print(f"reaped {n} stale command(s)")
        return 0
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="InfraDocs federation agent")
    parser.add_argument("--config", default="config.yml")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("poll")
    sub.add_parser("reap")

    args = parser.parse_args()
    if args.cmd in (None, "poll"):
        sys.exit(run_poll(args))
    if args.cmd == "reap":
        sys.exit(run_reap(args))
    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()
