"""
MongoDB store CRUD tests for Anonymous Studio.

Run:
    pytest tests/test_store_mongo.py -v

Uses ``mongomock`` to simulate a real MongoDB server without requiring a live
database.  MongoStore._ensure_collections is patched because mongomock does not
support capped-collection options; all other MongoStore behaviour is exercised
against the in-process mock.

Each test gets its own isolated MongoDB database (unique name via UUID) so that
data written by one test never leaks into another.

Test coverage:
- PIISession CRUD (add, get, list, list_by_card)
- PipelineCard CRUD (add, get, update, delete, list, cards_by_status)
  - Status lifecycle: done_at set/cleared on done↔non-done transitions
  - Audit trail: pipeline.create, pipeline.move, compliance.attest,
    pipeline.delete
- Appointment CRUD (add, get, update, delete, list, upcoming)
  - Audit trail: schedule.create, schedule.update, schedule.delete
- Audit log (log_user_action, list_audit ordering and limits)
- Stats aggregation (entity breakdown, pipeline counts, attested cards)
- get_store() factory returning MongoStore when ANON_STORE_BACKEND=mongo
- Cross-instance data sharing (two MongoStore objects, same URI → same data)
"""
from __future__ import annotations

import os
import uuid
import unittest.mock as mock

import pytest

mongomock = pytest.importorskip("mongomock")

from store.models import PIISession, PipelineCard, Appointment, UserAccount
from store import get_store, _reset_store
from services.local_auth import hash_password


# ── Helpers ───────────────────────────────────────────────────────────────────

def _unique_uri() -> str:
    """Return a URI with a unique database name so tests don't share state."""
    db = f"anon_test_{uuid.uuid4().hex[:12]}"
    return f"mongodb://localhost:27017/{db}"


def _make_store(uri: str = None):
    """Return a fresh MongoStore backed by mongomock at the given URI."""
    from store.mongo import MongoStore

    if uri is None:
        uri = _unique_uri()
    with mock.patch.object(MongoStore, "_ensure_collections", return_value=None):
        return MongoStore(uri)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def store():
    """Isolated MongoStore per test (unique database name)."""
    with mongomock.patch(servers=(("localhost", 27017),)):
        yield _make_store()


@pytest.fixture
def store_pair():
    """Two MongoStore instances pointing at the same URI (shared state test)."""
    with mongomock.patch(servers=(("localhost", 27017),)):
        uri = _unique_uri()
        yield _make_store(uri), _make_store(uri)


# ── PIISession ────────────────────────────────────────────────────────────────

class TestMongoSession:
    def test_add_session_returns_session(self, store):
        s = PIISession(title="Mongo Run", operator="replace",
                       entities=[{"entity_type": "EMAIL_ADDRESS"}],
                       entity_counts={"EMAIL_ADDRESS": 2})
        result = store.add_session(s)
        assert result.id == s.id
        assert result.title == "Mongo Run"

    def test_get_session_roundtrip(self, store):
        s = PIISession(title="RoundTrip", operator="mask",
                       entity_counts={"PERSON": 1})
        store.add_session(s)
        got = store.get_session(s.id)
        assert got is not None
        assert got.id == s.id
        assert got.title == "RoundTrip"
        assert got.operator == "mask"

    def test_get_session_missing_returns_none(self, store):
        assert store.get_session("nonexistent-id") is None

    def test_add_session_emits_audit_entry(self, store):
        s = PIISession(entities=[{}, {}], operator="replace")
        store.add_session(s)
        audit = store.list_audit()
        assert any(
            e.action == "pii.anonymize" and e.resource_id == s.id
            for e in audit
        )

    def test_list_sessions_returns_all(self, store):
        s1 = PIISession(title="First")
        s2 = PIISession(title="Second")
        store.add_session(s1)
        store.add_session(s2)
        ids = {s.id for s in store.list_sessions()}
        assert s1.id in ids
        assert s2.id in ids

    def test_list_sessions_by_card_filters_correctly(self, store):
        card = PipelineCard(title="Linked")
        store.add_card(card)
        s_linked = PIISession(title="Linked Session",
                              pipeline_card_id=card.id)
        s_other = PIISession(title="Other Session", pipeline_card_id=None)
        store.add_session(s_linked)
        store.add_session(s_other)
        result = store.list_sessions_by_card(card.id)
        assert len(result) == 1
        assert result[0].id == s_linked.id

    def test_list_sessions_by_card_empty_for_unknown(self, store):
        store.add_session(PIISession(pipeline_card_id="other-card"))
        assert store.list_sessions_by_card("ghost-card") == []


