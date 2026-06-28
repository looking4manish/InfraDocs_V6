"""Priority-ranked, gossip-based cluster with automatic failover — NO shared DB.

Each node runs its own MongoDB and learns about its peers purely by talking to them
(pull-based gossip over the tailnet). The functions here are PURE: they take a roster
snapshot + the current time and return a decision. All timing/IO lives in the manager
and the API layer so this core can be tested adversarially.

Model:
  - Every node has a priority 1-99 (1 = best). The primary is the lowest-priority-number
    node in the current majority partition.
  - A node health-checks every peer every HEALTH_INTERVAL; a peer unheard-from for
    UNREACHABLE_AFTER (= MISS_ROUNDS rounds) is considered unreachable.
  - Election is triggered ONLY by primary LOSS, never by a better node appearing.
  - MAJORITY GUARD: a node may conclude an election only if it can see a STRICT majority
    of the known fleet (itself included). A minority partition stays secondary and never
    self-promotes — this is the split-brain guard.
  - NO auto-preempt / NO auto-failback: a recovered higher-priority node rejoins as
    secondary; reclaiming primary is a manual operator action.
  - OVERRIDE: while set, elections are frozen fleet-wide (the current primary is pinned).
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

HEALTH_INTERVAL_SECONDS = 10
MISS_ROUNDS = 3
UNREACHABLE_AFTER_SECONDS = HEALTH_INTERVAL_SECONDS * MISS_ROUNDS  # ~30s


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    # Mongo (tz_aware=False) returns naive datetimes; normalize to UTC-aware so
    # comparisons with an aware `now` never raise.
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _age(now: datetime, last_seen: Optional[datetime]) -> float:
    last_seen = _aware(last_seen)
    if last_seen is None:
        return float("inf")
    return (now - last_seen).total_seconds()


def reachable_nodes(nodes: List[dict], now: datetime, timeout: float = UNREACHABLE_AFTER_SECONDS) -> List[dict]:
    """Nodes heard from within `timeout`. The local node ('self': True) is always
    reachable to itself."""
    return [n for n in nodes if n.get("self") or _age(now, n.get("last_seen")) <= timeout]


def has_majority(reachable_count: int, total_known: int) -> bool:
    """Strict majority of the KNOWN fleet (itself included). 3 of 5 -> yes; 2 of 5 -> no;
    2 of 4 -> no (a tie is NOT a majority — both halves of an even split stay secondary)."""
    return reachable_count * 2 > total_known


def _winner(reach: List[dict]) -> dict:
    """Lowest priority NUMBER wins; node_id breaks ties deterministically."""
    return min(reach, key=lambda n: (n["priority"], n["node_id"]))


def evaluate_cluster(
    nodes: List[dict],
    self_id: str,
    now: datetime,
    *,
    override: bool = False,
    election_grace_elapsed: bool = True,
    timeout: float = UNREACHABLE_AFTER_SECONDS,
) -> dict:
    """Decide this node's role + who it believes is leader, from its roster snapshot.

    `nodes`: list of {node_id, priority, last_seen, is_primary, self}. The element with
    self=True is this node. `override`: this node's remembered override flag (gossiped
    from the primary; remembered even if the primary goes unreachable). `election_grace_elapsed`:
    whether one full health round has passed since primary-loss was first detected (the
    manager tracks the clock); False means "wait, priorities may not all be known yet".

    Returns: {current_leader, self_role, minority, action, reason}. `action` ∈
    {stay, frozen, follow, promote_self, step_down, wait_election, no_leader}.
    """
    total = len(nodes)
    reach = reachable_nodes(nodes, now, timeout)
    reach_ids = {n["node_id"] for n in reach}
    majority = has_majority(len(reach), total)
    me = next(n for n in nodes if n["node_id"] == self_id)

    # Reachable nodes that currently SERVE as primary (their gossiped is_primary flag),
    # ranked: the lowest priority number is the legitimate one if more than one appears.
    primaries = sorted((n for n in reach if n.get("is_primary")), key=lambda n: (n["priority"], n["node_id"]))

    # OVERRIDE — elections frozen fleet-wide. Whoever serves as primary stays.
    if override:
        leader = primaries[0]["node_id"] if primaries else None
        return {"current_leader": leader, "self_role": "primary" if me.get("is_primary") else "secondary",
                "minority": not majority, "action": "frozen", "reason": "override set — elections frozen"}

    # A live primary is visible.
    if primaries:
        legit = primaries[0]
        if me.get("is_primary") and legit["node_id"] != self_id:
            # Two primaries are reachable (e.g. a partition healed after a force-promote);
            # the lower priority number is legitimate, so I step down. Deterministic — only
            # one side concludes "step down", so it can never ping-pong.
            return {"current_leader": legit["node_id"], "self_role": "secondary", "minority": not majority,
                    "action": "step_down", "reason": f"another primary {legit['node_id']} outranks me"}
        if legit["node_id"] == self_id:
            if majority:
                return {"current_leader": self_id, "self_role": "primary", "minority": False,
                        "action": "stay", "reason": "primary holding majority"}
            # A primary that has lost majority MUST relinquish — the split-brain guard
            # applies to the incumbent too, else a partitioned old primary = double primary.
            return {"current_leader": None, "self_role": "secondary", "minority": True,
                    "action": "step_down", "reason": "primary lost majority — stepping down"}
        # Someone else serves as primary and is reachable: follow it. NO auto-preempt,
        # even if I am higher priority — reclaiming is a manual action.
        return {"current_leader": legit["node_id"], "self_role": "secondary", "minority": not majority,
                "action": "follow", "reason": "following the live primary (no auto-preempt)"}

    # No primary visible -> the primary is lost. MAJORITY GUARD before any election.
    if not majority:
        return {"current_leader": None, "self_role": "secondary", "minority": True,
                "action": "no_leader", "reason": "minority partition — must not elect"}
    if not election_grace_elapsed:
        return {"current_leader": None, "self_role": "secondary", "minority": False,
                "action": "wait_election", "reason": "waiting one health round so all priorities are known"}
    win = _winner(reach)
    if win["node_id"] == self_id:
        return {"current_leader": self_id, "self_role": "primary", "minority": False,
                "action": "promote_self", "reason": "highest priority in the majority partition"}
    return {"current_leader": win["node_id"], "self_role": "secondary", "minority": False,
            "action": "follow", "reason": f"deferring to higher-priority survivor {win['node_id']}"}


# ----------------------- roster gossip (self-heal) --------------------------


def merge_gossip(roster: Dict[str, dict], msg: dict, now: datetime) -> Dict[str, dict]:
    """Fold one peer health message into the roster. Hearing from a node teaches us its
    priority + address directly, so a node that booted with an empty roster knows every
    peer's priority after a single gossip round. Mutates and returns `roster`."""
    nid = msg.get("node_id")
    if not nid:
        return roster
    rec = roster.setdefault(nid, {"node_id": nid})
    if msg.get("priority") is not None:
        rec["priority"] = msg["priority"]
    if msg.get("address"):
        rec["address"] = msg["address"]
    rec["is_primary"] = bool(msg.get("is_primary"))
    rec["last_scan_ts"] = msg.get("last_scan_ts")
    rec["last_seen"] = now
    # A node also relays peers it knows (so priorities propagate transitively in one round
    # even between nodes that can't yet reach each other directly but share a neighbour).
    for peer in msg.get("peers", []) or []:
        pid = peer.get("node_id")
        if not pid or pid == nid:
            continue
        prec = roster.setdefault(pid, {"node_id": pid})
        if peer.get("priority") is not None:
            prec.setdefault("priority", peer["priority"])
        if peer.get("address"):
            prec.setdefault("address", peer["address"])
    return roster


def priority_in_use(roster: Dict[str, dict], priority: int, exclude: Optional[str] = None) -> bool:
    """Is this priority already claimed by a known node (other than `exclude`)?"""
    for nid, rec in roster.items():
        if nid == exclude:
            continue
        if rec.get("priority") == priority:
            return True
    return False


def current_leader_address(roster: Dict[str, dict]) -> Optional[str]:
    """Address of the node currently serving as primary (for redirect + scan push)."""
    for rec in roster.values():
        if rec.get("is_primary") and rec.get("address"):
            return rec["address"]
    return None
