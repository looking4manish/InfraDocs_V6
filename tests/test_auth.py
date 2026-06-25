"""Auth core — bcrypt + seeded admin + sessions + change-password."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import auth as A


# --- tiny in-memory stand-in for db.db.users / db.db.sessions ---
def _match(d, q):
    return all(d.get(k) == v for k, v in q.items())


class _Coll:
    def __init__(self):
        self.docs = []

    def count_documents(self, q):
        return len([d for d in self.docs if _match(d, q)])

    def insert_one(self, d):
        self.docs.append(dict(d))

    def find_one(self, q):
        return next((d for d in self.docs if _match(d, q)), None)

    def update_one(self, q, u):
        d = self.find_one(q)
        if d:
            d.update(u.get("$set", {}))

    def delete_one(self, q):
        self.docs = [d for d in self.docs if not _match(d, q)]


class _DB:
    def __init__(self):
        self.users = _Coll()
        self.sessions = _Coll()


class _FakeDB:
    def __init__(self):
        self.db = _DB()


def test_hash_and_verify():
    h = A.hash_password("Changeme001")
    assert A.verify_password("Changeme001", h)
    assert not A.verify_password("wrong", h)


def test_seed_is_idempotent_and_flags_change():
    db = _FakeDB()
    A.seed_default_admin(db, "admin")
    A.seed_default_admin(db, "admin")  # second call is a no-op
    assert db.db.users.count_documents({}) == 1
    u = A.get_user(db, "admin")
    assert u["must_change_password"] is True
    assert A.verify_password(A.DEFAULT_PASSWORD, u["password_hash"])


def test_session_lifecycle():
    db = _FakeDB()
    A.seed_default_admin(db, "admin")
    tok = A.create_session(db, "admin")
    assert A.validate_session(db, tok) == "admin"
    A.delete_session(db, tok)
    assert A.validate_session(db, tok) is None
    assert A.validate_session(db, "bogus") is None


def test_expired_session_rejected():
    db = _FakeDB()
    tok = A.create_session(db, "admin")
    db.db.sessions.docs[0]["expires_at"] = datetime.now(timezone.utc) - timedelta(hours=1)
    assert A.validate_session(db, tok) is None


def test_change_password_clears_flag():
    db = _FakeDB()
    A.seed_default_admin(db, "admin")
    A.set_password(db, "admin", "NewStrongPass1")
    u = A.get_user(db, "admin")
    assert u["must_change_password"] is False
    assert A.verify_password("NewStrongPass1", u["password_hash"])
    assert not A.verify_password(A.DEFAULT_PASSWORD, u["password_hash"])
