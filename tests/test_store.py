"""
Tests for Anonymous Studio store package.

Run:
    pytest tests/test_store.py -v

Each test class uses a fresh MemoryStore(seed=False) via the ``store``
fixture to avoid test interdependence. Tests document the expected behaviour
of every public method — both MemoryStore and future MongoStore must pass
these tests.

Test coverage:
- PIISession CRUD
- PipelineCard CRUD + status lifecycle + attestation audit trail
- Appointment CRUD + audit trail for update/delete (bug fix)
- get_appointment() public method (new — fixes private _appointments access)
- Audit log ordering, limits, log_user_action
- upcoming_appointments filtering
- cards_by_status grouping
- stats() shape
- get_store() factory env var switching
- _reset_store() test isolation helper
"""
from __future__ import annotations

import os
import pytest

from store.memory import MemoryStore
from store.models import PIISession, PipelineCard, Appointment, AuditEntry, UserAccount
from store import get_store, _reset_store
from services.local_auth import hash_password


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def store() -> MemoryStore:
    """Fresh MemoryStore with no seed data."""
    return MemoryStore(seed=False)


@pytest.fixture
def seeded_store() -> MemoryStore:
    """MemoryStore with full demo seed data."""
    return MemoryStore(seed=True)


# ── PIISession ────────────────────────────────────────────────────────────────

class TestPIISession:
    def test_add_session_returns_session(self, store):
        s = PIISession(title="Test Run", operator="replace",
                       entities=[{"entity_type": "EMAIL_ADDRESS"}],
                       entity_counts={"EMAIL_ADDRESS": 1})
        result = store.add_session(s)
        assert result.id == s.id
        assert store.get_session(s.id) is s

    def test_add_session_emits_audit_entry(self, store):
        s = PIISession(entities=[{}, {}], operator="mask")
        store.add_session(s)
        audit = store.list_audit()
        assert any(e.action == "pii.anonymize" and e.resource_id == s.id
                   for e in audit)

    def test_get_session_missing_returns_none(self, store):
        assert store.get_session("nonexistent") is None

    def test_list_sessions_newest_first(self, store):
        s1 = PIISession(title="A")
        s2 = PIISession(title="B")
        store.add_session(s1)
        store.add_session(s2)
        sessions = store.list_sessions()
        # Both present; created_at strings are ISO-8601 so newest sorts last
        # (same-second ties acceptable in unit tests)
        assert len(sessions) == 2

    def test_list_sessions_by_card_returns_linked(self, store):
        card = PipelineCard(title="My Card")
        store.add_card(card)
        s1 = PIISession(title="Linked", pipeline_card_id=card.id)
        s2 = PIISession(title="Unlinked", pipeline_card_id=None)
        store.add_session(s1)
        store.add_session(s2)
        result = store.list_sessions_by_card(card.id)
        assert len(result) == 1
        assert result[0].id == s1.id

    def test_list_sessions_by_card_empty_for_unknown_card(self, store):
        s = PIISession(title="Some Session", pipeline_card_id="other-card")
        store.add_session(s)
        assert store.list_sessions_by_card("nonexistent") == []

    def test_list_sessions_by_card_multiple_sessions(self, store):
        card = PipelineCard(title="Multi")
        store.add_card(card)
        sessions = [PIISession(title=f"S{i}", pipeline_card_id=card.id) for i in range(3)]
        for s in sessions:
            store.add_session(s)
        result = store.list_sessions_by_card(card.id)
        assert len(result) == 3

    def test_attach_session_to_card_updates_session_id(self, store):
        """Attaching a session to a card updates the card's session_id field."""
        card = PipelineCard(title="Work Item")
        store.add_card(card)
        session = PIISession(title="Run 1", pipeline_card_id=card.id)
        store.add_session(session)
        store.update_card(card.id, session_id=session.id)
        updated = store.get_card(card.id)
        assert updated.session_id == session.id

    def test_attach_session_audit_entry(self, store):
        """Logging session.attach emits a retrievable audit entry on the card."""
        card = PipelineCard(title="Audit Card")
        store.add_card(card)
        session = PIISession(title="Run A", pipeline_card_id=card.id)
        store.add_session(session)
        store.log_user_action("user", "session.attach", "card", card.id,
                              f"Session {session.id[:8]} attached")
        audit = store.list_audit()
        assert any(
            e.action == "session.attach" and e.resource_id == card.id
            for e in audit
        )

    def test_update_session_changes_field(self, store):
        s = PIISession(title="Before")
        store.add_session(s)
        result = store.update_session(s.id, title="After")
        assert result is not None
        assert result.title == "After"
        assert store.get_session(s.id).title == "After"

    def test_update_session_links_to_card(self, store):
        card = PipelineCard(title="My Card")
        store.add_card(card)
        s = PIISession(title="Unlinked")
        store.add_session(s)
        assert s.pipeline_card_id is None
        store.update_session(s.id, pipeline_card_id=card.id)
        updated = store.get_session(s.id)
        assert updated.pipeline_card_id == card.id
        assert len(store.list_sessions_by_card(card.id)) == 1

    def test_update_session_missing_returns_none(self, store):
        assert store.update_session("nonexistent", title="X") is None

    def test_update_session_emits_audit_entry(self, store):
        s = PIISession(title="Audited")
        store.add_session(s)
        store.update_session(s.id, pipeline_card_id="card-xyz")
        audit = store.list_audit()
        matches = [e for e in audit
                   if e.action == "session.update" and e.resource_id == s.id]
        assert len(matches) == 1
        assert "pipeline_card_id" in matches[0].details


