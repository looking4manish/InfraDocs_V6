"""Blast radius — read-only teardown preview for a project/application.

Given a correlated application doc, enumerate EVERY asset that a teardown would
touch, and flag:
  - data_loss : removing it destroys data (volumes, storage, the project dir)
  - shared    : another application also depends on it (a shared image, or a cert
                covering multiple apps) — it must NOT be removed by a single-app kill

This is the safe, read-only foundation the future "Kill Button" sits on: you see
the full impact + the must-not-touch items before anything is ever removed. It
makes no host changes and deletes nothing.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List


def _vol_name(v: Any) -> str:
    return v.get("name") if isinstance(v, dict) else v


def compute_blast_radius(
    app: Dict[str, Any], all_apps: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Build the blast-radius plan for `app` given every application doc."""
    name = app["name"]
    others = [a for a in all_apps if a.get("name") != name]

    def shared_with(field: str, value: Any, extract=lambda x: x) -> List[str]:
        out = []
        for a in others:
            if any(extract(x) == value for x in (a.get(field) or [])):
                out.append(a["name"])
        return out

    items: List[Dict[str, Any]] = []

    def add(category, value, *, data_loss=False, shared=None, evidence=None):
        if not value:
            return
        items.append({
            "category": category,
            "name": value,
            "data_loss": data_loss,
            "shared": bool(shared),
            "shared_with": shared or [],
            "evidence": evidence,
        })

    for c in app.get("containers", []):
        add("docker_container", c)
    for img in app.get("images", []):
        add("docker_image", img, shared=shared_with("images", img))
    for v in app.get("volumes", []):
        add("docker_volume", _vol_name(v), data_loss=True,
            shared=shared_with("volumes", _vol_name(v), _vol_name))
    for ng in app.get("nginx_sites", []):
        add("nginx_server_block", ng)
    for cert in app.get("certificates", []):
        add("tls_certificate", cert, shared=shared_with("certificates", cert),
            evidence="serves this app's domain")
    for u in app.get("systemd_units", []):
        add("systemd_unit", u)
    if app.get("compose_file"):
        add("docker_compose", app["compose_file"])
    if app.get("project_dir"):
        add("project_directory", app["project_dir"], data_loss=True,
            evidence=f"{app.get('project_dir_size_bytes', 0)} bytes on disk")

    # Self-protection: never let a teardown touch InfraDocs' own pieces.
    protected = [i for i in items if str(i["name"]).startswith("infradocs-v6-")]

    summary = {
        "total": len(items),
        "data_loss": sum(1 for i in items if i["data_loss"]),
        "shared": sum(1 for i in items if i["shared"]),
        "by_category": dict(Counter(i["category"] for i in items)),
    }

    warnings: List[str] = []
    for i in items:
        if i["shared"]:
            warnings.append(
                f"{i['category']} '{i['name']}' is SHARED with "
                f"{', '.join(i['shared_with'])} — removing it would break them"
            )
    if protected:
        warnings.append(
            "blast radius includes InfraDocs' own assets — these are self-protected"
        )
    # Surface where the map may be incomplete so 'no orphans' is honest.
    if app.get("type") == "project" and not app.get("links"):
        warnings.append(
            "no linking evidence on this app — relationships may be incomplete"
        )

    return {
        "project": name,
        "type": app.get("type"),
        "summary": summary,
        "items": items,
        "protected": [i["name"] for i in protected],
        "warnings": warnings,
    }
