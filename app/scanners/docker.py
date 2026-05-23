"""Docker scanner — containers, images, volumes, networks."""

from typing import Any, Dict, List

import docker
from docker.errors import DockerException

from app.scanners.base import BaseScanner


class DockerScanner(BaseScanner):
    @property
    def scanner_name(self) -> str:
        return "docker"

    def __init__(self, server_id, project_detector):
        super().__init__(server_id, project_detector)
        try:
            self.client = docker.from_env()
        except DockerException as e:
            self.add_error(f"docker daemon unreachable: {e}")
            self.client = None

    def scan(self) -> List[Dict[str, Any]]:
        if not self.client:
            return []
        return (
            self._scan_containers()
            + self._scan_images()
            + self._scan_volumes()
            + self._scan_networks()
        )

    def _scan_containers(self) -> List[Dict[str, Any]]:
        assets: List[Dict[str, Any]] = []
        try:
            containers = self.client.containers.list(all=True)
        except DockerException as e:
            self.add_error(f"list containers: {e}")
            return assets

        for c in containers:
            try:
                labels = c.labels or {}
                working_dir = c.attrs.get("Config", {}).get("WorkingDir", "")
                project = self.project_detector.get_project_from_container(
                    labels, working_dir
                )

                ports = []
                for cport, bindings in (c.ports or {}).items():
                    for b in bindings or []:
                        ports.append(
                            {
                                "container_port": cport,
                                "host_port": b.get("HostPort"),
                                "host_ip": b.get("HostIp", "0.0.0.0"),
                            }
                        )

                mounts = [
                    {
                        "type": m.get("Type"),
                        "source": m.get("Source"),
                        "destination": m.get("Destination"),
                        "mode": m.get("Mode"),
                    }
                    for m in c.attrs.get("Mounts", [])
                ]

                health = {
                    "running": c.status == "running",
                    "restarts": c.attrs.get("RestartCount", 0),
                    "has_health_check": "Healthcheck" in c.attrs.get("Config", {}),
                }
                health_state = c.attrs.get("State", {}).get("Health")
                if health_state:
                    health["health_status"] = health_state.get("Status")

                image_name = (
                    c.image.tags[0] if c.image.tags else c.image.id[:19]
                )

                assets.append(
                    self.create_asset(
                        category="docker_container",
                        asset_id=f"{self.server_id}:container:{c.id[:12]}",
                        name=c.name,
                        status=c.status,
                        project=project,
                        metadata={
                            "container_id": c.id[:12],
                            "image": image_name,
                            "labels": labels,
                            "ports": ports,
                            "mounts": mounts,
                            "network_mode": c.attrs.get("HostConfig", {}).get(
                                "NetworkMode"
                            ),
                            "created": c.attrs.get("Created"),
                            "started_at": c.attrs.get("State", {}).get("StartedAt"),
                        },
                        health_indicators=health,
                    )
                )
            except Exception as e:
                self.add_error(f"container {getattr(c, 'name', '?')}: {e}")
        return assets

    def _scan_images(self) -> List[Dict[str, Any]]:
        assets: List[Dict[str, Any]] = []
        try:
            images = self.client.images.list()
            in_use_ids = set()
            for c in self.client.containers.list(all=True):
                in_use_ids.add(c.image.id)
        except DockerException as e:
            self.add_error(f"list images: {e}")
            return assets

        for img in images:
            try:
                tags = img.tags or ["<none>"]
                in_use = img.id in in_use_ids
                assets.append(
                    self.create_asset(
                        category="docker_image",
                        asset_id=f"{self.server_id}:image:{img.id[:12]}",
                        name=tags[0],
                        status="in_use" if in_use else "unused",
                        project="System",
                        metadata={
                            "image_id": img.id[:19],
                            "tags": tags,
                            "size_mb": round(img.attrs.get("Size", 0) / 1024 / 1024, 2),
                            "created": img.attrs.get("Created"),
                            "architecture": img.attrs.get("Architecture"),
                            "os": img.attrs.get("Os"),
                        },
                        health_indicators={
                            "in_use": in_use,
                            "is_dangling": tags == ["<none>"],
                        },
                    )
                )
            except Exception as e:
                self.add_error(f"image {img.id[:12]}: {e}")
        return assets

    def _scan_volumes(self) -> List[Dict[str, Any]]:
        assets: List[Dict[str, Any]] = []
        try:
            volumes = self.client.volumes.list()
            in_use_names = set()
            for c in self.client.containers.list(all=True):
                for m in c.attrs.get("Mounts", []):
                    if m.get("Name"):
                        in_use_names.add(m["Name"])
        except DockerException as e:
            self.add_error(f"list volumes: {e}")
            return assets

        for v in volumes:
            try:
                labels = v.attrs.get("Labels") or {}
                project = self.project_detector.get_project_from_container(labels, "")
                in_use = v.name in in_use_names
                assets.append(
                    self.create_asset(
                        category="docker_volume",
                        asset_id=f"{self.server_id}:volume:{v.name}",
                        name=v.name,
                        status="in_use" if in_use else "unused",
                        project=project,
                        metadata={
                            "driver": v.attrs.get("Driver"),
                            "mountpoint": v.attrs.get("Mountpoint"),
                            "labels": labels,
                            "created": v.attrs.get("CreatedAt"),
                        },
                        health_indicators={"in_use": in_use},
                    )
                )
            except Exception as e:
                self.add_error(f"volume {v.name}: {e}")
        return assets

    def _scan_networks(self) -> List[Dict[str, Any]]:
        assets: List[Dict[str, Any]] = []
        try:
            networks = self.client.networks.list()
        except DockerException as e:
            self.add_error(f"list networks: {e}")
            return assets

        for n in networks:
            try:
                if n.name in {"bridge", "host", "none"} and not n.attrs.get(
                    "Containers"
                ):
                    continue
                labels = n.attrs.get("Labels") or {}
                project = self.project_detector.get_project_from_container(labels, "")
                connected = list((n.attrs.get("Containers") or {}).keys())
                ipam_cfg = (n.attrs.get("IPAM") or {}).get("Config") or [{}]
                first_cfg = ipam_cfg[0] if ipam_cfg else {}
                assets.append(
                    self.create_asset(
                        category="docker_network",
                        asset_id=f"{self.server_id}:network:{n.id[:12]}",
                        name=n.name,
                        status="active" if connected else "inactive",
                        project=project,
                        metadata={
                            "driver": n.attrs.get("Driver"),
                            "scope": n.attrs.get("Scope"),
                            "subnet": first_cfg.get("Subnet"),
                            "gateway": first_cfg.get("Gateway"),
                            "connected_containers": len(connected),
                            "labels": labels,
                            "created": n.attrs.get("Created"),
                        },
                        health_indicators={"has_containers": bool(connected)},
                    )
                )
            except Exception as e:
                self.add_error(f"network {n.name}: {e}")
        return assets
