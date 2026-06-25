"""Optional AI layer (Tier 2 labeling + Tier 3 insights).

Talks to ANY OpenAI-compatible /chat/completions endpoint — OpenAI, a local Ollama,
vLLM, etc. — configured in the wizard (or via env). Disabled cleanly when unset, so
nothing here is required. Only non-sensitive service metadata is ever sent.
"""

import json
import os
import re
import urllib.request
from typing import Optional

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def config(db) -> dict:
    s = db.db.settings.find_one({"_id": "app"}) or {}
    return {
        "endpoint": s.get("ai_endpoint") or os.environ.get("INFRADOCS_AI_ENDPOINT"),
        "key": s.get("ai_key") or os.environ.get("INFRADOCS_AI_KEY", ""),
        "model": s.get("ai_model") or os.environ.get("INFRADOCS_AI_MODEL", "gpt-4o-mini"),
    }


def enabled(db) -> bool:
    return bool(config(db).get("endpoint"))


def chat(db, system: str, user: str, timeout: int = 45, json_mode: bool = True) -> Optional[str]:
    cfg = config(db)
    if not cfg["endpoint"]:
        return None
    url = cfg["endpoint"].rstrip("/") + "/chat/completions"
    body = {
        "model": cfg["model"],
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.1,
        "stream": False,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {cfg['key']}"} if cfg["key"] else {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
            data = json.loads(r.read().decode())
        return data["choices"][0]["message"]["content"]
    except Exception:
        # Some endpoints reject response_format — retry once without it.
        if json_mode:
            return chat(db, system, user, timeout=timeout, json_mode=False)
        return None


def _parse_json(text: Optional[str]) -> Optional[dict]:
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        m = _JSON_RE.search(text)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None


_LABEL_SYS = (
    "You identify infrastructure services from evidence. Reply with ONLY a JSON "
    "object: {\"label\": short product/service name, \"kind\": one of "
    "[web,database,cache,monitoring,queue,proxy,app,infra,other], \"purpose\": one "
    "concise sentence}. If unsure, give your best guess and set purpose accordingly."
)


def label_service(db, evidence: dict) -> Optional[dict]:
    out = _parse_json(chat(db, _LABEL_SYS, json.dumps(evidence)))
    if not out or not out.get("label"):
        return None
    return {"label": str(out.get("label"))[:60],
            "kind": str(out.get("kind", "other"))[:20],
            "purpose": str(out.get("purpose", ""))[:200]}


_INSIGHTS_SYS = (
    "You are an infrastructure analyst. Given a JSON inventory of servers, services, "
    "exposures and ports, return ONLY JSON: {\"summary\": 2-3 sentence overview, "
    "\"observations\": [up to 6 short strings — notable facts, exposure/security "
    "concerns, unlabeled or unusual services], \"recommendations\": [up to 4 short "
    "strings]}. Be specific and reference real names from the data."
)


def fleet_insights(db, inventory: dict) -> Optional[dict]:
    return _parse_json(chat(db, _INSIGHTS_SYS, json.dumps(inventory), timeout=90))
