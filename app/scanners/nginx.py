"""Nginx scanner — server blocks with brace-aware parsing.

V5 used a naive regex (`server\\s*\\{([^}]+)\\}`) that breaks on real
configs because nginx server blocks contain nested `location { ... }`
blocks. V6 uses a brace-balanced extractor that handles arbitrary nesting.
"""

import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.scanners.base import BaseScanner


NGINX_CONFIG_DIRS = (
    Path("/etc/nginx/sites-enabled"),
    Path("/etc/nginx/conf.d"),
)


class NginxScanner(BaseScanner):
    @property
    def scanner_name(self) -> str:
        return "nginx"

    def scan(self) -> List[Dict[str, Any]]:
        if not shutil.which("nginx"):
            return []

        assets: List[Dict[str, Any]] = []
        for cfg_dir in NGINX_CONFIG_DIRS:
            if not cfg_dir.exists():
                continue
            try:
                entries = list(cfg_dir.iterdir())
            except PermissionError as e:
                self.add_error(f"cannot read {cfg_dir}: {e}")
                continue

            for entry in entries:
                if entry.is_file() or entry.is_symlink():
                    assets.extend(self._parse_file(entry))
        return assets

    def _parse_file(self, path: Path) -> List[Dict[str, Any]]:
        try:
            content = path.read_text()
        except (OSError, UnicodeDecodeError) as e:
            self.add_error(f"read {path}: {e}")
            return []

        # Strip comments so they don't poison the brace counter
        content = re.sub(r"#[^\n]*", "", content)

        assets: List[Dict[str, Any]] = []
        for block in self._iter_server_blocks(content):
            asset = self._parse_block(block, path)
            if asset:
                assets.append(asset)
        return assets

    def _iter_server_blocks(self, content: str):
        """Yield the contents of each top-level `server { ... }` block."""
        i = 0
        n = len(content)
        while i < n:
            m = re.search(r"\bserver\s*\{", content[i:])
            if not m:
                return
            start = i + m.end()
            depth = 1
            j = start
            while j < n and depth > 0:
                ch = content[j]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        yield content[start:j]
                        i = j + 1
                        break
                j += 1
            else:
                # Unbalanced braces — stop
                return

    def _parse_block(self, block: str, path: Path) -> Optional[Dict[str, Any]]:
        names = re.findall(r"\bserver_name\s+([^;]+);", block)
        if not names:
            return None
        # Take the first server_name directive and split into individual hosts
        primary_names = names[0].split()
        if not primary_names:
            return None
        server_name = primary_names[0]

        listen = re.findall(r"\blisten\s+([^;]+);", block)
        upstream_match = re.search(r"\bproxy_pass\s+https?://([^/;]+)", block)
        upstream = upstream_match.group(1) if upstream_match else ""

        ssl_cert_match = re.search(r"\bssl_certificate\s+([^;]+);", block)
        has_ssl = bool(ssl_cert_match) or any("ssl" in l for l in listen)

        # Asset id needs the listen port too — a single file commonly defines
        # both an HTTP redirect block (`listen 80`) and an HTTPS block
        # (`listen 443 ssl`) for the same server_name.
        listen_port = "?"
        if listen:
            first_listen = listen[0].strip().split()[0]
            listen_port = first_listen.split(":")[-1] if ":" in first_listen else first_listen

        project = self.project_detector.get_project_from_domain(server_name)

        return self.create_asset(
            category="nginx_server_block",
            asset_id=f"{self.server_id}:nginx:{path.name}:{server_name}:{listen_port}",
            name=server_name,
            status="configured",
            project=project,
            metadata={
                "config_file": str(path),
                "server_names": primary_names,
                "listen": [l.strip() for l in listen],
                "upstream": upstream,
                "has_ssl": has_ssl,
                "ssl_certificate": ssl_cert_match.group(1).strip()
                if ssl_cert_match
                else None,
            },
            health_indicators={"has_ssl": has_ssl, "has_upstream": bool(upstream)},
        )
