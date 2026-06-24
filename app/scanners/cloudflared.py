"""Cloudflare Tunnel detector — exposure WITHOUT an open port.

cloudflared dials OUT to Cloudflare, so a service can be internet-reachable at a
public hostname with nothing listening publicly (this is how N150 is exposed).
Nginx-only exposure detection misses it entirely. We find cloudflared (systemd
unit / process / docker container) and parse its `ingress:` rules — each maps a
public hostname -> a local service. One `cloudflare_tunnel` asset per rule, marked
internet_exposed, so the correlator can attribute it to the app behind the service.

Read-only; never raises (BaseScanner contract).
"""

from __future__ import annotations

import glob
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from app.scanners.base import BaseScanner

CONFIG_GLOBS = [
    "/etc/cloudflared/*.yml",
    "/etc/cloudflared/*.yaml",
    "/root/.cloudflared/*.yml",
    str(Path.home() / ".cloudflared" / "*.yml"),
]
_SERVICE_PORT_RE = re.compile(r":(\d{2,5})\b")


def _running() -> bool:
    """Is cloudflared present (process or systemd unit)? Best-effort."""
    for cmd in (["pgrep", "-x", "cloudflared"], ["systemctl", "is-active", "cloudflared"]):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=5, check=False)
            if r.returncode == 0:
                return True
        except Exception:
            continue
    return False


def _config_files() -> List[str]:
    files: List[str] = []
    for pat in CONFIG_GLOBS:
        files.extend(glob.glob(pat))
    return sorted(set(files))


class CloudflaredScanner(BaseScanner):
    @property
    def scanner_name(self) -> str:
        return "cloudflared"

    def scan(self) -> List[Dict[str, Any]]:
        assets: List[Dict[str, Any]] = []
        present = _running()
        for cfg_file in _config_files():
            try:
                data = yaml.safe_load(Path(cfg_file).read_text()) or {}
            except Exception as e:
                self.add_error(f"parse {cfg_file}: {e}")
                continue
            tunnel = data.get("tunnel")
            for rule in data.get("ingress") or []:
                hostname = rule.get("hostname")
                if not hostname:  # the catch-all `service: http_status:404` rule
                    continue
                assets.append(self._make_asset(hostname, rule.get("service"),
                                                tunnel, cfg_file, present))
        return assets

    def _make_asset(self, hostname, service, tunnel, cfg_file, present) -> Dict[str, Any]:
        upstream_port = None
        if service:
            m = _SERVICE_PORT_RE.search(service)
            if m:
                upstream_port = int(m.group(1))
        project = self.project_detector.get_project_from_domain(hostname)
        return self.create_asset(
            category="cloudflare_tunnel",
            asset_id=f"{self.server_id}:cftunnel:{hostname}",
            name=hostname,
            status="active" if present else "configured",
            project=project,
            metadata={
                "hostname": hostname,
                "service": service,
                "upstream_port": upstream_port,
                "tunnel": tunnel,
                "config_file": cfg_file,
                "exposure_via": "cloudflare_tunnel",
            },
            health_indicators={
                "internet_exposed": True,
                "running": present,
            },
        )
