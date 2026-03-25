"""
MongoStore — persistent store backend backed by MongoDB.

Drop-in replacement for MemoryStore. Activated automatically when the
MONGODB_URI environment variable is set (see store/__init__.py factory).

Collections
-----------
pipeline_cards  — PipelineCard documents
appointments    — Appointment documents
audit_log       — AuditEntry documents (capped collection, 50 MB / 100 k docs)
pii_sessions    — PIISession documents

Document format
---------------
All domain model dataclasses are serialised with ``dataclasses.asdict()``.
The ``id`` field is stored as ``_id`` (MongoDB primary key) so we avoid
a separate ObjectId and the app never needs to handle ObjectId types.

Indexes (created idempotently on first ``get_store()`` call):
- pipeline_cards: (status, updated_at)
- appointments:   (scheduled_for, status)
- audit_log:      (resource_id, timestamp)
- pii_sessions:   (created_at,)

Requirements
------------
    pip install pymongo>=4.0

No ODM (mongoengine/beanie) is used to keep the dependency footprint small.

Usage
-----
Set the ``MONGODB_URI`` environment variable before starting the app::

    MONGODB_URI=mongodb://localhost:27017/anon_studio python app.py

Or in .env::

    MONGODB_URI=mongodb://localhost:27017/anon_studio
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from store.base import StoreBase
from store.models import PIISession, PipelineCard, Appointment, AuditEntry, UserAccount, _now, _uid

try:
    from pymongo import MongoClient, ASCENDING, DESCENDING
    from pymongo.collection import Collection
    _PYMONGO_AVAILABLE = True
except ImportError:
    _PYMONGO_AVAILABLE = False

# Capped audit log: 50 MB, max 100 000 documents
_AUDIT_CAP_SIZE = 50 * 1024 * 1024
_AUDIT_CAP_MAX  = 100_000


def _to_doc(obj) -> Dict[str, Any]:
    """Serialize a dataclass to a MongoDB document (id → _id)."""
    d = dataclasses.asdict(obj)
    d["_id"] = d.pop("id")
    return d


def _from_doc(cls, doc: Dict[str, Any]):
    """Deserialize a MongoDB document back to a dataclass (``_id`` → ``id``).

    Extra keys stored in MongoDB (e.g. internal bookkeeping fields added by
    update methods) are silently dropped so that schema additions to the store
    layer never cause ``TypeError`` on old documents.
    """
    d = dict(doc)
    d["id"] = str(d.pop("_id"))
    known = {f.name for f in dataclasses.fields(cls)}
    return cls(**{k: v for k, v in d.items() if k in known})


_VALID_CARD_STATUSES = frozenset({"backlog", "in_progress", "review", "done"})
_VALID_APPT_STATUSES = frozenset({"scheduled", "completed", "cancelled"})
_VALID_SEVERITIES    = frozenset({"info", "warning", "critical"})


class MongoStore(StoreBase):
    """
    Persistent store backed by MongoDB.

    Parameters
    ----------
    uri:
        MongoDB connection URI, e.g. ``mongodb://localhost:27017/anon_studio``.
        The database name is taken from the URI path; defaults to
        ``anon_studio`` if omitted.
    """

    def __init__(self, uri: str) -> None:
        if not _PYMONGO_AVAILABLE:
            raise ImportError(
                "pymongo is required for MongoStore. "
                "Install it with: pip install 'pymongo>=4.0'"
            )
        self._client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        # Extract database name from URI path, fall back to "anon_studio"
        db_name = (uri.split("/")[-1].split("?")[0].strip() or "anon_studio")
        self._db = self._client[db_name]
        self._ensure_collections()
        self._ensure_indexes()

    # ── Internal helpers ──────────────────────────────────────────────────────

    @property
    def _cards(self) -> Collection:
        return self._db["pipeline_cards"]

    @property
    def _appts(self) -> Collection:
        return self._db["appointments"]

    @property
    def _audit(self) -> Collection:
        return self._db["audit_log"]

    @property
    def _sessions(self) -> Collection:
        return self._db["pii_sessions"]

    @property
    def _users(self) -> Collection:
        return self._db["users"]

    def _ensure_collections(self) -> None:
        """Create the capped audit_log collection if it does not exist yet."""
        existing = self._db.list_collection_names()
        if "audit_log" not in existing:
            self._db.create_collection(
                "audit_log",
                capped=True,
                size=_AUDIT_CAP_SIZE,
                max=_AUDIT_CAP_MAX,
            )

    def _ensure_indexes(self) -> None:
        """Create all indexes idempotently (safe to call on every startup)."""
        self._cards.create_index([("status", ASCENDING), ("updated_at", DESCENDING)])
        self._appts.create_index([("scheduled_for", ASCENDING), ("status", ASCENDING)])
        self._audit.create_index([("resource_id", ASCENDING), ("timestamp", DESCENDING)])
        self._sessions.create_index([("created_at", DESCENDING)])
        self._users.create_index([("email", ASCENDING)], unique=True)

    def _log(self, actor: str, action: str, resource_type: str,
             resource_id: str, details: str = "", severity: str = "info") -> None:
        entry = AuditEntry(
            actor=actor, action=action,
            resource_type=resource_type, resource_id=resource_id,
            details=details, severity=severity,
        )
        self._audit.insert_one(_to_doc(entry))

    # ── PIISession ────────────────────────────────────────────────────────────

    def add_session(self, session: PIISession) -> PIISession:
        self._sessions.insert_one(_to_doc(session))
        entity_str = ", ".join(
            f"{v}× {k}" for k, v in session.entity_counts.items()
        ) if session.entity_counts else "0 entities"
        self._log("system", "pii.anonymize", "session", session.id,
                  f"{len(session.entities)} entities — {entity_str}")
        return session

    def get_session(self, session_id: str) -> Optional[PIISession]:
        doc = self._sessions.find_one({"_id": session_id})
        return _from_doc(PIISession, doc) if doc else None

    def list_sessions(self, limit: int = 100) -> List[PIISession]:
        cursor = self._sessions.find().sort("created_at", DESCENDING).limit(limit)
        return [_from_doc(PIISession, d) for d in cursor]

    def list_sessions_by_card(self, card_id: str) -> List[PIISession]:
        cursor = self._sessions.find(
            {"pipeline_card_id": card_id}
        ).sort("created_at", DESCENDING)
        return [_from_doc(PIISession, d) for d in cursor]

    def update_session(self, session_id: str, **kwargs) -> Optional[PIISession]:
        doc = self._sessions.find_one({"_id": session_id})
        if not doc:
            return None
        self._sessions.update_one({"_id": session_id}, {"$set": kwargs})
        self._log(
            "system", "session.update", "session", session_id,
            f"Updated session: {', '.join(kwargs.keys())}",
        )
        updated = self._sessions.find_one({"_id": session_id})
        return _from_doc(PIISession, updated) if updated else None

    def create_user(self, user: UserAccount) -> UserAccount:
        self._users.insert_one(_to_doc(user))
        self._log("system", "auth.register", "user", user.id, f"Registered {user.email}")
        return user

    def get_user(self, user_id: str) -> Optional[UserAccount]:
        doc = self._users.find_one({"_id": user_id})
        return _from_doc(UserAccount, doc) if doc else None

    def get_user_by_email(self, email: str) -> Optional[UserAccount]:
        doc = self._users.find_one({"email": str(email or "").strip().lower()})
        return _from_doc(UserAccount, doc) if doc else None

    def update_user(self, user_id: str, **kwargs) -> Optional[UserAccount]:
        doc = self._users.find_one({"_id": user_id})
        if not doc:
            return None
        kwargs["updated_at"] = _now()
        self._users.update_one({"_id": user_id}, {"$set": kwargs})
        self._log("system", "auth.user_update", "user", user_id, f"Updated user: {', '.join(kwargs.keys())}")
        updated = self._users.find_one({"_id": user_id})
        return _from_doc(UserAccount, updated) if updated else None

    def list_users(self) -> List[UserAccount]:
        cursor = self._users.find().sort("created_at", ASCENDING)
        return [_from_doc(UserAccount, d) for d in cursor]

    # ── PipelineCard ──────────────────────────────────────────────────────────

    def add_card(self, card: PipelineCard) -> PipelineCard:
        if card.status == "done" and not card.done_at:
            card.done_at = card.updated_at or _now()
        self._cards.insert_one(_to_doc(card))
        self._log("system", "pipeline.create", "card", card.id,
                  f"Created '{card.title}' in {card.status}")
        return card

    def get_card(self, card_id: str) -> Optional[PipelineCard]:
        doc = self._cards.find_one({"_id": card_id})
        return _from_doc(PipelineCard, doc) if doc else None

    def update_card(self, card_id: str, **kwargs) -> Optional[PipelineCard]:
        doc = self._cards.find_one({"_id": card_id})
        if not doc:
            return None
        old_status = doc.get("status")
        now_ts = _now()
        if "status" in kwargs:
            new_status = kwargs.get("status")
            if new_status == "done" and old_status != "done":
                kwargs["done_at"] = kwargs.get("done_at") or now_ts
            elif old_status == "done" and new_status != "done":
                kwargs["done_at"] = None
        kwargs["updated_at"] = now_ts
        self._cards.update_one({"_id": card_id}, {"$set": kwargs})
        updated = self._cards.find_one({"_id": card_id})

        new_status = kwargs.get("status", old_status)
        if "status" in kwargs and new_status != old_status:
            self._log("system", "pipeline.move", "card", card_id,
                      f"Moved {old_status} → {new_status}")
        if kwargs.get("attested"):
            sig_key = str(kwargs.get("attestation_sig_key_id", "") or "").strip()
            sig_hash = str(kwargs.get("attestation_sig_payload_hash", "") or "").strip()
            sig_note = f" (signed {sig_key}:{sig_hash[:12]})" if sig_key and sig_hash else ""
            self._log(kwargs.get("attested_by", "user"), "compliance.attest",
                      "card", card_id,
                      f"Attested by {kwargs.get('attested_by', 'unknown')}{sig_note}")
        return _from_doc(PipelineCard, updated)

    def delete_card(self, card_id: str) -> bool:
        doc = self._cards.find_one({"_id": card_id})
        if not doc:
            return False
        title = doc.get("title", card_id)
        self._cards.delete_one({"_id": card_id})
        self._log("system", "pipeline.delete", "card", card_id,
                  f"Deleted card '{title}'", severity="warning")
        return True

    def list_cards(self, status: Optional[str] = None) -> List[PipelineCard]:
        if status is not None and status not in _VALID_CARD_STATUSES:
            raise ValueError(f"Invalid card status '{status}'. Must be one of {sorted(_VALID_CARD_STATUSES)}.")
        query = {"status": status} if status else {}
        cursor = self._cards.find(query).sort("updated_at", DESCENDING)
        return [_from_doc(PipelineCard, d) for d in cursor]

    def cards_by_status(self) -> Dict[str, List[PipelineCard]]:
        all_cards = self.list_cards()
        result: Dict[str, List[PipelineCard]] = {
            "backlog": [], "in_progress": [], "review": [], "done": []
        }
        for c in all_cards:
            result.setdefault(c.status, []).append(c)
        return result

    # ── Appointment ───────────────────────────────────────────────────────────

    def add_appointment(self, appt: Appointment) -> Appointment:
        self._appts.insert_one(_to_doc(appt))
        self._log("system", "schedule.create", "appointment", appt.id,
                  f"Scheduled '{appt.title}' for {appt.scheduled_for}")
        return appt

    def get_appointment(self, appt_id: str) -> Optional[Appointment]:
        doc = self._appts.find_one({"_id": appt_id})
        return _from_doc(Appointment, doc) if doc else None

    def update_appointment(self, appt_id: str, **kwargs) -> Optional[Appointment]:
        doc = self._appts.find_one({"_id": appt_id})
        if not doc:
            return None
        kwargs["updated_at"] = _now()
        self._appts.update_one({"_id": appt_id}, {"$set": kwargs})
        self._log("system", "schedule.update", "appointment", appt_id,
                  f"Updated fields: {', '.join(kwargs.keys())}")
        updated = self._appts.find_one({"_id": appt_id})
        return _from_doc(Appointment, updated)

    def delete_appointment(self, appt_id: str) -> bool:
        doc = self._appts.find_one({"_id": appt_id})
        if not doc:
            return False
        title = doc.get("title", appt_id)
        self._appts.delete_one({"_id": appt_id})
        self._log("system", "schedule.delete", "appointment", appt_id,
                  f"Deleted appointment '{title}'", severity="warning")
        return True

    def list_appointments(self) -> List[Appointment]:
        cursor = self._appts.find().sort("scheduled_for", ASCENDING)
        return [_from_doc(Appointment, d) for d in cursor]

    def upcoming_appointments(self, limit: int = 5) -> List[Appointment]:
        now = _now()
        cursor = (
            self._appts
            .find({"scheduled_for": {"$gte": now},
                   "status": {"$nin": ["cancelled", "completed"]}})
            .sort("scheduled_for", ASCENDING)
            .limit(limit)
        )
        return [_from_doc(Appointment, d) for d in cursor]

    # ── Audit log ─────────────────────────────────────────────────────────────

    def log_user_action(self, actor: str, action: str, resource_type: str,
                        resource_id: str = "", details: str = "",
                        severity: str = "info") -> None:
        if severity not in _VALID_SEVERITIES:
            severity = "info"
        self._log(actor, action, resource_type, resource_id, details, severity)

    def list_audit(self, limit: int = 200) -> List[AuditEntry]:
        # Capped collections preserve insertion order; reverse with sort on timestamp
        cursor = self._audit.find().sort("timestamp", DESCENDING).limit(limit)
        return [_from_doc(AuditEntry, d) for d in cursor]

    # ── Stats ─────────────────────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        pipeline_counts = {s: self._cards.count_documents({"status": s})
                           for s in ("backlog", "in_progress", "review", "done")}
        # Entity breakdown via aggregation
        pipeline = [
            {"$project": {"entity_counts": 1}},
            {"$addFields": {"pairs": {"$objectToArray": "$entity_counts"}}},
            {"$unwind": "$pairs"},
            {"$group": {"_id": "$pairs.k", "total": {"$sum": "$pairs.v"}}},
        ]
        entity_breakdown: Dict[str, int] = {}
        total_entities = 0
        for row in self._sessions.aggregate(pipeline):
            entity_breakdown[row["_id"]] = row["total"]
            total_entities += row["total"]

        return {
            "total_sessions":          self._sessions.count_documents({}),
            "total_entities_redacted": total_entities,
            "entity_breakdown":        entity_breakdown,
            "pipeline_by_status":      pipeline_counts,
            "total_appointments":      self._appts.count_documents({}),
            "total_audit_entries":     self._audit.count_documents({}),
            "attested_cards":          self._cards.count_documents({"attested": True}),
        }