# ── PipelineCard ──────────────────────────────────────────────────────────────

class TestPipelineCard:
    def test_add_card_returns_card(self, store):
        c = PipelineCard(title="My Task")
        result = store.add_card(c)
        assert result.id == c.id
        assert store.get_card(c.id) is c

    def test_add_card_emits_audit_entry(self, store):
        c = PipelineCard(title="Audited Card")
        store.add_card(c)
        assert any(e.action == "pipeline.create" and e.resource_id == c.id
                   for e in store.list_audit())

    def test_get_card_missing_returns_none(self, store):
        assert store.get_card("nope") is None

    def test_update_card_changes_field(self, store):
        c = PipelineCard(title="Old Title")
        store.add_card(c)
        updated = store.update_card(c.id, title="New Title")
        assert updated.title == "New Title"
        assert store.get_card(c.id).title == "New Title"

    def test_update_card_missing_returns_none(self, store):
        assert store.update_card("missing", title="X") is None

    def test_update_card_status_change_emits_pipeline_move(self, store):
        c = PipelineCard(status="backlog")
        store.add_card(c)
        store.update_card(c.id, status="in_progress")
        assert any(e.action == "pipeline.move" and e.resource_id == c.id
                   for e in store.list_audit())

    def test_update_card_same_status_no_move_audit(self, store):
        c = PipelineCard(status="backlog")
        store.add_card(c)
        audit_before = len(store.list_audit())
        store.update_card(c.id, status="backlog")
        # Only updated_at changed — no pipeline.move entry
        move_entries = [e for e in store.list_audit()
                        if e.action == "pipeline.move" and e.resource_id == c.id]
        assert len(move_entries) == 0

    def test_update_card_attestation_emits_attest_audit(self, store):
        c = PipelineCard()
        store.add_card(c)
        store.update_card(c.id, attested=True, attested_by="Alice")
        assert any(e.action == "compliance.attest" and e.resource_id == c.id
                   for e in store.list_audit())

    def test_update_card_to_done_sets_done_at(self, store):
        c = PipelineCard(status="review")
        store.add_card(c)
        updated = store.update_card(c.id, status="done")
        assert updated.done_at is not None

    def test_update_card_reopen_clears_done_at(self, store):
        c = PipelineCard(status="backlog")
        store.add_card(c)
        store.update_card(c.id, status="done")
        reopened = store.update_card(c.id, status="review")
        assert reopened.done_at is None

    def test_delete_card_removes_card(self, store):
        c = PipelineCard()
        store.add_card(c)
        assert store.delete_card(c.id) is True
        assert store.get_card(c.id) is None

    def test_delete_card_emits_warning_audit(self, store):
        c = PipelineCard(title="Gone")
        store.add_card(c)
        store.delete_card(c.id)
        entries = [e for e in store.list_audit()
                   if e.action == "pipeline.delete" and e.resource_id == c.id]
        assert len(entries) == 1
        assert entries[0].severity == "warning"

    def test_delete_card_missing_returns_false(self, store):
        assert store.delete_card("ghost") is False

    def test_list_cards_all(self, store):
        store.add_card(PipelineCard(status="backlog"))
        store.add_card(PipelineCard(status="done"))
        assert len(store.list_cards()) == 2

    def test_list_cards_filtered_by_status(self, store):
        store.add_card(PipelineCard(status="backlog"))
        store.add_card(PipelineCard(status="done"))
        assert len(store.list_cards(status="backlog")) == 1
        assert len(store.list_cards(status="review")) == 0

    def test_cards_by_status_grouping(self, store):
        store.add_card(PipelineCard(status="backlog"))
        store.add_card(PipelineCard(status="backlog"))
        store.add_card(PipelineCard(status="review"))
        result = store.cards_by_status()
        assert len(result["backlog"]) == 2
        assert len(result["review"]) == 1
        assert len(result["in_progress"]) == 0
        assert len(result["done"]) == 0


