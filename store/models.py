"""
Anonymous Studio — Domain Models
=================================
Single source of truth for all data shapes used by both MemoryStore and
MongoStore. These dataclasses define the schema; no ORM or ODM is involved.

Serialization notes
-------------------
- ``dataclasses.asdict(model)`` produces a JSON-serializable dict suitable
  for both MongoDB insertion and Taipy state binding.
- MongoDB: strip the ``id`` field and store it as ``_id``.
  e.g. ``doc = {**asdict(card), "_id": card.id}; del doc["id"]``
- Taipy state: all fields must be JSON-serializable (str / int / float /
  bool / list / dict). No datetime objects — use ISO-8601 strings (_now()).

Adding a new field
------------------
1. Add the field here with a default.
2. Add a corresponding column/key in MongoStore if the field needs to be
   indexed or queried.
3. Update the Taipy table ``columns=`` string in app.py if the field should
   appear in the UI.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    """Current timestamp as ISO-8601 string (seconds precision)."""
    return datetime.now().isoformat(timespec="seconds")


def _uid() -> str:
    """Short unique ID — 8-char hex prefix of a UUID4.

    Long enough to be collision-free in practice for a single-tenant app.
    MongoStore note: MongoDB's ObjectId is NOT used; these string IDs are
    stored as ``_id`` directly so app code never needs to handle ObjectId.
    """
    return str(uuid.uuid4())[:8]


# ── Domain Models ─────────────────────────────────────────────────────────────

@dataclass
class PIISession:
    """One de-identification run — quick text or background file job.

    Created by:
    - ``on_qt_anonymize`` (PII Text page) for quick text runs
    - ``_bg_job_done`` via ``store.add_session()`` for file job completions
    """
    id: str                          = field(default_factory=_uid)
    title: str                       = "Untitled Session"
    original_text: str               = ""
    anonymized_text: str             = ""
    entities: List[Dict]             = field(default_factory=list)
    entity_counts: Dict[str, int]    = field(default_factory=dict)
    operator: str                    = "replace"
    source_type: str                 = "text"   # "text" | "file"
    file_name: Optional[str]         = None
    created_at: str                  = field(default_factory=_now)
    pipeline_card_id: Optional[str]  = None
    processing_ms: float             = 0.0      # engine wall-clock ms; 0 = not measured


@dataclass
class PipelineCard:
    """Kanban card tracking one de-identification pipeline task.

    Status lifecycle: backlog → in_progress → review → done
    Taipy pipeline page uses ``store.cards_by_status()`` to build the board.
    ``scenario_id`` links the card to a taipy.core Scenario for result loading.
    ``job_id`` is the anonymization job UUID used to look up PROGRESS_REGISTRY.

    Attestation:
    - Set ``attested=True``, ``attested_by``, ``attested_at``, ``attestation``
      all at once via ``store.update_card(id, attested=True, ...)``
    - ``update_card`` auto-logs a ``compliance.attest`` audit entry when
      ``attested=True`` is passed.
    - Optional digital signature metadata is stored in ``attestation_sig_*``
      fields when signature keys are configured.
    """
    id: str                      = field(default_factory=_uid)
    title: str                   = "New Task"
    description: str             = ""
    status: str                  = "backlog"   # backlog|in_progress|review|done
    card_type: str               = "file"      # file|text|database|api
    data_source: str             = ""          # free-text description of the data origin
    assignee: str                = ""
    priority: str                = "medium"    # low|medium|high|critical
    labels: List[str]            = field(default_factory=list)
    session_id: Optional[str]    = None
    created_at: str              = field(default_factory=_now)
    updated_at: str              = field(default_factory=_now)
    done_at: Optional[str]       = None
    attestation: str             = ""
    attested: bool               = False
    attested_by: str             = ""
    attested_at: Optional[str]   = None
    attestation_sig_alg: str     = ""   # e.g. "ed25519"
    attestation_sig_key_id: str  = ""   # signer key identifier
    attestation_sig: str         = ""   # base64 detached signature
    attestation_sig_public_key: str = ""  # base64 raw Ed25519 public key
    attestation_sig_payload: str = ""   # canonical payload JSON
    attestation_sig_payload_hash: str = ""  # SHA-256 hex of payload JSON
    attestation_sig_verified: bool = False
    attestation_sig_error: str   = ""   # signing error when signature is unavailable
    scenario_id: Optional[str]   = None  # taipy.core Scenario.id
    job_id: Optional[str]        = None  # anonymization job UUID


@dataclass
class Appointment:
    """Scheduled compliance review or attestation meeting.

    ``pipeline_card_id`` optionally links to the card being reviewed.
    ``scheduled_for`` is an ISO-8601 datetime string used for sorting and
    upcoming-appointment filtering (string comparison works because the
    format is lexicographically ordered).
    """
    id: str                          = field(default_factory=_uid)
    title: str                       = "PII Review"
    description: str                 = ""
    scheduled_for: str               = ""  # ISO-8601 datetime string
    duration_mins: int               = 30
    attendees: List[str]             = field(default_factory=list)
    pipeline_card_id: Optional[str]  = None
    status: str                      = "scheduled"  # scheduled|completed|cancelled
    created_at: str                  = field(default_factory=_now)


@dataclass
class AuditEntry:
    """Immutable compliance audit log entry.

    Entries must never be modified or deleted after creation.
    MongoStore: use a capped collection (max_size=52_428_800, max=100_000)
    to enforce append-only semantics and automatic rotation.

    Severity levels:
    - ``info``     — normal operation
    - ``warning``  — deletions, unusual events
    - ``critical`` — security or compliance violations
    """
    id: str            = field(default_factory=_uid)
    timestamp: str     = field(default_factory=_now)
    actor: str         = "system"
    action: str        = ""
    resource_type: str = ""
    resource_id: str   = ""
    details: str       = ""
    severity: str      = "info"  # info | warning | critical

@dataclass
class UserAccount:
    """Application user record for local email/password authentication."""

    id: str                      = field(default_factory=_uid)
    email: str                   = ""
    password_hash: str           = ""
    role: str                    = "Researcher"
    full_name: str               = ""
    is_active: bool              = True
    created_at: str              = field(default_factory=_now)
    updated_at: str              = field(default_factory=_now)
    last_login_at: Optional[str] = None