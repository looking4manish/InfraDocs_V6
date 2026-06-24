"""Caddy reverse-proxy detector — the other common reverse proxy besides nginx.

Parses Caddyfile site blocks for their address(es) and `reverse_proxy` upstreams,
so a service fronted by Caddy is recognised as exposed (with its public hostname)
just like an nginx server block. Read-only; never raises.
"""

from __future__ import annotations

import glob
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.scanners.base import BaseScanner

CONFIG_GLOBS = [
    "/etc/caddy/Caddyfile",
    "/etc/caddy/*.caddy",
    "/etc/caddy/conf.d/*",
]
_PORT_RE = re.compile(r":(\d{2,5})\b")
# Address tokens that don't represent a public hostname.
_LOCAL_ADDR = ("localhost", "127.0.0.1", "::1")


def parse_caddyfile(text: str) -> List[Dict[str, Any]]:
    """Return [{addresses:[...], upstreams:[...]}] for each site block."""
    sites: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    depth = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        opens, closes = line.count("{"), line.count("}")
        if depth == 0 and opens and current is None:
            addr = line.split("{")[0].strip()
            if addr and not addr.startswith(("@", "(")):  # skip matchers/snippets/global
                current = {
                    "addresses": [a.strip() for a in addr.split(",") if a.strip()],
                    "upstreams": [],
                }
        if current is not None and "reverse_proxy" in line:
            after = line.split("reverse_proxy", 1)[1].split("{")[0].strip()
            current["upstreams"] += [
                u for u in after.split() if u and not u.startswith(("/", "@", "{"))
            ]
        depth += opens - closes
        if depth <= 0:
            if current:
                sites.append(current)
                current = None
            depth = 0
    if current:
        sites.append(current)
    return sites


class CaddyScanner(BaseScanner):
    @property
    def scanner_name(self) -> str:
        return "caddy"

    def scan(self) -> List[Dict[str, Any]]:
        assets: List[Dict[str, Any]] = []
        for cfg_file in self._config_files():
            try:
                text = Path(cfg_file).read_text(errors="replace")
            except OSError:
                continue
            for site in parse_caddyfile(text):
                for addr in site["addresses"]:
                    host = addr.split(":")[0]
                    if not host or host in _LOCAL_ADDR or addr.startswith(":"):
                        continue  # bare port / localhost — not public
                    assets.append(self._make_asset(host, site["upstreams"], cfg_file))
        return assets

    @staticmethod
    def _config_files() -> List[str]:
        files: List[str] = []
        for pat in CONFIG_GLOBS:
            files.extend(glob.glob(pat))
        return sorted(set(files))

    def _make_asset(self, host, upstreams, cfg_file) -> Dict[str, Any]:
        upstream_port = None
        for up in upstreams:
            m = _PORT_RE.search(up)
            if m:
                upstream_port = int(m.group(1))
                break
        return self.create_asset(
            category="caddy_site",
            asset_id=f"{self.server_id}:caddy:{host}",
            name=host,
            status="configured",
            project=self.project_detector.get_project_from_domain(host),
            metadata={
                "server_name": host,
                "upstreams": upstreams,
                "upstream_port": upstream_port,
                "config_file": cfg_file,
                "exposure_via": "caddy",
                "has_ssl": True,  # Caddy auto-provisions TLS for public hostnames
            },
            health_indicators={"internet_exposed": True},
        )
