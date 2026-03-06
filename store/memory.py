"""
Anonymous Studio — In-Memory Store
====================================
Pure-Python dict-based implementation of StoreBase. Used in development
mode and as the fallback when MONGODB_URI is not set.

All data is lost on process restart. This is intentional for the dev/demo
use case — MongoDB (MongoStore) provides persistence in production.

Thread safety
-------------
Taipy GUI runs callbacks in a thread pool. The in-memory dicts are NOT
protected by locks. In practice, concurrent writes are rare (one user,
sequential UI actions), but this implementation is NOT safe for high-
concurrency production use. MongoStore provides correct concurrent behavior
via MongoDB's document-level locking.

Seeding
-------
``MemoryStore(seed=True)`` (the default) pre-populates demo cards,
appointments, and audit entries on first construction. Pass ``seed=False``
in unit tests for a clean, predictable state.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from store.base import StoreBase
from store.models import (
    _now, _uid,
    PIISession, PipelineCard, Appointment, AuditEntry,
)


class MemoryStore(StoreBase):
    """In-memory implementation. See store/base.py for the full contract."""

    def __init__(self, seed: bool = True):
        self._sessions: Dict[str, PIISession] = {}
        self._cards: Dict[str, PipelineCard] = {}
        self._appointments: Dict[str, Appointment] = {}
        self._audit: List[AuditEntry] = []
        if seed:
            self._seed_demo_data()

    # ── Internal audit helper ─────────────────────────────────────────────────

    def _log(
        self,
        actor: str,
        action: str,
        resource_type: str,
        resource_id: str,
        details: str = "",
        severity: str = "info",
    ) -> None:
        self._audit.append(AuditEntry(
            actor=actor,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            severity=severity,
        ))

    # ── Sessions ──────────────────────────────────────────────────────────────

    def add_session(self, session: PIISession) -> PIISession:
        self._sessions[session.id] = session
        self._log(
            "system", "pii.anonymize", "session", session.id,
            f"Anonymized {len(session.entities)} entities using '{session.operator}'",
        )
        return session

    def get_session(self, session_id: str) -> Optional[PIISession]:
        return self._sessions.get(session_id)

    def list_sessions(self) -> List[PIISession]:
        return sorted(self._sessions.values(), key=lambda s: s.created_at, reverse=True)

    # ── Pipeline Cards ─────────────────────────────────────────────────────────

    def add_card(self, card: PipelineCard) -> PipelineCard:
        if card.status == "done" and not card.done_at:
            card.done_at = card.updated_at or _now()
        self._cards[card.id] = card
        self._log(
            "system", "pipeline.create", "card", card.id,
            f"Created card '{card.title}' in '{card.status}'",
        )
        return card

    def update_card(self, card_id: str, **kwargs) -> Optional[PipelineCard]:
        card = self._cards.get(card_id)
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
        if "status" in kwargs and kwargs["status"] != old_status:
            self._log(
                "system", "pipeline.move", "card", card_id,
                f"Moved '{card.title}' from '{old_status}' → '{kwargs['status']}'",
            )
        if kwargs.get("attested"):
            sig_key = str(getattr(card, "attestation_sig_key_id", "") or "").strip()
            sig_hash = str(getattr(card, "attestation_sig_payload_hash", "") or "").strip()
            sig_note = f" (signed {sig_key}:{sig_hash[:12]})" if sig_key and sig_hash else ""
            self._log(
                "system", "compliance.attest", "card", card_id,
                f"Attested by '{card.attested_by}'{sig_note}",
            )
        return card

    def delete_card(self, card_id: str) -> bool:
        if card_id in self._cards:
            title = self._cards[card_id].title
            del self._cards[card_id]
            self._log(
                "system", "pipeline.delete", "card", card_id,
                f"Deleted '{title}'", severity="warning",
            )
            return True
        return False

    def get_card(self, card_id: str) -> Optional[PipelineCard]:
        return self._cards.get(card_id)

    def list_cards(self, status: Optional[str] = None) -> List[PipelineCard]:
        cards = list(self._cards.values())
        if status:
            cards = [c for c in cards if c.status == status]
        return sorted(cards, key=lambda c: c.updated_at, reverse=True)

    def cards_by_status(self) -> Dict[str, List[PipelineCard]]:
        result: Dict[str, List[PipelineCard]] = {
            "backlog": [], "in_progress": [], "review": [], "done": [],
        }
        for card in self._cards.values():
            result.setdefault(card.status, []).append(card)
        return result

    # ── Appointments ───────────────────────────────────────────────────────────

    def add_appointment(self, appt: Appointment) -> Appointment:
        self._appointments[appt.id] = appt
        self._log(
            "system", "schedule.create", "appointment", appt.id,
            f"Scheduled '{appt.title}' for {appt.scheduled_for}",
        )
        return appt

    def get_appointment(self, appt_id: str) -> Optional[Appointment]:
        """Return the appointment or None. Prefer this over _appointments directly."""
        return self._appointments.get(appt_id)

    def update_appointment(self, appt_id: str, **kwargs) -> Optional[Appointment]:
        appt = self._appointments.get(appt_id)
        if not appt:
            return None
        for k, v in kwargs.items():
            if hasattr(appt, k):
                setattr(appt, k, v)
        self._log(
            "system", "schedule.update", "appointment", appt_id,
            f"Updated '{appt.title}': {', '.join(kwargs.keys())}",
        )
        return appt

    def delete_appointment(self, appt_id: str) -> bool:
        if appt_id in self._appointments:
            title = self._appointments[appt_id].title
            del self._appointments[appt_id]
            self._log(
                "system", "schedule.delete", "appointment", appt_id,
                f"Deleted '{title}'", severity="warning",
            )
            return True
        return False

    def list_appointments(self) -> List[Appointment]:
        return sorted(self._appointments.values(), key=lambda a: a.scheduled_for)

    def upcoming_appointments(self, limit: int = 5) -> List[Appointment]:
        now = _now()
        upcoming = [
            a for a in self._appointments.values()
            if a.scheduled_for >= now and a.status == "scheduled"
        ]
        return sorted(upcoming, key=lambda a: a.scheduled_for)[:limit]

    # ── Audit Log ──────────────────────────────────────────────────────────────

    def list_audit(self, limit: int = 200) -> List[AuditEntry]:
        return list(reversed(self._audit[-limit:]))

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

    # ── Stats ──────────────────────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        sessions = list(self._sessions.values())
        entity_freq: Dict[str, int] = {}
        total_entities = 0
        for s in sessions:
            for etype, cnt in s.entity_counts.items():
                entity_freq[etype] = entity_freq.get(etype, 0) + cnt
                total_entities += cnt

        cards = list(self._cards.values())
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
            "total_appointments": len(self._appointments),
            "total_audit_entries": len(self._audit),
            "attested_cards": attested,
        }

    # ── Seed Demo Data ─────────────────────────────────────────────────────────

    def _seed_demo_data(self) -> None:
        """Populate realistic demo data for development and demos.

        Only called when seed=True (the default). In tests, use seed=False
        for a clean, deterministic starting state.
        """
        demo_cards = [
            PipelineCard(
                id="card-001", title="Q1 Customer Export Anonymization",
                description="De-identify customer names, emails, and SSNs from Q1 export.",
                status="review", assignee="Carley Fant", priority="high",
                labels=["HIPAA", "customer-data"],
            ),
            PipelineCard(
                id="card-002", title="HR Records PII Scrub",
                description="Remove all PII from historical HR records prior to archival.",
                status="in_progress", assignee="Sakshi Patel", priority="critical",
                labels=["GDPR", "HR"],
            ),
            PipelineCard(
                id="card-003", title="Research Dataset Anonymization",
                description="Apply k-anonymity preprocessing and de-identify participant data.",
                status="done", assignee="Diamond Hogans", priority="medium",
                labels=["research"], attested=True, attested_by="Compliance Officer",
                attested_at=_now(), attestation="Verified: all PII removed per IRB protocol.",
            ),
            PipelineCard(
                id="card-004", title="Patient Records HIPAA Compliance",
                description="Scrub PHI from inbound patient dataset before ML pipeline.",
                status="backlog", priority="high", labels=["HIPAA", "healthcare"],
            ),
            PipelineCard(
                id="card-005", title="Vendor Contract Data Review",
                description="Flag and remove bank account numbers and SSNs from vendor contracts.",
                status="backlog", assignee="Elijah Jenkins", priority="low",
                labels=["contracts"],
            ),
            # ── Extra work: outstanding feature backlog from project issues ──
            PipelineCard(
                id="card-006", title="Allowlist / Denylist Support",
                description=(
                    "Add allow_list and deny_list inputs to PII Text page. "
                    "Pass allow_list= to analyzer.analyze() and use "
                    "ad_hoc_recognizers=[PatternRecognizer(deny_list=...)] for denylist."
                ),
                status="backlog", priority="medium",
                labels=["feature", "pii-engine"],
            ),
            PipelineCard(
                id="card-007", title="Encrypt Operator Key Management",
                description=(
                    "Add UI field for AES encryption key on PII Text page. "
                    "Support 128/192/256-bit keys. Store key in env var, not hardcoded. "
                    "Enable DeanonymizeEngine decrypt round-trip."
                ),
                status="backlog", priority="medium",
                labels=["feature", "security"],
            ),
            PipelineCard(
                id="card-008", title="ORGANIZATION Entity Support",
                description=(
                    "Add ORGANIZATION to ALL_ENTITIES in pii_engine.py. "
                    "Configure ORG→ORGANIZATION NLP mapping with 0.4 confidence "
                    "multiplier to reduce false positives."
                ),
                status="backlog", priority="low",
                labels=["feature", "pii-engine"],
            ),
            PipelineCard(
                id="card-009", title="REST API for PII Detection",
                description=(
                    "Build REST API endpoints for PII detection, de-identification, "
                    "and pipeline CRUD using FastAPI. Add API key authentication "
                    "and Swagger documentation."
                ),
                status="backlog", priority="high",
                labels=["feature", "api"],
            ),
            PipelineCard(
                id="card-010", title="MongoDB Persistence Layer",
                description=(
                    "Implement MongoStore backend for persistent storage of sessions, "
                    "cards, appointments, and audit logs. Read MONGODB_URI from env. "
                    "Replace in-memory store for production use."
                ),
                status="backlog", assignee="Sakshi Patel", priority="critical",
                labels=["feature", "infrastructure"],
            ),
            PipelineCard(
                id="card-011", title="Export Audit Logs as CSV/JSON",
                description=(
                    "Add download buttons to export audit log and pipeline data "
                    "in CSV and JSON formats for compliance documentation sharing."
                ),
                status="backlog", priority="medium",
                labels=["feature", "compliance"],
            ),
            PipelineCard(
                id="card-012", title="Image PII Detection via OCR",
                description=(
                    "Accept PNG/JPG uploads, extract text via Tesseract OCR, "
                    "then apply Presidio PII detection to the extracted text. "
                    "Display annotated results."
                ),
                status="backlog", priority="low",
                labels=["feature", "ocr"],
            ),
            PipelineCard(
                id="card-013", title="Role-Based Authentication",
                description=(
                    "Implement user login with email/password and role-based access "
                    "(Admin, Compliance Officer, Developer, Researcher). "
                    "Store hashed passwords in MongoDB."
                ),
                status="backlog", priority="high",
                labels=["feature", "security"],
            ),
            PipelineCard(
                id="card-014", title="Compliance Review Notifications",
                description=(
                    "Send email or in-app notifications 24 hours before scheduled "
                    "review appointments. Include appointment details and linked "
                    "pipeline card information."
                ),
                status="backlog", priority="medium",
                labels=["feature", "compliance"],
            ),
            PipelineCard(
                id="card-015", title="File Attachments on Pipeline Cards",
                description=(
                    "Allow users to attach anonymized output files (CSV, TXT, JSON) "
                    "to pipeline cards. Support multiple attachments per card "
                    "with download capability."
                ),
                status="backlog", priority="medium",
                labels=["feature", "pipeline"],
            ),
        ]
        for card in demo_cards:
            self._cards[card.id] = card

        demo_appts = [
            Appointment(
                id="appt-001", title="Q1 Export Compliance Review",
                description="Review de-identified Q1 dataset with compliance team.",
                scheduled_for="2026-03-05T10:00:00", duration_mins=60,
                attendees=["Carley Fant", "Compliance Officer", "Data Analyst"],
                pipeline_card_id="card-001", status="scheduled",
            ),
            Appointment(
                id="appt-002", title="HR Anonymization Sign-off",
                description="Final attestation meeting for HR records.",
                scheduled_for="2026-03-10T14:00:00", duration_mins=30,
                attendees=["Sakshi Patel", "HR Lead"],
                pipeline_card_id="card-002", status="scheduled",
            ),
            Appointment(
                id="appt-003", title="Research IRB Attestation",
                scheduled_for="2026-02-20T09:00:00", duration_mins=45,
                attendees=["Diamond Hogans", "IRB Committee"],
                pipeline_card_id="card-003", status="completed",
            ),
        ]
        for appt in demo_appts:
            self._appointments[appt.id] = appt

        self._log("system", "app.start", "system", "app", "Anonymous Studio initialized")
        self._log("carley.fant", "pii.anonymize", "session", "demo-1",
                  "Anonymized 12 entities (EMAIL×3, PHONE×2, SSN×7)")
        self._log("sakshi.patel", "pipeline.move", "card", "card-002",
                  "Moved 'HR Records PII Scrub' from backlog → in_progress")
        self._log("diamond.hogans", "compliance.attest", "card", "card-003",
                  "Attested research dataset")
