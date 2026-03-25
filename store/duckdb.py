"""DuckDB-backed store backend.

Provides local persistent storage with a single-file DuckDB database.
Useful for single-node demos where in-memory reset is undesirable and
MongoDB is unnecessary.
"""

from __future__ import annotations

import dataclasses
import json
import os
import tempfile
from typing import Any, Dict, List, Optional

from store.base import StoreBase
from store.models import PIISession, PipelineCard, Appointment, AuditEntry, UserAccount, _now


_VALID_CARD_STATUSES = frozenset({"backlog", "in_progress", "review", "done"})
_VALID_APPT_STATUSES = frozenset({"scheduled", "completed", "cancelled"})
_VALID_SEVERITIES = frozenset({"info", "warning", "critical"})


def _default_duckdb_path() -> str:
    return os.environ.get(
        "ANON_DUCKDB_PATH",
        os.path.join(tempfile.gettempdir(), "anon_studio.duckdb"),
    )


def _to_payload(obj: Any) -> str:
    return json.dumps(dataclasses.asdict(obj), ensure_ascii=True, separators=(",", ":"))


def _from_payload(cls, payload: str):
    return cls(**json.loads(payload))


class DuckDBStore(StoreBase):
    """Persistent store backed by a local DuckDB file."""

    def __init__(self, path: Optional[str] = None, seed: bool = True) -> None:
        try:
            import duckdb  # type: ignore
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "duckdb is required for DuckDBStore. Install with: pip install duckdb>=1.0"
            ) from exc

        self._path = os.path.abspath(path or _default_duckdb_path())
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        self._conn = duckdb.connect(self._path)
        self._ensure_schema()
        if seed and not self._has_any_data():
            self._seed_demo_data()

    # ── Schema / low-level helpers ───────────────────────────────────────────

    def _ensure_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pii_sessions (
              id VARCHAR PRIMARY KEY,
              created_at VARCHAR,
              payload TEXT NOT NULL
            );
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pipeline_cards (
              id VARCHAR PRIMARY KEY,
              updated_at VARCHAR,
              payload TEXT NOT NULL
            );
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS appointments (
              id VARCHAR PRIMARY KEY,
              scheduled_for VARCHAR,
              payload TEXT NOT NULL
            );
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
              id VARCHAR PRIMARY KEY,
              timestamp VARCHAR,
              payload TEXT NOT NULL
            );
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
              id VARCHAR PRIMARY KEY,
              created_at VARCHAR,
              payload TEXT NOT NULL
            );
            """
        )

    def _has_any_data(self) -> bool:
        row = self._conn.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM pii_sessions)
              + (SELECT COUNT(*) FROM pipeline_cards)
              + (SELECT COUNT(*) FROM appointments)
              + (SELECT COUNT(*) FROM audit_log)
              + (SELECT COUNT(*) FROM users)
            """
        ).fetchone()
        return bool(row and int(row[0]) > 0)

    def _upsert(self, table: str, rid: str, sort_value: str, payload: str) -> None:
        sort_col = {
            "pii_sessions": "created_at",
            "pipeline_cards": "updated_at",
            "appointments": "scheduled_for",
            "audit_log": "timestamp",
            "users": "created_at",
        }[table]
        self._conn.execute(f"DELETE FROM {table} WHERE id = ?", [rid])
        self._conn.execute(
            f"INSERT INTO {table} (id, {sort_col}, payload) VALUES (?, ?, ?)",
            [rid, sort_value, payload],
        )

    def _get_payload(self, table: str, rid: str) -> Optional[str]:
        row = self._conn.execute(f"SELECT payload FROM {table} WHERE id = ?", [rid]).fetchone()
        return str(row[0]) if row else None

    def _list_payloads(self, table: str, order_col: str, desc: bool = True, limit: Optional[int] = None) -> List[str]:
        order = "DESC" if desc else "ASC"
        sql = f"SELECT payload FROM {table} ORDER BY {order_col} {order}"
        params: List[Any] = []
        if isinstance(limit, int) and limit > 0:
            sql += " LIMIT ?"
            params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        return [str(r[0]) for r in rows]

    def _log(
        self,
        actor: str,
        action: str,
        resource_type: str,
        resource_id: str,
        details: str = "",
        severity: str = "info",
    ) -> None:
        entry = AuditEntry(
            actor=actor,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            severity=severity if severity in _VALID_SEVERITIES else "info",
        )
        self._upsert("audit_log", entry.id, entry.timestamp, _to_payload(entry))

    # ── Sessions ──────────────────────────────────────────────────────────────

    def add_session(self, session: PIISession) -> PIISession:
        self._upsert("pii_sessions", session.id, session.created_at, _to_payload(session))
        self._log(
            "system",
            "pii.anonymize",
            "session",
            session.id,
            f"Anonymized {len(session.entities)} entities using '{session.operator}'",
        )
        return session

    def get_session(self, session_id: str) -> Optional[PIISession]:
        payload = self._get_payload("pii_sessions", session_id)
        return _from_payload(PIISession, payload) if payload else None

    def list_sessions(self) -> List[PIISession]:
        payloads = self._list_payloads("pii_sessions", "created_at", desc=True)
        return [_from_payload(PIISession, p) for p in payloads]

    def list_sessions_by_card(self, card_id: str) -> List[PIISession]:
        rows = self._conn.execute(
            "SELECT payload FROM pii_sessions "
            "WHERE json_extract_string(payload::JSON, '$.pipeline_card_id') = ? "
            "ORDER BY created_at DESC",
            [card_id],
        ).fetchall()
        return [_from_payload(PIISession, str(r[0])) for r in rows]

    def update_session(self, session_id: str, **kwargs) -> Optional[PIISession]:
        session = self.get_session(session_id)
        if not session:
            return None
        for k, v in kwargs.items():
            if hasattr(session, k):
                setattr(session, k, v)
        self._upsert("pii_sessions", session.id, session.created_at, _to_payload(session))
        self._log(
            "system", "session.update", "session", session_id,
            f"Updated session: {', '.join(kwargs.keys())}",
        )
        return session

    def create_user(self, user: UserAccount) -> UserAccount:
        self._upsert("users", user.id, user.created_at, _to_payload(user))
        self._log("system", "auth.register", "user", user.id, f"Registered {user.email}")
        return user

    def get_user(self, user_id: str) -> Optional[UserAccount]:
        payload = self._get_payload("users", user_id)
        return _from_payload(UserAccount, payload) if payload else None

    def get_user_by_email(self, email: str) -> Optional[UserAccount]:
        rows = self._conn.execute(
            "SELECT payload FROM users "
            "WHERE lower(json_extract_string(payload::JSON, '$.email')) = ? "
            "LIMIT 1",
            [str(email or "").strip().lower()],
        ).fetchall()
        return _from_payload(UserAccount, str(rows[0][0])) if rows else None

    def update_user(self, user_id: str, **kwargs) -> Optional[UserAccount]:
        user = self.get_user(user_id)
        if not user:
            return None
        for k, v in kwargs.items():
            if hasattr(user, k):
                setattr(user, k, v)
        user.updated_at = _now()
        self._upsert("users", user.id, user.created_at, _to_payload(user))
        self._log("system", "auth.user_update", "user", user_id, f"Updated user: {', '.join(kwargs.keys())}")
        return user

    def list_users(self) -> List[UserAccount]:
        payloads = self._list_payloads("users", "created_at", desc=False)
        return [_from_payload(UserAccount, p) for p in payloads]

    # ── Pipeline cards ────────────────────────────────────────────────────────

    def add_card(self, card: PipelineCard) -> PipelineCard:
        self._upsert("pipeline_cards", card.id, card.updated_at, _to_payload(card))
        self._log(
            "system",
            "pipeline.create",
            "card",
            card.id,
            f"Created card '{card.title}' in '{card.status}'",
        )
        return card

    def get_card(self, card_id: str) -> Optional[PipelineCard]:
        payload = self._get_payload("pipeline_cards", card_id)
        return _from_payload(PipelineCard, payload) if payload else None

    def update_card(self, card_id: str, **kwargs) -> Optional[PipelineCard]:
        card = self.get_card(card_id)
        if not card:
            return None
        old_status = card.status
        now_ts = _now()
        if "status" in kwargs:
            new_status = kwargs.get("status")
            if new_status == "done" and old_status != "done":
                kwargs["done_at"] = kwargs.get("done_at") or now_ts
            elif old_status == "done" and new_status != "done":
                kwargs["done_at"] = None
        for k, v in kwargs.items():
            if hasattr(card, k):
                setattr(card, k, v)
        card.updated_at = now_ts
        self._upsert("pipeline_cards", card.id, card.updated_at, _to_payload(card))

        if "status" in kwargs and kwargs.get("status") != old_status:
            self._log(
                "system",
                "pipeline.move",
                "card",
                card_id,
                f"Moved '{card.title}' from '{old_status}' -> '{kwargs.get('status')}'",
            )
        if kwargs.get("attested"):
            sig_key = str(getattr(card, "attestation_sig_key_id", "") or "").strip()
            sig_hash = str(getattr(card, "attestation_sig_payload_hash", "") or "").strip()
            sig_note = f" (signed {sig_key}:{sig_hash[:12]})" if sig_key and sig_hash else ""
            self._log(
                "system",
                "compliance.attest",
                "card",
                card_id,
                f"Attested by '{card.attested_by}'{sig_note}",
            )
        return card

    def delete_card(self, card_id: str) -> bool:
        card = self.get_card(card_id)
        if not card:
            return False
        self._conn.execute("DELETE FROM pipeline_cards WHERE id = ?", [card_id])
        self._log("system", "pipeline.delete", "card", card_id, f"Deleted '{card.title}'", severity="warning")
        return True

    def list_cards(self, status: Optional[str] = None) -> List[PipelineCard]:
        cards = [_from_payload(PipelineCard, p) for p in self._list_payloads("pipeline_cards", "updated_at", desc=True)]
        if status is None:
            return cards
        if status not in _VALID_CARD_STATUSES:
            raise ValueError(f"Invalid card status '{status}'. Must be one of {sorted(_VALID_CARD_STATUSES)}.")
        return [c for c in cards if c.status == status]

    def cards_by_status(self) -> Dict[str, List[PipelineCard]]:
        result: Dict[str, List[PipelineCard]] = {"backlog": [], "in_progress": [], "review": [], "done": []}
        for card in self.list_cards():
            result.setdefault(card.status, []).append(card)
        return result

    # ── Appointments ──────────────────────────────────────────────────────────

    def add_appointment(self, appt: Appointment) -> Appointment:
        self._upsert("appointments", appt.id, appt.scheduled_for, _to_payload(appt))
        self._log(
            "system",
            "schedule.create",
            "appointment",
            appt.id,
            f"Scheduled '{appt.title}' for {appt.scheduled_for}",
        )
        return appt

    def get_appointment(self, appt_id: str) -> Optional[Appointment]:
        payload = self._get_payload("appointments", appt_id)
        return _from_payload(Appointment, payload) if payload else None

    def update_appointment(self, appt_id: str, **kwargs) -> Optional[Appointment]:
        appt = self.get_appointment(appt_id)
        if not appt:
            return None
        for k, v in kwargs.items():
            if hasattr(appt, k):
                setattr(appt, k, v)
        self._upsert("appointments", appt.id, appt.scheduled_for, _to_payload(appt))
        self._log(
            "system",
            "schedule.update",
            "appointment",
            appt_id,
            f"Updated '{appt.title}': {', '.join(kwargs.keys())}",
        )
        return appt

    def delete_appointment(self, appt_id: str) -> bool:
        appt = self.get_appointment(appt_id)
        if not appt:
            return False
        self._conn.execute("DELETE FROM appointments WHERE id = ?", [appt_id])
        self._log("system", "schedule.delete", "appointment", appt_id, f"Deleted '{appt.title}'", severity="warning")
        return True

    def list_appointments(self) -> List[Appointment]:
        payloads = self._list_payloads("appointments", "scheduled_for", desc=False)
        return [_from_payload(Appointment, p) for p in payloads]

    def upcoming_appointments(self, limit: int = 5) -> List[Appointment]:
        now = _now()
        rows = [a for a in self.list_appointments() if a.scheduled_for >= now and a.status == "scheduled"]
        return rows[:limit]

    # ── Audit ─────────────────────────────────────────────────────────────────

    def list_audit(self, limit: int = 200) -> List[AuditEntry]:
        payloads = self._list_payloads("audit_log", "timestamp", desc=True, limit=limit)
        return [_from_payload(AuditEntry, p) for p in payloads]

    def log_user_action(
        self,
        actor: str,
        action: str,
        resource_type: str,
        resource_id: str,
        details: str = "",
        severity: str = "info",
    ) -> None:
        self._log(actor, action, resource_type, resource_id, details, severity)

    # ── Stats ─────────────────────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        sessions = self.list_sessions()
        cards = self.list_cards()
        appts = self.list_appointments()
        audit = self.list_audit(limit=200000)

        entity_freq: Dict[str, int] = {}
        total_entities = 0
        for s in sessions:
            for etype, cnt in (s.entity_counts or {}).items():
                v = int(cnt)
                entity_freq[etype] = entity_freq.get(etype, 0) + v
                total_entities += v

        status_counts: Dict[str, int] = {"backlog": 0, "in_progress": 0, "review": 0, "done": 0}
        attested = 0
        for c in cards:
            if c.status in status_counts:
                status_counts[c.status] += 1
            if c.attested:
                attested += 1

        return {
            "total_sessions": len(sessions),
            "total_entities_redacted": total_entities,
            "entity_breakdown": entity_freq,
            "pipeline_by_status": status_counts,
            "total_appointments": len(appts),
            "total_audit_entries": len(audit),
            "attested_cards": attested,
        }

    # ── Seed ──────────────────────────────────────────────────────────────────

    def _seed_demo_data(self) -> None:
        from store.memory import MemoryStore

        seed_store = MemoryStore(seed=True)
        for session in seed_store.list_sessions():
            self._upsert("pii_sessions", session.id, session.created_at, _to_payload(session))
        for card in seed_store.list_cards():
            self._upsert("pipeline_cards", card.id, card.updated_at, _to_payload(card))
        for appt in seed_store.list_appointments():
            self._upsert("appointments", appt.id, appt.scheduled_for, _to_payload(appt))
        for entry in seed_store.list_audit(limit=100000):
            if entry.severity not in _VALID_SEVERITIES:
                entry.severity = "info"
            self._upsert("audit_log", entry.id, entry.timestamp, _to_payload(entry))
        for user in seed_store.list_users():
            self._upsert("users", user.id, user.created_at, _to_payload(user))
