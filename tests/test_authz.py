"""
Tests for services/authz.py — OpenFGA authorization client.

Invariants verified:
  1. OPENFGA_ENABLED=false → authz_check always returns True (bypass mode)
  2. OPENFGA_ENABLED=true, FGA returns allowed=true  → authz_check returns True
  3. OPENFGA_ENABLED=true, FGA returns allowed=false → authz_check returns False
  4. OPENFGA_ENABLED=true, FGA raises (HTTP error)   → authz_check returns False (fail-closed)
  5. OPENFGA_ENABLED=true, FGA raises (network error) → authz_check returns False (fail-closed)
  6. Empty principal → authz_check returns False (deny, no API call made)
  7. Missing OPENFGA_STORE_ID → authz_check returns False

  8. principal_for: email present → "user:<email>"
  9. principal_for: no email, username present → "user:<username>"
 10. principal_for: neither set → empty string

 11. app.on_attest_confirm: authz deny blocks store write
 12. app.on_export_audit_csv: authz deny blocks download
 13. app.on_export_audit_json: authz deny blocks download
 14. app.on_export_audit_csv: unauthenticated session blocks before authz
 15. app.on_export_audit_json: unauthenticated session blocks before authz
"""
from __future__ import annotations

import importlib
import json
import os
from unittest.mock import MagicMock, patch, call
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import urllib.error
import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def _reload_authz(**env_overrides):
    """Reload services.authz with specific env vars set."""
    import services.authz as az
    with patch.dict(os.environ, env_overrides, clear=False):
        importlib.reload(az)
    return az


def _app():
    try:
        import app
        return app
    except Exception as exc:
        pytest.skip(f"app module unavailable: {exc}")


def _make_state(**kwargs):
    state = MagicMock()
    defaults = dict(
        gui_user="alice",
        gui_user_email="alice@example.com",
        gui_user_groups="",
        gui_auth_source="proxy",
        attest_cid="card-001",
        attest_note="Reviewed.",
        attest_by="",
        audit_table=MagicMock(__class__=MagicMock()),
    )
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(state, k, v)
    return state


# ── Invariant 1: bypass mode ──────────────────────────────────────────────────

class TestBypassMode:
    def test_disabled_always_allows(self):
        import services.authz as az
        with patch.dict(os.environ, {"OPENFGA_ENABLED": "false"}):
            importlib.reload(az)
            assert az.authz_check("user:alice@example.com", "can_attest", "card", "c1") is True

    def test_disabled_allows_empty_principal(self):
        import services.authz as az
        with patch.dict(os.environ, {"OPENFGA_ENABLED": "false"}):
            importlib.reload(az)
            assert az.authz_check("", "can_attest", "card", "c1") is True


# ── Invariants 2-7: enabled mode ─────────────────────────────────────────────

class TestEnabledMode:
    """All tests patch urllib.request.urlopen to avoid needing a running FGA."""

    def _az_enabled(self):
        import services.authz as az
        with patch.dict(os.environ, {
            "OPENFGA_ENABLED":  "true",
            "OPENFGA_STORE_ID": "store-abc",
            "OPENFGA_MODEL_ID": "model-xyz",
            "OPENFGA_API_URL":  "http://fga.local:8080",
        }):
            importlib.reload(az)
        return az

    def test_allowed_true_returns_true(self):
        az = self._az_enabled()
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"allowed": True}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = az.authz_check("user:alice@example.com", "can_attest", "card", "c1")
        assert result is True

    def test_allowed_false_returns_false(self):
        az = self._az_enabled()
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"allowed": False}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = az.authz_check("user:bob@example.com", "can_attest", "card", "c1")
        assert result is False

    def test_http_error_fails_closed(self):
        az = self._az_enabled()
        exc = urllib.error.HTTPError(
            url="http://fga.local:8080/...", code=403,
            msg="Forbidden", hdrs=None, fp=None,
        )
        with patch("urllib.request.urlopen", side_effect=exc):
            result = az.authz_check("user:alice@example.com", "can_attest", "card", "c1")
        assert result is False

    def test_network_error_fails_closed(self):
        az = self._az_enabled()
        with patch("urllib.request.urlopen", side_effect=ConnectionRefusedError("offline")):
            result = az.authz_check("user:alice@example.com", "can_attest", "card", "c1")
        assert result is False

    def test_empty_principal_denied_without_api_call(self):
        az = self._az_enabled()
        with patch("urllib.request.urlopen") as mock_open:
            result = az.authz_check("", "can_attest", "card", "c1")
        assert result is False
        mock_open.assert_not_called()

    def test_missing_store_id_denied(self):
        import services.authz as az
        with patch.dict(os.environ, {
            "OPENFGA_ENABLED":  "true",
            "OPENFGA_STORE_ID": "",
            "OPENFGA_API_URL":  "http://fga.local:8080",
        }):
            importlib.reload(az)
        with patch("urllib.request.urlopen") as mock_open:
            result = az.authz_check("user:alice@example.com", "can_attest", "card", "c1")
        assert result is False
        mock_open.assert_not_called()


