"""Priority-ranked gossip cluster — the core election logic, tested adversarially.

These are pure-function tests (no DB): election on primary loss, the MAJORITY GUARD
(split-brain), no-double-primary across a partition, no-auto-preempt, override freeze,
the election grace round, and roster self-heal.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app.cluster as C

NOW = datetime(2026, 6, 28, 12, 0, 0, tzinfo=timezone.utc)


def node(node_id, priority, *, seen_ago=0, primary=False, me=False):
    return {
        "node_id": node_id,
        "priority": priority,
        "last_seen": NOW - timedelta(seconds=seen_ago),
        "is_primary": primary,
        "self": me,
    }


# ----------------------- majority arithmetic --------------------------------


def test_majority_arithmetic():
    assert C.has_majority(3, 5) is True
    assert C.has_majority(2, 5) is False
    assert C.has_majority(2, 4) is False   # an even split is NOT a majority — both halves hold
    assert C.has_majority(3, 4) is True
    assert C.has_majority(1, 1) is True


# ----------------------- steady state ---------------------------------------


def test_lone_primary_holds():
    d = C.evaluate_cluster([node("A", 1, primary=True, me=True)], "A", NOW)
    assert d["self_role"] == "primary" and d["action"] == "stay"


def test_incumbent_primary_with_majority_stays():
    nodes = [node("A", 1, primary=True, me=True), node("B", 2), node("C", 3)]
    d = C.evaluate_cluster(nodes, "A", NOW)
    assert d["action"] == "stay" and d["current_leader"] == "A"


# ----------------------- election on primary loss ---------------------------


def test_election_elects_highest_priority_survivor():
    # A(p1) the primary is gone; among survivors B(p2),C(p3) the highest priority wins.
    nodes = [node("A", 1, primary=True, seen_ago=40), node("B", 2, me=True), node("C", 3)]
    d = C.evaluate_cluster(nodes, "B", NOW)
    assert d["action"] == "promote_self" and d["current_leader"] == "B"
    # ...and C defers to B rather than also promoting
    nodes_c = [node("A", 1, primary=True, seen_ago=40), node("B", 2), node("C", 3, me=True)]
    dc = C.evaluate_cluster(nodes_c, "C", NOW)
    assert dc["action"] == "follow" and dc["current_leader"] == "B" and dc["self_role"] == "secondary"


def test_election_waits_one_round_before_concluding():
    nodes = [node("A", 1, primary=True, seen_ago=40), node("B", 2, me=True), node("C", 3)]
    d = C.evaluate_cluster(nodes, "B", NOW, election_grace_elapsed=False)
    assert d["action"] == "wait_election" and d["self_role"] == "secondary"


# ----------------------- MAJORITY GUARD (split-brain) -----------------------


def test_minority_partition_must_not_elect():
    # 5-node fleet; from D's view only D+E are reachable (3 nodes gone) -> minority.
    nodes = [
        node("A", 1, primary=True, seen_ago=40), node("B", 2, seen_ago=40),
        node("C", 3, seen_ago=40), node("D", 4, me=True), node("E", 5, seen_ago=5),
    ]
    d = C.evaluate_cluster(nodes, "D", NOW)
    assert d["minority"] is True
    assert d["action"] == "no_leader"
    assert d["self_role"] == "secondary"        # MUST stay secondary
    assert d["current_leader"] is None


def test_majority_partition_does_elect():
    # Same fleet; from C's view A,B are gone but C,D,E are up -> majority of 5.
    nodes = [
        node("A", 1, primary=True, seen_ago=40), node("B", 2, seen_ago=40),
        node("C", 3, me=True), node("D", 4, seen_ago=5), node("E", 5, seen_ago=5),
    ]
    d = C.evaluate_cluster(nodes, "C", NOW)
    assert d["minority"] is False
    assert d["action"] == "promote_self" and d["current_leader"] == "C"


def test_partition_never_yields_two_primaries():
    # Fleet A(p1)..E(p5), A is primary. Split into {A,B} (minority) and {C,D,E} (majority).
    # Evaluate every node FROM ITS OWN partition's reachability and assert <= 1 primary.
    def view(self_id, reachable_ids, primaries):
        out = []
        for nid, prio in [("A", 1), ("B", 2), ("C", 3), ("D", 4), ("E", 5)]:
            out.append(node(nid, prio, seen_ago=(0 if nid in reachable_ids else 40),
                            primary=(nid in primaries), me=(nid == self_id)))
        return out

    minority = {"A", "B"}
    majority = {"C", "D", "E"}
    decisions = {
        "A": C.evaluate_cluster(view("A", minority, {"A"}), "A", NOW),   # old primary, minority
        "B": C.evaluate_cluster(view("B", minority, {"A"}), "B", NOW),
        "C": C.evaluate_cluster(view("C", majority, set()), "C", NOW),   # majority, no primary visible
        "D": C.evaluate_cluster(view("D", majority, set()), "D", NOW),
        "E": C.evaluate_cluster(view("E", majority, set()), "E", NOW),
    }
    # the old primary in the minority steps down
    assert decisions["A"]["action"] == "step_down" and decisions["A"]["self_role"] == "secondary"
    # at most one node concludes it is primary
    primaries = [nid for nid, d in decisions.items()
                 if d["self_role"] == "primary" or d["action"] in ("promote_self", "stay")]
    assert len(primaries) <= 1, f"double primary! {primaries}"
    assert primaries == ["C"]   # the highest-priority survivor in the majority


def test_partitioned_old_primary_steps_down():
    # 3-node fleet, A primary, but A can only see itself (B,C gone) -> 1 of 3, minority.
    nodes = [node("A", 1, primary=True, me=True), node("B", 2, seen_ago=40), node("C", 3, seen_ago=40)]
    d = C.evaluate_cluster(nodes, "A", NOW)
    assert d["action"] == "step_down" and d["self_role"] == "secondary" and d["minority"] is True


# ----------------------- no auto-preempt / failback -------------------------


def test_recovered_higher_priority_node_stays_secondary():
    # C(p3) is the elected primary and healthy; A(p1) just recovered. A must NOT preempt.
    nodes = [node("A", 1, me=True), node("B", 2), node("C", 3, primary=True)]
    d = C.evaluate_cluster(nodes, "A", NOW)
    assert d["action"] == "follow" and d["current_leader"] == "C" and d["self_role"] == "secondary"


def test_two_primaries_on_heal_lower_number_wins():
    # A force-promote left two primaries; on heal the lower priority number keeps it.
    nodes_b = [node("A", 1, primary=True), node("B", 2, primary=True, me=True), node("C", 3)]
    d = C.evaluate_cluster(nodes_b, "B", NOW)
    assert d["action"] == "step_down" and d["current_leader"] == "A"
    nodes_a = [node("A", 1, primary=True, me=True), node("B", 2, primary=True), node("C", 3)]
    da = C.evaluate_cluster(nodes_a, "A", NOW)
    assert da["action"] == "stay" and da["self_role"] == "primary"


# ----------------------- override -------------------------------------------


def test_override_freezes_election_even_when_primary_lost():
    # primary gone, this node IS in a majority and would otherwise win — but override pins.
    nodes = [node("A", 1, primary=True, seen_ago=40), node("B", 2, me=True), node("C", 3, seen_ago=5)]
    d = C.evaluate_cluster(nodes, "B", NOW, override=True)
    assert d["action"] == "frozen"
    assert d["self_role"] == "secondary"          # did NOT promote despite majority + loss
    assert d["current_leader"] != "B"


# ----------------------- roster self-heal -----------------------------------


def test_roster_self_heals_in_one_round():
    # A node boots knowing only itself, then hears from every peer in one gossip round.
    roster = {"A": {"node_id": "A", "priority": 1, "self": True}}
    for nid, prio in [("B", 2), ("C", 3), ("D", 4)]:
        C.merge_gossip(roster, {"node_id": nid, "priority": prio, "address": f"http://{nid}"}, NOW)
    assert set(roster) == {"A", "B", "C", "D"}
    assert {nid: r["priority"] for nid, r in roster.items()} == {"A": 1, "B": 2, "C": 3, "D": 4}


def test_roster_learns_peers_transitively():
    # B relays that it knows E, so A learns E's priority without hearing E directly.
    roster = {"A": {"node_id": "A", "priority": 1, "self": True}}
    C.merge_gossip(roster, {"node_id": "B", "priority": 2,
                            "peers": [{"node_id": "E", "priority": 5, "address": "http://E"}]}, NOW)
    assert roster["E"]["priority"] == 5


def test_priority_in_use_and_leader_address():
    roster = {"A": {"node_id": "A", "priority": 1, "is_primary": True, "address": "http://a"},
              "B": {"node_id": "B", "priority": 2}}
    assert C.priority_in_use(roster, 1) is True
    assert C.priority_in_use(roster, 1, exclude="A") is False
    assert C.priority_in_use(roster, 7) is False
    assert C.current_leader_address(roster) == "http://a"
