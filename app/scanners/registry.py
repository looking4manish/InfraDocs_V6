"""Scanner registry — name → class mapping."""

from typing import Dict, Type

from app.scanners.base import BaseScanner
from app.scanners.compose import ComposeScanner
from app.scanners.cron import CronScanner
from app.scanners.docker import DockerScanner
from app.scanners.nginx import NginxScanner
from app.scanners.port import PortScanner
from app.scanners.storage import StorageScanner
from app.scanners.systemd import SystemdScanner


SCANNERS: Dict[str, Type[BaseScanner]] = {
    "systemd": SystemdScanner,
    "docker": DockerScanner,
    "compose": ComposeScanner,
    "nginx": NginxScanner,
    "port": PortScanner,
    "storage": StorageScanner,
    "cron": CronScanner,
}
