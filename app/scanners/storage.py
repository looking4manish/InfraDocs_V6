"""Storage scanner — mountpoints and usage."""

import subprocess
from typing import Any, Dict, List

from app.scanners.base import BaseScanner


SKIP_SOURCES = {"tmpfs", "devtmpfs", "udev", "overlay", "squashfs"}


class StorageScanner(BaseScanner):
    @property
    def scanner_name(self) -> str:
        return "storage"

    def scan(self) -> List[Dict[str, Any]]:
        try:
            result = subprocess.run(
                ["df", "-h", "--output=source,target,size,used,avail,pcent,fstype"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except Exception as e:
            self.add_error(f"df failed: {e}")
            return []

        assets: List[Dict[str, Any]] = []
        for line in result.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) < 7:
                continue
            source, target, size, used, avail, percent, fstype = parts[:7]
            if source in SKIP_SOURCES or fstype in SKIP_SOURCES:
                continue
            if target.startswith("/snap/"):
                continue
            try:
                usage_pct = int(percent.rstrip("%"))
            except ValueError:
                usage_pct = 0

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
                    },
                    health_indicators={
                        "usage_percent": usage_pct,
                        "near_full": usage_pct >= 75,
                        "critical": usage_pct >= 90,
                    },
                )
            )
        return assets