# ── PipelineCard ──────────────────────────────────────────────────────────────

class TestMongoCard:
    def test_add_card_returns_card(self, store):
        c = PipelineCard(title="My Card", status="backlog")
        result = store.add_card(c)
        assert result.id == c.id
        assert result.title == "My Card"

    def test_get_card_roundtrip(self, store):
        c = PipelineCard(title="Pipeline Task", status="in_progress",
                         assignee="Elijah Jenkins", priority="high")
        store.add_card(c)
        got = store.get_card(c.id)
        assert got is not None
        assert got.title == "Pipeline Task"
        assert got.status == "in_progress"
        assert got.assignee == "Elijah Jenkins"
        assert got.priority == "high"

    def test_get_card_missing_returns_none(self, store):
        assert store.get_card("no-such-card") is None

    def test_add_card_emits_pipeline_create_audit(self, store):
        c = PipelineCard(title="Audited")
        store.add_card(c)
        assert any(
            e.action == "pipeline.create" and e.resource_id == c.id
            for e in store.list_audit()
        )

    def test_update_card_changes_title(self, store):
        c = PipelineCard(title="Old Title")
        store.add_card(c)
        updated = store.update_card(c.id, title="New Title")
        assert updated is not None
        assert updated.title == "New Title"
        assert store.get_card(c.id).title == "New Title"

    def test_update_card_missing_returns_none(self, store):
        assert store.update_card("ghost-id", title="X") is None

    def test_update_card_status_change_emits_pipeline_move(self, store):
        c = PipelineCard(status="backlog")
        store.add_card(c)
        store.update_card(c.id, status="in_progress")
        assert any(
            e.action == "pipeline.move" and e.resource_id == c.id
            for e in store.list_audit()
        )

    def test_update_card_same_status_no_move_audit(self, store):
        c = PipelineCard(status="backlog")
        store.add_card(c)
        store.update_card(c.id, status="backlog")
        move_entries = [
            e for e in store.list_audit()
            if e.action == "pipeline.move" and e.resource_id == c.id
        ]
        assert len(move_entries) == 0

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

    def test_update_card_attestation_emits_attest_audit(self, store):
        c = PipelineCard()
        store.add_card(c)
        store.update_card(c.id, attested=True, attested_by="Compliance Officer")
        assert any(
            e.action == "compliance.attest" and e.resource_id == c.id
            for e in store.list_audit()
        )

    def test_delete_card_removes_card(self, store):
        c = PipelineCard()
        store.add_card(c)
        assert store.delete_card(c.id) is True
        assert store.get_card(c.id) is None

    def test_delete_card_emits_warning_audit(self, store):
        c = PipelineCard(title="To Delete")
        store.add_card(c)
        store.delete_card(c.id)
        entries = [
            e for e in store.list_audit()
            if e.action == "pipeline.delete" and e.resource_id == c.id
        ]
        assert len(entries) == 1
        assert entries[0].severity == "warning"

    def test_delete_card_missing_returns_false(self, store):
        assert store.delete_card("ghost") is False

    def test_list_cards_returns_all(self, store):
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

