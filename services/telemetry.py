"""
Anonymous Studio — Taipy Telemetry (Prometheus exporter)

Hooks into the Taipy EventProcessor to emit Prometheus metrics for every
job lifecycle change.  A lightweight HTTP server (started via
`start_metrics_server`) lets Prometheus scrape those metrics at
``http://<host>:<ANON_METRICS_PORT>/metrics``.

Grafana (or any Prometheus-compatible tool) can then visualise:
  - Functional metric : jobs created / completed / failed  (Counter)
  - Operational metric: job queue depth per status          (Gauge)
  - Performance metric: job execution duration              (Histogram)
  - Data metric       : entities detected / rows processed  (Counter)

Environment variables
---------------------
ANON_METRICS_PORT  Port for the Prometheus metrics endpoint.
                   Set to a positive integer to enable  (e.g. 9100).
                   Defaults to 0 (disabled).

Usage (called from app.py once the EventProcessor is live)
----------------------------------------------------------
    from services.telemetry import register_telemetry, start_metrics_server

    register_telemetry(event_processor)   # subscribe to Taipy events
    start_metrics_server(9100)            # expose /metrics

Public API
----------
    register_telemetry(event_processor)  -> None
    start_metrics_server(port)           -> None
    record_job_completion(job_id, stats) -> None   # called from tasks.py / bg thread
    get_telemetry_snapshot()             -> dict   # in-process counters (no prom needed)
    get_recent_events(limit)             -> list   # last N captured Taipy events
    clear_telemetry()                    -> None   # reset counters (tests only)
"""
from __future__ import annotations

import logging
import time
from threading import Lock
from typing import Any, Dict, Optional

_log = logging.getLogger(__name__)

# ── Optional Prometheus dependency ─────────────────────────────────────────────
try:
    from prometheus_client import (
        Counter,
        Gauge,
        Histogram,
        start_http_server as _prom_start_http_server,
    )
    _PROM_AVAILABLE = True
except ImportError:  # prometheus_client not installed
    _PROM_AVAILABLE = False
    _log.warning(
        "[Telemetry] prometheus_client is not installed.  "
        "Metrics collection is disabled.  "
        "Install with: pip install prometheus_client"
    )

# ── Metric definitions (created only when prometheus_client is available) ──────
if _PROM_AVAILABLE:
    _JOBS_CREATED = Counter(
        "anon_jobs_created_total",
        "Total number of Taipy jobs created (submitted to the Orchestrator).",
    )
    _JOBS_STATUS = Counter(
        "anon_jobs_status_total",
        "Total number of Taipy jobs that reached a terminal or transitional status.",
        ["status"],          # COMPLETED | FAILED | CANCELED | RUNNING | SKIPPED …
    )
    _SCENARIOS_CREATED = Counter(
        "anon_scenarios_created_total",
        "Total number of PII pipeline scenarios created.",
    )
    _JOB_DURATION = Histogram(
        "anon_job_duration_seconds",
        "Wall-clock duration of completed or failed PII pipeline jobs.",
        buckets=(5, 15, 30, 60, 120, 300, 600, float("inf")),
    )
    _ENTITIES_DETECTED = Counter(
        "anon_entities_detected_total",
        "Cumulative PII entities detected across all completed jobs.",
    )
    _ROWS_PROCESSED = Counter(
        "anon_rows_processed_total",
        "Cumulative dataset rows processed across all completed jobs.",
    )
    _QUEUE_DEPTH = Gauge(
        "anon_job_queue_depth",
        "Current number of Taipy jobs in a given status.",
        ["status"],
    )

# ── Per-job start-time registry (for duration calculation) ──────────────────────
_job_start: Dict[str, float] = {}
_job_start_lock = Lock()

# ── Guard: only register once ──────────────────────────────────────────────────
_registered = False

# ── In-process telemetry state (always available, no prometheus_client needed) ──
_TELEMETRY_LOCK = Lock()
_TELEMETRY_STATE: Dict[str, Any] = {
    "jobs_created":        0,
    "jobs_running":        0,
    "jobs_completed":      0,
    "jobs_failed":         0,
    "jobs_canceled":       0,
    "scenarios_created":   0,
    "entities_detected":   0,
    "rows_processed":      0,
    "durations_s":         [],   # list[float] — wall-clock seconds per completed job
}
_RECENT_EVENTS: list = []        # list[dict] — last _MAX_EVENTS entries
_MAX_EVENTS = 200


