"""
Anonymous Studio — Store Package
==================================
Exports the ``get_store()`` factory and all public model/base symbols.

Backend selection
-----------------
``get_store()`` reads ``ANON_STORE_BACKEND`` and ``MONGODB_URI``:

- ``ANON_STORE_BACKEND=memory`` (default) → ``MemoryStore()``
- ``ANON_STORE_BACKEND=duckdb`` → ``DuckDBStore(ANON_DUCKDB_PATH)``
- ``ANON_STORE_BACKEND=mongo`` + ``MONGODB_URI`` set → ``MongoStore(uri)``
- ``ANON_STORE_BACKEND=auto`` → legacy behavior (use Mongo when URI is set)

Usage in app.py (unchanged from the original store.py import):

    from store import get_store, PipelineCard, Appointment, _now, _uid

Singleton pattern
-----------------
``get_store()`` caches the instance in ``_store``. The same instance is
returned on every call within a process. In Taipy's development mode
(single process), this means all callbacks share one store. In standalone
mode (multi-process workers), each worker gets its own MemoryStore instance,
but all workers share the same MongoDB database — which is the desired
behaviour for a production deployment.

To reset the singleton in tests:
    from store import _reset_store
    _reset_store()
"""
from __future__ import annotations

import os
from typing import Optional

from store.base import StoreBase
from store.models import (
    _now, _uid,
    PIISession, PipelineCard, Appointment, AuditEntry, UserAccount,
)
# Import utilities for re-export
from store.utils import (
    filter_audit_entries,
    filter_appointments_by_status,
    filter_appointments_by_time_range,
    get_scheduled_appointments,
    filter_cards_by_priority,
    filter_cards_by_status,
    filter_cards_attested,
    filter_sessions_by_time_window,
    filter_sessions_by_entities,
    count_by_severity,
    count_by_priority,
    count_sessions_by_operator,
    is_in_time_window,
    parse_time_window,
    filter_by_predicate,
    group_by,
    count_by,
)

__all__ = [
    # Factory
    "get_store",
    "get_store_backend_mode",
    "describe_store_backend",
    # Status string for UI banners (mirrors SPACY_MODEL_STATUS pattern)
    "STORE_STATUS",
    # Base class (for isinstance checks and type hints)
    "StoreBase",
    # Models
    "PIISession", "PipelineCard", "Appointment", "AuditEntry",
    "UserAccount",
    # Helpers (imported by app.py)
    "_now", "_uid",
    # Data access utilities (imported from store.utils)
    "filter_audit_entries",
    "filter_appointments_by_status",
    "filter_appointments_by_time_range",
    "get_scheduled_appointments",
    "filter_cards_by_priority",
    "filter_cards_by_status",
    "filter_cards_attested",
    "filter_sessions_by_time_window",
    "filter_sessions_by_entities",
    "count_by_severity",
    "count_by_priority",
    "count_sessions_by_operator",
    "is_in_time_window",
    "parse_time_window",
    "filter_by_predicate",
    "group_by",
    "count_by",
]

def _resolve_store_backend() -> str:
    mode = (os.environ.get("ANON_STORE_BACKEND", "memory") or "memory").strip().lower()
    if mode in {"memory", "duckdb", "mongo", "auto"}:
        return mode
    return "memory"


def _mongo_host_label(uri: str) -> str:
    return uri.split("@")[-1].split("/")[0] if "@" in uri else uri.split("//")[-1].split("/")[0]


def get_store_backend_mode() -> str:
    """Return configured backend mode from environment."""
    return _resolve_store_backend()


def describe_store_backend() -> str:
    """Return human-readable backend status for UI banners."""
    backend = _resolve_store_backend()
    mongo_uri = os.environ.get("MONGODB_URI", "").strip()
    duckdb_path = os.path.abspath(
        os.environ.get(
            "ANON_DUCKDB_PATH",
            os.path.join("/tmp", "anon_studio.duckdb"),
        )
    )
    if backend == "duckdb":
        return f"DuckDB: {duckdb_path}"
    if backend == "mongo" and mongo_uri:
        return f"MongoDB: {_mongo_host_label(mongo_uri)}"
    if backend == "auto" and mongo_uri:
        return f"MongoDB (auto): {_mongo_host_label(mongo_uri)}"
    if backend == "mongo" and not mongo_uri:
        return "Mongo selected but MONGODB_URI is empty. Falling back to in-memory."
    return "▲ In-memory store (data resets on restart)"


STORE_STATUS = describe_store_backend()

_store: Optional[StoreBase] = None


def get_store() -> StoreBase:
    """Return the global store singleton, creating it on first call.

    Backend selection:
    - ANON_STORE_BACKEND=memory (default) -> MemoryStore
    - ANON_STORE_BACKEND=duckdb -> DuckDBStore
    - ANON_STORE_BACKEND=mongo + MONGODB_URI set -> MongoStore
    - ANON_STORE_BACKEND=auto -> MongoStore when MONGODB_URI is set, else MemoryStore
    """
    global _store
    if _store is None:
        backend = _resolve_store_backend()
        uri = os.environ.get("MONGODB_URI", "").strip()
        use_mongo = (backend == "mongo" and bool(uri)) or (backend == "auto" and bool(uri))
        if backend == "duckdb":
            from store.duckdb import DuckDBStore  # deferred — optional dependency

            _store = DuckDBStore(os.environ.get("ANON_DUCKDB_PATH", "").strip() or None)
        elif use_mongo:
            from store.mongo import MongoStore  # deferred — pymongo optional
            _store = MongoStore(uri)
        else:
            from store.memory import MemoryStore
            _store = MemoryStore()
    return _store


def _reset_store() -> None:
    """Reset the singleton. Only for use in tests."""
    global _store
    _store = None


# Backward-compat alias — existing code that does ``isinstance(s, DataStore)``
# continues to work. New code should use StoreBase.
DataStore = None  # set lazily below to avoid circular import at module level


def __getattr__(name: str):
    """Lazy alias for DataStore → MemoryStore for backward compatibility."""
    if name == "DataStore":
        from store.memory import MemoryStore
        return MemoryStore
    raise AttributeError(f"module 'store' has no attribute {name!r}")
