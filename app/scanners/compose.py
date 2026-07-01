"""Docker Compose scanner — finds compose files across the configured scan roots.

Walks the SAME full-disk footprint as the project detector (projects_root +
direct_roots + scan_roots) so a compose app installed anywhere on disk is found,
not just under one home-relative folder. Shares the detector's traversal guards:
pseudo-fs / network-mount skipping, a bounded depth, and a wall-clock deadline so
a full-disk walk can never hang the scan.
"""

import time
from pathlib import Path
from typing import Any, Dict, List

import yaml

from app.core.project_detector import (
    DEFAULT_SCAN_TIMEOUT, _MAX_DEPTH, _SKIP_DIRS, _read_base, _skip_mountpoints,
    _to_real, _PSEUDO_DIRS,
)
from app.scanners.base import BaseScanner


COMPOSE_FILENAMES = (
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
)


class ComposeScanner(BaseScanner):
    @property
    def scanner_name(self) -> str:
        return "compose"

    def scan(self) -> List[Dict[str, Any]]:
        pd = self.project_detector
        roots = pd.discovery_roots()
        depth = min(getattr(pd, "scan_depth", 3), _MAX_DEPTH)
        self._skip_mounts = _skip_mountpoints()
        self._deadline = time.monotonic() + DEFAULT_SCAN_TIMEOUT

        assets: List[Dict[str, Any]] = []
        seen_dirs: set = set()   # a compose app is its dir; don't emit it twice
        found_any_root = False
        for root in roots:
            base = _read_base(root)   # host-mount translation in a container
            if base is None:
                continue
            found_any_root = True
            for path in self._walk(base, depth):
                real = _to_real(path)
                if str(real.parent) in seen_dirs:
                    continue
                seen_dirs.add(str(real.parent))
                try:
                    assets.append(self._parse_compose(path, real))
                except Exception as e:
                    self.add_error(f"parse {real}: {e}")
        if not found_any_root:
            self.add_error(f"no scan roots readable: {[str(r) for r in roots]}")
        return [a for a in assets if a is not None]

    def _walk(self, root: Path, depth: int):
        """Walk `root` (bounded depth, guarded) yielding compose files."""
        stack = [(root, 0)]
        while stack:
            if time.monotonic() > self._deadline:
                self.add_error(f"compose walk timed out under {_to_real(root)}")
                return
            current, lvl = stack.pop()
            try:
                entries = list(current.iterdir())
            except (PermissionError, OSError):
                continue
            for entry in entries:
                try:
                    is_dir = entry.is_dir()
                except OSError:
                    continue
                if is_dir:
                    real = _to_real(entry)
                    if (
                        entry.name in _SKIP_DIRS
                        or entry.name.startswith(".")
                        or str(real) in _PSEUDO_DIRS
                        or str(real) in self._skip_mounts
                    ):
                        continue
                    if lvl < depth:
                        stack.append((entry, lvl + 1))
                elif entry.name in COMPOSE_FILENAMES:
                    yield entry

    def _parse_compose(self, path: Path, real: Path) -> Dict[str, Any]:
        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}

        services = data.get("services") or {}
        volumes = data.get("volumes") or {}
        networks = data.get("networks") or {}

        project = self.project_detector.get_project_from_path(str(real))

        return self.create_asset(
            category="docker_compose",
            asset_id=f"{self.server_id}:compose:{real}",
            name=real.parent.name,
            status="configured",
            project=project,
            metadata={
                "file_path": str(real),
                "services": list(services.keys()),
                "services_count": len(services),
                "volumes_count": len(volumes),
                "networks_count": len(networks),
                "compose_version": data.get("version"),
            },
            health_indicators={
                "has_services": bool(services),
                "has_volumes": bool(volumes),
                "has_networks": bool(networks),
            },
        )
