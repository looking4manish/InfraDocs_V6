"""Project detection.

A "project" is a directory that owns assets. Projects are discovered from:
  - direct subfolders of each configured root (the classic single-root model),
  - a bounded filesystem scan for project markers (docker-compose.yml / .git)
    under those roots — so nested/scattered projects are found, and
  - Docker Compose working-dirs (passed in via `discovered`) — the exact host
    path of each compose app, wherever it lives.

Every project carries its full path, so scattered layouts (/data/x,
/home/data/project/y, …) are listed with their real location. Assets whose path
falls under a project's directory get that project (longest-prefix wins);
everything else is "System". Project names are NEVER inferred from service-name
prefixes (the V5 'cloud-init -> Cloud' bug).
"""

import os
from pathlib import Path
from typing import Dict, List, Optional

# In a container the host root is mounted here; read filesystem scans through it
# but record the REAL host path so it matches asset paths from docker/scanners.
_HOST_ROOT = os.environ.get("INFRADOCS_HOST_ROOT", "").rstrip("/")

_MARKERS = ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml", ".git")
_SKIP_DIRS = {
    "node_modules", "__pycache__", ".git", "venv", ".venv", "env", "vendor",
    "site-packages", ".cache", "dist", "build", "target", "backups",
}


def _read_base(root: Path) -> Optional[Path]:
    """Where to actually read `root` from. In a container (_HOST_ROOT set) ALWAYS go
    via /host — the container's own /data, /srv, … are not the host's. Native: direct."""
    if _HOST_ROOT:
        hp = Path(_HOST_ROOT + str(root))
        return hp if hp.exists() else None
    return root if root.exists() else None


def _to_real(p: Path) -> Path:
    """Strip the /host prefix so stored paths are the real host paths."""
    s = str(p)
    if _HOST_ROOT and s.startswith(_HOST_ROOT + "/"):
        return Path(s[len(_HOST_ROOT):])
    if _HOST_ROOT and s == _HOST_ROOT:
        return Path("/")
    return p


def attach_root_paths(applications: List[dict], project_paths: Dict[str, str]) -> None:
    """Tag each project's application doc with its full root path (for the UI)."""
    for app in applications:
        path = project_paths.get(app.get("name"))
        if path:
            app["root_path"] = path


def discover_docker_projects() -> Dict[str, str]:
    """name -> host working-dir for every Compose project Docker knows about."""
    out: Dict[str, str] = {}
    try:
        import docker  # local import: keep the detector usable without docker

        client = docker.from_env()
        for c in client.containers.list(all=True):
            labels = c.labels or {}
            proj = labels.get("com.docker.compose.project")
            wd = labels.get("com.docker.compose.project.working_dir")
            if proj and wd:
                out.setdefault(proj, wd)
            for m in c.attrs.get("Mounts", []) or []:
                src = m.get("Source")
                if proj and not wd and m.get("Type") == "bind" and src:
                    out.setdefault(proj, src)
    except Exception:
        pass
    return out


class ProjectDetector:
    DOMAIN_MAPPING = {
        "infra": "InfraDocs_V6",
        "chat": "openwebui",
        "openwebui": "openwebui",
        "rws": "raveuploader_rws",
        "dashboard": "OCI_Dashboard",
    }

    def __init__(
        self,
        projects_root: Optional[str] = None,
        scan_roots: Optional[List[str]] = None,
        scan_depth: int = 2,
        discovered: Optional[Dict[str, str]] = None,
    ):
        self.projects_root = Path(projects_root or "/home/msinha/projects")
        self._projects: Dict[str, Path] = {}  # name -> resolved dir

        # Dedicated root: every direct subfolder is a project (classic) + nested markers.
        self._discover_root(self.projects_root, scan_depth, direct=True)
        # Extra scan roots: ONLY marker-bearing dirs — don't turn every subfolder of a
        # broad root (e.g. /home) into a project.
        for r in scan_roots or []:
            self._discover_root(Path(r), scan_depth, direct=False)
        for name, path in (discovered or {}).items():
            self._add(name, Path(path))

    # ---- discovery ----
    def _add(self, name: str, path: Path) -> None:
        if not name:
            return
        try:
            path = path.resolve()
        except OSError:
            return
        # Keep the first path seen for a name (don't let a later root shadow it).
        self._projects.setdefault(name, path)

    def _discover_root(self, root: Path, depth: int, direct: bool = True) -> None:
        base = _read_base(root)   # read directly or via the container /host mount
        if base is None:
            return
        if direct:
            try:
                for d in base.iterdir():
                    if d.is_dir() and not d.name.startswith("."):
                        self._add(d.name, _to_real(d))   # classic: direct subfolder = project
            except OSError:
                pass
        self._marker_scan(base, depth)         # bounded hunt for (nested) project markers

    def _marker_scan(self, root: Path, depth: int) -> None:
        frontier = [(root, 0)]
        while frontier:
            d, lvl = frontier.pop()
            try:
                entries = list(d.iterdir())
            except OSError:
                continue
            names = {e.name for e in entries}
            if d != root and names.intersection(_MARKERS):
                self._add(d.name, _to_real(d))
                continue                  # a project marker → don't descend further
            if lvl < depth:
                for e in entries:
                    if e.is_dir() and not e.name.startswith(".") and e.name not in _SKIP_DIRS:
                        frontier.append((e, lvl + 1))

    # ---- queries ----
    def list_projects(self) -> List[str]:
        return list(self._projects.keys())

    def project_paths(self) -> Dict[str, str]:
        """name -> full path, for the UI to show where each project lives."""
        return {n: str(p) for n, p in self._projects.items()}

    def get_project_from_path(self, path: str) -> str:
        if not path:
            return "System"
        try:
            p = Path(path).resolve()
        except OSError:
            return "System"
        best, best_len = "System", -1
        for name, root in self._projects.items():
            if p == root or root in p.parents:
                if len(str(root)) > best_len:
                    best, best_len = name, len(str(root))
        if best != "System":
            return best
        # Fallback: the app is deployed outside its discovered dir but a path
        # component exactly matches a known project name — e.g. an nginx
        # `root /home/x/mxh/dist` while the mxh project lives in /data/mxh.
        parts = set(p.parts)
        for name in self._projects:
            if name in parts:
                return name
        return "System"

    def get_project_from_service_name(self, service_name: str, unit_file_path: str = "") -> str:
        if unit_file_path:
            return self.get_project_from_path(unit_file_path)
        return "System"

    def get_project_from_container(
        self,
        container_labels: dict,
        working_dir: str = "",
        bind_mounts: List[str] = None,
        container_name: str = "",
    ) -> str:
        compose_project = container_labels.get("com.docker.compose.project")
        if compose_project and compose_project in self._projects:
            return compose_project
        if working_dir:
            tagged = self.get_project_from_path(working_dir)
            if tagged != "System":
                return tagged
        for src in bind_mounts or []:
            tagged = self.get_project_from_path(src)
            if tagged != "System":
                return tagged
        if container_name and container_name in self._projects:
            return container_name
        return "System"

    def get_project_from_domain(self, domain: str) -> str:
        if not domain:
            return "System"
        subdomain = domain.lower().split(".")[0]
        candidate = self.DOMAIN_MAPPING.get(subdomain)
        if candidate and candidate in self._projects:
            return candidate
        return "System"
