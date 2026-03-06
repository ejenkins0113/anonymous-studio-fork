"""Shared in-process runtime context for the Taipy GUI app."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Event, Lock, Thread
from typing import Any, Dict, Optional, Set


@dataclass
class AppContext:
    """Container for mutable runtime registries used across callbacks."""

    scenarios: Dict[str, Any] = field(default_factory=dict)
    submission_ids: Dict[str, str] = field(default_factory=dict)
    file_cache: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    burndown_cache: Dict[str, Any] = field(
        default_factory=lambda: {"ts": 0.0, "sig": "", "payload": None}
    )
    live_state_ids: Set[str] = field(default_factory=set)
    live_state_lock: Lock = field(default_factory=Lock)
    live_stop_event: Event = field(default_factory=Event)
    live_thread: Optional[Thread] = None
    event_processor: Any = None
