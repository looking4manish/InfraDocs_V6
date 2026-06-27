"""Secondary-side federation agent — pull dispatched commands and run them.

Run on a secondary (cron / loop). It reads the secondary config the setup
wizard wrote (settings doc `_id="app"`: role=secondary, primary_url, join_token),
polls the primary for any commands queued against this server_id, executes each
via the local guarded actions dispatcher, and reports results back — all over
outbound requests, so it works behind NAT/CGNAT.

Usage:
    python -m app.federation_agent poll      # one claim/execute/report cycle
"""

import argparse
import sys

from app import federation as F
from app.core.config_loader import load_config
from app.core.db_manager import DBManager


def run_poll(args) -> int:
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

    """Primary-side: close out commands claimed but never reported (cron-friendly).

    Run this on the PRIMARY, not a secondary — it operates on the queue directly."""

    from app.api.routers.federation import reap_stale_commands

    cfg = load_config(args.config)

    db = DBManager(uri=cfg.mongodb.uri, database=cfg.mongodb.database)

    try:

        n = reap_stale_commands(db)

        print(f"reaped {n} stale command(s)")

        return 0

    finally:

        db.close()





def main():
    parser = argparse.ArgumentParser(description="InfraDocs federation agent (secondary)")
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