class TestMongoAppointment:
    def test_add_appointment_returns_appt(self, store):
        a = Appointment(title="Compliance Review",
                        scheduled_for="2026-04-01T10:00:00")
        result = store.add_appointment(a)
        assert result.id == a.id
        assert result.title == "Compliance Review"

    def test_get_appointment_roundtrip(self, store):
        a = Appointment(title="HIPAA Audit",
                        scheduled_for="2026-05-15T14:00:00",
                        duration_mins=60,
                        attendees=["Alice", "Bob"])
        store.add_appointment(a)
        got = store.get_appointment(a.id)
        assert got is not None
        assert got.id == a.id
        assert got.title == "HIPAA Audit"
        assert got.duration_mins == 60

    def test_get_appointment_missing_returns_none(self, store):
        assert store.get_appointment("missing-appt") is None

    def test_add_appointment_emits_schedule_create_audit(self, store):
        a = Appointment(title="Schedule Test",
                        scheduled_for="2026-06-01T09:00:00")
        store.add_appointment(a)
        assert any(
            e.action == "schedule.create" and e.resource_id == a.id
            for e in store.list_audit()
        )

    def test_update_appointment_changes_field(self, store):
        a = Appointment(title="Old Title",
                        scheduled_for="2026-04-01T10:00:00")
        store.add_appointment(a)
        updated = store.update_appointment(a.id, title="New Title")
        assert updated is not None
        assert updated.title == "New Title"
        assert store.get_appointment(a.id).title == "New Title"

    def test_update_appointment_missing_returns_none(self, store):
        assert store.update_appointment("ghost-appt", title="X") is None

    def test_update_appointment_emits_schedule_update_audit(self, store):
        a = Appointment(title="Updatable",
                        scheduled_for="2026-04-01T10:00:00")
        store.add_appointment(a)
        store.update_appointment(a.id, title="Updated")
        assert any(
            e.action == "schedule.update" and e.resource_id == a.id
            for e in store.list_audit()
        )

    def test_delete_appointment_removes_appt(self, store):
        a = Appointment(scheduled_for="2026-04-01T10:00:00")
        store.add_appointment(a)
        assert store.delete_appointment(a.id) is True
        assert store.get_appointment(a.id) is None

    def test_delete_appointment_emits_warning_audit(self, store):
        a = Appointment(title="Gone", scheduled_for="2026-04-01T10:00:00")
        store.add_appointment(a)
        store.delete_appointment(a.id)
        entries = [
            e for e in store.list_audit()
            if e.action == "schedule.delete" and e.resource_id == a.id
        ]
        assert len(entries) == 1
        assert entries[0].severity == "warning"

    def test_delete_appointment_missing_returns_false(self, store):
        assert store.delete_appointment("ghost-appt") is False

    def test_list_appointments_sorted_by_scheduled_for(self, store):
        store.add_appointment(Appointment(scheduled_for="2026-05-01T10:00:00"))
        store.add_appointment(Appointment(scheduled_for="2026-03-01T10:00:00"))
        store.add_appointment(Appointment(scheduled_for="2026-04-01T10:00:00"))
        appts = store.list_appointments()
        dates = [a.scheduled_for for a in appts]
        assert dates == sorted(dates)

    def test_upcoming_appointments_excludes_past(self, store):
        store.add_appointment(Appointment(
            title="Past", scheduled_for="2020-01-01T10:00:00",
            status="scheduled"))
        store.add_appointment(Appointment(
            title="Future", scheduled_for="2099-01-01T10:00:00",
            status="scheduled"))
        titles = [a.title for a in store.upcoming_appointments()]
        assert "Future" in titles
        assert "Past" not in titles

    def test_upcoming_appointments_excludes_cancelled(self, store):
        store.add_appointment(Appointment(
            title="Cancelled", scheduled_for="2099-01-01T10:00:00",
            status="cancelled"))
        store.add_appointment(Appointment(
            title="Scheduled", scheduled_for="2099-02-01T10:00:00",
            status="scheduled"))
        titles = [a.title for a in store.upcoming_appointments()]
        assert "Scheduled" in titles
        assert "Cancelled" not in titles

    def test_upcoming_appointments_respects_limit(self, store):
        for i in range(10):
            store.add_appointment(Appointment(
                scheduled_for=f"2099-{i+1:02d}-01T10:00:00",
                status="scheduled"))
        assert len(store.upcoming_appointments(limit=3)) == 3


