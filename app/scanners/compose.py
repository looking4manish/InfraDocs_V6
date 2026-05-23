"""Docker Compose scanner — finds compose files under projects_root."""

from pathlib import Path
from typing import Any, Dict, List

import yaml

from app.scanners.base import BaseScanner


COMPOSE_FILENAMES = (
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
)

# Skip these directory names when walking — node_modules can hide thousands of
# stub compose.yml files that aren't real deployments.
SKIP_DIRS = {
    "node_modules",
    "venv",
    ".venv",
    ".git",
    "dist",
    "build",
    "__pycache__",
}


class ComposeScanner(BaseScanner):
    @property
    def scanner_name(self) -> str:
        return "compose"

    def scan(self) -> List[Dict[str, Any]]:
        root = self.project_detector.projects_root
        if not root.exists():
            self.add_error(f"projects_root not found: {root}")
            return []

        assets: List[Dict[str, Any]] = []
        for path in self._walk(root):
            try:
                assets.append(self._parse_compose(path))
            except Exception as e:
                self.add_error(f"parse {path}: {e}")
        return [a for a in assets if a is not None]

    def _walk(self, root: Path):
        """Walk projects_root yielding compose files, skipping noise dirs."""
        stack = [root]
        while stack:
            current = stack.pop()
            try:
                for entry in current.iterdir():
                    if entry.is_dir():
                        if entry.name in SKIP_DIRS or entry.name.startswith("."):
                            continue
                        stack.append(entry)
                    elif entry.is_file() and entry.name in COMPOSE_FILENAMES:
                        yield entry
            except (PermissionError, OSError):
                continue

    def _parse_compose(self, path: Path) -> Dict[str, Any]:
        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}

        services = data.get("services") or {}
        volumes = data.get("volumes") or {}
        networks = data.get("networks") or {}

        project = self.project_detector.get_project_from_path(str(path))

        return self.create_asset(
            category="docker_compose",
            asset_id=f"{self.server_id}:compose:{path}",
            name=path.parent.name,
            status="configured",
            project=project,
            metadata={
                "file_path": str(path),
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
