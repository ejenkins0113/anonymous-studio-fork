from __future__ import annotations

import pytest


def test_taipy_mockstate_smoke():
    try:
        from taipy.gui import Gui
        from taipy.gui.test import MockState
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.skip(f"Taipy MockState unavailable in this environment: {exc}")

    state = MockState(Gui(""), counter=1, label="demo")
    assert state.counter == 1
    assert state.label == "demo"

    state.counter = 2
    assert state.counter == 2


def test_on_qt_show_rationale_change_toggles_columns():
    """on_qt_show_rationale_change updates qt_entity_columns with/without
    Recognizer and Rationale when the toggle is flipped."""
    try:
        from unittest.mock import MagicMock
        from app import on_qt_show_rationale_change, QT_COLUMNS_FULL, QT_COLUMNS_SHORT
    except Exception as exc:
        pytest.skip(f"app module unavailable in this environment: {exc}")

    state = MagicMock()

    # Enable rationale → full columns (Recognizer + Rationale included)
    on_qt_show_rationale_change(state, value=True)
    assert state.qt_entity_columns == QT_COLUMNS_FULL

    # Disable rationale → short columns (Recognizer + Rationale omitted)
    on_qt_show_rationale_change(state, value=False)
    assert state.qt_entity_columns == QT_COLUMNS_SHORT

    assert "Recognizer" in QT_COLUMNS_FULL
    assert "Rationale" in QT_COLUMNS_FULL
    assert "Recognizer" not in QT_COLUMNS_SHORT
    assert "Rationale" not in QT_COLUMNS_SHORT