# ── Audit Log ─────────────────────────────────────────────────────────────────

class TestMongoAuditLog:
    def test_log_user_action_appends_entry(self, store):
        store.log_user_action("alice", "job.submit", "job", "j1",
                              "Submitted 100 rows")
        match = next(
            (e for e in store.list_audit()
             if e.actor == "alice" and e.action == "job.submit"),
            None,
        )
        assert match is not None

    def test_list_audit_newest_first(self, store):
        # Insert entries with explicitly distinct timestamps (bypassing the
        # second-precision _now() default so the DESCENDING sort is deterministic
        # in mongomock, which ties-break equal timestamps in insertion order).
        from store.models import AuditEntry
        from store.mongo import _to_doc

        e_old = AuditEntry(action="first_action", actor="u",
                           resource_type="r", resource_id="id1",
                           timestamp="2026-01-01T01:00:00")
        e_new = AuditEntry(action="second_action", actor="u",
                           resource_type="r", resource_id="id2",
                           timestamp="2026-01-01T02:00:00")
        store._audit.insert_one(_to_doc(e_old))
        store._audit.insert_one(_to_doc(e_new))

        entries = store.list_audit()
        actions = [e.action for e in entries]
        # second_action has the later timestamp → must appear first (newest first)
        assert actions.index("second_action") < actions.index("first_action")

    def test_list_audit_respects_limit(self, store):
        for i in range(20):
            store.log_user_action("u", f"action-{i}", "r", "id")
        assert len(store.list_audit(limit=5)) == 5

    def test_audit_severity_stored(self, store):
        store.log_user_action("u", "warn_action", "r", "id",
                              severity="warning")
        entry = next(
            (e for e in store.list_audit() if e.action == "warn_action"),
            None,
        )
        assert entry is not None
        assert entry.severity == "warning"

    def test_invalid_severity_defaults_to_info(self, store):
        store.log_user_action("u", "bad_sev_action", "r", "id",
                              severity="not_a_real_level")
        entry = next(
            (e for e in store.list_audit() if e.action == "bad_sev_action"),
            None,
        )
        assert entry is not None
        assert entry.severity == "info"


class TestMongoUsers:
    def test_create_user_roundtrip(self, store):
        user = UserAccount(
            email="tester@example.com",
            role="Developer",
            password_hash=hash_password("Example123!"),
        )
        created = store.create_user(user)
        assert created.id == user.id
        assert store.get_user(user.id).email == "tester@example.com"

    def test_get_user_by_email(self, store):
        user = UserAccount(
            email="tester@example.com",
            role="Researcher",
            password_hash=hash_password("Example123!"),
        )
        store.create_user(user)
        fetched = store.get_user_by_email("tester@example.com")
        assert fetched is not None
        assert fetched.id == user.id

    def test_update_user(self, store):
        user = UserAccount(
            email="tester@example.com",
            role="Admin",
            password_hash=hash_password("Example123!"),
        )
        store.create_user(user)
        updated = store.update_user(user.id, last_login_at="2026-03-24T12:00:00")
        assert updated is not None
        assert updated.last_login_at == "2026-03-24T12:00:00"


# ── Stats ──────────────────────────────────────────────────────────────────────

