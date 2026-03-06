"""Shared progress state helpers for GUI and worker runtimes.

This module centralizes how progress is read/written so the GUI does not need
to depend directly on worker task internals.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Dict, MutableMapping

from services.progress_snapshots import (
    delete_progress_snapshot,
    read_progress_snapshot,
    write_progress_snapshot,
)

_FALLBACK_REGISTRY: Dict[str, Dict[str, Any]] = {}


def get_progress_registry() -> MutableMapping[str, Dict[str, Any]]:
    """Return the task-owned in-memory registry when available."""
    try:
        from tasks import PROGRESS_REGISTRY as task_registry

        return task_registry
    except Exception:
        return _FALLBACK_REGISTRY


def read_progress(job_id: str) -> Dict[str, Any]:
    """Return freshest progress payload from memory + durable snapshot."""
    mem_registry = get_progress_registry()
    mem = dict(mem_registry.get(job_id, {}) or {})
    snap = dict(read_progress_snapshot(job_id) or {})
    if not mem:
        return snap
    if not snap:
        return mem
    mem_updated = float(mem.get("updated_at", 0) or 0.0)
    snap_updated = float(snap.get("updated_at", 0) or 0.0)
    return {**snap, **mem} if mem_updated >= snap_updated else {**mem, **snap}


def persist_progress(job_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Persist progress to memory registry and durable snapshot storage."""
    if not job_id:
        return {}
    merged = {
        **read_progress(job_id),
        **(payload or {}),
        "updated_at": float((payload or {}).get("updated_at", 0) or time.time()),
        "ts": str((payload or {}).get("ts", "") or datetime.now().isoformat(timespec="seconds")),
    }
    get_progress_registry()[job_id] = merged
    write_progress_snapshot(job_id, merged)
    return merged


def clear_progress(job_id: str) -> None:
    """Remove progress state from memory registry and durable snapshot."""
    if not job_id:
        return
    get_progress_registry().pop(job_id, None)
    delete_progress_snapshot(job_id)
