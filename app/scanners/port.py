"""Port scanner — listening ports with PID→cwd project resolution.

V5's port scanner fell back to `process_name.title()` for project tagging
(the exact false-project bug V5 fought elsewhere). V6 instead reads
`/proc/<pid>/cwd` and runs the result through `ProjectDetector`, so a port
only gets a project name if its process is actually running from inside a
project directory.
"""

import os
import re
import subprocess
from typing import Any, Dict, List, Optional

from app.scanners.base import BaseScanner


class PortScanner(BaseScanner):
    @property
    def scanner_name(self) -> str:
        return "port"

    def scan(self) -> List[Dict[str, Any]]:
        try:
            result = subprocess.run(
                ["ss", "-tulpnH"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except Exception as e:
            self.add_error(f"ss command failed: {e}")
            return []

        assets: List[Dict[str, Any]] = []
        seen: set = set()

        for line in result.stdout.splitlines():
            parsed = self._parse_line(line)
            if not parsed:
                continue
            key = (parsed["protocol"], parsed["port"], parsed["local_address"])
            if key in seen:
                continue
            seen.add(key)

            project = self._project_for_pid(parsed["pid"])
            # Include local_address in asset_id so IPv4 / IPv6 listeners on the
            # same port get distinct docs (otherwise one upsert overwrites the other).
            assets.append(
                self.create_asset(
                    category="network_port",
                    asset_id=(
                        f"{self.server_id}:port:{parsed['protocol']}:"
                        f"{parsed['local_address']}"
                    ),
                    name=f"{parsed['port']}/{parsed['protocol']}",
                    status="listening",
                    project=project,
                    metadata={
                        "port": parsed["port"],
                        "protocol": parsed["protocol"],
                        "local_address": parsed["local_address"],
                        "process": parsed["process"],
                        "pid": parsed["pid"],
                    },
                    health_indicators={
                        "has_process": parsed["process"] != "unknown",
                    },
                )
            )
        return assets

    def _parse_line(self, line: str) -> Optional[Dict[str, Any]]:
        if "LISTEN" not in line and "UNCONN" not in line:
            return None
        parts = line.split()
        if len(parts) < 5:
            return None
        protocol = parts[0]
        local_address = parts[4]
        if ":" not in local_address:
            return None
        try:
            port = int(local_address.rsplit(":", 1)[1])
        except ValueError:
            return None

        process_name = "unknown"
        pid: Optional[int] = None
        proc_match = re.search(r'\("([^"]+)",pid=(\d+)', " ".join(parts[5:]))
        if proc_match:
            process_name = proc_match.group(1)
            pid = int(proc_match.group(2))

        return {
            "protocol": protocol,
            "port": port,
            "local_address": local_address,
            "process": process_name,
            "pid": pid,
        }

    def _project_for_pid(self, pid: Optional[int]) -> str:
        if pid is None:
            return "System"
        try:
            cwd = os.readlink(f"/proc/{pid}/cwd")
        except (OSError, PermissionError):
            return "System"
        return self.project_detector.get_project_from_path(cwd)
