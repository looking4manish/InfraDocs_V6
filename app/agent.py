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
import uuid
from app.core.project_detector import (
    ProjectDetector, attach_root_paths, discover_docker_projects,
)
from app.correlator import SYSTEM_BUCKET, correlate
from app.ports_registry import build_ports_registry
from app.scanners.registry import SCANNERS
from app.storage_registry import build_storage_registry


def audit_ownership(
    assets: List[Dict[str, Any]],
    valid_projects: List[str],
) -> Dict[str, Any]:
    """Verify the Phase 7 ownership invariant on a freshly scanned asset set.

    Every asset must carry a non-empty `project` that is either the literal
    string "System" or one of the discovered project folder names. Returns a
    report with counts and any offenders (does not raise).
    """
    valid = set(valid_projects) | {SYSTEM_BUCKET}
    missing: List[Dict[str, str]] = []
    unknown: List[Dict[str, str]] = []
    by_project: Dict[str, int] = {}

    for a in assets:
        proj = a.get("project")
        if not proj:
            missing.append({"asset_id": a.get("asset_id", "?"), "category": a.get("category", "?")})
            continue
        by_project[proj] = by_project.get(proj, 0) + 1
        if proj not in valid:
            unknown.append(
                {
                    "asset_id": a.get("asset_id", "?"),
                    "category": a.get("category", "?"),
                    "project": proj,
                }
            )

    return {
        "total_assets": len(assets),
        "missing_project": missing,
        "unknown_project": unknown,
        "by_project": by_project,
        "ok": not missing and not unknown,
    }


def run_scan(args):
    cfg = load_config(args.config)
    logger = get_scan_logger("manual")

    pd = ProjectDetector(
        projects_root=cfg.paths.projects_root,
        scan_roots=cfg.paths.scan_roots,
        scan_depth=cfg.paths.scan_depth,
        discovered=discover_docker_projects(),
    )
    scanners = []
    for name in cfg.scanning.enabled_scanners:
        cls = SCANNERS.get(name)
        if not cls:
            print(f"⚠  unknown scanner: {name} (skipping)")
            continue
        scanners.append(cls(server_id=cfg.server.id, project_detector=pd))
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

    audit = audit_ownership(all_assets, pd.list_projects())
    if not audit["ok"]:
        logger.warning(
            "ownership audit found issues: %d missing, %d unknown",
            len(audit["missing_project"]),
            len(audit["unknown_project"]),
        )
        for offender in audit["missing_project"][:10]:
            logger.warning("missing project on %s", offender)
        for offender in audit["unknown_project"][:10]:
            logger.warning("unknown project on %s", offender)

    if not args.incremental:
        deleted = db.delete_all_assets()
        logger.info(f"deleted {deleted} old assets (full scan)")

    written = 0
    for asset in all_assets:
        if db.upsert_asset(asset):
            written += 1

    # Application correlation: join raw assets into application docs.
    applications = correlate(
        all_assets,
        server_id=cfg.server.id,
        projects_root=cfg.paths.projects_root,
    )
    attach_root_paths(applications, pd.project_paths())
    apps_written = db.replace_applications(applications)

    # Ports registry (Phase 7B) — evidence-based port inventory.
    ports = build_ports_registry(
        all_assets,
        server_id=cfg.server.id,
        valid_projects=pd.list_projects() + [SYSTEM_BUCKET],
    )
    ports_written = db.replace_ports(ports)

    # Storage registry (Phase 7C) — mounts + volumes + project trees + binds.
    storage_rows = build_storage_registry(
        all_assets,
        server_id=cfg.server.id,
        projects_root=cfg.paths.projects_root,
        valid_projects=pd.list_projects() + [SYSTEM_BUCKET],
    )
    storage_written = db.replace_storage(storage_rows)

    duration = (datetime.now(timezone.utc) - start).total_seconds()
    status = "success" if all(r["status"] != "failed" for r in per_scanner) else "partial"

    db.insert_scan_log(
        {
            "scan_id": uuid.uuid4().hex,
            "started_at": start,
            "finished_at": datetime.now(timezone.utc),
            "scan_type": "incremental" if args.incremental else "full",
            "duration_seconds": duration,
            "total_assets": len(all_assets),
            "assets_written": written,
            "applications_built": apps_written,
            "ports_registered": ports_written,
            "storage_registered": storage_written,
            "scanners": per_scanner,
            "ownership_audit": {
                "ok": audit["ok"],
                "missing_count": len(audit["missing_project"]),
                "unknown_count": len(audit["unknown_project"]),
                "by_project": audit["by_project"],
            },
            "status": status,
        }
    )

    print()
    print("=" * 63)
    print(f"📊 scan complete in {duration:.2f}s")
    print(f"  scanners: {len(scanners)}")
    print(f"  assets discovered: {len(all_assets)}")
    print(f"  assets written: {written}")
    print(f"  applications correlated: {apps_written}")
    print(f"  ports registered: {ports_written}")
    print(f"  storage entities registered: {storage_written}")
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
        for proj, count in sorted(audit["by_project"].items(), key=lambda x: -x[1]):
            print(f"  • {proj}: {count}")
        print()
        print(f"📋 ownership audit: {'✓ OK' if audit['ok'] else '⚠ ISSUES'}")
        if audit["missing_project"]:
            print(f"  • {len(audit['missing_project'])} assets missing project field")
        if audit["unknown_project"]:
            print(f"  • {len(audit['unknown_project'])} assets with unknown project")

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
