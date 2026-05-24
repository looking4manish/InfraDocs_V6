"""Storage scanner — mountpoints and usage."""

import subprocess
from typing import Any, Dict, List, Tuple

from app.scanners.base import BaseScanner


SKIP_SOURCES = {"tmpfs", "devtmpfs", "udev", "overlay", "squashfs"}


def _df_rows(byte_accurate: bool) -> List[Tuple[str, ...]]:
    """Run df with the requested unit (-h human, -B1 bytes) and parse rows."""
    flag = "-B1" if byte_accurate else "-h"
    try:
        result = subprocess.run(
            ["df", flag, "--output=source,target,size,used,avail,pcent,fstype"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return []
    rows = []
    for line in result.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 7:
            rows.append(tuple(parts[:7]))
    return rows


class StorageScanner(BaseScanner):
    @property
    def scanner_name(self) -> str:
        return "storage"

    def scan(self) -> List[Dict[str, Any]]:
        human_rows = _df_rows(byte_accurate=False)
        if not human_rows:
            self.add_error("df failed or returned no rows")
            return []

        byte_rows = _df_rows(byte_accurate=True)
        # Index byte-accurate rows by (source, target) so we can join.
        byte_idx = {(r[0], r[1]): r for r in byte_rows}

        assets: List[Dict[str, Any]] = []
        for source, target, size, used, avail, percent, fstype in human_rows:
            if source in SKIP_SOURCES or fstype in SKIP_SOURCES:
                continue
            if target.startswith("/snap/"):
                continue
            try:
                usage_pct = int(percent.rstrip("%"))
            except ValueError:
                usage_pct = 0

            # Byte-exact figures (used by Phase 7C storage registry).
            bs, bt, bu, ba = None, None, None, None
            br = byte_idx.get((source, target))
            if br:
                try:
                    bs = int(br[2])
                    bu = int(br[3])
                    ba = int(br[4])
                    bt = bs  # df reports size == total
                except (TypeError, ValueError):
                    pass

            project = self.project_detector.get_project_from_path(target)
            assets.append(
                self.create_asset(
                    category="storage_mount",
                    asset_id=f"{self.server_id}:mount:{target}",
                    name=target,
                    status="mounted",
                    project=project,
                    metadata={
                        "source": source,
                        "fstype": fstype,
                        "size": size,
                        "used": used,
                        "available": avail,
                        "usage_percent": usage_pct,
                        "size_bytes": bs,
                        "total_bytes": bt,
                        "used_bytes": bu,
                        "free_bytes": ba,
                    },
                    health_indicators={
                        "usage_percent": usage_pct,
                        "near_full": usage_pct >= 75,
                        "critical": usage_pct >= 90,
                    },
                )
            )
        return assets