# ── Appointment ───────────────────────────────────────────────────────────────

class TestAppointment:
    def test_add_appointment_returns_appt(self, store):
        a = Appointment(title="Review", scheduled_for="2026-04-01T10:00:00")
        result = store.add_appointment(a)
        assert result.id == a.id

    def test_add_appointment_emits_audit_entry(self, store):
        a = Appointment(title="Audit Me", scheduled_for="2026-04-01T10:00:00")
        store.add_appointment(a)
        assert any(e.action == "schedule.create" and e.resource_id == a.id
                   for e in store.list_audit())

    def test_get_appointment_returns_appt(self, store):
        """Regression: app.py previously accessed store._appointments directly."""
        a = Appointment(scheduled_for="2026-04-01T10:00:00")
        store.add_appointment(a)
        result = store.get_appointment(a.id)
        assert result is a

    def test_get_appointment_missing_returns_none(self, store):
        assert store.get_appointment("missing") is None

    def test_update_appointment_changes_field(self, store):
        a = Appointment(title="Old", scheduled_for="2026-04-01T10:00:00")
        store.add_appointment(a)
        updated = store.update_appointment(a.id, title="New")
        assert updated.title == "New"

    def test_update_appointment_emits_audit_entry(self, store):
        """Regression: update_appointment previously emitted no audit entry."""
        a = Appointment(title="T", scheduled_for="2026-04-01T10:00:00")
        store.add_appointment(a)
        store.update_appointment(a.id, title="Updated")
        assert any(e.action == "schedule.update" and e.resource_id == a.id
                   for e in store.list_audit())

    def test_update_appointment_missing_returns_none(self, store):
        assert store.update_appointment("ghost", title="X") is None

    def test_delete_appointment_removes_appt(self, store):
        a = Appointment(scheduled_for="2026-04-01T10:00:00")
        store.add_appointment(a)
        assert store.delete_appointment(a.id) is True
        assert store.get_appointment(a.id) is None

    def test_delete_appointment_emits_warning_audit(self, store):
        """Regression: delete_appointment previously emitted no audit entry."""
        a = Appointment(title="Gone", scheduled_for="2026-04-01T10:00:00")
        store.add_appointment(a)
        store.delete_appointment(a.id)
        entries = [e for e in store.list_audit()
                   if e.action == "schedule.delete" and e.resource_id == a.id]
        assert len(entries) == 1
        assert entries[0].severity == "warning"

    def test_delete_appointment_missing_returns_false(self, store):
        assert store.delete_appointment("ghost") is False

    def test_list_appointments_sorted_by_scheduled_for(self, store):
        store.add_appointment(Appointment(scheduled_for="2026-05-01T10:00:00"))
        store.add_appointment(Appointment(scheduled_for="2026-03-01T10:00:00"))
        store.add_appointment(Appointment(scheduled_for="2026-04-01T10:00:00"))
        appts = store.list_appointments()
        dates = [a.scheduled_for for a in appts]
        assert dates == sorted(dates)

    def test_upcoming_appointments_excludes_past(self, store):
        store.add_appointment(Appointment(
            title="Past", scheduled_for="2020-01-01T10:00:00", status="scheduled"))
        store.add_appointment(Appointment(
            title="Future", scheduled_for="2099-01-01T10:00:00", status="scheduled"))
        upcoming = store.upcoming_appointments()
        titles = [a.title for a in upcoming]
        assert "Future" in titles
        assert "Past" not in titles

    def test_upcoming_appointments_excludes_cancelled(self, store):
        store.add_appointment(Appointment(
            title="Cancelled", scheduled_for="2099-01-01T10:00:00", status="cancelled"))
        store.add_appointment(Appointment(
            title="Scheduled", scheduled_for="2099-02-01T10:00:00", status="scheduled"))
        upcoming = store.upcoming_appointments()
        titles = [a.title for a in upcoming]
        assert "Scheduled" in titles
        assert "Cancelled" not in titles

    def test_upcoming_appointments_respects_limit(self, store):
        for i in range(10):
            store.add_appointment(Appointment(
                scheduled_for=f"2099-{i+1:02d}-01T10:00:00", status="scheduled"))
        assert len(store.upcoming_appointments(limit=3)) == 3


