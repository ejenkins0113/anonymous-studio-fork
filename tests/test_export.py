"""Tests for card-011 Export Audit Logs & Pipeline Data functionality."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pandas as pd

import app
from store import get_store, PipelineCard, AuditEntry


def _make_state(pipeline_export_status_filter="All"):
    return SimpleNamespace(
        audit_search="",
        audit_sev="all",
        audit_table=pd.DataFrame(),
        is_authenticated=True,
        current_user_role="Admin",
        pipeline_export_status_filter=pipeline_export_status_filter,
    )


def test_on_audit_export_csv_downloads_csv(monkeypatch):
    store = get_store()
    store.log_user_action("tester", "test.action", "test", "1", "detail-a")
    store.log_user_action("tester", "test.action", "test", "2", "detail-b")

    state = _make_state()
    captured = {}
    monkeypatch.setattr(app, "download",
                        lambda _s, content, name: captured.update(content=content, name=name))
    monkeypatch.setattr(app, "notify", lambda *a, **kw: None)
    monkeypatch.setattr(app, "_refresh_audit", lambda _s: None)
    monkeypatch.setattr(app, "store", store)

    app.on_audit_export_csv(state)

    assert captured["name"] == "audit_log.csv"
    csv_text = captured["content"].decode("utf-8")
    assert "tester" in csv_text
    assert "detail-a" in csv_text
    df = pd.read_csv(pd.io.common.StringIO(csv_text))
    assert len(df) >= 2


def test_on_audit_export_json_downloads_json(monkeypatch):
    store = get_store()
    store.log_user_action("tester", "test.action", "test", "1", "detail-j")

    state = _make_state()
    captured = {}
    monkeypatch.setattr(app, "download",
                        lambda _s, content, name: captured.update(content=content, name=name))
    monkeypatch.setattr(app, "notify", lambda *a, **kw: None)
    monkeypatch.setattr(app, "_refresh_audit", lambda _s: None)
    monkeypatch.setattr(app, "store", store)

    app.on_audit_export_json(state)

    assert captured["name"] == "audit_log.json"
    data = json.loads(captured["content"].decode("utf-8"))
    assert isinstance(data, list)
    assert any("detail-j" in e.get("details", "") for e in data)


def test_on_audit_export_csv_empty_warns(monkeypatch):
    from store.memory import MemoryStore
    empty_store = MemoryStore(seed=False)

    state = _make_state()
    notifications = []
    monkeypatch.setattr(app, "download", lambda *a, **kw: None)
    monkeypatch.setattr(app, "notify",
                        lambda _s, level, msg: notifications.append((level, msg)))
    monkeypatch.setattr(app, "_refresh_audit", lambda _s: None)
    monkeypatch.setattr(app, "store", empty_store)

    app.on_audit_export_csv(state)

    assert any(level == "warning" for level, _ in notifications)


def test_on_pipeline_export_csv_downloads_csv(monkeypatch):
    store = get_store()
    card = PipelineCard(title="Test Card", status="backlog", priority="high")
    store.add_card(card)

    state = _make_state()
    captured = {}
    monkeypatch.setattr(app, "download",
                        lambda _s, content, name: captured.update(content=content, name=name))
    monkeypatch.setattr(app, "notify", lambda *a, **kw: None)
    monkeypatch.setattr(app, "_refresh_audit", lambda _s: None)
    monkeypatch.setattr(app, "store", store)

    app.on_pipeline_export_csv(state)

    assert captured["name"] == "pipeline_cards.csv"
    csv_text = captured["content"].decode("utf-8")
    assert "Test Card" in csv_text


def test_on_pipeline_export_json_downloads_json(monkeypatch):
    store = get_store()
    card = PipelineCard(title="JSON Card", status="review", priority="medium")
    store.add_card(card)

    state = _make_state()
    captured = {}
    monkeypatch.setattr(app, "download",
                        lambda _s, content, name: captured.update(content=content, name=name))
    monkeypatch.setattr(app, "notify", lambda *a, **kw: None)
    monkeypatch.setattr(app, "_refresh_audit", lambda _s: None)
    monkeypatch.setattr(app, "store", store)

    app.on_pipeline_export_json(state)

    assert captured["name"] == "pipeline_cards.json"
    data = json.loads(captured["content"].decode("utf-8"))
    assert isinstance(data, list)
    assert any(c.get("title") == "JSON Card" for c in data)


def test_on_pipeline_export_csv_empty_warns(monkeypatch):
    from store.memory import MemoryStore
    empty_store = MemoryStore(seed=False)

    state = _make_state()
    notifications = []
    monkeypatch.setattr(app, "download", lambda *a, **kw: None)
    monkeypatch.setattr(app, "notify",
                        lambda _s, level, msg: notifications.append((level, msg)))
    monkeypatch.setattr(app, "_refresh_audit", lambda _s: None)
    monkeypatch.setattr(app, "store", empty_store)

    app.on_pipeline_export_csv(state)

    assert any(level == "warning" for level, _ in notifications)


def test_on_pipeline_export_csv_filtered_by_status(monkeypatch):
    """Filtered CSV export only includes cards with matching status."""
    from store.memory import MemoryStore
    test_store = MemoryStore(seed=False)
    test_store.add_card(PipelineCard(title="Backlog Card", status="backlog"))
    test_store.add_card(PipelineCard(title="Done Card", status="done"))

    state = _make_state(pipeline_export_status_filter="backlog")
    captured = {}
    monkeypatch.setattr(app, "download",
                        lambda _s, content, name: captured.update(content=content, name=name))
    monkeypatch.setattr(app, "notify", lambda *a, **kw: None)
    monkeypatch.setattr(app, "_refresh_audit", lambda _s: None)
    monkeypatch.setattr(app, "store", test_store)

    app.on_pipeline_export_csv(state)

    assert captured["name"] == "pipeline_backlog.csv"
    csv_text = captured["content"].decode("utf-8")
    assert "Backlog Card" in csv_text
    assert "Done Card" not in csv_text


def test_on_pipeline_export_json_filtered_by_status(monkeypatch):
    """Filtered JSON export only includes cards with matching status."""
    from store.memory import MemoryStore
    test_store = MemoryStore(seed=False)
    test_store.add_card(PipelineCard(title="Review Card", status="review"))
    test_store.add_card(PipelineCard(title="In Progress Card", status="in_progress"))

    state = _make_state(pipeline_export_status_filter="review")
    captured = {}
    monkeypatch.setattr(app, "download",
                        lambda _s, content, name: captured.update(content=content, name=name))
    monkeypatch.setattr(app, "notify", lambda *a, **kw: None)
    monkeypatch.setattr(app, "_refresh_audit", lambda _s: None)
    monkeypatch.setattr(app, "store", test_store)

    app.on_pipeline_export_json(state)

    assert captured["name"] == "pipeline_review.json"
    data = json.loads(captured["content"].decode("utf-8"))
    assert all(c["status"] == "review" for c in data)
    assert any(c["title"] == "Review Card" for c in data)


def test_on_pipeline_export_filtered_empty_warns(monkeypatch):
    """Filtered export warns when no cards match the selected status."""
    from store.memory import MemoryStore
    test_store = MemoryStore(seed=False)
    test_store.add_card(PipelineCard(title="Done Card", status="done"))

    state = _make_state(pipeline_export_status_filter="backlog")
    notifications = []
    monkeypatch.setattr(app, "download", lambda *a, **kw: None)
    monkeypatch.setattr(app, "notify",
                        lambda _s, level, msg: notifications.append((level, msg)))
    monkeypatch.setattr(app, "_refresh_audit", lambda _s: None)
    monkeypatch.setattr(app, "store", test_store)

    app.on_pipeline_export_csv(state)

    assert any(level == "warning" for level, _ in notifications)


def test_on_pipeline_export_all_unfiltered(monkeypatch):
    """'All' filter exports every card regardless of status."""
    from store.memory import MemoryStore
    test_store = MemoryStore(seed=False)
    test_store.add_card(PipelineCard(title="Card A", status="backlog"))
    test_store.add_card(PipelineCard(title="Card B", status="done"))

    state = _make_state(pipeline_export_status_filter="All")
    captured = {}
    monkeypatch.setattr(app, "download",
                        lambda _s, content, name: captured.update(content=content, name=name))
    monkeypatch.setattr(app, "notify", lambda *a, **kw: None)
    monkeypatch.setattr(app, "_refresh_audit", lambda _s: None)
    monkeypatch.setattr(app, "store", test_store)

    app.on_pipeline_export_csv(state)

    assert captured["name"] == "pipeline_cards.csv"
    csv_text = captured["content"].decode("utf-8")
    assert "Card A" in csv_text
    assert "Card B" in csv_text

    """Export actions should themselves be logged in the audit trail."""
    from store.memory import MemoryStore
    test_store = MemoryStore(seed=False)
    card = PipelineCard(title="Audit Trail Card", status="backlog")
    test_store.add_card(card)

    state = _make_state()
    monkeypatch.setattr(app, "download", lambda *a, **kw: None)
    monkeypatch.setattr(app, "notify", lambda *a, **kw: None)
    monkeypatch.setattr(app, "_refresh_audit", lambda _s: None)
    monkeypatch.setattr(app, "store", test_store)

    audit_before = len(test_store.list_audit())
    app.on_pipeline_export_csv(state)
    audit_after = len(test_store.list_audit())

    assert audit_after > audit_before
    newest = test_store.list_audit()[0]
    assert "pipeline.export" in newest.action
