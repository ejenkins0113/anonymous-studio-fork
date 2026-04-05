"""
Tests for Sprint 3 features:
  #44 — Anonymize PII with multiple operators (inline selector)
  #39 — Pipeline summary dashboard: dash_kpi_sessions_total
  #27 — Detection rationale toggle (on_qt_show_rationale_change)
  #35 — Save de-identification session (_refresh_sessions DataFrame shape)

Design notes
------------
- app.store is the module-level singleton; _reset_store() clears it but does
  NOT update app.store — so store-level tests must go through app.store
  directly, not get_store(), to match what app functions actually see.
- Dashboard/session tests use delta assertions (count before vs. after) so
  they're safe to run in any order without resetting global state.
"""
from __future__ import annotations

import pandas as pd
import pytest
from unittest.mock import MagicMock


def _app():
    """Import app with memory store; skip if environment can't support it."""
    try:
        import app
        return app
    except Exception as exc:
        pytest.skip(f"app module unavailable: {exc}")


def _definitions():
    """Import Taipy page definitions for markup contract checks."""
    try:
        from pages import definitions
        return definitions
    except Exception as exc:
        pytest.skip(f"definitions module unavailable: {exc}")


# ── #44 — operator selector state vars ───────────────────────────────────────

class TestOperatorSelector:
    def test_qt_operator_default_is_replace(self):
        assert _app().qt_operator == "replace"

    def test_qt_operator_list_contains_all_presidio_ops(self):
        expected = {"replace", "redact", "mask", "hash", "synthesize"}
        assert expected.issubset(set(_app().qt_operator_list))

    def test_qt_operator_list_includes_synthesize(self):
        assert "synthesize" in _app().qt_operator_list


# ── #27 — detection rationale toggle ─────────────────────────────────────────

class TestRationaleToggle:
    def test_default_shows_full_columns(self):
        app = _app()
        assert app.qt_entity_columns == app.QT_COLUMNS_FULL

    def test_toggle_off_switches_to_short_columns(self):
        app = _app()
        state = MagicMock()
        app.on_qt_show_rationale_change(state, value=False)
        assert state.qt_entity_columns == app.QT_COLUMNS_SHORT

    def test_toggle_on_switches_to_full_columns(self):
        app = _app()
        state = MagicMock()
        app.on_qt_show_rationale_change(state, value=True)
        assert state.qt_entity_columns == app.QT_COLUMNS_FULL

    def test_full_columns_includes_recognizer(self):
        assert "Recognizer" in _app().QT_COLUMNS_FULL

    def test_short_columns_excludes_recognizer(self):
        assert "Recognizer" not in _app().QT_COLUMNS_SHORT


# ── #39 — dashboard sessions KPI ─────────────────────────────────────────────

class TestDashboardSessionsKPI:
    def test_dash_kpi_sessions_total_exists_and_is_zero_at_startup(self):
        app = _app()
        assert hasattr(app, "dash_kpi_sessions_total")
        assert app.dash_kpi_sessions_total == 0

    def test_dash_kpi_sessions_total_is_int(self):
        assert isinstance(_app().dash_kpi_sessions_total, int)

    def test_refresh_dashboard_increments_sessions_kpi(self):
        """_refresh_dashboard must set dash_kpi_sessions_total = len(store.sessions)."""
        app = _app()
        from store import PIISession

        before = len(app.store.list_sessions())

        app.store.add_session(PIISession(
            title="KPI delta test",
            original_text="John Doe",
            anonymized_text="<PERSON>",
            entities=[],
            entity_counts={"PERSON": 1},
            operator="replace",
        ))

        state = MagicMock()
        state.dash_completion_pct = 0
        state.dash_inflight_cards = 0
        state.dash_backlog_cards  = 0
        state.dash_time_window    = "All"
        state.dash_report_mode    = "Overview"

        app._invalidate_store_caches()
        app._refresh_dashboard(state)

        assert state.dash_kpi_sessions_total == before + 1


# ── #35 — _refresh_sessions DataFrame shape ───────────────────────────────────

class TestRefreshSessions:
    def test_refresh_sessions_returns_dataframe_with_correct_columns(self):
        """_refresh_sessions must always set qt_sessions_data with the 5 expected columns."""
        app = _app()
        state = MagicMock()
        app._refresh_sessions(state)

        df = state.qt_sessions_data
        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == ["ID", "Title", "Operator", "Entities", "Created"]

    def test_saved_session_appears_in_sessions_dataframe(self):
        app = _app()
        from store import PIISession

        before = len(app.store.list_sessions())

        app.store.add_session(PIISession(
            title="SSN run",
            original_text="SSN: 123-45-6789",
            anonymized_text="SSN: <US_SSN>",
            entities=[],
            entity_counts={"US_SSN": 1},
            operator="mask",
        ))

        state = MagicMock()
        app._invalidate_store_caches()
        app._refresh_sessions(state)

        df = state.qt_sessions_data
        assert len(df) == before + 1

        # The row we just saved should be last (list_sessions newest-first is fine;
        # just find our row by title to avoid ordering assumptions).
        our_row = df[df["Title"] == "SSN run"].iloc[0]
        assert our_row["Operator"] == "mask"
        assert our_row["Entities"] == 1

    def test_session_id_is_truncated_to_8_chars(self):
        app = _app()
        from store import PIISession

        app.store.add_session(PIISession(title="id-len-check", entity_counts={"EMAIL": 2}))

        state = MagicMock()
        app._invalidate_store_caches()
        app._refresh_sessions(state)

        df = state.qt_sessions_data
        our_row = df[df["Title"] == "id-len-check"].iloc[0]
        assert len(our_row["ID"]) == 8


# ── markup contracts for Sprint 3 UI placement ────────────────────────────────

class TestSprint3MarkupContracts:
    def test_analyze_page_exposes_operator_selector_inline_before_actions(self):
        qt = _definitions().QT
        selector = "<|{qt_operator}|selector|"

        assert qt.count(selector) == 2
        assert qt.index(selector) < qt.index("<|part|class_name=qt-actions|")

    def test_dashboard_overview_strip_includes_sessions_saved_ticker(self):
        dash = _definitions().DASH
        ticker = "<|{dash_kpi_sessions_total}|text|class_name=dash-ticker-value|>"
        label = "<|Sessions Saved|text|class_name=dash-ticker-label|>"

        assert ticker in dash
        assert label in dash
        assert dash.index(ticker) < dash.index("<|part|class_name=dash-status-band|")

    def test_settings_dialog_keeps_rationale_toggle_and_dynamic_columns_binding(self):
        qt = _definitions().QT
        dialog = "<|{qt_settings_open}|dialog|"
        toggle = "<|{qt_show_rationale}|toggle|on_change=on_qt_show_rationale_change|"
        columns = "<|{qt_entity_rows}|table|columns={qt_entity_columns}|"

        assert columns in qt
        assert toggle in qt
        assert qt.index(dialog) < qt.index(toggle) < qt.index('<|part|render={qt_operator=="synthesize"}|')