def _record_event(entity_type: str, operation: str, attr_name: str, attr_value: str, entity_id: str) -> None:
    """Append an event to the recent-events ring buffer."""
    entry = {
        "ts":          time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "entity_type": entity_type,
        "operation":   operation,
        "attribute":   attr_name,
        "value":       attr_value,
        "entity_id":   entity_id[:16] if entity_id else "",
    }
    with _TELEMETRY_LOCK:
        _RECENT_EVENTS.append(entry)
        if len(_RECENT_EVENTS) > _MAX_EVENTS:
            del _RECENT_EVENTS[: len(_RECENT_EVENTS) - _MAX_EVENTS]


def _on_telemetry_event(event: Any) -> None:
    """Server-side Taipy event callback (no GUI state)."""
    try:
        entity_type = str(getattr(event, "entity_type", ""))
        operation   = str(getattr(event, "operation",   ""))
        attr_name   = str(getattr(event, "attribute_name",  "") or "")
        attr_value  = str(getattr(event, "attribute_value", "") or "")
        entity_id   = str(getattr(event, "entity_id",   "") or "")

        # ── Job created ───────────────────────────────────────────────────────
        if "JOB" in entity_type and "CREATION" in operation:
            if _PROM_AVAILABLE:
                _JOBS_CREATED.inc()
            with _TELEMETRY_LOCK:
                _TELEMETRY_STATE["jobs_created"] += 1
            with _job_start_lock:
                _job_start[entity_id] = time.monotonic()
            _record_event(entity_type, operation, attr_name, attr_value, entity_id)
            return

        # ── Job status update ─────────────────────────────────────────────────
        if "JOB" in entity_type and "UPDATE" in operation and attr_name == "status":
            status_upper = attr_value.upper()
            if _PROM_AVAILABLE:
                _JOBS_STATUS.labels(status=status_upper).inc()
                _QUEUE_DEPTH.labels(status=status_upper).inc()

            terminal = {"COMPLETED", "FAILED", "CANCELED", "SKIPPED", "ABANDONED"}
            duration: Optional[float] = None
            if any(t in status_upper for t in terminal):
                if _PROM_AVAILABLE:
                    _QUEUE_DEPTH.labels(status="RUNNING").dec()
                    _QUEUE_DEPTH.labels(status="PENDING").dec()
                with _job_start_lock:
                    start = _job_start.pop(entity_id, None)
                if start is not None:
                    duration = time.monotonic() - start
                    if _PROM_AVAILABLE:
                        _JOB_DURATION.observe(duration)

                with _TELEMETRY_LOCK:
                    if "COMPLETED" in status_upper or "SKIPPED" in status_upper:
                        _TELEMETRY_STATE["jobs_completed"] += 1
                        _TELEMETRY_STATE["jobs_running"] = max(0, _TELEMETRY_STATE["jobs_running"] - 1)
                    elif "FAILED" in status_upper or "ABANDONED" in status_upper:
                        _TELEMETRY_STATE["jobs_failed"] += 1
                        _TELEMETRY_STATE["jobs_running"] = max(0, _TELEMETRY_STATE["jobs_running"] - 1)
                    elif "CANCELED" in status_upper:
                        _TELEMETRY_STATE["jobs_canceled"] += 1
                        _TELEMETRY_STATE["jobs_running"] = max(0, _TELEMETRY_STATE["jobs_running"] - 1)
                    if duration is not None:
                        _TELEMETRY_STATE["durations_s"].append(round(duration, 2))
                        if len(_TELEMETRY_STATE["durations_s"]) > 1000:
                            _TELEMETRY_STATE["durations_s"] = _TELEMETRY_STATE["durations_s"][-1000:]
            elif "RUNNING" in status_upper:
                if _PROM_AVAILABLE:
                    _QUEUE_DEPTH.labels(status="PENDING").dec()
                with _TELEMETRY_LOCK:
                    _TELEMETRY_STATE["jobs_running"] += 1

            _record_event(entity_type, operation, attr_name, attr_value, entity_id)
            return

        # ── Scenario created ──────────────────────────────────────────────────
        if "SCENARIO" in entity_type and "CREATION" in operation:
            if _PROM_AVAILABLE:
                _SCENARIOS_CREATED.inc()
            with _TELEMETRY_LOCK:
                _TELEMETRY_STATE["scenarios_created"] += 1
            _record_event(entity_type, operation, attr_name, attr_value, entity_id)
            return

    except Exception:  # telemetry must never crash the app
        pass


