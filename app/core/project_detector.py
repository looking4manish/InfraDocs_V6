"""Project detection helper.

Centralized logic for tagging assets with their owning project.
Only assets under projects_root/* receive a project name; everything else
is "System". This eliminates the false-project bug V5 hit (cloud-init.service
becoming a "Cloud" project, etc.) by refusing to infer projects from
service-name prefixes.
"""

from pathlib import Path
from typing import List


class ProjectDetector:
    DOMAIN_MAPPING = {
        "infra": "InfraDocs_V6",
        "chat": "openwebui",
        "openwebui": "openwebui",
        "rws": "raveuploader_rws",
        "dashboard": "OCI_Dashboard",
    }

    def __init__(self, projects_root: str = "/home/msinha/projects"):
        self.projects_root = Path(projects_root)
        self._project_dirs = self._scan_projects()

    def _scan_projects(self) -> List[str]:
        if not self.projects_root.exists():
            return []
        return [
            d.name
            for d in self.projects_root.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        ]

    def list_projects(self) -> List[str]:
        return list(self._project_dirs)

    def get_project_from_path(self, path: str) -> str:
        if not path:
            return "System"
        try:
            path_obj = Path(path).resolve()
            rel = path_obj.relative_to(self.projects_root)
            project = rel.parts[0] if rel.parts else None
            if project and project in self._project_dirs:
                return project
        except (ValueError, OSError):
            pass
        return "System"

    def get_project_from_service_name(
        self, service_name: str, unit_file_path: str = ""
    ) -> str:
        if unit_file_path:
            return self.get_project_from_path(unit_file_path)
        return "System"

    def get_project_from_container(
        self, container_labels: dict, working_dir: str = ""
    ) -> str:
        compose_project = container_labels.get("com.docker.compose.project")
        if compose_project and compose_project in self._project_dirs:
            return compose_project
        if working_dir:
            return self.get_project_from_path(working_dir)
        return "System"

    def get_project_from_domain(self, domain: str) -> str:
        if not domain:
            return "System"
        subdomain = domain.lower().split(".")[0]
        candidate = self.DOMAIN_MAPPING.get(subdomain)
        if candidate and candidate in self._project_dirs:
            return candidate
        return "System"
