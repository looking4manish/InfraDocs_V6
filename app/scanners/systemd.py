"""Systemd scanner — services and timers."""

import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.scanners.base import BaseScanner


# Properties we ask `systemctl show` for in one shot — cheaper than N calls.
SYSTEMD_SHOW_PROPS = [
    "FragmentPath",
    "DropInPaths",
    "ExecStart",
    "WorkingDirectory",
    "User",
    "Group",
    "Environment",
    "EnvironmentFiles",
    "Restart",
    "Description",
    "UnitFileState",
]


def _parse_show_output(text: str) -> Dict[str, str]:
    out = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k] = v
    return out


def _env_keys_from_systemd(env_value: str) -> List[str]:
    """systemd's Environment= is space-separated KEY=VAL pairs (quoted as needed)."""
    if not env_value:
        return []
    keys = []
    # Simple tokenizer: split on whitespace not in quotes
    tokens = re.findall(r'(?:[^\s"]+|"[^"]*")+', env_value)
    for t in tokens:
        t = t.strip('"')
        if "=" in t:
            keys.append(t.split("=", 1)[0])
    return keys


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

            show = self._systemctl_show(unit_name)
            unit_file_path = show.get("FragmentPath", "")
            project = self.project_detector.get_project_from_service_name(
                unit_name, unit_file_path
            )
            # Also try resolving via WorkingDirectory / ExecStart if unit file
            # is in /etc/systemd but the binary lives in a project dir.
            # Only consider absolute paths — `!/root` and similar systemd
            # quoting prefixes are not real filesystem paths.
            if project == "System":
                working_dir = show.get("WorkingDirectory", "")
                if working_dir.startswith("/"):
                    project = self.project_detector.get_project_from_path(working_dir)
            if project == "System":
                exec_start = show.get("ExecStart", "")
                m = re.search(r"path=(/\S+)", exec_start)
                if m:
                    project = self.project_detector.get_project_from_path(m.group(1))

            metadata = {
                "load_state": load_state,
                "active_state": active_state,
                "sub_state": sub_state,
                "unit_type": unit_type,
                "unit_file": unit_file_path or None,
                "drop_in_paths": [
                    p for p in (show.get("DropInPaths") or "").split() if p
                ],
                "exec_start": show.get("ExecStart") or None,
                "working_directory": show.get("WorkingDirectory") or None,
                "user": show.get("User") or None,
                "group": show.get("Group") or None,
                "restart": show.get("Restart") or None,
                "unit_file_state": show.get("UnitFileState") or None,
                "description": show.get("Description") or None,
                "environment_keys": _env_keys_from_systemd(show.get("Environment") or ""),
                "environment_files": [
                    p for p in (show.get("EnvironmentFiles") or "").split() if p
                ],
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

    def _systemctl_show(self, unit_name: str) -> Dict[str, str]:
        try:
            result = subprocess.run(
                [
                    "systemctl",
                    "show",
                    "-p",
                    ",".join(SYSTEMD_SHOW_PROPS),
                    unit_name,
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            return _parse_show_output(result.stdout)
        except Exception:
            return {}

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