def record_job_completion(job_id: str, stats: Optional[Dict[str, Any]]) -> None:
    """
    Record data-plane metrics once a PII job completes.

    Called from ``tasks.py`` (or ``_bg_job_done`` in app.py) after the
    anonymization function finishes, passing the ``job_stats`` dict.

    Parameters
    ----------
    job_id : str
        The application-level job identifier.
    stats  : dict or None
        The ``job_stats`` dict produced by ``run_pii_anonymization``.
        Expected keys: ``total_entities`` (int), ``processed_rows`` (int).
    """
    if not stats:
        return
    try:
        entities = int(stats.get("total_entities", 0) or 0)
        rows     = int(stats.get("processed_rows",  0) or 0)
        if _PROM_AVAILABLE:
            if entities > 0:
                _ENTITIES_DETECTED.inc(entities)
            if rows > 0:
                _ROWS_PROCESSED.inc(rows)
        with _TELEMETRY_LOCK:
            if entities > 0:
                _TELEMETRY_STATE["entities_detected"] += entities
            if rows > 0:
                _TELEMETRY_STATE["rows_processed"] += rows
    except Exception:
        pass


def get_telemetry_snapshot() -> Dict[str, Any]:
    """Return a point-in-time copy of the in-process telemetry counters.

    Always available — does not require prometheus_client.

    Returns
    -------
    dict with keys:
        jobs_created, jobs_running, jobs_completed, jobs_failed, jobs_canceled,
        scenarios_created, entities_detected, rows_processed,
        duration_avg_s, duration_p95_s, duration_count,
        prometheus_available, metrics_port
    """
    import os
    with _TELEMETRY_LOCK:
        state = dict(_TELEMETRY_STATE)
        durations = list(state.pop("durations_s", []))

    duration_avg: Optional[float] = None
    duration_p95: Optional[float] = None
    if durations:
        durations_sorted = sorted(durations)
        duration_avg = round(sum(durations_sorted) / len(durations_sorted), 2)
        p95_idx = max(0, int(len(durations_sorted) * 0.95) - 1)
        duration_p95 = durations_sorted[p95_idx]

    metrics_port = int(os.environ.get("ANON_METRICS_PORT", "0") or "0")
    return {
        **state,
        "duration_avg_s":   duration_avg,
        "duration_p95_s":   duration_p95,
        "duration_count":   len(durations),
        "prometheus_available": _PROM_AVAILABLE,
        "metrics_port":     metrics_port,
    }


def get_recent_events(limit: int = 100) -> list:
    """Return the most recent *limit* Taipy events as a list of dicts."""
    with _TELEMETRY_LOCK:
        return list(_RECENT_EVENTS[-limit:])


def clear_telemetry() -> None:
    """Reset all in-process counters and event log. Useful for testing."""
    with _TELEMETRY_LOCK:
        for k in list(_TELEMETRY_STATE.keys()):
            _TELEMETRY_STATE[k] = [] if isinstance(_TELEMETRY_STATE[k], list) else 0
        _RECENT_EVENTS.clear()


def register_telemetry(event_processor: Any) -> None:
    """
    Subscribe the telemetry callback to the Taipy EventProcessor.

    Safe to call multiple times; only the first call registers.

    Parameters
    ----------
    event_processor : taipy.event.EventProcessor
        The running EventProcessor instance from app.py.
    """
    global _registered
    if _registered:
        return
    if not _PROM_AVAILABLE:
        _log.warning("[Telemetry] Skipping registration — prometheus_client not installed.")
        return
    try:
        event_processor.on_event(callback=_on_telemetry_event)
        _registered = True
        _log.info("[Telemetry] Registered Taipy event hook for Prometheus metrics.")
    except Exception as exc:
        _log.warning("[Telemetry] Failed to register event hook: %s", exc)


def start_metrics_server(port: int) -> None:
    """
    Start the Prometheus HTTP metrics server on *port*.

    Idempotent — subsequent calls with the same port are no-ops.

    Parameters
    ----------
    port : int
        TCP port to bind.  Grafana/Prometheus will scrape
        ``http://<host>:<port>/metrics``.
    """
    if not _PROM_AVAILABLE:
        _log.warning("[Telemetry] Cannot start metrics server — prometheus_client not installed.")
        return
    if port <= 0:
        return
    try:
        _prom_start_http_server(port)
        _log.info("[Telemetry] Prometheus metrics server listening on :%d/metrics", port)
    except OSError as exc:
        _log.warning("[Telemetry] Could not start metrics server on port %d: %s", port, exc)