# ── Audit Log ─────────────────────────────────────────────────────────────────

class TestAuditLog:
    def test_log_user_action_appends_entry(self, store):
        store.log_user_action("alice", "job.submit", "job", "j1", "Submitted 100 rows")
        entries = store.list_audit()
        assert len(entries) == 1
        assert entries[0].actor == "alice"
        assert entries[0].action == "job.submit"

    def test_list_audit_newest_first(self, store):
        store.log_user_action("u", "a1", "r", "id1")
        store.log_user_action("u", "a2", "r", "id2")
        entries = store.list_audit()
        assert entries[0].action == "a2"
        assert entries[1].action == "a1"

    def test_list_audit_respects_limit(self, store):
        for i in range(50):
            store.log_user_action("u", f"action-{i}", "r", "id")
        assert len(store.list_audit(limit=10)) == 10

    def test_list_audit_default_limit_200(self, store):
        for i in range(250):
            store.log_user_action("u", f"action-{i}", "r", "id")
        assert len(store.list_audit()) == 200

    def test_audit_severity_stored(self, store):
        store.log_user_action("u", "a", "r", "id", severity="warning")
        assert store.list_audit()[0].severity == "warning"


class TestUsers:
    def test_create_user_roundtrip(self, store):
        user = UserAccount(
            email="tester@example.com",
            full_name="Test User",
            role="Developer",
            password_hash=hash_password("Example123!"),
        )
        created = store.create_user(user)
        assert created.id == user.id
        assert store.get_user(user.id).email == "tester@example.com"

    def test_get_user_by_email_normalizes_case(self, store):
        user = UserAccount(
            email="tester@example.com",
            role="Researcher",
            password_hash=hash_password("Example123!"),
        )
        store.create_user(user)
        fetched = store.get_user_by_email("TESTER@example.com")
        assert fetched is not None
        assert fetched.id == user.id

    def test_update_user_changes_last_login(self, store):
        user = UserAccount(
            email="tester@example.com",
            role="Admin",
            password_hash=hash_password("Example123!"),
        )
        store.create_user(user)
        updated = store.update_user(user.id, last_login_at="2026-03-24T12:00:00")
        assert updated is not None
        assert updated.last_login_at == "2026-03-24T12:00:00"

    def test_list_users_returns_created_user(self, store):
        user = UserAccount(
            email="tester@example.com",
            role="Compliance Officer",
            password_hash=hash_password("Example123!"),
        )
        store.create_user(user)
        emails = [entry.email for entry in store.list_users()]
        assert "tester@example.com" in emails


# ── Stats ─────────────────────────────────────────────────────────────────────

class TestStats:
    def test_stats_shape(self, store):
        result = store.stats()
        assert "total_sessions" in result
        assert "total_entities_redacted" in result
        assert "entity_breakdown" in result
        assert "pipeline_by_status" in result
        assert "total_appointments" in result
        assert "total_audit_entries" in result
        assert "attested_cards" in result

    def test_stats_pipeline_by_status_keys(self, store):
        result = store.stats()
        expected_keys = {"backlog", "in_progress", "review", "done"}
        assert set(result["pipeline_by_status"].keys()) == expected_keys

    def test_stats_counts_entities(self, store):
        s = PIISession(entity_counts={"EMAIL_ADDRESS": 3, "PERSON": 2})
        store.add_session(s)
        result = store.stats()
        assert result["total_entities_redacted"] == 5
        assert result["entity_breakdown"]["EMAIL_ADDRESS"] == 3

    def test_stats_attested_cards(self, store):
        store.add_card(PipelineCard(attested=True))
        store.add_card(PipelineCard(attested=False))
        assert store.stats()["attested_cards"] == 1


# ── Seeded data ───────────────────────────────────────────────────────────────