class TestMongoStats:
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
        expected = {"backlog", "in_progress", "review", "done"}
        assert set(result["pipeline_by_status"].keys()) == expected

    def test_stats_counts_sessions_and_entities(self, store):
        store.add_session(PIISession(
            entity_counts={"EMAIL_ADDRESS": 3, "PERSON": 2}))
        result = store.stats()
        assert result["total_sessions"] == 1
        assert result["total_entities_redacted"] == 5
        assert result["entity_breakdown"]["EMAIL_ADDRESS"] == 3
        assert result["entity_breakdown"]["PERSON"] == 2

    def test_stats_attested_cards(self, store):
        store.add_card(PipelineCard(attested=True))
        store.add_card(PipelineCard(attested=False))
        assert store.stats()["attested_cards"] == 1

    def test_stats_pipeline_counts(self, store):
        store.add_card(PipelineCard(status="backlog"))
        store.add_card(PipelineCard(status="backlog"))
        store.add_card(PipelineCard(status="in_progress"))
        result = store.stats()
        assert result["pipeline_by_status"]["backlog"] == 2
        assert result["pipeline_by_status"]["in_progress"] == 1
        assert result["pipeline_by_status"]["review"] == 0

    def test_stats_appointment_count(self, store):
        store.add_appointment(Appointment(scheduled_for="2026-04-01T10:00:00"))
        store.add_appointment(Appointment(scheduled_for="2026-05-01T10:00:00"))
        assert store.stats()["total_appointments"] == 2

    def test_stats_audit_entries_counted(self, store):
        store.log_user_action("u", "test.action", "r", "id1")
        store.log_user_action("u", "test.action", "r", "id2")
        result = store.stats()
        assert result["total_audit_entries"] >= 2


# ── Cross-instance sharing (persistence semantics) ────────────────────────────

class TestMongoSharedInstance:
    def test_two_stores_same_uri_share_data(self, store_pair):
        """Two MongoStore objects pointing at the same URI see the same data."""
        s1, s2 = store_pair
        card = PipelineCard(title="Shared Card")
        s1.add_card(card)
        got = s2.get_card(card.id)
        assert got is not None
        assert got.title == "Shared Card"

    def test_deletion_visible_across_instances(self, store_pair):
        s1, s2 = store_pair
        card = PipelineCard(title="Delete Me")
        s1.add_card(card)
        s2.delete_card(card.id)
        assert s1.get_card(card.id) is None

    def test_update_visible_across_instances(self, store_pair):
        s1, s2 = store_pair
        appt = Appointment(title="Original",
                           scheduled_for="2026-04-01T10:00:00")
        s1.add_appointment(appt)
        s2.update_appointment(appt.id, title="Updated")
        got = s1.get_appointment(appt.id)
        assert got.title == "Updated"


# ── get_store() factory ───────────────────────────────────────────────────────

class TestMongoFactory:
    def setup_method(self):
        _reset_store()

    def teardown_method(self):
        _reset_store()
        os.environ.pop("MONGODB_URI", None)
        os.environ.pop("ANON_STORE_BACKEND", None)

    def test_factory_returns_mongo_store_when_configured(self):
        from store.mongo import MongoStore

        os.environ["ANON_STORE_BACKEND"] = "mongo"
        os.environ["MONGODB_URI"] = _unique_uri()
        with mongomock.patch(servers=(("localhost", 27017),)):
            with mock.patch.object(MongoStore, "_ensure_collections",
                                   return_value=None):
                s = get_store()
                assert isinstance(s, MongoStore)

    def test_factory_falls_back_to_memory_without_uri(self):
        from store.memory import MemoryStore

        os.environ["ANON_STORE_BACKEND"] = "mongo"
        os.environ.pop("MONGODB_URI", None)
        s = get_store()
        assert isinstance(s, MemoryStore)

    def test_factory_auto_mode_uses_mongo_when_uri_set(self):
        from store.mongo import MongoStore

        os.environ["ANON_STORE_BACKEND"] = "auto"
        os.environ["MONGODB_URI"] = _unique_uri()
        with mongomock.patch(servers=(("localhost", 27017),)):
            with mock.patch.object(MongoStore, "_ensure_collections",
                                   return_value=None):
                s = get_store()
                assert isinstance(s, MongoStore)

    def test_factory_returns_singleton(self):
        from store.mongo import MongoStore

        os.environ["ANON_STORE_BACKEND"] = "mongo"
        os.environ["MONGODB_URI"] = _unique_uri()
        with mongomock.patch(servers=(("localhost", 27017),)):
            with mock.patch.object(MongoStore, "_ensure_collections",
                                   return_value=None):
                s1 = get_store()
                s2 = get_store()
                assert s1 is s2
