"""
services/authz.py — OpenFGA authorization client for Anonymous Studio.

Design
------
• Fail-closed: any error during an FGA check → returns False (deny).
• Bypass mode: if OPENFGA_ENABLED != "true" the module is a no-op that
  always returns True — safe for local dev and unit tests without a
  running FGA stack.
• No external SDK dependency: uses stdlib urllib so the import always
  succeeds regardless of installed packages.

Principal mapping
-----------------
The OpenFGA principal for a user is ``user:<email>`` if gui_user_email is
set, otherwise ``user:<gui_user>`` (the proxy sub claim).  Call
``principal_for(state)`` to derive this consistently everywhere.

Usage
-----
    from services.authz import authz_check, principal_for

    principal = principal_for(state)
    if not authz_check(principal, "can_attest", "card", card_id):
        notify(state, "error", "Not authorized to attest this card.")
        return
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass  # Taipy state type for IDE; avoided at runtime to keep import lightweight

_log = logging.getLogger(__name__)

# ── Configuration (read once at module load) ──────────────────────────────────
OPENFGA_ENABLED  = os.getenv("OPENFGA_ENABLED", "false").lower() == "true"
OPENFGA_API_URL  = os.getenv("OPENFGA_API_URL",  "http://localhost:8080").rstrip("/")
OPENFGA_STORE_ID = os.getenv("OPENFGA_STORE_ID", "")
OPENFGA_MODEL_ID = os.getenv("OPENFGA_MODEL_ID", "")

_TIMEOUT_S = 3  # per-request timeout for FGA API calls


# ── Public API ────────────────────────────────────────────────────────────────

def principal_for(state) -> str:  # type: ignore[return]
    """
    Derive the OpenFGA principal string for the current session user.

    Returns ``"user:<email>"`` if gui_user_email is set and non-empty,
    else ``"user:<gui_user>"``.  Returns an empty string if neither is
    available (unauthenticated session — caller should block before here).
    """
    email = getattr(state, "gui_user_email", "").strip()
    sub   = getattr(state, "gui_user",       "").strip()
    identifier = email or sub
    return f"user:{identifier}" if identifier else ""


def authz_check(
    principal: str,
    relation: str,
    resource_type: str,
    resource_id: str,
) -> bool:
    """
    Check whether *principal* has *relation* on *resource_type*:*resource_id*.

    Parameters
    ----------
    principal     : OpenFGA user string, e.g. ``"user:alice@example.com"``
    relation      : OpenFGA relation, e.g. ``"can_attest"`` or ``"can_export"``
    resource_type : OpenFGA type, e.g. ``"card"`` or ``"audit_log"``
    resource_id   : resource identifier, e.g. ``"card-001"`` or ``"global"``

    Returns
    -------
    bool — True if allowed, False if denied or on any error.
    """
    if not OPENFGA_ENABLED:
        _log.debug(
            "authz bypass (OPENFGA_ENABLED=false): %s %s %s:%s",
            principal, relation, resource_type, resource_id,
        )
        return True

    if not OPENFGA_STORE_ID:
        _log.error("authz_check: OPENFGA_STORE_ID not set — denying")
        return False

    if not principal:
        _log.warning("authz_check: empty principal — denying")
        return False

    url = f"{OPENFGA_API_URL}/stores/{OPENFGA_STORE_ID}/check"
    body: dict = {
        "tuple_key": {
            "user":     principal,
            "relation": relation,
            "object":   f"{resource_type}:{resource_id}",
        },
    }
    if OPENFGA_MODEL_ID:
        body["authorization_model_id"] = OPENFGA_MODEL_ID

    try:
        data = json.dumps(body).encode()
        req  = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            result = json.loads(resp.read())
        allowed = bool(result.get("allowed", False))
        _log.info(
            "authz_check %s %s %s:%s → %s",
            principal, relation, resource_type, resource_id,
            "ALLOW" if allowed else "DENY",
        )
        return allowed

    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode(errors="replace") if exc.fp else ""
        _log.error(
            "authz_check HTTP %s for %s %s %s:%s — %s — denying",
            exc.code, principal, relation, resource_type, resource_id, body_text,
        )
        return False

    except Exception as exc:
        _log.error(
            "authz_check error for %s %s %s:%s — %s — denying",
            principal, relation, resource_type, resource_id, exc,
        )
        return False