# ── Invariants 8-10: principal_for ───────────────────────────────────────────

class TestPrincipalFor:
    def _az(self):
        import services.authz as az
        return az

    def test_email_present_uses_email(self):
        az = self._az()
        state = MagicMock(gui_user="alice", gui_user_email="alice@example.com")
        assert az.principal_for(state) == "user:alice@example.com"

    def test_no_email_falls_back_to_username(self):
        az = self._az()
        state = MagicMock(gui_user="alice", gui_user_email="")
        assert az.principal_for(state) == "user:alice"

    def test_neither_set_returns_empty(self):
        az = self._az()
        state = MagicMock(gui_user="", gui_user_email="")
        assert az.principal_for(state) == ""


# ── Invariants 11-13: app enforcement ────────────────────────────────────────

class TestAppEnforcement:
    def test_attest_confirm_authz_deny_blocks_store_write(self):
        app = _app()
        from store import PipelineCard

        state = _make_state(gui_auth_source="proxy", gui_user="alice",
                            gui_user_email="alice@example.com")
        notified = []

        with patch("app.authz_check", return_value=False), \
             patch("app.notify", side_effect=lambda s, lvl, msg: notified.append((lvl, msg))), \
             patch("app.store") as mock_store:
            app.on_attest_confirm(state)

        assert any(lvl == "error" for lvl, _ in notified)
        mock_store.update_card.assert_not_called()

    def test_attest_confirm_authz_allow_proceeds(self):
        app = _app()
        from store import PipelineCard
        import pandas as pd

        card = PipelineCard(id="card-001", title="Test Card")
        state = _make_state(gui_auth_source="proxy", gui_user="alice",
                            gui_user_email="alice@example.com")

        with patch("app.authz_check", return_value=True), \
             patch("app.notify"), \
             patch("app.store") as mock_store, \
             patch("app._refresh_pipeline"), \
             patch("app._refresh_audit"), \
             patch("app._refresh_dashboard"), \
             patch("app.build_attestation_payload", return_value={"schema": "v1"}), \
             patch("app.sign_attestation_payload") as mock_sign:
            mock_store.get_card.return_value = card
            mock_sign.return_value = MagicMock(
                signed=True, algorithm="ed25519", key_id="k1",
                signature_b64="sig", public_key_b64="pk",
                payload_json='{}', payload_hash="abc",
                verified=True, error="",
            )
            app.on_attest_confirm(state)

        mock_store.update_card.assert_called_once()

    def test_export_audit_csv_authz_deny_blocks_download(self):
        app = _app()
        state = _make_state(gui_auth_source="proxy", gui_user="bob",
                            gui_user_email="bob@example.com")
        notified = []

        with patch("app.authz_check", return_value=False), \
             patch("app.notify", side_effect=lambda s, lvl, msg: notified.append((lvl, msg))), \
             patch("app.download") as mock_download:
            app.on_export_audit_csv(state)

        assert any(lvl == "error" for lvl, _ in notified)
        mock_download.assert_not_called()

    def test_export_audit_json_authz_deny_blocks_download(self):
        app = _app()
        state = _make_state(gui_auth_source="proxy", gui_user="bob",
                            gui_user_email="bob@example.com")
        notified = []

        with patch("app.authz_check", return_value=False), \
             patch("app.notify", side_effect=lambda s, lvl, msg: notified.append((lvl, msg))), \
             patch("app.download") as mock_download:
            app.on_export_audit_json(state)

        assert any(lvl == "error" for lvl, _ in notified)
        mock_download.assert_not_called()

    def test_export_audit_csv_unauthenticated_blocks_before_authz(self):
        app = _app()
        state = _make_state(gui_auth_source="unauthenticated", gui_user="", gui_user_email="")
        notified = []

        with patch("app.authz_check") as mock_authz, \
             patch("app.notify", side_effect=lambda s, lvl, msg: notified.append((lvl, msg))), \
             patch("app.download") as mock_download:
            app.on_export_audit_csv(state)

        assert any(lvl == "error" for lvl, _ in notified)
        mock_authz.assert_not_called()
        mock_download.assert_not_called()

    def test_export_audit_json_unauthenticated_blocks_before_authz(self):
        app = _app()
        state = _make_state(gui_auth_source="unauthenticated", gui_user="", gui_user_email="")
        notified = []

        with patch("app.authz_check") as mock_authz, \
             patch("app.notify", side_effect=lambda s, lvl, msg: notified.append((lvl, msg))), \
             patch("app.download") as mock_download:
            app.on_export_audit_json(state)

        assert any(lvl == "error" for lvl, _ in notified)
        mock_authz.assert_not_called()
        mock_download.assert_not_called()
