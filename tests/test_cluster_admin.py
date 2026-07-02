"""Admin/Cluster role-transition guards — PURE tests (no DB), so the split-brain-critical
invariants run everywhere. Covers the three the spec calls out: majority-recompute-after-
evict, demotion-refused-when-leaderless, and primary->standalone orphan refusal, plus the
tombstone rule that keeps an evicted ghost from re-inflating the majority denominator.
"""

from datetime import datetime, timedelta, timezone

import app.cluster as CC

NOW = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
DEAD = NOW - timedelta(seconds=300)


def node(nid, prio, *, primary=False, me=False, seen=NOW):
    return {"node_id": nid, "priority": prio, "is_primary": primary, "self": me, "last_seen": seen}


# ---- majority recompute after evict (quorum denominator) -------------------

def test_fleet_size_excludes_tombstoned():
    assert CC.fleet_size(["B", "C", "D"], tombstones=set()) == 4      # self + 3
    assert CC.fleet_size(["B", "C", "D"], tombstones={"D"}) == 3      # ghost evicted
    assert CC.fleet_size([], tombstones=set()) == 1                   # lone node


def test_majority_recomputes_after_evicting_a_ghost():
    # Fleet of 4 (self A + B,C,D). A+B live, C+D dead — a live pair is NOT a majority of 4.
    roster_ids = ["B", "C", "D"]
    assert CC.fleet_size(roster_ids, set()) == 4
    assert CC.has_majority(2, 4) is False
    # Evict the dead ghost D → denominator shrinks to 3 → A+B ARE now a majority.
    assert CC.fleet_size(roster_ids, {"D"}) == 3
    assert CC.has_majority(2, 3) is True


def test_merge_gossip_never_relearns_a_tombstoned_node():
    # Direct message from a tombstoned node is dropped whole (incl. its relayed peers).
    r = {}
    CC.merge_gossip(r, {"node_id": "X", "priority": 5,
                        "peers": [{"node_id": "Y", "priority": 6}]}, NOW, tombstones={"X"})
    assert "X" not in r and "Y" not in r
    # A tombstoned node relayed by a live peer is also refused.
    r2 = {}
    CC.merge_gossip(r2, {"node_id": "X", "priority": 5,
                         "peers": [{"node_id": "Y", "priority": 6}]}, NOW, tombstones={"Y"})
    assert "X" in r2 and "Y" not in r2


# ---- demotion refused when it would leave the cluster leaderless -----------

def test_demotion_refused_when_no_alternative_primary():
    nodes = [node("A", 1, primary=True, me=True), node("B", 2)]   # only A serves
    ok, reason = CC.can_demote_primary(nodes, "A", NOW, override=False)
    assert ok is False and "leaderless" in reason


def test_demotion_refused_when_override_pinned():
    nodes = [node("A", 1, primary=True, me=True), node("B", 2, primary=True)]
    ok, reason = CC.can_demote_primary(nodes, "A", NOW, override=True)
    assert ok is False and "override" in reason


def test_demotion_allowed_with_a_reachable_alternative_primary():
    nodes = [node("A", 1, primary=True, me=True), node("B", 2, primary=True, seen=NOW)]
    ok, reason = CC.can_demote_primary(nodes, "A", NOW, override=False)
    assert ok is True and reason is None


def test_demotion_refused_if_alternative_primary_is_unreachable():
    nodes = [node("A", 1, primary=True, me=True), node("B", 2, primary=True, seen=DEAD)]
    ok, reason = CC.can_demote_primary(nodes, "A", NOW, override=False)
    assert ok is False and "leaderless" in reason


# ---- primary -> standalone orphan refusal ----------------------------------

def test_standalone_refused_while_secondaries_enrolled():
    ok, deps, reason = CC.can_go_standalone([{"node_id": "B"}, {"node_id": "C"}])
    assert ok is False
    assert deps == ["B", "C"]
    assert "redirecting" in reason


def test_standalone_allowed_when_no_dependents():
    ok, deps, reason = CC.can_go_standalone([])
    assert ok is True and deps == [] and reason is None
