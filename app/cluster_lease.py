"""Mongo-lease leader election — the atomic write IS the arbiter.

A single document (`cluster_lease`, fixed _id) holds the current leader's node id
and an expiry. Acquisition/renewal is ONE atomic `find_one_and_update` whose filter
matches only when the lease is expired or already mine; combined with the unique
`_id`, two nodes can never both win:

  - lease absent  -> upsert inserts; a concurrent upsert hits a duplicate-key on
    `_id` and loses.
  - lease expired -> the first updater (serialized on the single document) sets a
    fresh holder+expiry; a racing updater no longer matches the filter, falls to
    upsert, hits duplicate-key, and loses.
  - lease live & held by another node -> filter doesn't match -> upsert ->
    duplicate-key -> loses (cannot steal a live lease).

There are deliberately NO heartbeats or term numbers — the single-document atomic
write is the entire split-brain guard. Manual `force_acquire` is the one escape
hatch and is only ever reached behind an explicit operator confirmation.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

LEASE_ID = "leader"


def _now(now: Optional[datetime]) -> datetime:
    return now or datetime.now(timezone.utc)


def _as_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Mongo (with tz_aware=False) hands datetimes back NAIVE; our `now` is aware.
    Normalize to UTC-aware so comparisons never mix naive/aware."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def try_acquire_or_renew(db, node_id: str, ttl_seconds: int, now: Optional[datetime] = None) -> bool:
    """Atomically acquire the lease (if free/expired) or renew it (if already mine).
    Returns True iff this node holds the lease afterwards. `db` is a pymongo Database.
    """
    now = _now(now)
    expiry = now + timedelta(seconds=ttl_seconds)
    try:
        doc = db.cluster_lease.find_one_and_update(
            {"_id": LEASE_ID, "$or": [{"expires_at": {"$lte": now}}, {"holder": node_id}]},
            {"$set": {"holder": node_id, "expires_at": expiry, "renewed_at": now}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return bool(doc and doc.get("holder") == node_id)
    except DuplicateKeyError:
        # Another node holds a live lease (its doc already exists). We lost.
        return False


def lease_state(db, now: Optional[datetime] = None) -> dict:
    """Current lease view: holder, expiry, whether it's still valid, and if forced."""
    now = _now(now)
    doc = db.cluster_lease.find_one({"_id": LEASE_ID})
    if not doc:
        return {"holder": None, "expires_at": None, "renewed_at": None, "valid": False, "forced": False}
    exp = _as_aware(doc.get("expires_at"))
    return {
        "holder": doc.get("holder"),
        "expires_at": exp,
        "renewed_at": _as_aware(doc.get("renewed_at")),
        "valid": bool(exp and exp > now),
        "forced": bool(doc.get("forced_at")),
    }


def is_leader(db, node_id: str, now: Optional[datetime] = None) -> bool:
    """True only if this node holds a CURRENTLY-VALID lease. A node that thinks it
    is leader but whose lease lapsed (or was taken) returns False here — callers
    must gate leader-only work on this, never on a cached belief."""
    st = lease_state(db, now)
    return st["valid"] and st["holder"] == node_id


def force_acquire(db, node_id: str, ttl_seconds: int, now: Optional[datetime] = None) -> dict:
    """Unconditionally seize the lease (manual override). DANGEROUS: bypasses the
    atomic guard, so it can create two primaries if the old one is actually alive.
    Only ever called behind an explicit operator confirmation (see /promote)."""
    now = _now(now)
    db.cluster_lease.update_one(
        {"_id": LEASE_ID},
        {"$set": {"holder": node_id, "expires_at": now + timedelta(seconds=ttl_seconds),
                  "renewed_at": now, "forced_at": now}},
        upsert=True,
    )
    return lease_state(db, now)


def release(db, node_id: str, now: Optional[datetime] = None) -> bool:
    """Graceful step-down: expire the lease iff we hold it (lets a peer take over
    immediately instead of waiting out the TTL). No-op if we don't hold it."""
    now = _now(now)
    res = db.cluster_lease.update_one(
        {"_id": LEASE_ID, "holder": node_id},
        {"$set": {"expires_at": now, "released_at": now}},
    )
    return res.modified_count > 0
