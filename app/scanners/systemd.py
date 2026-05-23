"""Systemd scanner — services and timers."""

import subprocess
from typing import Any, Dict, List

from app.scanners.base import BaseScanner


class SystemdScanner(BaseScanner):
    @property
    def scanner_name(self) -> str:
        return "systemd"

    def scan(self) -> List[Dict[str, Any]]:
        return self._scan_units("service") + self._scan_units("timer")

    def _scan_units(self, unit_type: str) -> List[Dict[str, Any]]:
        category = f"systemd_{unit_type}"
        assets: List[Dict[str, Any]] = []

        try:
            result = subprocess.run(
                [
                    "systemctl",
                    "list-units",
                    f"--type={unit_type}",
                    "--all",
                    "--no-pager",
                    "--plain",
                ],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except Exception as e:
            self.add_error(f"systemctl list-units {unit_type} failed: {e}")
            return assets

        for line in result.stdout.splitlines():
            parts = line.split(None, 4)
            if len(parts) < 4:
                continue
            unit_name = parts[0]
            if not unit_name.endswith(f".{unit_type}"):
                continue

            load_state, active_state, sub_state = parts[1], parts[2], parts[3]

            unit_file_path = self._get_unit_file_path(unit_name)
            project = self.project_detector.get_project_from_service_name(
                unit_name, unit_file_path
            )

            metadata = {
                "load_state": load_state,
                "active_state": active_state,
                "sub_state": sub_state,
                "unit_type": unit_type,
                "unit_file": unit_file_path or None,
            }
            health = {
                "loaded": load_state == "loaded",
                "active": active_state == "active",
            }
            if unit_type == "service":
                health["enabled"] = self._is_enabled(unit_name)

            assets.append(
                self.create_asset(
                    category=category,
                    asset_id=f"{self.server_id}:{unit_type}:{unit_name}",
                    name=unit_name,
                    status=active_state,
                    project=project,
                    metadata=metadata,
                    health_indicators=health,
                )
            )
        return assets

    def _get_unit_file_path(self, unit_name: str) -> str:
        try:
            result = subprocess.run(
                ["systemctl", "show", "-p", "FragmentPath", "--value", unit_name],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            return result.stdout.strip()
        except Exception:
            return ""

    def _is_enabled(self, unit_name: str) -> bool:
        try:
            result = subprocess.run(
                ["systemctl", "is-enabled", "--quiet", unit_name],
                capture_output=True,
                timeout=5,
                check=False,
            )
            return result.returncode == 0
        except Exception:
            return False
