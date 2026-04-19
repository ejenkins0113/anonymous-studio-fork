"""
Anonymous Studio — Store Abstract Base Class
=============================================
Defines the contract that every store backend must satisfy.

Implementing a new backend
---------------------------
1. Subclass ``StoreBase``.
2. Implement every ``@abstractmethod``.
3. Add a condition in ``store/__init__.py :: get_store()`` to return it.

Design rules
------------
- All methods are **synchronous** — Taipy GUI callbacks are synchronous and
  spawning async event loops inside them causes Taipy WebSocket hangs.
- Write methods return the mutated model so callers don't need a second read.
- ``log_user_action`` is the public audit API; ``_log`` is an internal helper
  used by write methods to auto-audit state changes (e.g. pipeline.move).
- ``stats()`` is allowed to be expensive; it is only called on dashboard
  refresh, not in hot paths.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from store.models import PIISession, PipelineCard, Appointment, AuditEntry, UserAccount


class StoreBase(ABC):
    """Abstract interface for all Anonymous Studio data store backends."""

    # ── Sessions ──────────────────────────────────────────────────────────────

    @abstractmethod
    def add_session(self, session: PIISession) -> PIISession:
        """Persist a new PII session and emit a ``pii.anonymize`` audit entry."""

    @abstractmethod
    def get_session(self, session_id: str) -> Optional[PIISession]:
        """Return the session or None if not found."""

    @abstractmethod
    def list_sessions(self) -> List[PIISession]:
        """All sessions, newest first."""

    @abstractmethod
    def list_sessions_by_card(self, card_id: str) -> List[PIISession]:
        """All sessions linked to a specific pipeline card, newest first."""

    @abstractmethod
    def update_session(self, session_id: str, **kwargs) -> Optional[PIISession]:
        """Update fields on an existing session.

        Returns the updated session or None if session_id not found.
        Emits a ``session.update`` audit entry on success.
        """

    @abstractmethod
    def create_user(self, user: UserAccount) -> UserAccount:
        """Persist a new user account."""

    @abstractmethod
    def get_user(self, user_id: str) -> Optional[UserAccount]:
        """Return the user account or None."""

    @abstractmethod
    def get_user_by_email(self, email: str) -> Optional[UserAccount]:
        """Return the user account for the given email or None."""

    @abstractmethod
    def update_user(self, user_id: str, **kwargs) -> Optional[UserAccount]:
        """Update fields on an existing user account."""

    @abstractmethod
    def list_users(self) -> List[UserAccount]:
        """Return all user accounts."""

    def update_user_settings(self, user_id: str, **kwargs) -> Optional[UserAccount]:
        """Update notification settings for an existing user.

        This is a convenience helper built on top of update_user().
        """
        return self.update_user(user_id, **kwargs)

    # ── Pipeline Cards ─────────────────────────────────────────────────────────

    @abstractmethod
    def add_card(self, card: PipelineCard) -> PipelineCard:
        """Persist a new card and emit a ``pipeline.create`` audit entry."""

    @abstractmethod
    def update_card(self, card_id: str, **kwargs) -> Optional[PipelineCard]:
        """Update fields on an existing card.

        Auto-emits:
        - ``pipeline.move``   when ``status`` changes
        - ``compliance.attest`` when ``attested=True`` is passed
        Returns None if card_id not found.
        """

    @abstractmethod
    def delete_card(self, card_id: str) -> bool:
        """Delete a card and emit a ``pipeline.delete`` audit entry.
        Returns True if the card existed.
        """

    @abstractmethod
    def get_card(self, card_id: str) -> Optional[PipelineCard]:
        """Return the card or None."""

    @abstractmethod
    def list_cards(self, status: Optional[str] = None) -> List[PipelineCard]:
        """All cards, newest-updated first. Pass status to filter by column."""

    @abstractmethod
    def cards_by_status(self) -> Dict[str, List[PipelineCard]]:
        """Dict with keys backlog/in_progress/review/done → sorted card lists."""

    # ── Appointments ───────────────────────────────────────────────────────────

    @abstractmethod
    def add_appointment(self, appt: Appointment) -> Appointment:
        """Persist and emit a ``schedule.create`` audit entry."""

    @abstractmethod
    def get_appointment(self, appt_id: str) -> Optional[Appointment]:
        """Return the appointment or None."""

    @abstractmethod
    def update_appointment(self, appt_id: str, **kwargs) -> Optional[Appointment]:
        """Update fields and emit a ``schedule.update`` audit entry.
        Returns None if appt_id not found.
        """

    @abstractmethod
    def delete_appointment(self, appt_id: str) -> bool:
        """Delete and emit a ``schedule.delete`` audit entry.
        Returns True if the appointment existed.
        """

    @abstractmethod
    def list_appointments(self) -> List[Appointment]:
        """All appointments sorted by scheduled_for ascending."""

    @abstractmethod
    def upcoming_appointments(self, limit: int = 5) -> List[Appointment]:
        """Scheduled appointments in the future, soonest first, up to limit."""

    # ── Audit Log ──────────────────────────────────────────────────────────────

    @abstractmethod
    def list_audit(self, limit: int = 200) -> List[AuditEntry]:
        """Most recent audit entries first, up to limit."""

    @abstractmethod
    def log_user_action(
        self,
        actor: str,
        action: str,
        resource_type: str,
        resource_id: str,
        details: str = "",
        severity: str = "info",
    ) -> None:
        """Append a user-initiated audit entry. Does not return a value."""

    # ── Stats ──────────────────────────────────────────────────────────────────

    @abstractmethod
    def stats(self) -> Dict[str, Any]:
        """Aggregate counts for the dashboard.

        Returns dict with at minimum:
          total_sessions, total_entities_redacted, entity_breakdown,
          pipeline_by_status, total_appointments, total_audit_entries,
          attested_cards
        """
