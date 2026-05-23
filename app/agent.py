"""InfraDocs V6 agent — orchestrates scanners and writes to MongoDB.

Usage:
    python -m app.agent scan          # full scan, replace existing assets
    python -m app.agent scan --incremental  # upsert only
    python -m app.agent status        # print DB stats
"""

import argparse
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.core.config_loader import load_config
from app.core.db_manager import DBManager
from app.core.logger import get_scan_logger, setup_logger
from app.core.project_detector import ProjectDetector
from app.scanners.registry import SCANNERS


def build_scanners(enabled: List[str], server_id: str, projects_root: str):
    pd = ProjectDetector(projects_root=projects_root)
    instances = []
    for name in enabled:
        cls = SCANNERS.get(name)
        if not cls:
            print(f"⚠  unknown scanner: {name} (skipping)")
            continue
        instances.append(cls(server_id=server_id, project_detector=pd))
    return instances


def run_scan(args):
    cfg = load_config(args.config)
    logger = get_scan_logger("manual")

    scanners = build_scanners(
        cfg.scanning.enabled_scanners,
        cfg.server.id,
        cfg.paths.projects_root,
    )
    print(f"✓ loaded {len(scanners)} scanners: {[s.scanner_name for s in scanners]}")

    db = DBManager(uri=cfg.mongodb.uri, database=cfg.mongodb.database)
    db.create_indexes()

    all_assets: List[Dict[str, Any]] = []
    per_scanner: List[Dict[str, Any]] = []
    start = datetime.now(timezone.utc)

    for sc in scanners:
        result = sc.execute()
        per_scanner.append(
            {
                "scanner": result["scanner"],
                "status": result["status"],
                "assets_found": result["assets_found"],
                "duration_seconds": result["duration_seconds"],
                "errors": result["errors"],
            }
        )
        all_assets.extend(result["assets"])

    if not args.incremental:
        deleted = db.delete_all_assets()
        logger.info(f"deleted {deleted} old assets (full scan)")

    written = 0
    for asset in all_assets:
        if db.upsert_asset(asset):
            written += 1

    duration = (datetime.now(timezone.utc) - start).total_seconds()
    status = "success" if all(r["status"] != "failed" for r in per_scanner) else "partial"

    db.insert_scan_log(
        {
            "scan_type": "incremental" if args.incremental else "full",
            "duration_seconds": duration,
            "total_assets": len(all_assets),
            "assets_written": written,
            "scanners": per_scanner,
            "status": status,
        }
    )

    print()
    print("=" * 63)
    print(f"📊 scan complete in {duration:.2f}s")
    print(f"  scanners: {len(scanners)}")
    print(f"  assets discovered: {len(all_assets)}")
    print(f"  assets written: {written}")
    failed = [r["scanner"] for r in per_scanner if r["status"] == "failed"]
    if failed:
        print(f"  ⚠ failed: {', '.join(failed)}")
    print(f"  status: {status}")
    print("=" * 63)

    if args.summary:
        print()
        print("📋 by category:")
        by_cat: Dict[str, int] = {}
        for a in all_assets:
            by_cat[a["category"]] = by_cat.get(a["category"], 0) + 1
        for cat, count in sorted(by_cat.items()):
            print(f"  • {cat}: {count}")
        print()
        print("📋 by project:")
        by_proj: Dict[str, int] = {}
        for a in all_assets:
            by_proj[a["project"]] = by_proj.get(a["project"], 0) + 1
        for proj, count in sorted(by_proj.items(), key=lambda x: -x[1]):
            print(f"  • {proj}: {count}")

    db.close()


def show_status(args):
    cfg = load_config(args.config)
    print(f"server: {cfg.server.name} ({cfg.server.id})")
    print(f"api_port: {cfg.server.api_port}")
    try:
        db = DBManager(uri=cfg.mongodb.uri, database=cfg.mongodb.database)
        stats = db.get_stats()
        print(f"mongo: connected to {stats['database']}")
        print(f"  assets: {stats['assets_count']}")
        print(f"  projects: {stats['projects_count']}")
        print(f"  scan_logs: {stats['scan_logs_count']}")
        db.close()
    except Exception as e:
        print(f"mongo: FAILED ({e})")


def main():
    parser = argparse.ArgumentParser(description="InfraDocs V6 agent")
    parser.add_argument("--config", default="config.yml")
    sub = parser.add_subparsers(dest="cmd")

    scan_p = sub.add_parser("scan")
    scan_p.add_argument("--incremental", action="store_true")
    scan_p.add_argument("--summary", action="store_true", default=True)

    sub.add_parser("status")

    args = parser.parse_args()
    if not args.cmd:
        args.cmd = "scan"
        args.incremental = False
        args.summary = True

    setup_logger("agent", log_file="logs/agent.log", level="INFO")

    if args.cmd == "scan":
        run_scan(args)
    elif args.cmd == "status":
        show_status(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
