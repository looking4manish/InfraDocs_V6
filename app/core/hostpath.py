"""Read host config files transparently — directly (native) or via the container
/host mount (dockerized). Lets path-based scanners (cloudflared, caddy, …) find the
REAL host's configs instead of the container's empty ones, and report real paths.
"""

import glob
import os
from pathlib import Path
from typing import Iterator, List, Tuple

HOST_ROOT = os.environ.get("INFRADOCS_HOST_ROOT", "").rstrip("/")


def _to_real(p: str) -> str:
    if HOST_ROOT and p.startswith(HOST_ROOT + "/"):
        return p[len(HOST_ROOT):]
    return p


def host_glob(patterns: List[str]) -> List[str]:
    """Real host paths matching any pattern (searched directly + under /host)."""
    seen, out = set(), []
    for pat in patterns:
        bases = ["", HOST_ROOT] if HOST_ROOT else [""]
        for base in bases:
            for fp in glob.glob(base + pat):
                real = _to_real(fp)
                if real not in seen:
                    seen.add(real)
                    out.append(fp)  # the readable path (may be /host-prefixed)
    return out


def read_host_configs(patterns: List[str]) -> Iterator[Tuple[str, str]]:
    """Yield (real_path, text) for each readable file matching the patterns."""
    for fp in host_glob(patterns):
        try:
            yield _to_real(fp), Path(fp).read_text(errors="replace")
        except OSError:
            continue