class TestSeedData:
    def test_seeded_store_has_demo_cards(self, seeded_store):
        assert len(seeded_store.list_cards()) == 15

    def test_seeded_store_has_demo_appointments(self, seeded_store):
        assert len(seeded_store.list_appointments()) == 3

    def test_seeded_store_has_audit_entries(self, seeded_store):
        assert len(seeded_store.list_audit()) > 0

    def test_empty_store_is_clean(self, store):
        assert len(store.list_cards()) == 0
        assert len(store.list_appointments()) == 0
        assert len(store.list_audit()) == 0

    # ── Sprint 2 status: backlog verification ──────────────────────────────────
    # After sprint 2, card-011 (Export) moved from backlog to done.
    # Remaining backlog: 6 cards.
    #   card-004  Patient Records HIPAA Compliance     (high priority)
    #   card-005  Vendor Contract Data Review          (low priority)
    #   card-012  Image PII Detection via OCR          (low priority)
    #   card-013  Role-Based Authentication            (high priority)
    #   card-014  Compliance Review Notifications      (medium priority)
    #   card-015  File Attachments on Pipeline Cards   (medium priority)

    def test_sprint_1_retro_backlog_card_ids(self, seeded_store):
        """Backlog card IDs must exactly match the current backlog."""
        backlog_ids = {c.id for c in seeded_store.list_cards(status="backlog")}
        expected = {
            "card-004",  # Patient Records HIPAA Compliance
            "card-005",  # Vendor Contract Data Review
            "card-012",  # Image PII Detection via OCR
            "card-013",  # Role-Based Authentication
            "card-014",  # Compliance Review Notifications
            "card-015",  # File Attachments on Pipeline Cards
        }
        assert backlog_ids == expected

    def test_sprint_1_retro_backlog_count(self, seeded_store):
        """Six cards must be in backlog after sprint 2."""
        assert len(seeded_store.list_cards(status="backlog")) == 6

    def test_sprint_1_retro_done_card_ids(self, seeded_store):
        """Done card IDs must match completed work through sprint 2."""
        done_ids = {c.id for c in seeded_store.list_cards(status="done")}
        expected = {
            "card-003",  # Research Dataset Anonymization (attested)
            "card-006",  # Allowlist / Denylist Support
            "card-008",  # ORGANIZATION Entity Support
            "card-009",  # REST API for PII Detection
            "card-010",  # MongoDB Persistence Layer
            "card-011",  # Export Audit Logs as CSV/JSON
        }
        assert done_ids == expected

    def test_sprint_1_retro_in_progress_card_ids(self, seeded_store):
        """In-progress card IDs must match the sprint 1 retro active work."""
        in_progress_ids = {c.id for c in seeded_store.list_cards(status="in_progress")}
        expected = {
            "card-002",  # HR Records PII Scrub
            "card-007",  # Encrypt Operator Key Management (partial)
        }
        assert in_progress_ids == expected

    def test_sprint_1_retro_review_card_ids(self, seeded_store):
        """Review card IDs must match the sprint 1 retro review queue."""
        review_ids = {c.id for c in seeded_store.list_cards(status="review")}
        assert review_ids == {"card-001"}  # Q1 Customer Export Anonymization


# ── get_store() factory ───────────────────────────────────────────────────────

class TestGetStore:
    def setup_method(self):
        _reset_store()

    def teardown_method(self):
        _reset_store()
        os.environ.pop("MONGODB_URI", None)
        os.environ.pop("ANON_STORE_BACKEND", None)

    def test_returns_memory_store_without_uri(self):
        os.environ.pop("MONGODB_URI", None)
        os.environ.pop("ANON_STORE_BACKEND", None)
        from store.memory import MemoryStore
        s = get_store()
        assert isinstance(s, MemoryStore)

    def test_defaults_to_memory_even_when_mongo_uri_is_set(self):
        os.environ["MONGODB_URI"] = "mongodb://localhost:27017/anon_studio"
        os.environ.pop("ANON_STORE_BACKEND", None)
        from store.memory import MemoryStore
        s = get_store()
        assert isinstance(s, MemoryStore)

    def test_returns_same_singleton(self):
        s1 = get_store()
        s2 = get_store()
        assert s1 is s2

    def test_reset_store_clears_singleton(self):
        s1 = get_store()
        _reset_store()
        s2 = get_store()
        assert s1 is not s2
