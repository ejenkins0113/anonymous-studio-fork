"""
Anonymous Studio — Main Application
CPSC 4205 | Group 3 | Spring 2026

Pages
  /dashboard  — live stats, pipeline overview, upcoming reviews
  /jobs       — submit datasets, monitor background jobs, download results
  /pipeline   — Kanban board linked to taipy.core scenario status
  /schedule   — appointment / review scheduling
  /audit      — immutable compliance audit log
"""
from __future__ import annotations
import numbers
import logging
import os, re, time, warnings, tempfile
from threading import Thread

_log = logging.getLogger(__name__)
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
load_dotenv()  # load .env before any os.environ reads (no-op if file absent)

warnings.filterwarnings("ignore", category=DeprecationWarning, module="spacy")
warnings.filterwarnings("ignore", category=UserWarning, module="torch")
warnings.filterwarnings("ignore", message="urllib3.*", category=UserWarning)

import pandas as pd
try:
    import plotly.graph_objects as go
except Exception:  # optional: fallback if plotly is unavailable in env
    go = None
import taipy as tp
from taipy.gui import Gui, notify, invoke_callback, invoke_long_callback, download, get_state_id, navigate, Icon
import taipy.core as tc
from taipy.core import Status
from taipy.event import EventProcessor

# ── Project modules ───────────────────────────────────────────────────────────
import core_config as cc
from store import (
    get_store,
    describe_store_backend,
    get_store_backend_mode,
    PIISession,
    PipelineCard,
    Appointment,
    _now,
    _uid,
)  # noqa: F401
from pii_engine import (
    get_engine,
    ALL_ENTITIES,
    OPERATORS,
    OPERATOR_LABELS,
    get_spacy_model_choice,
    get_spacy_model_options,
    get_spacy_model_status,
    set_spacy_model,
    highlight_md,
)
from pages import PAGES
from ui.theme import CHART_LAYOUT, DASH_STYLEKIT, MONO_COLORWAY
from services.jobs import (
    all_jobs_done_like,
    build_entity_stats_df,
    build_job_config,
    build_queue_quality_md,
    build_result_quality_md,
    latest_cancellable_job,
    new_job_id,
    parse_upload_to_df,
    resolve_upload_bytes,
    stage_csv_upload_for_job,
)
from services.app_context import AppContext
from services.geo_signals import (
    build_geo_place_counts as build_geo_place_counts_base,
    normalize_geo_token as normalize_geo_token_base,
    resolve_geo_city as resolve_geo_city_base,
)
from services.job_progress import (
    clear_progress,
    get_progress_registry,
    persist_progress,
    read_progress,
)
from services.attestation_crypto import (
    build_attestation_payload,
    sign_attestation_payload,
    signature_required,
)
from services.synthetic import SyntheticConfig, synthesize_from_anonymized_text

store  = get_store()
engine = get_engine()
# Backward-compatible alias used by tests and diagnostics.
PROGRESS_REGISTRY = get_progress_registry()
delete_progress_snapshot = clear_progress

GEO_CITY_COORDS: Dict[str, tuple[float, float]] = {
    "new york": (40.7128, -74.0060),
    "los angeles": (34.0522, -118.2437),
    "chicago": (41.8781, -87.6298),
    "atlanta": (33.7490, -84.3880),
    "austin": (30.2672, -97.7431),
    "dallas": (32.7767, -96.7970),
    "denver": (39.7392, -104.9903),
    "seattle": (47.6062, -122.3321),
    "miami": (25.7617, -80.1918),
    "san francisco": (37.7749, -122.4194),
    "washington": (38.9072, -77.0369),
    "boston": (42.3601, -71.0589),
    "houston": (29.7604, -95.3698),
    "phoenix": (33.4484, -112.0740),
    "philadelphia": (39.9526, -75.1652),
    "london": (51.5072, -0.1276),
    "paris": (48.8566, 2.3522),
    "berlin": (52.5200, 13.4050),
    "tokyo": (35.6762, 139.6503),
    "sydney": (-33.8688, 151.2093),
    "toronto": (43.6532, -79.3832),
    "vancouver": (49.2827, -123.1207),
}
GEO_ALIAS_TO_CITY = {
    "new york city": "new york",
    "nyc": "new york",
    "la": "los angeles",
    "sf": "san francisco",
    "bay area": "san francisco",
    "washington dc": "washington",
    "washington d c": "washington",
}
GEO_LOCATION_ENTITY_TYPES = {"LOCATION", "GPE", "LOC"}


def _drunken_bishop(hex_str: str, label: str = "") -> str:
    """Generate OpenSSH-style randomart from a hex digest (Drunken Bishop algorithm)."""
    CHARS = " .o+=*BOX@%&#/^SE"
    W, H = 17, 9
    board = [[0] * W for _ in range(H)]
    x, y = W // 2, H // 2
    data = bytes.fromhex(hex_str)
    for byte in data:
        for shift in range(0, 8, 2):
            dx = 1 if (byte >> shift) & 1 else -1
            dy = 1 if (byte >> (shift + 1)) & 1 else -1
            x = max(0, min(W - 1, x + dx))
            y = max(0, min(H - 1, y + dy))
            board[y][x] += 1
    board[H // 2][W // 2] = len(CHARS) - 2  # S = start
    board[y][x]            = len(CHARS) - 1  # E = end
    top    = f"+--[SHA-256]--{'-' * (W - 13)}+"
    bottom = f"+--[{label[:W-6]}]{'-' * max(0, W - 6 - len(label[:W-6]))}+"
    rows   = [top]
    for row in board:
        rows.append("|" + "".join(CHARS[min(v, len(CHARS) - 1)] for v in row) + "|")
    rows.append(bottom)
    return "\n".join(rows)


def _store_status_ui(status_text: str) -> tuple[str, str]:
    """Return compact store label plus full hover tooltip text."""
    raw = str(status_text or "").strip()
    lower = raw.lower()
    if lower.startswith("✓ mongodb"):
        label = "𖠰 Mongo"
    elif lower.startswith("✓ duckdb"):
        label = "𐦖 DuckDB"
    else:
        label = "⸙ In Memory"
    hover = raw or "In-memory store (data resets on restart)"
    return label, hover


def _spacy_status_ui(status_text: str) -> tuple[str, str]:
    """Return compact NLP engine label + full hover details."""
    raw = str(status_text or "").strip()
    lower = raw.lower()
    if "full ner model" in lower:
        label = "Full NER"
    elif "blank model" in lower:
        label = "Regex-only"
    elif "model" in lower:
        label = "Custom"
    else:
        label = "Unknown"
    hover = raw or "NLP model status unavailable."
    return label, hover


def _raw_input_backend_ui() -> tuple[str, str]:
    """Return compact Taipy raw_input DataNode backend label + tooltip."""
    mode = (os.environ.get("ANON_MODE", "development") or "development").strip().lower()
    configured = (os.environ.get("ANON_RAW_INPUT_BACKEND", "auto") or "auto").strip().lower()
    if configured not in {"auto", "memory", "mongo", "pickle"}:
        configured = "auto"
    resolved = ("memory" if mode == "development" else "mongo") if configured == "auto" else configured
    label_map = {
        "mongo": "Mongo",
        "memory": "In Memory",
        "pickle": "Pickle",
    }
    label = label_map.get(resolved, resolved.title())
    hover = (
        f"Taipy raw_input DataNode backend: {resolved} "
        f"(ANON_RAW_INPUT_BACKEND={configured}, ANON_MODE={mode})"
    )
    return label, hover


def _priority_to_severity(priority: str) -> str:
    """Map Kanban card priority to audit log severity."""
    return {"critical": "critical", "high": "warning"}.get(str(priority).lower(), "info")


def _normalize_geo_token(value: Any) -> str:
    """Compatibility wrapper around geo helper module."""
    return normalize_geo_token_base(value)


def _resolve_geo_city(value: Any, city_coords: Dict[str, tuple[float, float]]) -> str:
    """Compatibility wrapper around geo helper module."""
    return resolve_geo_city_base(value, city_coords, GEO_ALIAS_TO_CITY)


def _build_geo_place_counts(
    sessions: List[Any],
    city_coords: Dict[str, tuple[float, float]],
) -> tuple[Dict[str, int], int]:
    """Compatibility wrapper around geo helper module."""
    return build_geo_place_counts_base(
        sessions,
        city_coords,
        GEO_ALIAS_TO_CITY,
        GEO_LOCATION_ENTITY_TYPES,
    )


def _geo_city_view(lat_values: List[float], lon_values: List[float]) -> Dict[str, Any]:
    """Build a city-focused map viewport (center + zoom) for Scattermap tile maps."""
    if not lat_values or not lon_values:
        return {"center": {"lat": 39.5, "lon": -98.35}, "zoom": 3.2}

    min_lat, max_lat = min(lat_values), max(lat_values)
    min_lon, max_lon = min(lon_values), max(lon_values)
    lat_span = max(2.0, max_lat - min_lat)
    lon_span = max(2.0, max_lon - min_lon)
    span = max(lat_span, lon_span * 0.75)

    import math
    zoom = max(1.5, min(10.0, math.log2(280.0 / max(span, 2.0))))
    return {
        "center": {"lat": (min_lat + max_lat) / 2.0, "lon": (min_lon + max_lon) / 2.0},
        "zoom": round(zoom, 2),
    }

# Standalone security note only when raw_input explicitly uses pickle backend.
if os.environ.get("ANON_MODE", "development") == "standalone":
    _raw_backend = (os.environ.get("ANON_RAW_INPUT_BACKEND", "auto") or "auto").strip().lower()
    if _raw_backend == "pickle":
        import warnings as _w
        _w.warn(
            "\n[AnonymousStudio] ANON_MODE=standalone with ANON_RAW_INPUT_BACKEND=pickle: "
            "raw_input payloads are persisted as pickle. Use mongo for worker-safe, "
            "non-pickle persistence.\n",
            UserWarning,
            stacklevel=1,
        )

# ═══════════════════════════════════════════════════════════════════════════════
#  STATE  (every variable below is reactive Taipy GUI state)
# ═══════════════════════════════════════════════════════════════════════════════

# ── Navigation ────────────────────────────────────────────────────────────────
active_page = "dashboard"

menu_lov = [
    ("dashboard", Icon("images/dashboard.svg", "Dashboard")),
    ("analyze",   Icon("images/piitext.svg",   "Analyze Text")),
    ("jobs",      Icon("images/jobs.svg",       "Batch Jobs")),
    ("pipeline",  Icon("images/pipeline.svg",   "Pipeline")),
    ("schedule",  Icon("images/schedule.svg",   "Reviews")),
    ("audit",     Icon("images/audit.svg",      "Audit Log")),
    ("ui_demo",   Icon("images/dashboard.svg",  "UI")),
]

# ── Quick-text PII (inline mode, no file upload needed) ──────────────────────
spacy_status = get_spacy_model_status()
spacy_status_label, spacy_status_hover = _spacy_status_ui(spacy_status)
spacy_model_sel = get_spacy_model_choice()
spacy_model_lov = get_spacy_model_options()
store_status = describe_store_backend()
store_status_label, store_status_hover = _store_status_ui(store_status)
raw_input_status_label, raw_input_status_hover = _raw_input_backend_ui()
# Bool companions for <|status|> LED widgets
spacy_ok      = "blank" not in spacy_status.lower()
store_ok      = store_status.startswith("✓")
raw_input_ok  = True

try:
    import dask as _dask_mod
    dask_version = _dask_mod.__version__
    dask_status  = f"✓ Dask {dask_version}"
except ImportError:
    dask_version = ""
    dask_status  = "✗ Dask not installed"

# ── Store backend settings ────────────────────────────────────────────────────
_initial_store_backend = get_store_backend_mode()
store_backend_sel      = _initial_store_backend if _initial_store_backend in ("memory", "duckdb", "mongo") else "memory"
store_backend_lov      = ["memory", "duckdb", "mongo"]
store_mongo_uri        = os.environ.get("MONGODB_URI", "").strip()
store_duckdb_path      = os.environ.get(
    "ANON_DUCKDB_PATH",
    os.path.join(tempfile.gettempdir(), "anon_studio.duckdb"),
).strip()
store_settings_open    = False
store_settings_msg     = ""
qt_input  = (
    "Patient: Jane Doe, DOB: 03/15/1982\n"
    "SSN: 987-65-4321 | Email: jane.doe@hospital.org\n"
    "Phone: +1-800-555-0199 | Card: 4111-1111-1111-1111\n"
    "Physician: Dr. Robert Kim | IP: 192.168.1.101"
)
qt_operator        = "replace"
qt_operator_list   = [*OPERATORS, "synthesize"]
qt_threshold       = 0.35
qt_entities        = ALL_ENTITIES.copy()
qt_all_entities    = ALL_ENTITIES.copy()
qt_highlight_md    = ""
qt_anonymized      = ""
qt_anonymized_raw  = ""          # raw text for session save (no markdown)
qt_entity_rows     = pd.DataFrame(
    columns=["Entity Type", "Text", "Confidence", "Confidence Band", "Span", "Recognizer"]
)
qt_summary         = ""
qt_confidence_md   = "Confidence profile: N/A"
qt_entity_breakdown_md = "No entities detected yet."
qt_conf_bands_md   = "Very High 0 | High 0 | Medium 0 | Low 0"
qt_kpi_total_entities = 0
qt_kpi_dominant_band  = "N/A"
qt_kpi_avg_confidence = "N/A"
qt_kpi_low_confidence = 0
qt_kpi_total_entities_ticker = "0"
qt_kpi_dominant_band_ticker = "N/A"
qt_kpi_avg_confidence_ticker = "N/A"
qt_kpi_low_confidence_ticker = "0"
qt_last_proc_ms    = 0.0     # timing from last engine.anonymize() call
qt_session_saved   = False
qt_sessions_data   = pd.DataFrame(columns=["ID", "Title", "Operator", "Entities", "Created"])
qt_entity_chart    = pd.DataFrame(columns=["Entity Type", "Count"])
qt_entity_figure   = {}
qt_entity_chart_visible = False
qt_has_entities    = False
qt_settings_open   = False
qt_allowlist_text  = ""   # comma-separated words to never flag as PII
qt_denylist_text   = ""   # comma-separated words to always flag as PII
qt_ner_model_lov   = [
    "spaCy/en_core_web_lg",
    "flair/ner-english-large",
    "HuggingFace/obi/deid_roberta_i2b2",
    "HuggingFace/StanfordAIMI/stanford-deidentifier-base",
    "stanza/en",
    "Azure AI Language",
    "Other",
]
qt_ner_model_sel   = (
    f"spaCy/{spacy_model_sel}" if str(spacy_model_sel or "").strip() not in {"", "auto", "blank"} else "spaCy/en_core_web_lg"
)
qt_ner_other_model = ""
qt_ner_note        = ""
qt_synth_provider = os.environ.get("ANON_SYNTH_PROVIDER", "faker").strip().lower() or "faker"
qt_synth_provider_lov = ["faker", "openai", "azure_openai"]
qt_synth_model = os.environ.get("ANON_SYNTH_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
qt_synth_api_key = os.environ.get("OPENAI_API_KEY", "").strip()
qt_synth_api_base = (
    os.environ.get("AZURE_OPENAI_ENDPOINT")
    or os.environ.get("OPENAI_API_BASE")
    or ""
).strip()
qt_synth_deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "").strip()
qt_synth_api_version = os.environ.get("OPENAI_API_VERSION", "2024-08-01-preview").strip()
qt_synth_temperature = 0.2
qt_synth_max_tokens = 800
qt_synth_note = ""

# ── Job submission (large file) ───────────────────────────────────────────────
job_file_content   = None          # raw bytes of uploaded CSV / Excel
job_file_name      = ""
job_file_hash      = ""
job_file_art       = ""
job_operator       = "replace"
job_operator_list  = OPERATORS
job_spacy_model    = get_spacy_model_choice()
job_spacy_model_lov = get_spacy_model_options()
job_threshold      = 0.35
job_entities       = ALL_ENTITIES.copy()
job_all_entities   = ALL_ENTITIES.copy()
job_chunk_size        = 500
job_compute_backend   = "auto"
job_compute_backend_lov = ["auto", "pandas", "dask"]
job_dask_min_rows     = 250000
job_mongo_write_batch = 5000          # MongoDB raw_input DataNode write batch size
job_card_id           = ""            # link to a Kanban card
job_title          = "New Job"

# Job tracking table
job_table_data = pd.DataFrame(columns=["job_id", "Job ID", "Title", "Progress", "Status", "Entities", "Duration", "Message"])    # shown in Jobs page

# Per-job progress (polled every second while a job is running)
active_job_id        = ""          # job_config["job_id"] of the running job
active_scenario_id   = ""          # tc.Scenario.id
job_active_submission_id = ""
job_submission_status = "—"
job_progress_pct     = 0
job_progress_msg     = ""
job_progress_status  = ""          # running | done | error
job_is_running       = False
job_expected_rows    = 0

# Download
download_ready       = False
download_scenario_id = ""
download_rows        = 0
download_cols        = 0

# Preview table (first 50 rows of result)
preview_data       = pd.DataFrame()
preview_cols: List[str]  = []
stats_entity_rows  = pd.DataFrame(columns=["Entity Type", "Count"])
stats_entity_chart_figure = {}
job_errors_data    = pd.DataFrame(columns=["Time", "Source", "Details", "Severity"])
job_quality_md     = "Run a job to see quality summary."
job_kpi_total        = 0
job_kpi_running      = 0
job_kpi_success      = "0%"
job_kpi_success_pct  = 0.0   # float companion for indicator widget
job_kpi_entities     = 0
job_run_health     = "Idle"
job_stage_text     = ""
job_eta_text       = "ETA —"
job_processed_text = "0 / 0 rows"
job_active_started = 0.0
job_adv_open       = False
job_view_tab       = "Results"
job_view_tab_lov   = ["Results", "Job History", "Data Nodes", "Errors / Audit"]
orchestration_scenario = None
orchestration_job      = None
ops_status_items: List[str] = ["Run health: Idle", "Submission: —", "Store: —"]
ops_tree_lov: List[Dict[str, Any]] = []
ops_tree_selected = ""
ops_tree_expanded: List[str] = []
ops_tree_meta: Dict[str, str] = {}
ops_tree_selected_md = "Select a node to inspect orchestration context."
ops_metric_running = 0
ops_metric_total = 1
ops_metric_delta = 0
whatif_scenarios_lov: List[str] = []
whatif_scenarios_sel: List[str] = []
whatif_compare_md = "Select at least two scenarios and run Compare."
whatif_compare_data = pd.DataFrame(columns=["Scenario", "Processed Rows", "Entities", "Entities / Row"])
whatif_compare_chart = pd.DataFrame(columns=["Scenario", "Entities"])
whatif_compare_figure = {}
whatif_compare_has_data = False
comparator_scenarios: List[Any] = []   # Scenario objects fed to <|scenario_comparator|>
submission_table = pd.DataFrame(columns=["Submission", "Entity", "Status", "Jobs", "Created"])
cycle_table = pd.DataFrame(columns=["Cycle", "Frequency", "Start", "End", "Scenarios"])

# ── Runtime context / registries ─────────────────────────────────────────────
APP_CTX = AppContext()
# Backward-compatible aliases for existing code/tests.
_SCENARIOS = APP_CTX.scenarios            # job_id -> tc.Scenario
_SUBMISSION_IDS = APP_CTX.submission_ids  # job_id -> taipy submission id
_JOB_UI_POLL_MS = max(500, int(os.environ.get("ANON_UI_PROGRESS_POLL_MS", "1000")))
try:
    _DASH_LIVE_POLL_SEC = max(1.0, float(os.environ.get("ANON_DASH_LIVE_POLL_SEC", "3") or "3"))
except Exception:
    _DASH_LIVE_POLL_SEC = 3.0
_LIVE_STATE_IDS = APP_CTX.live_state_ids
_LIVE_STATE_LOCK = APP_CTX.live_state_lock
_LIVE_STOP_EVENT = APP_CTX.live_stop_event
try:
    _BURNDOWN_CACHE_TTL_SEC = max(0.0, float(os.environ.get("ANON_BURNDOWN_CACHE_TTL_SEC", "0") or "0"))
except Exception:
    _BURNDOWN_CACHE_TTL_SEC = 0.0

# ── File upload cache (bytes must live outside Taipy state — state is JSON) ───
# Keyed by get_state_id(state) so concurrent users never share each other's uploads.
_FILE_CACHE = APP_CTX.file_cache
_BURNDOWN_CACHE = APP_CTX.burndown_cache


def _progress_from_sources(job_id: str) -> Dict[str, Any]:
    """Get the freshest progress payload from in-memory and durable snapshot."""
    return read_progress(job_id)


def _persist_progress(job_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Persist progress in both in-memory registry and durable snapshot."""
    return persist_progress(job_id, payload)


def _register_live_state(state) -> None:
    """Track connected GUI state ids for live dashboard refresh callbacks."""
    sid = get_state_id(state)
    if sid is None:
        return
    with _LIVE_STATE_LOCK:
        _LIVE_STATE_IDS.add(str(sid))


def _on_live_dashboard_tick(state) -> None:
    """UI-thread callback invoked periodically for each connected client."""
    try:
        _refresh_dashboard(state)
    except Exception:
        pass


def _live_dashboard_loop(gui: Gui) -> None:
    """Background poller that pushes dashboard refresh callbacks to clients."""
    while not _LIVE_STOP_EVENT.wait(_DASH_LIVE_POLL_SEC):
        if not hasattr(gui, "_server"):
            continue
        with _LIVE_STATE_LOCK:
            targets = list(_LIVE_STATE_IDS)
        if not targets:
            continue
        stale: List[str] = []
        for sid in targets:
            try:
                invoke_callback(gui, sid, _on_live_dashboard_tick, ())
            except Exception:
                stale.append(sid)
        if stale:
            with _LIVE_STATE_LOCK:
                for sid in stale:
                    _LIVE_STATE_IDS.discard(sid)


def _start_live_dashboard_thread(gui: Gui) -> None:
    if APP_CTX.live_thread is not None and APP_CTX.live_thread.is_alive():
        return
    _LIVE_STOP_EVENT.clear()
    APP_CTX.live_thread = Thread(
        target=_live_dashboard_loop,
        args=(gui,),
        name="anon-live-dashboard",
        daemon=True,
    )
    APP_CTX.live_thread.start()


def _stop_live_dashboard_thread() -> None:
    _LIVE_STOP_EVENT.set()
    t = APP_CTX.live_thread
    APP_CTX.live_thread = None
    if t is not None and t.is_alive():
        t.join(timeout=1.0)

# ── Pipeline (Kanban) ─────────────────────────────────────────────────────────
_CARD_COLS = ["id", "Select", "ID", "Title", "Priority", "Assignee", "Labels", "Job", "Attested", "Updated"]
kanban_backlog      = pd.DataFrame(columns=_CARD_COLS)
kanban_in_progress  = pd.DataFrame(columns=_CARD_COLS)
kanban_review       = pd.DataFrame(columns=_CARD_COLS)
kanban_done         = pd.DataFrame(columns=_CARD_COLS)
pipeline_all        = pd.DataFrame(columns=_CARD_COLS)
kanban_backlog_len     = 0
kanban_in_progress_len = 0
kanban_review_len      = 0
kanban_done_len        = 0
pipeline_burndown = pd.DataFrame(columns=["Date", "Remaining", "Ideal"])
pipeline_burndown_figure = {}
pipeline_burndown_visible = False
pipeline_burndown_md = "No burndown data yet."
pipeline_front_md = "No pipeline cards yet. Create your first card to start tracking work."

sel_card_id    = ""
sel_card_title = ""
sel_card_short_id = ""
sel_card_source = ""
pipeline_selected_md = (
    "Select a card by either highlighting a row in the board or choosing a card from the picker."
)
pipeline_select_mode = "highlight"
pipeline_select_mode_lov = ["highlight", "picker"]
pipeline_card_lov: List[tuple[str, str]] = [("(no cards)", "")]
pipeline_card_pick = ""
backlog_sel      = []
in_progress_sel  = []
review_sel       = []
done_sel         = []
pipeline_all_sel = []
card_form_open = False
card_id_edit   = ""
card_title_f   = ""
card_desc_f    = ""
card_status_f  = "backlog"
card_assign_f  = ""
card_priority_f = "medium"
card_labels_f  = ""
card_attest_f  = ""
card_status_opts   = ["backlog", "in_progress", "review", "done"]
card_priority_opts = ["low", "medium", "high", "critical"]
card_session_f     = ""        # session_id selected in card form
card_session_opts: List[str] = ["(none)"]  # populated on form open

attest_open   = False
attest_cid    = ""
attest_note   = ""
attest_by     = ""

# Per-card audit history dialog
card_audit_open = False
card_audit_data = pd.DataFrame(columns=["Time", "Action", "Actor", "Details"])

# ── Schedule ──────────────────────────────────────────────────────────────────
appt_table     = pd.DataFrame(columns=["id", "Title", "Date / Time", "Duration", "Attendees", "Linked Card", "Status"])
upcoming_table = pd.DataFrame(columns=["Title", "Date", "Time"])
appt_form_open = False
appt_id_edit   = ""
appt_title_f   = ""
appt_desc_f    = ""
appt_date_f    = None
appt_time_f    = "10:00"
appt_dur_f     = 30
appt_att_f     = ""
appt_card_f    = ""
appt_status_f  = "scheduled"
appt_status_opts = ["scheduled", "completed", "cancelled"]
sel_appt_id    = ""
schedule_sysreq_expanded = False

# ── Audit ─────────────────────────────────────────────────────────────────────
audit_table = pd.DataFrame(columns=["Time", "Actor", "Action", "Resource", "Details", "Severity"])
audit_search  = ""
audit_sev     = "all"
audit_sev_opts = ["all", "info", "warning", "critical"]
selected_data_node = None

# ── Dashboard ─────────────────────────────────────────────────────────────────
dash_jobs_total     = 0
dash_jobs_running   = 0
dash_jobs_done      = 0
dash_jobs_failed    = 0
dash_cards_total    = 0
dash_cards_attested = 0
dash_upcoming_md    = ""
dash_stage_chart    = pd.DataFrame(columns=["Stage", "Count"])
dash_entity_chart   = pd.DataFrame(columns=["Entity Type", "Sessions"])
dash_stage_figure = {}
dash_entity_chart_figure = {}
dash_entity_mix_chart = pd.DataFrame(columns=["Entity Type", "Count"])
dash_entity_mix_figure = {}
dash_entity_dominance_pct = 0.0
dash_entity_dominance_pct_label = "0.0%"
dash_entity_chart_layout = {}
dash_stage_report   = pd.DataFrame(columns=["Stage", "Count", "Share"])
dash_entity_report  = pd.DataFrame(columns=["Entity Type", "Count", "Share"])
dash_stage_breakdown_md = ""
dash_entity_breakdown_md = ""
dash_pipeline_report_md = ""
dash_entity_report_md   = ""
dash_completion_pct = 0
dash_inflight_cards = 0
dash_backlog_cards = 0
dash_completion_pct_ticker = "0% (=)"
dash_inflight_cards_ticker = "0 (=)"
dash_backlog_cards_ticker = "0 (=)"
dash_completion_pct_delta = 0
dash_inflight_cards_delta = 0
dash_backlog_cards_delta = 0
dash_stage_chart_visible  = False
dash_entity_chart_visible = False
dash_has_reviews  = False
dash_has_any_data = False   # True when at least one section has content
dash_empty_hint_visible = True
dash_intro_md = "*Start by analyzing text, creating pipeline cards, or scheduling reviews — data will appear here.*"
dash_report_mode = "All"
dash_report_mode_lov = ["All", "Operations", "Compliance", "Throughput"]
dash_time_window = "30d"
dash_time_window_lov = ["24h", "7d", "30d", "All"]
dash_report_summary_md = ""
dash_kpi_entities_total = 0
dash_kpi_entities_total_label = "0"
dash_kpi_reviews_scheduled = 0
dash_audit_chart = pd.DataFrame(columns=["Severity", "Count"])
dash_priority_chart = pd.DataFrame(columns=["Priority", "Count"])
dash_ops_trend = pd.DataFrame(columns=["Date", "Entities", "Sessions"])
dash_map_chart = pd.DataFrame(columns=["Place", "Lat", "Lon", "Mentions"])
dash_map_figure = {}
dash_audit_chart_visible = False
dash_priority_chart_visible = False
dash_ops_trend_visible = False
dash_map_visible = False
dash_map_md = ""

# Engine Performance panel (populated by _refresh_dashboard from session timing)
# Numeric types are required by the native Taipy metric / indicator widgets.
dash_perf_visible        = False
dash_perf_avg_ms         = 0.0    # <|...|metric|> — avg processing latency
dash_perf_max_ms         = 50.0   # gauge upper bound, updated to 120 % of peak
dash_perf_delta_ms       = 0.0    # latest session vs avg — negative = faster
dash_perf_count          = 0      # <|...|metric|> — total timed sessions
dash_perf_figure         = {}
perf_telemetry_table     = pd.DataFrame(columns=["Session", "ms"])

# ── UI (Taipy + Plotly showcase over live app data) ──────────────────────────
ui_demo_mode = "All"
ui_demo_mode_lov = ["All", "Entities", "Confidence", "Operations"]
ui_demo_top_n = 10
ui_demo_summary_md = "Run Analyze Text or submit jobs to populate UI visuals."
ui_demo_last_refresh = "—"
ui_demo_has_data = False
ui_demo_entity_table = pd.DataFrame(columns=["Entity Type", "Count", "Share %", "Cumulative %"])
ui_demo_evidence_table = pd.DataFrame(columns=["Entity Type", "Confidence", "Recognizer", "Text"])
ui_demo_pipeline_table = pd.DataFrame(columns=["Stage", "Count"])
ui_demo_pareto_figure = {}
ui_demo_treemap_figure = {}
ui_demo_heatmap_figure = {}
ui_demo_conf_box_figure = {}
ui_demo_timeline_figure = {}
ui_demo_pipeline_figure = {}
ui_demo_map_figure = {}
ui_demo_map_md = ""
ui_plot_type = "bar"
ui_plot_type_lov = [
    "bar",
    "line",
    "scatter",
    "area",
    "pie",
    "box",
    "histogram",
    "heatmap",
    "3d_scatter",
    "surface",
    "candlestick",
    "sankey",
    "polar_radar",
    "treemap",
    "funnel",
    "violin",
    "choropleth",
]
ui_plot_orientation = "vertical"
ui_plot_orientation_lov = ["vertical", "horizontal"]
ui_plot_barmode = "group"
ui_plot_barmode_lov = ["group", "stack", "overlay"]
ui_plot_trace_mode = "lines+markers"
ui_plot_trace_mode_lov = ["lines+markers", "lines", "markers"]
ui_plot_palette = "mono"
ui_plot_palette_lov = ["mono", "default", "high_contrast"]
ui_plot_theme = "app_dark"
ui_plot_theme_lov = ["app_dark", "plotly_dark", "plotly_white"]
ui_plot_show_legend = "on"
ui_plot_show_legend_lov = ["on", "off"]
ui_plot_playground_figure = {}
ui_plot_option_rows = pd.DataFrame(columns=["Option", "Value", "Description"])
# Context-sensitive control visibility
ui_plot_show_orientation = True
ui_plot_show_barmode = True
ui_plot_show_trace_mode = False

# Shared dark chart layout (matches app theme) — exposed as state var for Taipy markup
chart_layout = {**CHART_LAYOUT}
mono_colorway = MONO_COLORWAY.copy()

dash_stage_pie_layout = {
    **chart_layout,
    "colorway": mono_colorway,
}
dash_stage_chart_options = {"hole": 0.52, "textinfo": "label+percent"}

dash_entity_chart_layout = {
    **chart_layout,
    "colorway": mono_colorway,
    "margin": {"t": 28, "b": 44, "l": 150, "r": 16},
    "xaxis": {**chart_layout["xaxis"], "dtick": 1, "title": "Sessions"},
    "yaxis": {**chart_layout["yaxis"], "automargin": True},
}

# Entity count bar chart on Jobs results tab — needs wide left margin for long entity names
# Burndown chart layout — used by both Dashboard and Pipeline pages
burndown_chart_layout = {
    **chart_layout,
    "margin": {"t": 24, "b": 42, "l": 48, "r": 14},
    "xaxis": {**chart_layout["xaxis"], "title": "Date"},
    "yaxis": {**chart_layout["yaxis"], "title": "Open Cards", "rangemode": "tozero"},
}

stats_entity_chart_layout = {
    **chart_layout,
    "margin": {"t": 8, "b": 40, "l": 160, "r": 16},
    "yaxis": {**chart_layout["yaxis"], "automargin": True},
    "xaxis": {**chart_layout["xaxis"], "title": "Count", "dtick": 1},
}

# ═══════════════════════════════════════════════════════════════════════════════
#  REFRESH HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _refresh_pipeline(state):
    by_s = store.cards_by_status()
    # Flatten status buckets instead of calling store.list_cards() again.
    all_cards = sorted(
        [c for cards in by_s.values() for c in cards],
        key=lambda c: c.updated_at, reverse=True,
    )
    selected_card_id = str(getattr(state, "sel_card_id", "") or "")
    state.kanban_backlog     = _card_rows(by_s["backlog"], selected_card_id)
    state.kanban_in_progress = _card_rows(by_s["in_progress"], selected_card_id)
    state.kanban_review      = _card_rows(by_s["review"], selected_card_id)
    state.kanban_done        = _card_rows(by_s["done"], selected_card_id)
    state.pipeline_all       = _card_rows(all_cards, selected_card_id)
    state.kanban_backlog_len     = len(by_s["backlog"])
    state.kanban_in_progress_len = len(by_s["in_progress"])
    state.kanban_review_len      = len(by_s["review"])
    state.kanban_done_len        = len(by_s["done"])
    _refresh_pipeline_picker(state, all_cards)
    _refresh_pipeline_burndown(state, all_cards)
    # Clear stale selection when a previously selected card was deleted.
    if state.sel_card_id and not store.get_card(state.sel_card_id):
        _clear_selected_card(state, clear_selection_vars=True)
    _update_pipeline_front_md(state, all_cards)
    _update_pipeline_selected_md(state)


def _refresh_pipeline_picker(state, cards: List[Any]) -> None:
    options: List[tuple[str, str]] = []
    for c in cards:
        status_label = str(getattr(c, "status", "")).replace("_", " ").title()
        title = str(getattr(c, "title", "") or "").strip()[:42]
        label = f"{c.id[:8]} | {title} | {status_label}"
        options.append((label, c.id))

    state.pipeline_card_lov = options if options else [("(no cards)", "")]

    valid_ids = [value for _, value in options if value]
    current_pick = str(getattr(state, "pipeline_card_pick", "") or "")
    current_sel = str(getattr(state, "sel_card_id", "") or "")

    if current_sel and current_sel in valid_ids:
        state.pipeline_card_pick = current_sel
    elif current_pick and current_pick in valid_ids:
        state.pipeline_card_pick = current_pick
    else:
        state.pipeline_card_pick = valid_ids[0] if valid_ids else ""

    mode = str(getattr(state, "pipeline_select_mode", "highlight") or "highlight").strip().lower()
    if mode not in {"highlight", "picker"}:
        state.pipeline_select_mode = "highlight"


def _parse_iso_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


_PIPELINE_STATUS_RE = re.compile(r"\b(backlog|in[_ ]progress|review|done)\b", flags=re.IGNORECASE)
_PIPELINE_ARROW_RE = re.compile(
    r"\b(backlog|in[_ ]progress|review|done)\b\s*(?:→|->|to)\s*\b(backlog|in[_ ]progress|review|done)\b",
    flags=re.IGNORECASE,
)


def _parse_pipeline_move_status(details: Optional[str]) -> Optional[tuple[str, str]]:
    if not details:
        return None
    text = str(details or "").lower()

    def _norm(status: str) -> str:
        s = str(status or "").strip().lower().replace(" ", "_")
        return "in_progress" if s == "in_progress" else s

    # Preferred: explicit arrow/to patterns, e.g. "backlog → review" / "backlog -> review" / "backlog to review".
    match = _PIPELINE_ARROW_RE.search(text)
    if match:
        from_status = _norm(match.group(1))
        to_status = _norm(match.group(2))
        if from_status and to_status:
            return from_status, to_status

    # Fallback: extract statuses in sequence from text like "Moved ... from 'backlog' ... 'review'".
    statuses = [_norm(m.group(1)) for m in _PIPELINE_STATUS_RE.finditer(text)]
    if len(statuses) >= 2:
        return statuses[0], statuses[-1]
    return None


def _update_pipeline_front_md(state, cards: List[Any]) -> None:
    total = len(cards)
    if total == 0:
        state.pipeline_front_md = "No pipeline cards yet. Create your first card to start tracking work."
        return
    open_cards = sum(1 for c in cards if getattr(c, "status", "") != "done")
    done_cards = max(0, total - open_cards)
    attested = sum(1 for c in cards if bool(getattr(c, "attested", False)))
    high_backlog = sum(
        1
        for c in cards
        if getattr(c, "status", "") == "backlog"
        and str(getattr(c, "priority", "")).lower() in {"high", "critical"}
    )
    latest_dt = max(
        (_parse_iso_dt(getattr(c, "updated_at", None)) for c in cards),
        default=None,
    )
    latest_label = latest_dt.strftime("%Y-%m-%d %H:%M") if latest_dt else "n/a"
    state.pipeline_front_md = (
        f"**{total}** total cards · **{open_cards}** open · **{done_cards}** done · "
        f"**{high_backlog}** high-priority backlog · **{attested}/{total}** attested · "
        f"last update `{latest_label}`"
    )


def _pipeline_burndown_signature(cards: List[Any]) -> str:
    """Stable signature of card state used for short-lived burndown cache."""
    rows: List[str] = []
    for c in cards:
        cid = str(getattr(c, "id", "") or "").strip()
        if not cid:
            continue
        rows.append(
            "|".join(
                [
                    cid,
                    str(getattr(c, "status", "") or ""),
                    str(getattr(c, "created_at", "") or ""),
                    str(getattr(c, "updated_at", "") or ""),
                    str(getattr(c, "done_at", "") or ""),
                ]
            )
        )
    rows.sort()
    return "||".join(rows)


def _refresh_pipeline_burndown(state, cards: List[Any]) -> None:
    """Build burndown from card lifecycle events (creation and done/reopen transitions)."""
    global _BURNDOWN_CACHE
    signature = _pipeline_burndown_signature(cards)
    if _BURNDOWN_CACHE_TTL_SEC > 0 and signature:
        age = time.time() - float(_BURNDOWN_CACHE.get("ts", 0.0) or 0.0)
        if (
            _BURNDOWN_CACHE.get("sig") == signature
            and age <= _BURNDOWN_CACHE_TTL_SEC
            and isinstance(_BURNDOWN_CACHE.get("payload"), dict)
        ):
            payload = _BURNDOWN_CACHE["payload"]
            cached_df = payload.get("df")
            state.pipeline_burndown = cached_df.copy() if isinstance(cached_df, pd.DataFrame) else pd.DataFrame(
                columns=["Date", "Remaining", "Ideal"]
            )
            state.pipeline_burndown_figure = payload.get("fig", {})
            state.pipeline_burndown_visible = bool(payload.get("visible", False))
            state.pipeline_burndown_md = str(payload.get("md", "No cards available for burndown yet."))
            return

    now = datetime.now()
    events: List[tuple[datetime, int]] = []
    valid_cards = 0
    card_created_at: Dict[str, datetime] = {}
    fallback_done_at: Dict[str, datetime] = {}

    for card in cards:
        created_at = _parse_iso_dt(getattr(card, "created_at", None))
        if created_at is None:
            continue
        card_id = str(getattr(card, "id", "") or "").strip()
        if not card_id:
            continue
        valid_cards += 1
        card_created_at[card_id] = created_at
        events.append((created_at, +1))
        if getattr(card, "status", "") == "done":
            done_at = (
                _parse_iso_dt(getattr(card, "done_at", None))
                or _parse_iso_dt(getattr(card, "updated_at", None))
                or created_at
            )
            if done_at < created_at:
                done_at = created_at
            fallback_done_at[card_id] = done_at

    done_transition_seen: set[str] = set()
    try:
        # Favor accuracy over truncation: older move events can change today's burndown curve.
        # Store backends cap audit size anyway (Mongo capped collection / in-memory practical limits).
        audit_limit = max(2000, valid_cards * 60)
        audit_entries = store.list_audit(limit=audit_limit)
    except Exception:
        audit_entries = []

    for entry in reversed(audit_entries):
        if getattr(entry, "action", "") != "pipeline.move":
            continue
        card_id = str(getattr(entry, "resource_id", "") or "").strip()
        created_at = card_created_at.get(card_id)
        if created_at is None:
            continue
        parsed_status = _parse_pipeline_move_status(getattr(entry, "details", None))
        if not parsed_status:
            continue
        from_status, to_status = parsed_status
        if from_status == to_status:
            continue
        event_ts = _parse_iso_dt(getattr(entry, "timestamp", None))
        if event_ts is None:
            continue
        if event_ts < created_at:
            event_ts = created_at
        if from_status != "done" and to_status == "done":
            events.append((event_ts, -1))
            done_transition_seen.add(card_id)
        elif from_status == "done" and to_status != "done":
            events.append((event_ts, +1))
            done_transition_seen.add(card_id)

    for card_id, done_at in fallback_done_at.items():
        if card_id in done_transition_seen:
            continue
        events.append((done_at, -1))

    if not events or valid_cards == 0:
        state.pipeline_burndown = pd.DataFrame(columns=["Date", "Remaining", "Ideal"])
        state.pipeline_burndown_figure = {}
        state.pipeline_burndown_visible = False
        state.pipeline_burndown_md = "No cards available for burndown yet."
        _BURNDOWN_CACHE = {
            "ts": time.time(),
            "sig": signature,
            "payload": {
                "df": state.pipeline_burndown.copy(),
                "fig": {},
                "visible": False,
                "md": state.pipeline_burndown_md,
            },
        }
        return

    events.sort(key=lambda item: item[0])
    timeline: List[datetime] = []
    remaining: List[int] = []
    running = 0
    i = 0
    while i < len(events):
        ts = events[i][0]
        delta = 0
        while i < len(events) and events[i][0] == ts:
            delta += events[i][1]
            i += 1
        running = max(0, running + delta)
        timeline.append(ts)
        remaining.append(running)

    if timeline[-1] < now:
        timeline.append(now)
        remaining.append(remaining[-1])

    start_ts = timeline[0]
    total_cards = valid_cards
    open_cards = sum(1 for card in cards if getattr(card, "status", "") != "done")
    if remaining and remaining[-1] != open_cards:
        if timeline[-1] >= now:
            remaining[-1] = open_cards
        else:
            timeline.append(now)
            remaining.append(open_cards)
    closed_cards = max(0, total_cards - open_cards)
    start_remaining = remaining[0] if remaining else total_cards
    total_seconds = max(1.0, (timeline[-1] - start_ts).total_seconds())
    ideal = []
    for ts in timeline:
        elapsed_ratio = min(1.0, max(0.0, (ts - start_ts).total_seconds() / total_seconds))
        ideal.append(max(0.0, round(start_remaining * (1 - elapsed_ratio), 2)))

    state.pipeline_burndown = pd.DataFrame(
        {
            "Date": [ts.isoformat(timespec="minutes") for ts in timeline],
            "Remaining": remaining,
            "Ideal": ideal,
        },
        columns=["Date", "Remaining", "Ideal"],
    )
    state.pipeline_burndown_visible = not state.pipeline_burndown.empty
    state.pipeline_burndown_md = (
        f"**{open_cards}** open &nbsp;·&nbsp; **{closed_cards}** closed "
        f"of **{total_cards}** total &nbsp;·&nbsp; since **{start_ts.date().isoformat()}**"
    )

    if go is None or state.pipeline_burndown.empty:
        state.pipeline_burndown_figure = {}
        _BURNDOWN_CACHE = {
            "ts": time.time(),
            "sig": signature,
            "payload": {
                "df": state.pipeline_burndown.copy(),
                "fig": {},
                "visible": state.pipeline_burndown_visible,
                "md": state.pipeline_burndown_md,
            },
        }
        return

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=state.pipeline_burndown["Date"],
            y=state.pipeline_burndown["Ideal"],
            mode="lines",
            name="Ideal",
            line={"dash": "dash", "width": 2, "color": chart_layout["colorway"][4]},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=state.pipeline_burndown["Date"],
            y=state.pipeline_burndown["Remaining"],
            mode="lines+markers",
            name="Remaining",
            line={"width": 2, "color": chart_layout["colorway"][0]},
            marker={"size": 5},
        )
    )
    fig.update_layout(
        **{
            **chart_layout,
            "margin": {"t": 24, "b": 42, "l": 48, "r": 14},
            "xaxis": {**chart_layout["xaxis"], "title": "Date"},
            "yaxis": {**chart_layout["yaxis"], "title": "Open Cards", "rangemode": "tozero"},
        }
    )
    state.pipeline_burndown_figure = fig
    _BURNDOWN_CACHE = {
        "ts": time.time(),
        "sig": signature,
        "payload": {
            "df": state.pipeline_burndown.copy(),
            "fig": fig,
            "visible": state.pipeline_burndown_visible,
            "md": state.pipeline_burndown_md,
        },
    }


def _card_rows(cards, selected_card_id: str = ""):
    rows = []
    for c in cards:
        # sync job status from taipy.core if linked
        job_status = _resolve_job_status(getattr(c, 'scenario_id', None))
        rows.append({
            "id":        c.id,
            "Select":    str(c.id) == str(selected_card_id),
            "ID":        c.id[:8],
            "Title":     c.title,
            "Priority":  c.priority.title(),
            "Assignee":  c.assignee or "—",
            "Labels":    ", ".join(c.labels) if c.labels else "—",
            "Job":       job_status,
            "Attested":  "Yes" if c.attested else "No",
            "Updated":   c.updated_at[:10],
        })
    return pd.DataFrame(rows, columns=_CARD_COLS)


def _resolve_job_status(scenario_id: Optional[str]) -> str:
    """Map a taipy.core Scenario → human job status string."""
    if not scenario_id:
        return "—"
    try:
        scenario_id = str(scenario_id)

        def _job_matches_scenario(job) -> bool:
            submit_entity_id = str(
                getattr(job, "submit_entity_id", None)
                or getattr(job, "_submit_entity_id", None)
                or ""
            )
            if submit_entity_id:
                return submit_entity_id == scenario_id
            # Backward-compat fallback for older Taipy APIs.
            try:
                parents = tc.get_parents(job).get("scenarios", [])
                return any(str(p.id) == scenario_id for p in parents)
            except Exception:
                return False

        jobs = [j for j in tc.get_jobs() if _job_matches_scenario(j)]
        if not jobs:
            return "submitted"
        j = jobs[-1]
        m = {
            Status.SUBMITTED: "submitted",
            Status.BLOCKED:   "blocked",
            Status.PENDING:   "pending",
            Status.RUNNING:   "running",
            Status.CANCELED:  "cancelled",
            Status.FAILED:    "failed",
            Status.COMPLETED: "done",
            Status.SKIPPED:   "skipped",
            Status.ABANDONED: "abandoned",
        }
        return m.get(j.status, j.status.name.lower())
    except Exception:
        return "unknown"


def _jobs_for_scenario_id(scenario_id: str) -> List[Any]:
    """Return all taipy jobs linked to a given scenario id."""
    jobs = []
    try:
        scenario_id = str(scenario_id)
        for j in tc.get_jobs():
            submit_entity_id = str(
                getattr(j, "submit_entity_id", None)
                or getattr(j, "_submit_entity_id", None)
                or ""
            )
            if submit_entity_id and submit_entity_id == scenario_id:
                jobs.append(j)
                continue
            # Backward-compat fallback for older Taipy APIs.
            try:
                parents = tc.get_parents(j).get("scenarios", [])
                if any(str(p.id) == scenario_id for p in parents):
                    jobs.append(j)
            except Exception:
                pass
    except Exception:
        return []
    return jobs


def _refresh_appts(state):
    rows = []
    for a in store.list_appointments():
        smap = {"scheduled": "scheduled", "completed": "completed", "cancelled": "cancelled"}
        linked = ""
        if a.pipeline_card_id:
            c = store.get_card(a.pipeline_card_id)
            if c:
                linked = c.title
        rows.append({
            "id":          a.id,
            "Title":       a.title,
            "Date / Time": (a.scheduled_for.replace("T", " ")[:16]
                            if a.scheduled_for else "—"),
            "Duration":    f"{a.duration_mins} min",
            "Attendees":   ", ".join(a.attendees) if a.attendees else "—",
            "Linked Card": linked or "—",
            "Status":      a.status.title(),
        })
    state.appt_table = pd.DataFrame(
        rows, columns=["id", "Title", "Date / Time", "Duration", "Attendees", "Linked Card", "Status"]
    )
    upcoming_rows = [
        {"Title": a.title,
         "Date":  a.scheduled_for[:10],
         "Time":  a.scheduled_for[11:16] if len(a.scheduled_for) > 10 else ""}
        for a in store.upcoming_appointments(6)
    ]
    state.upcoming_table = pd.DataFrame(upcoming_rows, columns=["Title", "Date", "Time"])


def _refresh_audit(state):
    sev  = state.audit_sev
    srch = (state.audit_search or "").lower()
    rows = []
    for e in store.list_audit():
        if sev != "all" and e.severity != sev:
            continue
        if srch and srch not in e.action.lower() and srch not in e.details.lower():
            continue
        smap = {"info": "info", "warning": "warning", "critical": "critical"}
        rows.append({
            "Time":     e.timestamp[11:19],
            "Actor":    e.actor,
            "Action":   e.action,
            "Resource": f"{e.resource_type}/{e.resource_id}",
            "Details":  e.details[:80],
            "Severity": e.severity,
        })
    state.audit_table = pd.DataFrame(rows, columns=["Time", "Actor", "Action", "Resource", "Details", "Severity"])


def severity_cell_class(state, value, index, row, column_name):
    sev = str(value or "").strip().lower()
    if sev == "info":
        return "sev-info"
    if sev == "warning":
        return "sev-warning"
    if sev in ("critical", "error", "failed"):
        return "sev-critical"
    if sev in ("success", "done", "completed"):
        return "sev-success"
    return "sev-neutral"


def status_cell_class(state, value, index, row, column_name):
    status = str(value or "").strip().lower().replace(" ", "_")
    if status in ("running", "in_progress"):
        return "st-running"
    if status in ("submitted", "submitting", "pending", "blocked", "unknown"):
        return "st-pending"
    if status in ("review", "scheduled"):
        return "st-review"
    if status in ("done", "completed", "success"):
        return "st-done"
    if status in ("failed", "error", "rejected", "cancelled", "canceled", "abandoned"):
        return "st-failed"
    if status in ("backlog",):
        return "st-backlog"
    return "st-neutral"


def priority_cell_class(state, value, index, row, column_name):
    priority = str(value or "").strip().lower()
    if priority == "critical":
        return "pr-critical"
    if priority == "high":
        return "pr-high"
    if priority == "medium":
        return "pr-medium"
    if priority == "low":
        return "pr-low"
    return "pr-neutral"


def _refresh_job_table(state):
    rows = []
    done = failed = running = 0
    durations: List[float] = []
    total_entities = 0

    for jid, sc in _SCENARIOS.items():
        prog = _progress_from_sources(jid)
        pct  = prog.get("pct", 0)
        msg  = prog.get("message", "")
        sts  = str(prog.get("status", "running")).lower()
        taipy_sts = _resolve_job_status(getattr(sc, "id", None))
        if taipy_sts in ("done", "failed", "cancelled", "abandoned", "skipped"):
            if sts == "error":
                # Keep explicit task-level failures even if Taipy marks task execution done.
                sts = "error"
            elif taipy_sts == "done" or taipy_sts == "skipped":
                sts = "done"
            else:
                sts = "error"
            if not msg:
                msg = f"Taipy status: {taipy_sts}"
            if taipy_sts == "done" and pct < 100:
                pct = 100
        elif taipy_sts in ("running", "pending", "submitted", "blocked"):
            if sts not in ("done", "error"):
                sts = "running"
                if not msg:
                    msg = f"Taipy status: {taipy_sts}"
        stats_data = None
        try:
            stats_data = sc.job_stats.read()
        except Exception:
            pass
        entities = stats_data.get("total_entities", "—") if stats_data else "—"
        dur      = stats_data.get("duration_s", "—")     if stats_data else "—"
        if sts == "done":
            done += 1
        elif sts == "error":
            failed += 1
        else:
            running += 1
        if isinstance(dur, (int, float)):
            durations.append(float(dur))
        if isinstance(entities, int):
            total_entities += entities

        rows.append({
            "job_id":     jid,
            "Job ID":     jid[:8],
            "Title":      stats_data.get("job_id", jid)[:24] if stats_data else jid[:24],
            "Progress":   f"{pct}%",
            "Status":     sts,
            "Entities":   entities,
            "Duration":   f"{dur}s" if dur != "—" else "—",
            "Message":    msg[:60],
        })
    state.job_table_data = pd.DataFrame(
        rows, columns=["job_id", "Job ID", "Title", "Progress", "Status", "Entities", "Duration", "Message"]
    )
    total = len(rows)
    state.job_kpi_total = total
    state.job_kpi_running = running
    state.job_kpi_entities = total_entities
    closed = done + failed
    state.job_kpi_success = f"{(done / closed * 100):.0f}%" if closed else "0%"
    state.job_kpi_success_pct = round((done / closed * 100), 1) if closed else 0.0
    _refresh_job_health(state)
    _refresh_job_errors(state)
    _refresh_whatif(state)
    _refresh_sdm(state)


def _refresh_whatif(state):
    scenario_ids = [sc.id for sc in _SCENARIOS.values()]
    state.whatif_scenarios_lov = scenario_ids
    state.whatif_scenarios_sel = [
        sid for sid in (state.whatif_scenarios_sel or []) if sid in scenario_ids
    ]
    if not scenario_ids:
        state.whatif_compare_md = "No scenarios yet. Submit jobs to generate scenarios."
        state.whatif_compare_has_data = False
        state.whatif_compare_data = pd.DataFrame(
            columns=["Scenario", "Processed Rows", "Entities", "Entities / Row"]
        )
        state.whatif_compare_chart = pd.DataFrame(columns=["Scenario", "Entities"])
        state.whatif_compare_figure = {}
    elif not state.whatif_scenarios_sel:
        state.whatif_compare_md = (
            f"{len(scenario_ids)} scenarios available. Select at least two, then click Compare Scenarios."
        )


def _extract_whatif_comparison_df(comparisons: Any) -> pd.DataFrame:
    """Pull first comparator DataFrame from tp.compare_scenarios(...) output."""
    if isinstance(comparisons, pd.DataFrame):
        return comparisons.copy()
    if not isinstance(comparisons, dict):
        return pd.DataFrame()

    for _, data_node_result in comparisons.items():
        if isinstance(data_node_result, pd.DataFrame):
            return data_node_result.copy()
        if isinstance(data_node_result, dict):
            for _, comparator_result in data_node_result.items():
                if isinstance(comparator_result, pd.DataFrame):
                    return comparator_result.copy()
    return pd.DataFrame()


def _refresh_sdm(state):
    scenario_to_job = {
        str(getattr(sc, "id", "")): job_id
        for job_id, sc in _SCENARIOS.items()
        if getattr(sc, "id", None) is not None
    }
    sub_rows = []
    try:
        submissions = tp.get_submissions()
        for s in submissions:
            sub_id = str(getattr(s, "id", ""))
            entity = str(getattr(s, "entity_id", ""))
            status = str(getattr(getattr(s, "submission_status", None), "name", getattr(s, "submission_status", "—")))
            job_id = scenario_to_job.get(entity)
            if job_id and sub_id:
                _SUBMISSION_IDS[job_id] = sub_id
            sub_rows.append({
                "Submission": sub_id[:12],
                "Entity": entity[:24],
                "Status": status.lower() if isinstance(status, str) else "—",
                "Jobs": len(getattr(s, "jobs", []) or []),
                "Created": str(getattr(s, "creation_date", ""))[:19].replace("T", " "),
            })
    except Exception:
        pass
    state.submission_table = pd.DataFrame(
        sub_rows,
        columns=["Submission", "Entity", "Status", "Jobs", "Created"],
    )

    cycle_rows = []
    try:
        cycles = tp.get_cycles()
        for c in cycles:
            scenarios = []
            try:
                scenarios = tc.get_scenarios(cycle=c)
            except Exception:
                scenarios = []
            cycle_rows.append({
                "Cycle": str(getattr(c, "id", ""))[:12],
                "Frequency": str(getattr(c, "frequency", "—")).replace("Frequency.", "").lower(),
                "Start": str(getattr(c, "start_date", ""))[:10],
                "End": str(getattr(c, "end_date", ""))[:10],
                "Scenarios": len(scenarios),
            })
    except Exception:
        pass
    state.cycle_table = pd.DataFrame(
        cycle_rows,
        columns=["Cycle", "Frequency", "Start", "End", "Scenarios"],
    )


def _submission_status_label(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return "—"
    # Normalize provider-specific/raw enum strings into a small stable UI set.
    if "reject" in raw:
        return "Rejected"
    if "fail" in raw or "error" in raw:
        return "Failed"
    if "cancel" in raw:
        return "Cancelled"
    if "abandon" in raw:
        return "Abandoned"
    if "skip" in raw:
        return "Skipped"
    if "complete" in raw or "done" in raw or "success" in raw:
        return "Completed"
    if "run" in raw:
        return "Running"
    if "block" in raw:
        return "Blocked"
    if "pend" in raw:
        return "Pending"
    if "submit" in raw:
        return "Submitted"
    mapping = {
        "submitted": "Submitted",
        "pending": "Pending",
        "blocked": "Blocked",
        "running": "Running",
        "completed": "Completed",
        "failed": "Failed",
        "rejected": "Rejected",
        "canceled": "Cancelled",
        "cancelled": "Cancelled",
        "abandoned": "Abandoned",
    }
    return mapping.get(raw, "Submitted")


def _resolve_submission_state(job_id: str) -> Dict[str, str]:
    if not job_id:
        return {"id": "", "status": "—"}
    scenario = _SCENARIOS.get(job_id)
    scenario_id = str(getattr(scenario, "id", "") or "")
    known_sub_id = str(_SUBMISSION_IDS.get(job_id, "") or "")

    try:
        submissions = list(tp.get_submissions() or [])
    except Exception:
        submissions = []

    candidate = None
    if known_sub_id:
        for submission in reversed(submissions):
            if str(getattr(submission, "id", "")) == known_sub_id:
                candidate = submission
                break
    if candidate is None and scenario_id:
        for submission in reversed(submissions):
            if str(getattr(submission, "entity_id", "")) == scenario_id:
                candidate = submission
                break

    if candidate is None:
        if known_sub_id:
            return {"id": known_sub_id, "status": "Submitted"}
        return {"id": "", "status": "—"}

    sub_id = str(getattr(candidate, "id", "") or "")
    if sub_id:
        _SUBMISSION_IDS[job_id] = sub_id
    raw_status = getattr(getattr(candidate, "submission_status", None), "name", getattr(candidate, "submission_status", ""))
    return {"id": sub_id, "status": _submission_status_label(raw_status)}


def _format_eta(seconds: float) -> str:
    if seconds <= 0:
        return "ETA < 1m"
    mins, secs = divmod(int(seconds), 60)
    if mins >= 60:
        hrs, mins = divmod(mins, 60)
        return f"ETA {hrs}h {mins}m"
    return f"ETA {mins}m {secs:02d}s"


def _refresh_job_health(state):
    jid = state.active_job_id
    if not jid:
        state.job_run_health = "Idle"
        state.job_active_submission_id = ""
        state.job_submission_status = "—"
        state.job_stage_text = ""
        state.job_eta_text = "ETA —"
        state.job_processed_text = "0 / 0 rows"
        state.job_expected_rows = 0
        return

    prog = _progress_from_sources(jid)
    # If a stale client state references a removed job, reset the monitor.
    if not prog and jid not in _SCENARIOS:
        state.active_job_id = ""
        state.job_is_running = False
        state.job_progress_pct = 0
        state.job_progress_msg = ""
        state.job_progress_status = ""
        state.job_expected_rows = 0
        state.job_active_started = 0.0
        state.job_run_health = "Idle"
        state.job_active_submission_id = ""
        state.job_submission_status = "—"
        state.job_stage_text = ""
        state.job_eta_text = "ETA —"
        state.job_processed_text = "0 / 0 rows"
        return

    pct = float(prog.get("pct", state.job_progress_pct or 0))
    raw_total = prog.get("total", None)
    if isinstance(raw_total, numbers.Number) and int(raw_total) > 0:
        total = int(raw_total)
    else:
        total = int(state.job_expected_rows or 0)
    processed = int(prog.get("processed", 0) or 0)
    status = str(
        prog.get(
            "status",
            state.job_progress_status or ("running" if state.job_is_running else "idle"),
        )
    ).lower()
    msg = str(prog.get("message", state.job_progress_msg or "")).strip()
    msg_lower = msg.lower()
    reject_signal = "reject" in msg_lower or "outside the allowed upload directory" in msg_lower
    # Some workers can mark submission done while task-level message indicates a reject/failure.
    if status != "error" and any(token in msg_lower for token in ("rejected", "failed", "error")):
        status = "error"
    if msg == "No job running.":
        msg = ""
    if total <= 0 and msg:
        m = re.search(r"queuing job for\s+([\d,]+)\s+rows", msg, flags=re.IGNORECASE)
        if m:
            try:
                total = int(m.group(1).replace(",", ""))
            except Exception:
                pass
    if total <= 0:
        sc = _SCENARIOS.get(jid)
        if sc is not None:
            try:
                cfg = sc.job_config.read() or {}
                total = int(cfg.get("row_count_hint", 0) or 0)
            except Exception:
                pass

    if status == "error":
        state.job_run_health = "Error"
    elif reject_signal:
        state.job_run_health = "Rejected"
    elif status == "done":
        state.job_run_health = "Completed"
    elif status in ("idle", ""):
        state.job_run_health = "Idle"
    else:
        state.job_run_health = "Running"

    submission = _resolve_submission_state(jid)
    state.job_active_submission_id = str(submission.get("id", "") or "")
    sub_status = str(submission.get("status", "—") or "—")
    if sub_status == "—" and state.job_is_running:
        sub_status = "Submitting"
    if status == "error":
        sub_status = "Failed"
    elif reject_signal:
        sub_status = "Rejected"
    elif status == "done" and sub_status.strip().lower() in {"—", "unknown", "submitted", "submitting"}:
        sub_status = "Completed"
    state.job_submission_status = sub_status

    if not msg:
        if status == "done":
            msg = "Run completed."
        elif status == "error":
            msg = "Run failed."
        elif status == "running":
            msg = "Waiting for worker…"
    state.job_stage_text = msg
    if reject_signal and total <= 0 and processed <= 0:
        state.job_processed_text = "Rejected before processing"
    else:
        state.job_processed_text = f"{processed:,} / {total:,} rows" if total else "0 / 0 rows"

    if status == "running" and pct > 0 and state.job_active_started > 0:
        elapsed = max(0.0, time.time() - state.job_active_started)
        eta_s = elapsed * (100.0 - pct) / pct
        state.job_eta_text = _format_eta(eta_s)
    elif status == "done":
        state.job_eta_text = "ETA complete"
    elif status == "error":
        state.job_eta_text = "ETA unavailable"
    elif status in ("idle", ""):
        state.job_eta_text = "ETA —"
    else:
        state.job_eta_text = "ETA estimating…"


def _refresh_job_errors(state):
    jid = state.active_job_id or state.download_scenario_id
    rows = []
    if jid:
        sc = _SCENARIOS.get(jid)
        if sc:
            try:
                stats_data = sc.job_stats.read()
                for err in (stats_data or {}).get("errors", []):
                    rows.append({
                        "Time": datetime.now().strftime("%H:%M:%S"),
                        "Source": "processor",
                        "Details": str(err)[:140],
                        "Severity": "warning",
                    })
            except Exception:
                pass
        for e in store.list_audit(limit=80):
            if e.resource_type == "job" and e.resource_id == jid:
                rows.append({
                    "Time": e.timestamp[11:19],
                    "Source": "audit",
                    "Details": (e.details or "")[:140],
                    "Severity": e.severity,
                })
    state.job_errors_data = pd.DataFrame(
        rows,
        columns=["Time", "Source", "Details", "Severity"],
    )


def _ticker_numeric_label(current: int, previous: Optional[int], suffix: str = "") -> str:
    current_txt = f"{current}{suffix}"
    if previous is None:
        return f"{current_txt} (=)"
    delta = current - previous
    if delta > 0:
        return f"{current_txt} (+{delta})"
    if delta < 0:
        return f"{current_txt} ({delta})"
    return f"{current_txt} (=)"


def _refresh_dashboard_displays(state, by_s: Dict[str, int]) -> None:
    """Populate dashboard display widgets (status, metric, tree, selectors)."""
    prev_running = int(getattr(state, "ops_metric_running", 0) or 0)
    total_jobs = int(getattr(state, "dash_jobs_total", 0) or 0)
    running_jobs = int(getattr(state, "dash_jobs_running", 0) or 0)
    failed_jobs = int(getattr(state, "dash_jobs_failed", 0) or 0)

    state.ops_metric_running = running_jobs
    state.ops_metric_total = max(1, total_jobs)
    state.ops_metric_delta = running_jobs - prev_running

    store_label = str(getattr(state, "store_status_label", "") or "In Memory")
    run_health = str(getattr(state, "job_run_health", "Idle") or "Idle")
    review_count = int(by_s.get("review", 0) or 0)
    backlog_count = int(by_s.get("backlog", 0) or 0)

    run_status = "error" if failed_jobs > 0 else ("warning" if running_jobs > 0 else "success")
    review_status = "warning" if review_count > 0 else "info"

    state.ops_status_items = [
        ("info", f"Store backend: {store_label}"),
        (run_status, f"Jobs: {running_jobs} running / {total_jobs} total"),
        ("error" if failed_jobs > 0 else "success", f"Failed jobs: {failed_jobs}"),
        (review_status, f"Cards in review: {review_count} · Backlog: {backlog_count}"),
        ("info", f"Run health: {run_health}"),
    ]

    tree_meta: Dict[str, str] = {}
    job_children: List[Dict[str, Any]] = []
    for jid, sc in sorted(_SCENARIOS.items(), key=lambda kv: kv[0]):
        sid = str(getattr(sc, "id", "") or "")
        prog = _progress_from_sources(jid)
        pct = int(float(prog.get("pct", 0) or 0))
        status = str(prog.get("status", "running") or "running")
        message = str(prog.get("message", "") or "")

        node_id = f"job::{jid}"
        tree_meta[node_id] = (
            f"**Job** `{jid[:8]}` · status **{status}** · progress **{pct}%**  \n"
            f"Scenario `{sid[:12] or '—'}`  \n"
            f"{message if message else 'No task message available.'}"
        )
        job_children.append(
            {
                "id": node_id,
                "label": f"{jid[:8]} · {status} · {pct}%",
                "children": [
                    {"id": f"{node_id}::scenario", "label": f"Scenario {sid[:12] or '—'}"},
                ],
            }
        )

    if not job_children:
        job_children = [{"id": "job::none", "label": "No jobs submitted yet"}]
        tree_meta["job::none"] = "No job has been submitted yet."

    stage_children: List[Dict[str, Any]] = []
    for stage in ("backlog", "in_progress", "review", "done"):
        stage_count = int(by_s.get(stage, 0) or 0)
        stage_id = f"stage::{stage}"
        stage_label = stage.replace("_", " ").title()
        stage_children.append({"id": stage_id, "label": f"{stage_label}: {stage_count}"})
        tree_meta[stage_id] = f"**{stage_label}** cards: **{stage_count}**"

    review_children: List[Dict[str, Any]] = []
    upcoming = store.upcoming_appointments(3)
    for appt in upcoming:
        aid = str(getattr(appt, "id", "") or "")
        title = str(getattr(appt, "title", "Review"))
        when = str(getattr(appt, "scheduled_for", "") or "").replace("T", " ")[:16]
        rid = f"review::{aid or title}"
        review_children.append({"id": rid, "label": f"{title} · {when}"})
        tree_meta[rid] = f"**{title}**  \nScheduled: `{when or '—'}`"
    if not review_children:
        review_children = [{"id": "review::none", "label": "No upcoming reviews"}]
        tree_meta["review::none"] = "No upcoming reviews scheduled."

    state.ops_tree_lov = [
        {"id": "root::jobs", "label": f"Jobs ({len(job_children) if job_children[0]['id'] != 'job::none' else 0})", "children": job_children},
        {"id": "root::pipeline", "label": "Pipeline", "children": stage_children},
        {"id": "root::reviews", "label": "Upcoming Reviews", "children": review_children},
    ]
    state.ops_tree_meta = tree_meta
    if not getattr(state, "ops_tree_expanded", None):
        state.ops_tree_expanded = ["root::jobs", "root::pipeline", "root::reviews"]

    selected = str(getattr(state, "ops_tree_selected", "") or "")
    state.ops_tree_selected_md = tree_meta.get(
        selected,
        "Select a node to inspect orchestration context.",
    )


def _refresh_dashboard(state):
    def _parse_dt(value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            dt = value
        else:
            raw = str(value or "").strip()
            if not raw:
                return None
            # Accept common UTC suffix used in persisted Mongo payloads.
            if raw.endswith("Z"):
                raw = raw[:-1] + "+00:00"
            try:
                dt = datetime.fromisoformat(raw)
            except Exception:
                return None

        # Compare in local naive time to avoid aware/naive TypeError.
        if dt.tzinfo is not None:
            try:
                dt = dt.astimezone().replace(tzinfo=None)
            except Exception:
                return None
        return dt

    def _in_window(value: Any, window: str) -> bool:
        if window == "All":
            return True
        try:
            dt = _parse_dt(value)
            if dt is None:
                return False
            now = datetime.now()
            if window == "24h":
                return dt >= now - timedelta(hours=24)
            if window == "7d":
                return dt >= now - timedelta(days=7)
            if window == "30d":
                return dt >= now - timedelta(days=30)
            return True
        except Exception:
            return False

    st = store.stats()
    prev_completion_pct = int(getattr(state, "dash_completion_pct", 0) or 0)
    prev_inflight_cards = int(getattr(state, "dash_inflight_cards", 0) or 0)
    prev_backlog_cards = int(getattr(state, "dash_backlog_cards", 0) or 0)
    _dash_sessions = store.list_sessions()   # hoist — reused by entity chart, trend, perf panel
    state.dash_cards_total    = sum(st["pipeline_by_status"].values())
    state.dash_cards_attested = st["attested_cards"]
    state.dash_kpi_entities_total = st.get("total_entities_redacted", 0)
    state.dash_kpi_reviews_scheduled = len([
        a for a in store.list_appointments() if a.status == "scheduled"
    ])
    all_jobs = tc.get_jobs()
    state.dash_jobs_total   = len(_SCENARIOS)
    state.dash_jobs_running = sum(1 for j in all_jobs if j.status == Status.RUNNING)
    state.dash_jobs_done    = sum(1 for j in all_jobs if j.status == Status.COMPLETED)
    state.dash_jobs_failed  = sum(1 for j in all_jobs if j.status == Status.FAILED)
    upcoming = store.upcoming_appointments(4)
    html = []
    import html as _html
    for a in upcoming:
        dt = a.scheduled_for.replace("T", " ")[:16]
        safe_title = _html.escape(a.title)
        html.append(f"**{safe_title}**  \n{dt} · {a.duration_mins} min")
    if html:
        state.dash_upcoming_md = "  \n".join(html)
    else:
        state.dash_upcoming_md = "*No upcoming reviews scheduled.*"

    # Pipeline stage distribution
    by_s = st["pipeline_by_status"]
    total_cards = sum(by_s.values())
    state.dash_stage_chart = pd.DataFrame(
        [{"Stage": k.replace("_", " ").title(), "Count": v}
         for k, v in by_s.items() if v > 0]
    ) if any(by_s.values()) else pd.DataFrame(columns=["Stage", "Count"])
    _refresh_dashboard_displays(state, by_s)
    state.dash_stage_chart_visible = any(by_s.values())
    if state.dash_stage_chart_visible and go is not None:
        stage_df = state.dash_stage_chart
        fig_stage = go.Figure(
            go.Pie(
                labels=stage_df["Stage"],
                values=stage_df["Count"],
                hole=float(dash_stage_chart_options.get("hole", 0.52)),
                textinfo=str(dash_stage_chart_options.get("textinfo", "label+percent")),
                sort=False,
                marker=dict(
                    colors=mono_colorway[: max(1, len(stage_df))],
                    line=dict(color=chart_layout["plot_bgcolor"], width=1),
                ),
                hovertemplate="%{label}: %{value} cards (%{percent})<extra></extra>",
            )
        )
        fig_stage.update_layout(
            **{
                **dash_stage_pie_layout,
                "margin": {"t": 10, "b": 10, "l": 10, "r": 10},
            }
        )
        state.dash_stage_figure = fig_stage
    else:
        state.dash_stage_figure = {}

    stage_rows = []
    for k, v in by_s.items():
        if v <= 0:
            continue
        pct = (v / total_cards * 100.0) if total_cards else 0.0
        stage_rows.append({
            "Stage": k.replace("_", " ").title(),
            "Count": v,
            "Share": f"{pct:.1f}%",
        })
    state.dash_stage_report = pd.DataFrame(stage_rows, columns=["Stage", "Count", "Share"])
    if stage_rows:
        state.dash_stage_breakdown_md = "  \n".join(
            f"**{r['Stage']}** · {r['Count']} cards · {r['Share']}" for r in stage_rows
        )
    else:
        state.dash_stage_breakdown_md = "No pipeline stages available yet."
    state.dash_completion_pct = int(round((by_s.get("done", 0) / total_cards) * 100)) if total_cards else 0
    in_flight = by_s.get("in_progress", 0) + by_s.get("review", 0)
    state.dash_inflight_cards = in_flight
    state.dash_backlog_cards = by_s.get("backlog", 0)
    state.dash_completion_pct_delta = state.dash_completion_pct - prev_completion_pct
    state.dash_inflight_cards_delta = state.dash_inflight_cards - prev_inflight_cards
    state.dash_backlog_cards_delta = state.dash_backlog_cards - prev_backlog_cards
    state.dash_completion_pct_ticker = _ticker_numeric_label(
        state.dash_completion_pct, prev_completion_pct, suffix="%"
    )
    state.dash_inflight_cards_ticker = _ticker_numeric_label(
        state.dash_inflight_cards, prev_inflight_cards
    )
    state.dash_backlog_cards_ticker = _ticker_numeric_label(
        state.dash_backlog_cards, prev_backlog_cards
    )
    state.dash_pipeline_report_md = (
        f"Completion **{state.dash_completion_pct}%**  \n"
        f"In-flight **{in_flight}** cards · Backlog **{state.dash_backlog_cards}**"
        if total_cards else "No pipeline cards yet."
    )

    # Top entity types across all saved sessions
    entity_totals: Counter = Counter()
    for sess in _dash_sessions:
        if sess.entity_counts:
            entity_totals.update(sess.entity_counts)
    top = entity_totals.most_common(8)
    state.dash_entity_chart = pd.DataFrame(top, columns=["Entity Type", "Sessions"]) \
        if top else pd.DataFrame(columns=["Entity Type", "Sessions"])
    state.dash_entity_chart_visible = bool(top)
    if top:
        max_label_len = max(len(str(k)) for k, _ in top)
        left_margin = max(150, min(320, 24 + (max_label_len * 9)))
        x_tickfont = {**dict(chart_layout["xaxis"].get("tickfont", {})), "size": 12}
        y_tickfont = {**dict(chart_layout["yaxis"].get("tickfont", {})), "size": 12}
        entity_layout = {
            **chart_layout,
            "margin": {"t": 24, "b": 46, "l": left_margin, "r": 20},
            "xaxis": {
                **chart_layout["xaxis"],
                "dtick": 1,
                "title": "Sessions",
                "tickfont": x_tickfont,
            },
            "yaxis": {
                **chart_layout["yaxis"],
                "automargin": True,
                "tickfont": y_tickfont,
            },
        }
    else:
        x_tickfont = {**dict(chart_layout["xaxis"].get("tickfont", {})), "size": 12}
        y_tickfont = {**dict(chart_layout["yaxis"].get("tickfont", {})), "size": 12}
        entity_layout = {
            **chart_layout,
            "margin": {"t": 24, "b": 46, "l": 180, "r": 20},
            "xaxis": {
                **chart_layout["xaxis"],
                "dtick": 1,
                "title": "Sessions",
                "tickfont": x_tickfont,
            },
            "yaxis": {
                **chart_layout["yaxis"],
                "automargin": True,
                "tickfont": y_tickfont,
            },
        }
    state.dash_entity_chart_layout = entity_layout
    if state.dash_entity_chart_visible and go is not None:
        entity_df = state.dash_entity_chart.sort_values("Sessions", ascending=True)
        _n = len(entity_df)
        _bar_colors = [mono_colorway[i % len(mono_colorway)] for i in range(_n)]
        fig_entity = go.Figure(
            go.Bar(
                x=entity_df["Sessions"],
                y=entity_df["Entity Type"],
                orientation="h",
                marker=dict(color=_bar_colors),
                text=[str(v) for v in entity_df["Sessions"]],
                textposition="outside",
                cliponaxis=False,
                hovertemplate="%{y}: %{x} sessions<extra></extra>",
            )
        )
        fig_entity.update_layout(
            **{
                **entity_layout,
                "showlegend": False,
                "bargap": 0.22,
            }
        )
        state.dash_entity_chart_figure = fig_entity
    else:
        state.dash_entity_chart_figure = {}
    entity_sum = sum(entity_totals.values())
    ent_rows = [
        {"Entity Type": k, "Count": v, "Share": f"{(v / entity_sum * 100):.1f}%"}
        for k, v in top
    ] if entity_sum else []
    state.dash_entity_report = pd.DataFrame(ent_rows, columns=["Entity Type", "Count", "Share"])
    state.dash_entity_mix_chart = pd.DataFrame(
        [{"Entity Type": r["Entity Type"], "Count": r["Count"]} for r in ent_rows[:7]],
        columns=["Entity Type", "Count"],
    ) if ent_rows else pd.DataFrame(columns=["Entity Type", "Count"])
    if ent_rows and go is not None:
        mix_df = state.dash_entity_mix_chart
        mix_palette = mono_colorway[:len(mix_df)]
        viz_bg = chart_layout["plot_bgcolor"]
        viz_text = chart_layout["font"]["color"]
        fig_mix = go.Figure(
            go.Pie(
                labels=mix_df["Entity Type"],
                values=mix_df["Count"],
                hole=0.62,
                textinfo="label+percent",
                sort=False,
                marker=dict(
                    colors=mix_palette,
                    line=dict(color=viz_bg, width=1),
                ),
                textfont=dict(color=viz_text, size=11),
                hovertemplate="%{label}: %{value} detections (%{percent})<extra></extra>",
            )
        )
        fig_mix.update_layout(
            template="plotly_dark",
            paper_bgcolor=viz_bg,
            plot_bgcolor=viz_bg,
            margin=dict(t=10, b=10, l=10, r=10),
            showlegend=False,
            annotations=[
                dict(
                    text=f"{int(entity_sum)}<br>Total",
                    x=0.5, y=0.5,
                    font=dict(color=viz_text, size=15),
                    showarrow=False,
                )
            ],
        )
        state.dash_entity_mix_figure = fig_mix
    else:
        state.dash_entity_mix_figure = {}
    state.dash_entity_dominance_pct = (
        round((top[0][1] / entity_sum) * 100.0, 1) if top and entity_sum else 0.0
    )
    state.dash_entity_dominance_pct_label = f"{state.dash_entity_dominance_pct:.1f}%"
    state.dash_kpi_entities_total = int(entity_sum) if entity_sum else 0
    state.dash_kpi_entities_total_label = f"{int(state.dash_kpi_entities_total):,}"
    if ent_rows:
        state.dash_entity_breakdown_md = "  \n".join(
            f"**{r['Entity Type']}** · {r['Count']} detections · {r['Share']}" for r in ent_rows
        )
    else:
        state.dash_entity_breakdown_md = "No saved PII sessions yet."
    state.dash_entity_report_md = (
        f"Dominant entity **{top[0][0]}** · **{top[0][1]}** detections  \n"
        f"Entity families tracked **{len(entity_totals)}**"
        if top else "No saved PII sessions yet."
    )

    # Report widgets (mode + window)
    window = state.dash_time_window
    mode = state.dash_report_mode

    filtered_audit = [e for e in store.list_audit(limit=1000) if _in_window(e.timestamp, window)]
    severity_order = ("info", "warning", "critical")
    sev_counts = {s: 0 for s in severity_order}
    for e in filtered_audit:
        sev = str(getattr(e, "severity", "info")).lower()
        if sev in sev_counts:
            sev_counts[sev] += 1
    state.dash_audit_chart = pd.DataFrame(
        [{"Severity": s.title(), "Count": sev_counts[s]} for s in severity_order if sev_counts[s] > 0],
        columns=["Severity", "Count"],
    )
    state.dash_audit_chart_visible = not state.dash_audit_chart.empty

    cards = store.list_cards()
    pr_counts = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    for c in cards:
        p = str(getattr(c, "priority", "medium")).lower()
        if p in pr_counts:
            pr_counts[p] += 1
    state.dash_priority_chart = pd.DataFrame(
        [{"Priority": p.title(), "Count": pr_counts[p]} for p in ("critical", "high", "medium", "low") if pr_counts[p] > 0],
        columns=["Priority", "Count"],
    )
    state.dash_priority_chart_visible = not state.dash_priority_chart.empty

    sessions = [s for s in _dash_sessions if _in_window(s.created_at, window)]
    by_day: Dict[str, Dict[str, int]] = {}
    for s in sessions:
        day = str(getattr(s, "created_at", ""))[:10]
        if day not in by_day:
            by_day[day] = {"Entities": 0, "Sessions": 0}
        by_day[day]["Sessions"] += 1
        by_day[day]["Entities"] += int(sum((s.entity_counts or {}).values()))
    trend_rows = [{"Date": d, **vals} for d, vals in sorted(by_day.items())]
    state.dash_ops_trend = pd.DataFrame(trend_rows, columns=["Date", "Entities", "Sessions"])
    state.dash_ops_trend_visible = not state.dash_ops_trend.empty

    place_counts, unmapped_geo_mentions = _build_geo_place_counts(sessions, GEO_CITY_COORDS)
    map_rows = []
    for city, count in sorted(place_counts.items(), key=lambda kv: -kv[1]):
        lat, lon = GEO_CITY_COORDS[city]
        map_rows.append({"Place": city.title(), "Lat": lat, "Lon": lon, "Mentions": count})
    state.dash_map_chart = pd.DataFrame(map_rows, columns=["Place", "Lat", "Lon", "Mentions"])
    state.dash_map_visible = not state.dash_map_chart.empty
    if state.dash_map_visible and go is not None:
        lat_values = [float(v) for v in state.dash_map_chart["Lat"]]
        lon_values = [float(v) for v in state.dash_map_chart["Lon"]]
        city_view = _geo_city_view(lat_values, lon_values)
        max_mentions = max(1, int(state.dash_map_chart["Mentions"].max()))
        sizes = [10 + (28 * (m / max_mentions)) for m in state.dash_map_chart["Mentions"]]
        map_bg = "#F9F4EF"
        map_text = "#2F2A28"
        map_font = {**chart_layout["font"], "color": map_text}
        geo_scale = [
            [0.0, "#F4D8C8"],
            [0.5, chart_layout["colorway"][0]],
            [1.0, chart_layout["colorway"][1]],
        ]
        fig = go.Figure(
            go.Scattermap(
                lon=state.dash_map_chart["Lon"],
                lat=state.dash_map_chart["Lat"],
                text=[
                    f"{p}: {m} mention{'s' if m != 1 else ''}"
                    for p, m in zip(state.dash_map_chart["Place"], state.dash_map_chart["Mentions"])
                ],
                mode="markers+text",
                textposition="top center",
                textfont=dict(color=map_text, size=11),
                marker=dict(
                    size=sizes,
                    color=state.dash_map_chart["Mentions"],
                    colorscale=geo_scale,
                    opacity=0.94,
                    line=dict(color="#FFF8F2", width=1.8),
                    colorbar=dict(
                        title=dict(text="Mentions", font=dict(color=map_text)),
                        x=1.02,
                        xanchor="left",
                        thickness=12,
                        tickfont=dict(color=map_text),
                        bgcolor=map_bg,
                        outlinecolor="#E7D4C8",
                    ),
                ),
                hovertemplate="%{text}<extra></extra>",
            )
        )
        fig.update_layout(
            template="plotly_white",
            paper_bgcolor=map_bg,
            font=map_font,
            margin=dict(t=10, b=10, l=10, r=56),
            map=dict(
                style="carto-positron",
                center=city_view["center"],
                zoom=city_view["zoom"],
            ),
        )
        state.dash_map_figure = fig
    else:
        state.dash_map_figure = {}
    if state.dash_map_visible:
        extra = (
            f"  \nUnmapped location mentions: **{unmapped_geo_mentions}**"
            if unmapped_geo_mentions > 0
            else ""
        )
        state.dash_map_md = (
            f"Geo signal detected in **{len(state.dash_map_chart)}** locations "
            f"within **{window}** window.{extra}"
        )
    elif unmapped_geo_mentions > 0:
        state.dash_map_md = (
            f"Detected **{unmapped_geo_mentions}** location mentions in **{window}** window, "
            "but they could not be mapped yet."
        )
    else:
        state.dash_map_md = "No geographic mentions detected yet. Add location-rich text to see map points."

    report_bits = [f"Mode **{mode}**", f"Window **{window}**"]
    if mode == "Operations":
        report_bits.append(f"Sessions **{len(sessions)}**")
        report_bits.append(f"Running jobs **{state.dash_jobs_running}**")
    elif mode == "Compliance":
        report_bits.append(f"Scheduled reviews **{state.dash_kpi_reviews_scheduled}**")
        report_bits.append(f"Critical audit events **{sev_counts['critical']}**")
    elif mode == "Throughput":
        total_entities_window = sum(int(sum((s.entity_counts or {}).values())) for s in sessions)
        report_bits.append(f"Entities processed **{total_entities_window}**")
        report_bits.append(f"Completed jobs **{state.dash_jobs_done}**")
    else:
        report_bits.append(f"Cards **{state.dash_cards_total}**")
        report_bits.append(f"Entities tracked **{state.dash_kpi_entities_total}**")
    state.dash_report_summary_md = " · ".join(report_bits)

    # Visibility flags — hide entire sections when empty
    # Engine Performance panel — timing from saved sessions
    timing_sessions = [s for s in _dash_sessions if getattr(s, "processing_ms", 0) > 0]
    if timing_sessions and go is not None:
        timing_ms  = [s.processing_ms for s in timing_sessions]
        avg_ms     = sum(timing_ms) / len(timing_ms)
        latest_ms  = timing_ms[-1]
        # Numeric state consumed by native Taipy metric / indicator widgets
        state.dash_perf_avg_ms   = round(avg_ms, 1)
        state.dash_perf_delta_ms = round(latest_ms - avg_ms, 1)
        state.dash_perf_count    = len(timing_ms)
        state.dash_perf_max_ms   = max(50.0, round(max(timing_ms) * 1.2, 0))

        # Bar chart — last 12 sessions, processing time per session
        recent   = timing_sessions[-12:]
        labels   = [getattr(s, "title", s.id[:8]) for s in recent]
        values   = [round(s.processing_ms, 1) for s in recent]
        # Colour each bar by speed: green (<50ms), amber (<200ms), red (≥200ms)
        bar_colors = [
            "#22C55E" if v < 50 else "#F59E0B" if v < 200 else "#FF2B2B"
            for v in values
        ]
        perf_fig = go.Figure(go.Bar(
            x=labels, y=values,
            marker=dict(color=bar_colors),
            text=[f"{v} ms" for v in values],
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{x}<br>%{y} ms<extra></extra>",
        ))
        perf_fig.update_layout(
            **{
                **chart_layout,
                "margin": {"t": 28, "b": 90, "l": 50, "r": 16},
                "xaxis": {
                    **chart_layout["xaxis"],
                    "tickangle": -35,
                    "tickfont": {"size": 10},
                },
                "yaxis": {
                    **chart_layout["yaxis"],
                    "title": "ms",
                    "rangemode": "tozero",
                },
                "showlegend": False,
            }
        )
        state.dash_perf_figure = perf_fig
        state.perf_telemetry_table = pd.DataFrame({"Session": labels, "ms": values})
        state.dash_perf_visible = True
    else:
        state.dash_perf_avg_ms   = 0.0
        state.dash_perf_delta_ms = 0.0
        state.dash_perf_count    = 0
        state.dash_perf_max_ms   = 50.0
        state.dash_perf_visible  = False
        state.dash_perf_figure   = {}
        state.perf_telemetry_table = pd.DataFrame(columns=["Session", "ms"])

    state.dash_has_reviews = bool(upcoming)
    state.dash_has_any_data = (
        state.dash_has_reviews
        or state.dash_stage_chart_visible
        or state.dash_entity_chart_visible
        or state.dash_audit_chart_visible
        or state.dash_priority_chart_visible
        or state.dash_ops_trend_visible
        or state.dash_map_visible
        or state.dash_perf_visible
    )
    state.dash_empty_hint_visible = not state.dash_has_any_data
    state.dash_intro_md = (
        "" if state.dash_has_any_data
        else "*Start by analyzing text, creating pipeline cards, or scheduling reviews — data will appear here.*"
    )


def _refresh_ui_demo(state) -> None:
    top_n = max(3, min(25, int(getattr(state, "ui_demo_top_n", 10) or 10)))
    mode = str(getattr(state, "ui_demo_mode", "All") or "All")
    if mode not in {"All", "Entities", "Confidence", "Operations"}:
        mode = "All"
    state.ui_demo_top_n = top_n
    state.ui_demo_mode = mode

    stats = store.stats()
    sessions = list(store.list_sessions())
    entity_counts = dict(stats.get("entity_breakdown", {}) or {})
    sorted_entities = sorted(entity_counts.items(), key=lambda x: (-x[1], x[0]))
    total_entities = int(sum(v for _, v in sorted_entities))
    top = sorted_entities[:top_n]

    cum = 0
    table_rows = []
    for etype, count in top:
        count_i = int(count)
        cum += count_i
        share = (count_i / total_entities * 100.0) if total_entities else 0.0
        cumulative = (cum / total_entities * 100.0) if total_entities else 0.0
        table_rows.append(
            {
                "Entity Type": etype,
                "Count": count_i,
                "Share %": round(share, 1),
                "Cumulative %": round(cumulative, 1),
            }
        )
    state.ui_demo_entity_table = pd.DataFrame(
        table_rows, columns=["Entity Type", "Count", "Share %", "Cumulative %"]
    )

    evidence_rows = []
    for sess in sessions:
        for ent in (getattr(sess, "entities", None) or []):
            etype = str(ent.get("Entity Type", ent.get("entity_type", "")) or "")
            recognizer = str(ent.get("Recognizer", ent.get("recognizer", "")) or "")
            text_value = str(ent.get("Text", ent.get("text", "")) or "")
            conf = ent.get("Confidence")
            if conf is None:
                score = ent.get("score")
                if isinstance(score, (int, float)):
                    conf = int(round(float(score) * 100))
            if not isinstance(conf, (int, float)):
                conf = 0
            evidence_rows.append(
                {
                    "Entity Type": etype,
                    "Confidence": int(conf),
                    "Recognizer": recognizer,
                    "Text": text_value[:80],
                }
            )
    evidence_df = pd.DataFrame(
        evidence_rows, columns=["Entity Type", "Confidence", "Recognizer", "Text"]
    )
    state.ui_demo_evidence_table = evidence_df.head(300)

    pipeline_counts = stats.get("pipeline_by_status", {}) or {}
    pipeline_rows = [
        {"Stage": k.replace("_", " ").title(), "Count": int(v)}
        for k, v in pipeline_counts.items()
    ]
    state.ui_demo_pipeline_table = pd.DataFrame(pipeline_rows, columns=["Stage", "Count"])

    state.ui_demo_has_data = bool(total_entities or not evidence_df.empty or sum(pipeline_counts.values()))
    state.ui_demo_last_refresh = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    state.ui_demo_summary_md = (
        f"Mode **{mode}** · Top N **{top_n}** · Sessions **{len(sessions)}** · "
        f"Total detections **{total_entities:,}** · Refreshed `{state.ui_demo_last_refresh}`"
        if state.ui_demo_has_data
        else "No session/entity data yet. Run **Analyze Text** to populate UI visuals."
    )

    if go is None or not state.ui_demo_has_data:
        state.ui_demo_pareto_figure = {}
        state.ui_demo_treemap_figure = {}
        state.ui_demo_heatmap_figure = {}
        state.ui_demo_conf_box_figure = {}
        state.ui_demo_timeline_figure = {}
        state.ui_demo_pipeline_figure = {}
        state.ui_demo_map_figure = {}
        state.ui_demo_map_md = "No data yet. Analyze location-rich text to populate the map."
        return

    # Pareto chart (counts + cumulative share)
    if top and mode in {"All", "Entities"}:
        labels = [x[0] for x in top]
        counts = [int(x[1]) for x in top]
        cumulative = []
        running = 0
        for c in counts:
            running += c
            cumulative.append((running / total_entities * 100.0) if total_entities else 0.0)
        fig = go.Figure()
        fig.add_bar(x=labels, y=counts, name="Count", marker_color=chart_layout["colorway"][0])
        fig.add_scatter(
            x=labels,
            y=cumulative,
            name="Cumulative %",
            mode="lines+markers",
            yaxis="y2",
            line=dict(color=chart_layout["colorway"][3], width=2),
        )
        fig.update_layout(
            **{
                **chart_layout,
                "yaxis": {**chart_layout["yaxis"], "title": "Count"},
                "yaxis2": dict(
                    title="Cumulative %",
                    overlaying="y",
                    side="right",
                    range=[0, 105],
                    tickformat=".0f",
                ),
                "xaxis": {**chart_layout["xaxis"], "title": "Entity Type", "automargin": True},
                "margin": {"t": 30, "b": 70, "l": 56, "r": 56},
            }
        )
        state.ui_demo_pareto_figure = fig

        fig_tree = go.Figure(
            go.Treemap(
                labels=labels,
                parents=[""] * len(labels),
                values=counts,
                marker=dict(colors=counts, colorscale="Blues"),
                textinfo="label+value+percent root",
            )
        )
        fig_tree.update_layout(
            template="plotly_dark",
            paper_bgcolor=chart_layout["paper_bgcolor"],
            plot_bgcolor=chart_layout["plot_bgcolor"],
            margin=dict(t=10, b=10, l=10, r=10),
        )
        state.ui_demo_treemap_figure = fig_tree
    else:
        state.ui_demo_pareto_figure = {}
        state.ui_demo_treemap_figure = {}

    # Confidence box + recognizer/entity heatmap
    if not evidence_df.empty and mode in {"All", "Confidence"}:
        conf_fig = go.Figure()
        top_entity_labels = [r["Entity Type"] for r in table_rows] or sorted(evidence_df["Entity Type"].unique())[:top_n]
        for etype in top_entity_labels:
            subset = evidence_df[evidence_df["Entity Type"] == etype]
            if subset.empty:
                continue
            conf_fig.add_trace(
                go.Box(
                    y=subset["Confidence"],
                    name=etype,
                    boxpoints="outliers",
                    marker_color=chart_layout["colorway"][len(conf_fig.data) % len(chart_layout["colorway"])],
                )
            )
        conf_fig.update_layout(
            **{
                **chart_layout,
                "yaxis": {**chart_layout["yaxis"], "title": "Confidence %", "range": [0, 100]},
                "xaxis": {**chart_layout["xaxis"], "title": "Entity Type"},
                "margin": {"t": 26, "b": 70, "l": 56, "r": 20},
                "showlegend": False,
            }
        )
        state.ui_demo_conf_box_figure = conf_fig

        heat = (
            evidence_df.pivot_table(
                index="Recognizer",
                columns="Entity Type",
                values="Text",
                aggfunc="count",
                fill_value=0,
            )
            .sort_index()
        )
        if not heat.empty:
            heat = heat.iloc[:12, :12]
            heat_fig = go.Figure(
                go.Heatmap(
                    z=heat.values,
                    x=list(heat.columns),
                    y=list(heat.index),
                    colorscale="Viridis",
                    colorbar=dict(title="Count"),
                )
            )
            heat_fig.update_layout(
                **{
                    **chart_layout,
                    "margin": {"t": 26, "b": 60, "l": 120, "r": 20},
                    "xaxis": {**chart_layout["xaxis"], "title": "Entity Type"},
                    "yaxis": {**chart_layout["yaxis"], "title": "Recognizer", "automargin": True},
                }
            )
            state.ui_demo_heatmap_figure = heat_fig
        else:
            state.ui_demo_heatmap_figure = {}
    else:
        state.ui_demo_conf_box_figure = {}
        state.ui_demo_heatmap_figure = {}

    # Operations figures (session timeline + pipeline stage distribution)
    if mode in {"All", "Operations"}:
        by_day = {}
        for s in sessions:
            day = str(getattr(s, "created_at", ""))[:10]
            if not day:
                continue
            by_day.setdefault(day, {"Sessions": 0, "Entities": 0})
            by_day[day]["Sessions"] += 1
            by_day[day]["Entities"] += int(sum((getattr(s, "entity_counts", {}) or {}).values()))
        tdf = pd.DataFrame(
            [{"Date": d, **vals} for d, vals in sorted(by_day.items())],
            columns=["Date", "Sessions", "Entities"],
        )
        if not tdf.empty:
            timeline_fig = go.Figure()
            timeline_fig.add_scatter(x=tdf["Date"], y=tdf["Sessions"], mode="lines+markers", name="Sessions")
            timeline_fig.add_bar(x=tdf["Date"], y=tdf["Entities"], name="Entities", opacity=0.45)
            timeline_fig.update_layout(
                **{
                    **chart_layout,
                    "xaxis": {**chart_layout["xaxis"], "title": "Date"},
                    "yaxis": {**chart_layout["yaxis"], "title": "Count", "rangemode": "tozero"},
                    "margin": {"t": 26, "b": 56, "l": 56, "r": 20},
                }
            )
            state.ui_demo_timeline_figure = timeline_fig
        else:
            state.ui_demo_timeline_figure = {}

        p_rows = [{"Stage": k.replace("_", " ").title(), "Count": int(v)} for k, v in pipeline_counts.items() if int(v) > 0]
        if p_rows:
            p_df = pd.DataFrame(p_rows)
            p_fig = go.Figure(
                go.Bar(
                    x=p_df["Stage"],
                    y=p_df["Count"],
                    marker_color=mono_colorway[: len(p_df)],
                    text=p_df["Count"],
                    textposition="outside",
                )
            )
            p_fig.update_layout(
                **{
                    **chart_layout,
                    "xaxis": {**chart_layout["xaxis"], "title": "Pipeline Stage"},
                    "yaxis": {**chart_layout["yaxis"], "title": "Cards", "rangemode": "tozero"},
                    "margin": {"t": 26, "b": 56, "l": 56, "r": 20},
                    "showlegend": False,
                }
            )
            state.ui_demo_pipeline_figure = p_fig
        else:
            state.ui_demo_pipeline_figure = {}
    else:
        state.ui_demo_timeline_figure = {}
        state.ui_demo_pipeline_figure = {}

    # Geo Signal Map
    place_counts, unmapped = _build_geo_place_counts(sessions, GEO_CITY_COORDS)
    if place_counts and go is not None:
        map_rows = [
            {"Place": c.title(), "Lat": GEO_CITY_COORDS[c][0], "Lon": GEO_CITY_COORDS[c][1], "Mentions": n}
            for c, n in sorted(place_counts.items(), key=lambda kv: -kv[1])
        ]
        mdf = pd.DataFrame(map_rows)
        lat_values = [float(v) for v in mdf["Lat"]]
        lon_values = [float(v) for v in mdf["Lon"]]
        city_view = _geo_city_view(lat_values, lon_values)
        max_m = max(1, int(mdf["Mentions"].max()))
        sizes = [8 + 24 * (m / max_m) for m in mdf["Mentions"]]
        geo_scale = [
            [0.0, "#F4D8C8"],
            [0.5, chart_layout["colorway"][0]],
            [1.0, chart_layout["colorway"][1]],
        ]
        map_bg = "#F9F4EF"
        map_text = "#2F2A28"
        map_font = {**chart_layout["font"], "color": map_text}
        map_fig = go.Figure(
            go.Scattermap(
                lon=mdf["Lon"],
                lat=mdf["Lat"],
                text=[f"{p}: {m} mention{'s' if m != 1 else ''}" for p, m in zip(mdf["Place"], mdf["Mentions"])],
                mode="markers+text",
                textposition="top center",
                textfont=dict(color=map_text, size=11),
                marker=dict(
                    size=sizes,
                    color=mdf["Mentions"],
                    colorscale=geo_scale,
                    showscale=True,
                    colorbar=dict(
                        title=dict(text="Mentions", font=dict(color=map_text)),
                        thickness=12,
                        bgcolor=map_bg,
                        tickfont=dict(color=map_text),
                        outlinecolor="#E7D4C8",
                    ),
                    opacity=0.94,
                    line=dict(color="#FFF8F2", width=1.8),
                ),
                hovertemplate="%{text}<extra></extra>",
            )
        )
        map_fig.update_layout(
            template="plotly_white",
            paper_bgcolor=map_bg,
            font=map_font,
            margin=dict(t=10, b=10, l=10, r=10),
            map=dict(
                style="carto-positron",
                center=city_view["center"],
                zoom=city_view["zoom"],
            ),
        )
        state.ui_demo_map_figure = map_fig
        state.ui_demo_map_md = (
            f"**{len(mdf)}** mapped location{'s' if len(mdf) != 1 else ''} · "
            f"**{sum(place_counts.values())}** total mentions"
            + (f" · **{unmapped}** unmapped" if unmapped else "")
        )
    else:
        state.ui_demo_map_figure = {}
        state.ui_demo_map_md = (
            f"**{unmapped}** location mention{'s' if unmapped != 1 else ''} detected but not yet mapped."
            if unmapped else
            "No geographic mentions detected. Analyze location-rich text to populate the map."
        )


def _refresh_plotly_playground(state) -> None:
    chart_type = str(getattr(state, "ui_plot_type", "bar") or "bar").strip().lower()
    if chart_type not in {
        "bar",
        "line",
        "scatter",
        "area",
        "pie",
        "box",
        "histogram",
        "heatmap",
        "3d_scatter",
        "surface",
        "candlestick",
        "sankey",
        "polar_radar",
        "treemap",
        "funnel",
        "violin",
        "choropleth",
    }:
        chart_type = "bar"
    state.ui_plot_type = chart_type

    orientation = str(getattr(state, "ui_plot_orientation", "vertical") or "vertical").strip().lower()
    if orientation not in {"vertical", "horizontal"}:
        orientation = "vertical"
    state.ui_plot_orientation = orientation

    barmode = str(getattr(state, "ui_plot_barmode", "group") or "group").strip().lower()
    if barmode not in {"group", "stack", "overlay"}:
        barmode = "group"
    state.ui_plot_barmode = barmode

    trace_mode = str(getattr(state, "ui_plot_trace_mode", "lines+markers") or "lines+markers").strip().lower()
    if trace_mode not in {"lines", "markers", "lines+markers"}:
        trace_mode = "lines+markers"
    state.ui_plot_trace_mode = trace_mode

    palette = str(getattr(state, "ui_plot_palette", "mono") or "mono").strip().lower()
    if palette not in {"mono", "default", "high_contrast"}:
        palette = "mono"
    state.ui_plot_palette = palette

    theme = str(getattr(state, "ui_plot_theme", "app_dark") or "app_dark").strip().lower()
    if theme not in {"app_dark", "plotly_dark", "plotly_white"}:
        theme = "app_dark"
    state.ui_plot_theme = theme

    show_legend = str(getattr(state, "ui_plot_show_legend", "on") or "on").strip().lower() == "on"
    state.ui_plot_show_legend = "on" if show_legend else "off"

    # Context-sensitive control visibility
    uses_orientation = chart_type == "bar"
    uses_barmode = chart_type == "bar"
    uses_trace_mode = chart_type in {"line", "scatter", "area"}
    state.ui_plot_show_orientation = uses_orientation
    state.ui_plot_show_barmode = uses_barmode
    state.ui_plot_show_trace_mode = uses_trace_mode

    option_rows = [
        {"Option": "type", "Value": chart_type, "Description": "Primary chart trace family"},
        {"Option": "palette", "Value": palette, "Description": "Colorway preset"},
        {"Option": "theme", "Value": theme, "Description": "Layout template/background style"},
        {"Option": "showlegend", "Value": str(show_legend).lower(), "Description": "Legend visibility"},
    ]
    if uses_orientation:
        option_rows.insert(1, {"Option": "orientation", "Value": orientation, "Description": "Vertical/horizontal (bar only)"})
    if uses_barmode:
        option_rows.insert(2, {"Option": "barmode", "Value": barmode, "Description": "Group / stack / overlay (bar only)"})
    if uses_trace_mode:
        option_rows.insert(1, {"Option": "mode", "Value": trace_mode, "Description": "Line/marker rendering (line, scatter, area)"})
    state.ui_plot_option_rows = pd.DataFrame(option_rows, columns=["Option", "Value", "Description"])

    if go is None:
        state.ui_plot_playground_figure = {}
        return

    labels = ["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "URL", "IP_ADDRESS"]
    series_a = [34, 21, 17, 12, 9]
    series_b = [19, 16, 12, 14, 7]
    points_x = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    points_y = [12, 18, 15, 22, 19, 14, 17]
    points_z = [9, 14, 13, 11, 16, 12, 10]
    dates = ["2026-03-01", "2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05", "2026-03-06", "2026-03-07"]

    if palette == "mono":
        colors = list(mono_colorway)
    elif palette == "high_contrast":
        colors = ["#7FC97F", "#FDC086", "#BEAED4", "#FFFF99", "#386CB0", "#F0027F"]
    else:
        colors = ["#5B8FF9", "#5AD8A6", "#5D7092", "#F6BD16", "#E8684A", "#6DC8EC"]

    fig = go.Figure()
    orient_flag = "h" if orientation == "horizontal" else "v"

    if chart_type == "bar":
        if orient_flag == "h":
            fig.add_bar(y=labels, x=series_a, name="Current", orientation="h", marker_color=colors[0])
            fig.add_bar(y=labels, x=series_b, name="Previous", orientation="h", marker_color=colors[1])
            x_title, y_title = "Count", "Entity Type"
        else:
            fig.add_bar(x=labels, y=series_a, name="Current", marker_color=colors[0])
            fig.add_bar(x=labels, y=series_b, name="Previous", marker_color=colors[1])
            x_title, y_title = "Entity Type", "Count"
        fig.update_layout(barmode=barmode)
    elif chart_type == "line":
        fig.add_scatter(x=points_x, y=points_y, mode=trace_mode, name="Current", line=dict(color=colors[0], width=2))
        fig.add_scatter(x=points_x, y=points_z, mode=trace_mode, name="Previous", line=dict(color=colors[1], width=2))
        x_title, y_title = "Day", "Detections"
    elif chart_type == "scatter":
        fig.add_scatter(
            x=series_a,
            y=series_b,
            mode=trace_mode,
            name="Entity Clusters",
            marker=dict(size=[16, 14, 12, 10, 9], color=colors[:5]),
            text=labels,
        )
        x_title, y_title = "Current", "Previous"
    elif chart_type == "area":
        fig.add_scatter(x=points_x, y=points_y, mode=trace_mode, name="Current", fill="tozeroy", line=dict(color=colors[0]))
        fig.add_scatter(x=points_x, y=points_z, mode=trace_mode, name="Previous", fill="tozeroy", line=dict(color=colors[1]))
        x_title, y_title = "Day", "Detections"
    elif chart_type == "pie":
        fig.add_pie(labels=labels, values=series_a, hole=0.45, marker=dict(colors=colors[:len(labels)]), textinfo="label+percent")
        x_title, y_title = "", ""
    elif chart_type == "box":
        fig.add_box(y=[78, 81, 76, 90, 72, 84], name="PERSON", marker_color=colors[0], boxpoints="outliers")
        fig.add_box(y=[69, 74, 66, 80, 71, 77], name="EMAIL", marker_color=colors[1], boxpoints="outliers")
        fig.add_box(y=[62, 71, 68, 75, 64, 70], name="PHONE", marker_color=colors[2], boxpoints="outliers")
        x_title, y_title = "Entity Type", "Confidence %"
    elif chart_type == "histogram":
        fig.add_histogram(x=[92, 88, 75, 69, 85, 90, 78, 82, 71, 64, 59, 83], name="Confidence", marker_color=colors[0], nbinsx=8, opacity=0.85)
        x_title, y_title = "Confidence %", "Frequency"
    elif chart_type == "heatmap":
        z = [
            [21, 12, 9, 4],
            [14, 19, 7, 5],
            [9, 11, 15, 6],
            [7, 8, 12, 10],
        ]
        fig.add_heatmap(
            z=z,
            x=["PERSON", "EMAIL", "PHONE", "URL"],
            y=["Spacy", "Regex", "Denylist", "Custom Regex"],
            colorscale="Blues",
            colorbar=dict(title="Count"),
        )
        x_title, y_title = "Entity Type", "Recognizer"
    elif chart_type == "3d_scatter":
        fig.add_scatter3d(
            x=[12, 18, 22, 14, 19, 16, 24],
            y=[4, 7, 5, 9, 8, 6, 10],
            z=[72, 78, 81, 69, 75, 74, 84],
            mode="markers",
            marker=dict(size=8, color=[72, 78, 81, 69, 75, 74, 84], colorscale="Viridis", opacity=0.9),
            text=["Batch A", "Batch B", "Batch C", "Batch D", "Batch E", "Batch F", "Batch G"],
            name="3D points",
        )
        x_title, y_title = "Volume", "Jobs"
    elif chart_type == "surface":
        z = [
            [1, 3, 5, 6, 8],
            [2, 4, 7, 9, 10],
            [3, 5, 8, 11, 12],
            [2, 6, 9, 12, 14],
            [1, 4, 7, 10, 13],
        ]
        fig.add_surface(z=z, colorscale="Cividis", showscale=True, colorbar=dict(title="Risk"))
        x_title, y_title = "Feature X", "Feature Y"
    elif chart_type == "candlestick":
        fig.add_candlestick(
            x=dates,
            open=[14, 15, 13, 16, 17, 16, 18],
            high=[17, 16, 16, 18, 19, 18, 20],
            low=[12, 13, 12, 14, 15, 14, 16],
            close=[15, 14, 15, 17, 16, 17, 19],
            name="Detection volatility",
        )
        x_title, y_title = "Date", "Index"
    elif chart_type == "sankey":
        fig.add_sankey(
            node=dict(
                label=["Input", "Analyzer", "Rule Engine", "Anonymizer", "Export"],
                pad=18,
                thickness=16,
                color=colors[:5],
            ),
            link=dict(
                source=[0, 1, 1, 2, 3],
                target=[1, 2, 3, 3, 4],
                value=[100, 60, 40, 60, 100],
            ),
        )
        x_title, y_title = "", ""
    else:  # polar_radar
        categories = ["Recall", "Precision", "Latency", "Coverage", "Stability"]
        fig.add_scatterpolar(
            r=[82, 78, 65, 88, 80],
            theta=categories,
            fill="toself",
            name="Model A",
            line=dict(color=colors[0]),
        )
        fig.add_scatterpolar(
            r=[76, 74, 72, 84, 77],
            theta=categories,
            fill="toself",
            name="Model B",
            line=dict(color=colors[1]),
        )
        x_title, y_title = "", ""
    # ── new types ──────────────────────────────────────────────────────────────
    if chart_type == "treemap":
        fig = go.Figure(
            go.Treemap(
                labels=["PII Entities", *labels],
                parents=["", *["PII Entities"] * len(labels)],
                values=[0, *series_a],
                marker=dict(
                    colors=[0, *series_a],
                    colorscale="Blues",
                    showscale=True,
                    colorbar=dict(title="Count"),
                ),
                textinfo="label+value+percent root",
                hovertemplate="<b>%{label}</b><br>Count: %{value}<br>Share: %{percentRoot:.1%}<extra></extra>",
            )
        )
        x_title, y_title = "", ""
    elif chart_type == "funnel":
        stages = ["Backlog", "In Progress", "Review", "Done"]
        stage_counts = [42, 28, 16, 11]
        fig = go.Figure(
            go.Funnel(
                y=stages,
                x=stage_counts,
                textinfo="value+percent initial",
                marker=dict(color=colors[:len(stages)]),
                connector=dict(line=dict(color=colors[1], width=1, dash="dot")),
            )
        )
        x_title, y_title = "Cards", "Pipeline Stage"
    elif chart_type == "violin":
        violin_data = {
            "PERSON":        [78, 81, 76, 90, 72, 84, 88, 79, 83, 77, 85, 91],
            "EMAIL_ADDRESS": [69, 74, 66, 80, 71, 77, 82, 70, 75, 68, 79, 83],
            "PHONE_NUMBER":  [62, 71, 68, 75, 64, 70, 74, 65, 69, 63, 72, 78],
        }
        for i, (etype, vals) in enumerate(violin_data.items()):
            fig.add_trace(
                go.Violin(
                    y=vals,
                    name=etype,
                    box_visible=True,
                    meanline_visible=True,
                    fillcolor=colors[i],
                    opacity=0.75,
                    line_color=colors[i],
                    points="all",
                )
            )
        x_title, y_title = "Entity Type", "Confidence %"
    elif chart_type == "choropleth":
        countries = ["USA", "GBR", "DEU", "FRA", "CAN", "AUS", "IND", "BRA", "JPN", "CHN"]
        pii_counts = [340, 190, 160, 140, 130, 110, 95, 80, 75, 60]
        fig = go.Figure(
            go.Choropleth(
                locations=countries,
                z=pii_counts,
                locationmode="ISO-3",
                colorscale="Reds",
                colorbar=dict(title="PII Detections"),
                marker_line_color=chart_layout["xaxis"]["gridcolor"],
                marker_line_width=0.5,
                hovertemplate="<b>%{location}</b><br>Detections: %{z}<extra></extra>",
            )
        )
        fig.update_layout(
            geo=dict(
                showframe=False,
                showcoastlines=True,
                projection_type="natural earth",
                bgcolor=chart_layout["plot_bgcolor"],
                landcolor=chart_layout["paper_bgcolor"],
                coastlinecolor=chart_layout["xaxis"]["gridcolor"],
                countrycolor=chart_layout["xaxis"]["gridcolor"],
            )
        )
        x_title, y_title = "", ""

    layout_kwargs = dict(
        showlegend=show_legend,
        margin={"t": 42, "b": 56, "l": 56, "r": 24},
        title=f"Plotly Playground - {chart_type.replace('_', ' ').title()}",
    )
    if chart_type in {"bar", "line", "scatter", "area", "box", "histogram", "heatmap", "candlestick", "funnel", "violin"}:
        layout_kwargs["xaxis"] = {**chart_layout["xaxis"], "title": x_title}
        layout_kwargs["yaxis"] = {**chart_layout["yaxis"], "title": y_title, "rangemode": "tozero"}
    if chart_type == "3d_scatter":
        layout_kwargs["scene"] = dict(
            xaxis=dict(title=x_title),
            yaxis=dict(title=y_title),
            zaxis=dict(title="Confidence %"),
            bgcolor=chart_layout["plot_bgcolor"],
        )
    if chart_type == "surface":
        layout_kwargs["scene"] = dict(
            xaxis=dict(title=x_title),
            yaxis=dict(title=y_title),
            zaxis=dict(title="Risk score"),
            bgcolor=chart_layout["plot_bgcolor"],
        )
    if chart_type == "polar_radar":
        layout_kwargs["polar"] = dict(radialaxis=dict(visible=True, range=[0, 100]))

    if theme == "app_dark":
        layout_kwargs.update(chart_layout)
        layout_kwargs["colorway"] = colors
    else:
        layout_kwargs["template"] = theme
        layout_kwargs["paper_bgcolor"] = chart_layout["paper_bgcolor"] if theme == "plotly_dark" else "#F6F8FC"
        layout_kwargs["plot_bgcolor"] = chart_layout["plot_bgcolor"] if theme == "plotly_dark" else "#FFFFFF"
        layout_kwargs["font"] = chart_layout["font"] if theme == "plotly_dark" else {"color": "#1F2937", "size": 12}

    fig.update_layout(**layout_kwargs)
    state.ui_plot_playground_figure = fig


def _format_anon_md(text: str) -> str:
    """Convert raw anonymized text into markdown with highlighted replacement tags.

    Turns  <EMAIL_ADDRESS>  →  `EMAIL_ADDRESS`  so the tags render as
    visually distinct code spans in the Taipy markdown renderer.
    """
    return re.sub(r"<([A-Z_]+)>", r"`\1`", text)


def _confidence_band(score_pct: int) -> str:
    if score_pct >= 90:
        return "Very High"
    if score_pct >= 75:
        return "High"
    if score_pct >= 60:
        return "Medium"
    return "Low"


def _qt_rows_from_entities(entities: List[Dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for ent in entities:
        score_pct = int(round(float(ent.get("score", 0) or 0) * 100))
        rows.append(
            {
                "Entity Type": ent.get("entity_type", ""),
                "Text": ent.get("text", ""),
                "Confidence": score_pct,
                "Confidence Band": _confidence_band(score_pct),
                "Span": f"{ent.get('start', '?')}–{ent.get('end', '?')}",
                "Recognizer": ent.get("recognizer", ""),
            }
        )
    return pd.DataFrame(
        rows,
        columns=["Entity Type", "Text", "Confidence", "Confidence Band", "Span", "Recognizer"],
    )


def _qt_summary_from_counts(total: int, counts: Counter) -> str:
    if total <= 0:
        return "No PII detected."
    parts = ", ".join(f"{v}x {k}" for k, v in sorted(counts.items(), key=lambda x: -x[1]))
    return f"Anonymous Studio: {total} entities detected - {parts}"


def _qt_confidence_md(entity_rows: pd.DataFrame) -> str:
    if entity_rows.empty or "Confidence" not in entity_rows.columns:
        return "Confidence profile: N/A"
    conf = entity_rows["Confidence"].astype(int)
    avg = int(round(float(conf.mean()))) if len(conf) else 0
    bands = {}
    for label in ("Very High", "High", "Medium", "Low"):
        bands[label] = int((entity_rows["Confidence Band"] == label).sum())
    dominant = max(bands, key=bands.get) if any(bands.values()) else "N/A"
    return (
        f"Confidence profile: {dominant} | Avg {avg}%  \n"
        f"Very High {bands['Very High']} | High {bands['High']} | "
        f"Medium {bands['Medium']} | Low {bands['Low']}"
    )


def _set_qt_entity_state(state, entities: List[Dict[str, Any]]) -> Counter:
    state.qt_entity_rows = _qt_rows_from_entities(entities)
    counts = Counter(e["entity_type"] for e in entities)
    state.qt_entity_chart = pd.DataFrame(
        sorted(counts.items(), key=lambda x: (-x[1], x[0])),
        columns=["Entity Type", "Count"],
    ) if counts else pd.DataFrame(columns=["Entity Type", "Count"])
    state.qt_entity_chart_visible = bool(counts)
    if state.qt_entity_chart_visible and go is not None:
        qdf = state.qt_entity_chart.sort_values("Count", ascending=True)
        qt_layout = {
            **chart_layout,
            "margin": {"t": 16, "b": 42, "l": 180, "r": 16},
            "xaxis": {**chart_layout["xaxis"], "title": "Count", "dtick": 1},
            "yaxis": {**chart_layout["yaxis"], "automargin": True},
            "bargap": 0.22,
        }
        fig_qt = go.Figure(
            go.Bar(
                x=qdf["Count"],
                y=qdf["Entity Type"],
                orientation="h",
                marker=dict(color=mono_colorway[0]),
                text=[str(int(v)) for v in qdf["Count"]],
                textposition="outside",
                cliponaxis=False,
                hovertemplate="%{y}: %{x} entities<extra></extra>",
            )
        )
        fig_qt.update_layout(**qt_layout, showlegend=False)
        state.qt_entity_figure = fig_qt
    else:
        state.qt_entity_figure = {}
    state.qt_has_entities = bool(entities)
    state.qt_summary = _qt_summary_from_counts(len(entities), counts)
    state.qt_confidence_md = _qt_confidence_md(state.qt_entity_rows)
    state.qt_kpi_total_entities = len(entities)
    state.qt_kpi_total_entities_ticker = str(state.qt_kpi_total_entities)

    if counts:
        state.qt_entity_breakdown_md = ", ".join(
            f"{cnt}x {etype}" for etype, cnt in sorted(counts.items(), key=lambda x: (-x[1], x[0]))
        )
    else:
        state.qt_entity_breakdown_md = "No entities detected."

    if state.qt_entity_rows.empty:
        state.qt_kpi_dominant_band = "N/A"
        state.qt_kpi_avg_confidence = "N/A"
        state.qt_kpi_low_confidence = 0
        state.qt_kpi_dominant_band_ticker = state.qt_kpi_dominant_band
        state.qt_kpi_avg_confidence_ticker = state.qt_kpi_avg_confidence
        state.qt_kpi_low_confidence_ticker = str(state.qt_kpi_low_confidence)
        state.qt_conf_bands_md = "Very High 0 | High 0 | Medium 0 | Low 0"
        return counts

    conf = state.qt_entity_rows["Confidence"].astype(int)
    avg = int(round(float(conf.mean()))) if len(conf) else 0
    band_counts = {}
    for label in ("Very High", "High", "Medium", "Low"):
        band_counts[label] = int((state.qt_entity_rows["Confidence Band"] == label).sum())
    dominant = max(band_counts, key=band_counts.get) if any(band_counts.values()) else "N/A"
    state.qt_kpi_dominant_band = dominant
    state.qt_kpi_avg_confidence = f"{avg}%"
    state.qt_kpi_low_confidence = band_counts["Low"]
    state.qt_kpi_dominant_band_ticker = state.qt_kpi_dominant_band
    state.qt_kpi_avg_confidence_ticker = state.qt_kpi_avg_confidence
    state.qt_kpi_low_confidence_ticker = str(state.qt_kpi_low_confidence)
    state.qt_conf_bands_md = (
        f"Very High {band_counts['Very High']} | High {band_counts['High']} | "
        f"Medium {band_counts['Medium']} | Low {band_counts['Low']}"
    )
    return counts


# ═══════════════════════════════════════════════════════════════════════════════
#  CALLBACKS
# ═══════════════════════════════════════════════════════════════════════════════

def on_init(state):
    _register_live_state(state)
    state.store_status = describe_store_backend()
    state.store_status_label, state.store_status_hover = _store_status_ui(state.store_status)
    state.raw_input_status_label, state.raw_input_status_hover = _raw_input_backend_ui()
    state.spacy_model_sel = get_spacy_model_choice()
    state.spacy_model_lov = get_spacy_model_options()
    state.spacy_status = get_spacy_model_status()
    state.spacy_status_label, state.spacy_status_hover = _spacy_status_ui(state.spacy_status)
    state.job_spacy_model = state.spacy_model_sel
    state.job_spacy_model_lov = list(state.spacy_model_lov)
    current_choice = str(state.spacy_model_sel or "").strip()
    if current_choice and current_choice not in {"auto", "blank"}:
        state.qt_ner_model_sel = f"spaCy/{current_choice}"
    if str(getattr(state, "qt_synth_provider", "faker") or "faker") not in set(state.qt_synth_provider_lov):
        state.qt_synth_provider = "faker"
    _update_pipeline_selected_md(state)
    _refresh_pipeline(state)
    _refresh_appts(state)
    _refresh_audit(state)
    _refresh_dashboard(state)
    _refresh_ui_demo(state)
    _refresh_plotly_playground(state)
    _refresh_job_table(state)
    _sync_active_job_progress(state, load_results_on_done=True)
    _refresh_sessions(state)
    # Pre-populate PII Text page so it's immediately useful
    try:
        ents = engine.analyze(state.qt_input, state.qt_entities, state.qt_threshold)
        state.qt_highlight_md = highlight_md(state.qt_input, ents)
        _set_qt_entity_state(state, ents)
    except Exception:
        pass
    navigate(state, "dashboard")


# ── Navigation ────────────────────────────────────────────────────────────────
def on_menu_action(state, id, payload):
    valid_pages = {"dashboard", "analyze", "jobs", "pipeline", "schedule", "audit", "ui_demo"}

    def _normalize_page(value: Any) -> Optional[str]:
        if not isinstance(value, str):
            return None
        v = value.strip().lower()
        if not v:
            return None
        if v.startswith("/"):
            v = v[1:]
        if v == "":
            return "dashboard"
        return v if v in valid_pages else None

    page = None
    if isinstance(payload, dict):
        args = payload.get("args")
        if isinstance(args, (list, tuple)):
            # Taipy menu callback args can include both previous and new values.
            # Use the last valid page to avoid one-click lag.
            for arg in reversed(args):
                candidate = _normalize_page(arg)
                if candidate:
                    page = candidate
                    break
        if page is None:
            for key in ("value", "new_value", "page"):
                candidate = _normalize_page(payload.get(key))
                if candidate:
                    page = candidate
                    break
    if page is None:
        page = _normalize_page(id)
    if page is None:
        page = "dashboard"
    navigate(state, page)
    if page == "dashboard":
        _refresh_dashboard(state)
    elif page == "analyze":
        _refresh_sessions(state)
    elif page == "jobs":
        _refresh_job_table(state)
    elif page == "pipeline":
        _refresh_pipeline(state)
    elif page == "schedule":
        _refresh_appts(state)
    elif page == "audit":
        _refresh_audit(state)
    elif page == "ui_demo":
        _refresh_ui_demo(state)
        _refresh_plotly_playground(state)


def on_taipy_event(state, event):
    """Broadcast callback for taipy.core events to keep UI monitors current."""
    try:
        _refresh_job_table(state)
        _refresh_dashboard(state)
    except Exception:
        pass
    try:
        ent = str(getattr(event, "entity_type", ""))
        op = str(getattr(event, "operation", ""))
        attr = str(getattr(event, "attribute_name", ""))
        val = str(getattr(event, "attribute_value", ""))
        if "JOB" in ent and "UPDATE" in op and attr == "status" and "FAILED" in val.upper():
            notify(state, "error", "A Taipy job failed. Open Errors / Audit for details.")
    except Exception:
        pass


# ── Global on_change for table selection (single-click) ──────────────────────
_KANBAN_SEL_MAP = {
    "backlog_sel":     "kanban_backlog",
    "in_progress_sel": "kanban_in_progress",
    "review_sel":      "kanban_review",
    "done_sel":        "kanban_done",
    "pipeline_all_sel": "pipeline_all",
}


def _sync_kanban_select_flags(state) -> None:
    selected_card_id = str(getattr(state, "sel_card_id", "") or "")
    for df_name in _KANBAN_SEL_MAP.values():
        df = getattr(state, df_name, None)
        if not isinstance(df, pd.DataFrame) or df.empty or "Select" not in df.columns or "id" not in df.columns:
            continue
        patched = df.copy()
        patched["Select"] = patched["id"].astype(str).eq(selected_card_id)
        setattr(state, df_name, patched)

def _set_selected_card(state, cid: str, notify_user: bool = False) -> bool:
    """Persist selected card metadata; optionally surface a toast for UX clarity."""
    if not cid:
        return False
    c = store.get_card(cid)
    if not c:
        return False
    state.sel_card_id = c.id
    state.sel_card_title = c.title
    state.sel_card_short_id = c.id[:8]
    state.pipeline_card_pick = c.id
    if not getattr(state, "sel_card_source", ""):
        state.sel_card_source = "manual"
    _sync_kanban_select_flags(state)
    _update_pipeline_selected_md(state)
    if notify_user:
        notify(state, "success", f"Selected: {state.sel_card_title} ({state.sel_card_short_id})")
    return True


def _selected_banner_content(state) -> str:
    if state.sel_card_title:
        safe_title = str(state.sel_card_title).replace("*", "\\*").replace("_", "\\_")
        safe_sid = str(state.sel_card_short_id).replace("*", "\\*").replace("_", "\\_")
        return f"Selected: **{safe_title}** · ID **{safe_sid}**"
    return "No card selected. Click or check a row in the board to set the active card."


def _update_pipeline_selected_md(state):
    state.pipeline_selected_md = _selected_banner_content(state)


def _clear_other_card_selection_vars(state, keep_sel_var: str):
    for sel_var in _KANBAN_SEL_MAP.keys():
        if sel_var != keep_sel_var:
            setattr(state, sel_var, [])


def _clear_selected_card(state, clear_selection_vars: bool = True) -> None:
    state.sel_card_id = ""
    state.sel_card_title = ""
    state.sel_card_short_id = ""
    state.sel_card_source = ""
    state.pipeline_card_pick = ""
    if clear_selection_vars:
        for sel_var in _KANBAN_SEL_MAP.keys():
            setattr(state, sel_var, [])
    _sync_kanban_select_flags(state)
    _update_pipeline_selected_md(state)


def _extract_selected_card_id(state, value, df_name: str) -> str:
    """Resolve table selection payload to a card id across Taipy payload shapes."""
    first = value[0] if isinstance(value, list) and value else value
    df = getattr(state, df_name, None)

    def _from_row_index(raw_idx) -> str:
        if df is None or "id" not in df.columns:
            return ""
        if isinstance(raw_idx, str):
            token = raw_idx.strip()
            if token.isdigit():
                raw_idx = int(token)
            else:
                return ""
        if isinstance(raw_idx, numbers.Integral) and not isinstance(raw_idx, bool):
            idx = int(raw_idx)
            if 0 <= idx < len(df):
                cid = df.iloc[idx].get("id", "")
                return str(cid) if cid else ""
        return ""

    if isinstance(first, dict):
        cid = first.get("id") or first.get("row_id")
        if cid:
            return str(cid)
        for key in ("index", "idx", "row"):
            parsed = _from_row_index(first.get(key))
            if parsed:
                return parsed
        return ""

    if isinstance(first, str):
        token = first.strip()
        if not token:
            return ""
        if df is not None and "id" in df.columns:
            if (df["id"] == token).any():
                return token
            # Support short-id payloads.
            matches = df[df["id"].astype(str).str.startswith(token)]
            if len(matches) == 1:
                return str(matches.iloc[0]["id"])
        parsed = _from_row_index(token)
        if parsed:
            return parsed
        return ""

    parsed = _from_row_index(first)
    return parsed


def _apply_selection_from_var(state, sel_var: str, value, notify_user: bool = False) -> bool:
    df_name = _KANBAN_SEL_MAP.get(sel_var)
    if not df_name:
        return False
    normalized_value = value if isinstance(value, list) else ([value] if value is not None else [])
    cid = _extract_selected_card_id(state, normalized_value, df_name)
    if not cid:
        return False
    setattr(state, sel_var, normalized_value)
    _clear_other_card_selection_vars(state, sel_var)
    state.sel_card_source = sel_var
    return _set_selected_card(state, cid, notify_user=notify_user)


def _infer_selection_source(state, cid: str) -> str:
    for sel_var, df_name in _KANBAN_SEL_MAP.items():
        df = getattr(state, df_name, None)
        if df is not None and not df.empty and "id" in df.columns and (df["id"] == cid).any():
            return sel_var
    return ""

def on_change(state, var_name, value):
    if var_name in {"dash_report_mode", "dash_time_window"}:
        _refresh_dashboard(state)
        return
    if var_name == "spacy_model_sel":
        on_spacy_model_change(state, var_name, value)
        return
    if var_name in _KANBAN_SEL_MAP:
        _apply_selection_from_var(state, var_name, value)


def on_card_selection_change(state, var_name, value):
    if var_name in _KANBAN_SEL_MAP:
        _apply_selection_from_var(state, var_name, value)


def _get_table_row_from_action_payload(df: pd.DataFrame, payload) -> Dict[str, Any]:
    """Extract a table row dict from Taipy on_action payload (or legacy payload)."""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return {}
    if isinstance(payload, dict):
        idx = payload.get("index")
        if isinstance(idx, numbers.Integral):
            row = None
            if idx in df.index:
                row = df.loc[idx]
            else:
                i = int(idx)
                if 0 <= i < len(df):
                    row = df.iloc[i]
            if row is not None:
                return row.to_dict() if hasattr(row, "to_dict") else {}
        return {}
    # Backward-compatible path for older payload shapes.
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return payload[0]
    return {}


def on_card_pick(state, var_name, value):
    """Explicit row-pick callback for tables so selection is discoverable."""
    if var_name in _KANBAN_SEL_MAP:
        df_name = _KANBAN_SEL_MAP[var_name]
        payload = value if isinstance(value, dict) else {}
        normalized_value = (
            [int(payload["index"])]
            if isinstance(payload, dict) and isinstance(payload.get("index"), numbers.Integral)
            else (value if isinstance(value, list) else ([value] if value is not None else []))
        )
        cid = _extract_selected_card_id(state, normalized_value, df_name)
        # Toggle off when the same row is clicked again in the same board column.
        if (
            cid
            and str(getattr(state, "sel_card_id", "") or "") == str(cid)
            and str(getattr(state, "sel_card_source", "") or "") == var_name
        ):
            _clear_selected_card(state, clear_selection_vars=True)
            return
        _apply_selection_from_var(state, var_name, normalized_value)
        return
    for _sel_var, _df_name in _KANBAN_SEL_MAP.items():
        if _df_name == var_name:
            df = getattr(state, _df_name, pd.DataFrame())
            row = _get_table_row_from_action_payload(df, value)
            cid = str(row.get("id", "") or "")
            if cid:
                source = _infer_selection_source(state, cid)
                if source:
                    _set_selected_card(state, cid)
                    state.sel_card_source = source
                else:
                    _set_selected_card(state, cid)
            return


def _get_selected_card_id(state) -> str:
    """Read all Kanban selection variables and return the card ID of the
    currently highlighted row.  Taipy updates `selected` on single-click
    even though on_change may not fire — so we read them lazily here
    when an action button is pressed.
    """
    # First, honor explicit selection if still valid.
    if _set_selected_card(state, getattr(state, "sel_card_id", "")):
        return state.sel_card_id

    # Then try active source (prevents ghost selection from other tables).
    source = getattr(state, "sel_card_source", "")
    if source in _KANBAN_SEL_MAP:
        if _apply_selection_from_var(state, source, getattr(state, source, [])):
            return state.sel_card_id

    # Then try board columns before "All Cards".
    for sel_var in ("backlog_sel", "in_progress_sel", "review_sel", "done_sel", "pipeline_all_sel"):
        if _apply_selection_from_var(state, sel_var, getattr(state, sel_var, [])):
            return state.sel_card_id

    # Safe fallback: when only one card exists, target it automatically.
    df = getattr(state, "pipeline_all", None)
    if isinstance(df, pd.DataFrame) and len(df) == 1 and "id" in df.columns:
        cid = str(df.iloc[0]["id"])
        state.pipeline_all_sel = [0]
        _clear_other_card_selection_vars(state, "pipeline_all_sel")
        state.sel_card_source = "pipeline_all_sel"
        _set_selected_card(state, cid)
        return cid

    return ""


def on_card_select(state):
    cid = state.sel_card_id if store.get_card(state.sel_card_id) else _get_selected_card_id(state)
    if not cid:
        notify(state, "warning", "Select a card row first.")
        return
    _set_selected_card(state, cid, notify_user=True)


def on_pipeline_select_mode_change(state, var_name=None, value=None):
    mode = str(value if value is not None else getattr(state, "pipeline_select_mode", "highlight") or "highlight")
    mode = mode.strip().lower()
    if mode not in {"highlight", "picker"}:
        mode = "highlight"
    state.pipeline_select_mode = mode
    if mode == "picker" and not getattr(state, "pipeline_card_pick", ""):
        _refresh_pipeline_picker(state, store.list_cards())


def on_pipeline_pick_card(state):
    cid = str(getattr(state, "pipeline_card_pick", "") or "").strip()
    if not cid:
        notify(state, "warning", "No card available in picker.")
        return
    state.sel_card_source = "picker"
    if not _set_selected_card(state, cid, notify_user=True):
        notify(state, "warning", "Selected card is no longer available. Refreshing board.")
        _refresh_pipeline(state)


def _select_from_board_column(state, sel_var: str, label: str):
    current = getattr(state, sel_var, [])
    if _apply_selection_from_var(state, sel_var, current, notify_user=True):
        return
    notify(state, "warning", f"Select a row in {label} first.")


def on_select_backlog_card(state):
    _select_from_board_column(state, "backlog_sel", "Backlog")


def on_select_in_progress_card(state):
    _select_from_board_column(state, "in_progress_sel", "In Progress")


def on_select_review_card(state):
    _select_from_board_column(state, "review_sel", "Review")


def on_select_done_card(state):
    _select_from_board_column(state, "done_sel", "Done")


# ── Quick-text PII ────────────────────────────────────────────────────────────
def on_qt_analyze(state):
    if not state.qt_input.strip():
        notify(state, "warning", "Enter some text first.")
        return
    allowlist = [w.strip() for w in state.qt_allowlist_text.split(",") if w.strip()]
    denylist  = [w.strip() for w in state.qt_denylist_text.split(",") if w.strip()]
    ents = engine.analyze(
        state.qt_input,
        state.qt_entities,
        state.qt_threshold,
        allowlist=allowlist or None,
        denylist=denylist or None,
    )
    state.qt_highlight_md = highlight_md(state.qt_input, ents)
    _set_qt_entity_state(state, ents)
    if ents:
        notify(state, "warning", f"{len(ents)} PII entities detected.")
    else:
        notify(state, "success", "No PII detected.")


def on_qt_ner_model_change(state, var_name=None, value=None):
    selected = str(value if value is not None else getattr(state, "qt_ner_model_sel", "") or "").strip()
    if not selected:
        selected = "spaCy/en_core_web_lg"
    state.qt_ner_model_sel = selected

    if selected.lower().startswith("spacy/"):
        state.qt_ner_note = ""
        spacy_choice = selected.split("/", 1)[1].strip() or "auto"
        on_spacy_model_change(state, value=spacy_choice)
        return

    if selected == "Other":
        custom = str(getattr(state, "qt_ner_other_model", "") or "").strip()
        if not custom:
            state.qt_ner_note = "Set a custom model name under 'Other model name'."
            notify(state, "warning", state.qt_ner_note)
            return
        state.qt_ner_note = ""
        on_spacy_model_change(state, value=custom)
        return

    # Presidio Streamlit parity: expose package presets, but this build uses spaCy runtime.
    state.qt_ner_note = (
        f"Preset '{selected}' selected. This Taipy build currently runs spaCy in-process; "
        "using auto spaCy model resolution."
    )
    notify(state, "info", state.qt_ner_note)
    on_spacy_model_change(state, value="auto")


def on_qt_anonymize(state):
    if not state.qt_input.strip():
        notify(state, "warning", "Enter some text first.")
        return
    allowlist = [w.strip() for w in state.qt_allowlist_text.split(",") if w.strip()]
    denylist  = [w.strip() for w in state.qt_denylist_text.split(",") if w.strip()]
    t0 = time.perf_counter()
    qt_operator = str(getattr(state, "qt_operator", "replace") or "replace").strip().lower()
    operator_for_engine = "replace" if qt_operator == "synthesize" else qt_operator
    res = engine.anonymize(
        state.qt_input,
        state.qt_entities,
        operator_for_engine,
        state.qt_threshold,
        allowlist=allowlist or None,
        denylist=denylist or None,
    )
    final_text = res.anonymized_text
    if qt_operator == "synthesize":
        synth_cfg = SyntheticConfig(
            provider=str(getattr(state, "qt_synth_provider", "faker") or "faker"),
            model=str(getattr(state, "qt_synth_model", "gpt-4o-mini") or "gpt-4o-mini"),
            api_key=str(getattr(state, "qt_synth_api_key", "") or ""),
            api_base=str(getattr(state, "qt_synth_api_base", "") or ""),
            deployment_id=str(getattr(state, "qt_synth_deployment", "") or ""),
            api_version=str(getattr(state, "qt_synth_api_version", "2024-08-01-preview") or "2024-08-01-preview"),
            temperature=float(getattr(state, "qt_synth_temperature", 0.2) or 0.2),
            max_tokens=max(128, int(getattr(state, "qt_synth_max_tokens", 800) or 800)),
        )
        synth = synthesize_from_anonymized_text(res.anonymized_text, synth_cfg)
        final_text = synth.text
        state.qt_synth_note = synth.message
    proc_ms = (time.perf_counter() - t0) * 1000.0
    state.qt_last_proc_ms = round(proc_ms, 2)
    state.qt_anonymized_raw = final_text
    state.qt_anonymized     = _format_anon_md(final_text)
    state.qt_highlight_md = highlight_md(state.qt_input, res.entities)
    _set_qt_entity_state(state, res.entities)
    store.log_user_action("user", "pii.anonymize.text", "session", _uid(),
              f"{res.total_found} entities via '{qt_operator}' ({proc_ms:.0f} ms)")
    _refresh_audit(state)
    if qt_operator == "synthesize":
        if state.qt_synth_note:
            notify(state, "info", state.qt_synth_note)
        notify(state, "success", f"{res.total_found} entities synthesized.")
    else:
        notify(state, "success", f"{res.total_found} entities anonymized.")


def on_qt_load_sample(state):
    state.qt_input = (
        "Patient: Jane Doe, DOB: 03/15/1982\n"
        "SSN: 987-65-4321 | Email: jane.doe@hospital.org\n"
        "Phone: +1-800-555-0199 | Card: 4111-1111-1111-1111\n"
        "Physician: Dr. Robert Kim | IP: 192.168.1.101\n"
        "Passport: A12345678 | License: B2345678"
    )
    notify(state, "info", "Sample medical record loaded.")


def on_spacy_model_change(state, var_name=None, value=None):
    global engine

    requested = str(value if value is not None else state.spacy_model_sel or "auto").strip() or "auto"
    state.spacy_model_sel = requested

    resolved_model, has_ner, status_text = set_spacy_model(requested)
    engine = get_engine()
    state.spacy_status = status_text
    state.spacy_status_label, state.spacy_status_hover = _spacy_status_ui(status_text)
    state.spacy_model_lov = get_spacy_model_options()
    state.job_spacy_model_lov = list(state.spacy_model_lov)
    if not state.job_spacy_model:
        state.job_spacy_model = state.spacy_model_sel

    if requested in {"auto", "blank"}:
        if requested == "auto":
            notify(state, "success", f"NLP model set to auto (resolved: {resolved_model}).")
        else:
            notify(state, "warning", "NLP model set to blank (regex only).")
        return

    if resolved_model != requested:
        notify(
            state,
            "warning",
            f"Model '{requested}' not available; using '{resolved_model}'.",
        )
    elif has_ner:
        notify(state, "success", f"NLP model switched to {resolved_model}.")
    else:
        notify(state, "warning", "Selected model is blank (regex only).")

    lower_resolved = str(resolved_model or "").strip().lower()
    if lower_resolved and lower_resolved != "auto" and lower_resolved not in {"blank", "en_blank", "blank_en"}:
        state.qt_ner_model_sel = f"spaCy/{resolved_model}"


def on_qt_download_anonymized(state):
    if not state.qt_anonymized_raw:
        notify(state, "warning", "Run Anonymize first.")
        return
    content = state.qt_anonymized_raw.encode("utf-8")
    download(state, content=content, name="anonymized_output.txt")
    notify(state, "success", "Anonymized output downloaded.")


def on_qt_download_entities(state):
    if state.qt_entity_rows is None or state.qt_entity_rows.empty:
        notify(state, "warning", "No entities to export.")
        return
    csv_bytes = state.qt_entity_rows.to_csv(index=False).encode("utf-8")
    download(state, content=csv_bytes, name="entity_evidence.csv")
    notify(state, "success", "Entity evidence downloaded.")


def on_qt_settings_open(state):
    state.qt_settings_open = True


def on_qt_settings_close(state):
    state.qt_settings_open = False


def on_store_settings_open(state):
    state.store_backend_sel = get_store_backend_mode()
    state.store_mongo_uri = os.environ.get("MONGODB_URI", "").strip()
    state.store_duckdb_path = os.environ.get(
        "ANON_DUCKDB_PATH",
        os.path.join(tempfile.gettempdir(), "anon_studio.duckdb"),
    ).strip()
    state.store_settings_msg = ""
    state.store_settings_open = True


def on_store_settings_close(state):
    state.store_settings_open = False


def on_store_apply(state):
    global store, store_status
    import store as _store_mod
    prev_backend = (os.environ.get("ANON_STORE_BACKEND", "memory") or "memory").strip()
    prev_uri = os.environ.get("MONGODB_URI", "").strip()
    prev_duckdb = os.environ.get("ANON_DUCKDB_PATH", "").strip()
    backend = (state.store_backend_sel or "memory").strip().lower()
    uri     = (state.store_mongo_uri or "").strip()
    duckdb_path = (state.store_duckdb_path or "").strip()

    if backend == "mongo" and not uri:
        state.store_settings_msg = "⚠ MongoDB URI is required (e.g. mongodb://localhost:27017/anon_studio)."
        return
    if backend == "duckdb" and not duckdb_path:
        state.store_settings_msg = "⚠ DuckDB path is required (e.g. /tmp/anon_studio.duckdb)."
        return

    os.environ["ANON_STORE_BACKEND"] = backend
    if uri:
        os.environ["MONGODB_URI"] = uri
    elif backend != "mongo":
        os.environ.pop("MONGODB_URI", None)
    if duckdb_path:
        os.environ["ANON_DUCKDB_PATH"] = duckdb_path
    elif backend != "duckdb":
        os.environ.pop("ANON_DUCKDB_PATH", None)

    _store_mod._reset_store()
    try:
        # Rebind global store instance so all callbacks use the selected backend.
        store = _store_mod.get_store()
        status_text = _store_mod.describe_store_backend()
        store_status = status_text
        state.store_status = status_text
        state.store_status_label, state.store_status_hover = _store_status_ui(status_text)
        state.store_settings_open = False
        _refresh_pipeline(state)
        _refresh_appts(state)
        _refresh_audit(state)
        _refresh_dashboard(state)
        _refresh_sessions(state)
        notify(state, "success", f"Store backend set: {state.store_status}")
    except ModuleNotFoundError as exc:
        # Optional backend dependency missing — keep previous backend and show install hint.
        os.environ["ANON_STORE_BACKEND"] = prev_backend
        if prev_uri:
            os.environ["MONGODB_URI"] = prev_uri
        else:
            os.environ.pop("MONGODB_URI", None)
        if prev_duckdb:
            os.environ["ANON_DUCKDB_PATH"] = prev_duckdb
        else:
            os.environ.pop("ANON_DUCKDB_PATH", None)
        _store_mod._reset_store()
        store = _store_mod.get_store()
        status_text = _store_mod.describe_store_backend()
        store_status = status_text
        state.store_status = status_text
        state.store_status_label, state.store_status_hover = _store_status_ui(status_text)
        state.store_backend_sel = get_store_backend_mode()
        if backend == "mongo":
            state.store_settings_msg = (
                f"⚠ pymongo is not installed. Kept previous backend. "
                f"Run: pip install 'pymongo[srv]>=4.7' ({exc})"
            )
        elif backend == "duckdb":
            state.store_settings_msg = (
                f"⚠ duckdb is not installed. Kept previous backend. "
                f"Run: pip install 'duckdb>=1.0' ({exc})"
            )
        else:
            state.store_settings_msg = f"⚠ Backend dependency missing: {exc}"
    except Exception as exc:
        # Connection/setup failure: keep the previous backend instead of forcing memory.
        os.environ["ANON_STORE_BACKEND"] = prev_backend
        if prev_uri:
            os.environ["MONGODB_URI"] = prev_uri
        else:
            os.environ.pop("MONGODB_URI", None)
        if prev_duckdb:
            os.environ["ANON_DUCKDB_PATH"] = prev_duckdb
        else:
            os.environ.pop("ANON_DUCKDB_PATH", None)
        _store_mod._reset_store()
        store = _store_mod.get_store()
        status_text = _store_mod.describe_store_backend()
        store_status = status_text
        state.store_status = status_text
        state.store_status_label, state.store_status_hover = _store_status_ui(status_text)
        state.store_backend_sel = get_store_backend_mode()
        state.store_settings_msg = f"⚠ Connection failed. Kept previous backend: {exc}"


def on_qt_clear(state):
    state.qt_input = ""
    state.qt_anonymized = ""
    state.qt_anonymized_raw = ""
    state.qt_highlight_md = ""
    state.qt_entity_rows = pd.DataFrame(
        columns=["Entity Type", "Text", "Confidence", "Confidence Band", "Span", "Recognizer"]
    )
    state.qt_entity_chart = pd.DataFrame(columns=["Entity Type", "Count"])
    state.qt_entity_figure = {}
    state.qt_entity_chart_visible = False
    state.qt_has_entities = False
    state.qt_summary = ""
    state.qt_confidence_md = "Confidence profile: N/A"
    state.qt_entity_breakdown_md = "No entities detected."
    state.qt_conf_bands_md = "Very High 0 | High 0 | Medium 0 | Low 0"
    state.qt_kpi_total_entities = 0
    state.qt_kpi_dominant_band = "N/A"
    state.qt_kpi_avg_confidence = "N/A"
    state.qt_kpi_low_confidence = 0
    state.qt_kpi_total_entities_ticker = "0"
    state.qt_kpi_dominant_band_ticker = "N/A"
    state.qt_kpi_avg_confidence_ticker = "N/A"
    state.qt_kpi_low_confidence_ticker = "0"
    state.qt_session_saved = False


def _refresh_sessions(state):
    sessions = store.list_sessions()
    rows = [
        {
            "ID":       s.id[:8],
            "Title":    s.title[:50],
            "Operator": s.operator,
            "Entities": sum(s.entity_counts.values()) if s.entity_counts else 0,
            "Created":  s.created_at[5:16].replace("T", " "),
        }
        for s in sessions
    ]
    state.qt_sessions_data = pd.DataFrame(rows, columns=["ID", "Title", "Operator", "Entities", "Created"])


def on_qt_save_session(state):
    if not state.qt_anonymized_raw:
        notify(state, "warning", "Run Anonymize first before saving.")
        return
    title = (state.qt_input.strip().splitlines()[0][:50] or "Untitled Session")
    counts: Dict[str, int] = {}
    for _, row in state.qt_entity_rows.iterrows():
        counts[row["Entity Type"]] = counts.get(row["Entity Type"], 0) + 1
    session = PIISession(
        title=title,
        original_text=state.qt_input,
        anonymized_text=state.qt_anonymized_raw,
        entities=state.qt_entity_rows.to_dict("records"),
        entity_counts=counts,
        operator=state.qt_operator,
        source_type="text",
        processing_ms=float(getattr(state, "qt_last_proc_ms", 0.0) or 0.0),
    )
    store.add_session(session)
    store.log_user_action("user", "session.save", "session", session.id,
                          f"Saved session '{title}' ({len(counts)} entity types)")
    state.qt_session_saved = True
    _refresh_sessions(state)
    _refresh_dashboard(state)
    notify(state, "success", f"Session saved (ID: {session.id[:8]})")


def on_file_upload(state, action, payload):
    """Called when user uploads a file — cache raw bytes outside Taipy state."""
    _MAX_BYTES = 50 * 1024 * 1024  # 50 MB
    try:
        payload = payload or {}
        # Docs-aligned path source: bound file_selector content value.
        path = getattr(state, "job_file_content", None)
        if isinstance(path, (list, tuple)) and path:
            path = path[0]
        if not isinstance(path, str) or not path:
            # Fallback for runtime variants that still provide path in payload.
            path = payload.get("path") or payload.get("file")
        if not path:
            return  # spurious / cancel callback — ignore silently
        # Validate path is within the OS temp directory (path traversal guard)
        real = os.path.realpath(path)
        tmp  = os.path.realpath(tempfile.gettempdir())
        if not real.startswith(tmp):
            notify(state, "error", "Invalid upload path rejected.")
            return
        if not os.path.exists(real):
            return
        size = os.path.getsize(real)
        if size > _MAX_BYTES:
            notify(state, "error",
                   f"File too large ({size / 1_048_576:.1f} MB). "
                   f"Maximum is {_MAX_BYTES // 1_048_576} MB.")
            return
        with open(real, "rb") as f:
            raw = f.read()
        name = payload.get("name", os.path.basename(real))
        sid = get_state_id(state)
        import hashlib
        file_hash = hashlib.sha256(raw).hexdigest()
        _FILE_CACHE[sid] = {"bytes": raw, "name": name}
        state.job_file_content = name   # non-None flag (str is JSON-safe)
        state.job_file_name = name
        state.job_file_hash = file_hash
        state.job_file_art  = _drunken_bishop(file_hash, name)
        notify(state, "success", f"{name} ready.")
    except Exception as e:
        (_log.exception("upload_error"), notify(state, "error", "File upload failed. Check the file and try again."))[1]


def _bg_submit_job(raw_df, config):
    """
    Runs in a background thread (via invoke_long_callback).
    Creates the Scenario, writes DataNodes, submits to Orchestrator.
    Returns (taipy_scenario_id, job_id, submission_id) so _bg_job_done can update the card.
    """
    # Apply runtime MongoDB write batch size override before DataNode write.
    batch = config.get("mongo_write_batch")
    if batch and isinstance(batch, int) and batch >= 500:
        cc.MONGO_WRITE_BATCH = batch
    sc, sub = cc.submit_job(raw_df, config)
    _SCENARIOS[config["job_id"]] = sc
    sub_id = str(getattr(sub, "id", "") or "")
    if sub_id:
        _SUBMISSION_IDS[config["job_id"]] = sub_id
    return sc.id, config["job_id"], sub_id


def _sync_active_job_progress(state, load_results_on_done: bool = True) -> bool:
    """Refresh active job progress state from registry and repaint monitor/widgets."""
    jid = state.active_job_id
    if not jid:
        return False

    prog = _progress_from_sources(jid)
    sc = _SCENARIOS.get(jid)
    taipy_status = _resolve_job_status(getattr(sc, "id", None) if sc is not None else None)
    terminal_done = {"done", "skipped"}
    terminal_error = {"failed", "cancelled", "abandoned"}
    active_states = {"submitted", "blocked", "pending", "running"}
    msg_lower = str(prog.get("message", "") or "").lower()
    has_error_signal = any(token in msg_lower for token in ("rejected", "failed", "error"))

    # Reconcile UI progress with authoritative taipy job status.
    if taipy_status in terminal_done:
        if str(prog.get("status", "") or "").lower() == "error" or has_error_signal:
            prog = {
                **prog,
                "pct": float(prog.get("pct", state.job_progress_pct or 0) or 0),
                "processed": int(prog.get("processed", 0) or 0),
                "total": int(prog.get("total", state.job_expected_rows or 0) or 0),
                "message": prog.get("message") or "Run failed.",
                "status": "error",
                "updated_at": time.time(),
            }
        else:
            prog = {
                **prog,
                "pct": 100,
                "processed": int(prog.get("processed", state.job_expected_rows or 0) or 0),
                "total": int(prog.get("total", state.job_expected_rows or 0) or 0),
                "message": prog.get("message") or "Run completed.",
                "status": "done",
                "updated_at": time.time(),
            }
    elif taipy_status in terminal_error:
        prog = {
            **prog,
            "pct": float(prog.get("pct", state.job_progress_pct or 0) or 0),
            "processed": int(prog.get("processed", 0) or 0),
            "total": int(prog.get("total", state.job_expected_rows or 0) or 0),
            "message": prog.get("message") or f"Run {taipy_status}.",
            "status": "error",
            "updated_at": time.time(),
        }
    elif taipy_status in active_states:
        msg = str(prog.get("message", "") or "")
        if (not msg) or msg.lower().startswith("queuing job for"):
            if taipy_status == "running":
                msg = "Run in progress…"
            else:
                msg = f"Taipy status: {taipy_status}."
        prog = {
            **prog,
            "pct": float(prog.get("pct", state.job_progress_pct or 0) or 0),
            "processed": int(prog.get("processed", 0) or 0),
            "total": int(prog.get("total", state.job_expected_rows or 0) or 0),
            "message": msg,
            "status": "running",
            "updated_at": time.time(),
        }
    if prog:
        prog = _persist_progress(jid, prog)

    state.job_progress_pct = prog.get("pct", 0)
    state.job_progress_msg = prog.get("message", state.job_progress_msg or "")
    state.job_progress_status = prog.get(
        "status", state.job_progress_status or ("running" if state.job_is_running else "idle")
    )
    state.job_expected_rows = int(prog.get("total", state.job_expected_rows or 0) or 0)

    if load_results_on_done and state.job_progress_status in ("done", "error") and state.job_is_running:
        state.job_is_running = False
        _load_job_results(state, jid)

    _refresh_job_health(state)
    _refresh_job_table(state)
    _refresh_dashboard(state)
    return True


def _bg_job_done(state, status, result):
    """Called by invoke_long_callback on periodic ticks and completion."""
    if isinstance(status, int):
        _sync_active_job_progress(state, load_results_on_done=True)
        return
    if status is False:
        state.job_is_running = False
        state.job_progress_status = "error"
        state.job_submission_status = "Failed"
        if not state.job_progress_msg:
            state.job_progress_msg = "Background submission failed."
        if state.active_job_id:
            _persist_progress(
                state.active_job_id,
                {
                    "status": "error",
                    "message": state.job_progress_msg,
                    "updated_at": time.time(),
                },
            )
        _refresh_job_health(state)
        _refresh_job_table(state)
        _refresh_dashboard(state)
        notify(state, "error", "Job submission failed in background task.")
        return

    if result and isinstance(result, tuple) and len(result) >= 2:
        taipy_sc_id, job_id = result[0], result[1]
        sub_id = str(result[2]) if len(result) > 2 and result[2] else ""
        if sub_id:
            _SUBMISSION_IDS[job_id] = sub_id
            if state.active_job_id == job_id:
                state.job_active_submission_id = sub_id
                state.job_submission_status = "Submitted"
        for c in store.list_cards():
            if getattr(c, "job_id", None) == job_id:
                store.update_card(c.id, scenario_id=taipy_sc_id)
    _sync_active_job_progress(state, load_results_on_done=True)
    notify(state, "success", "Job submitted to Orchestrator.")


def on_submission_status_change(state, submittable, details):
    """Fires when the scenario widget detects a submission status change.

    Wired via <|{orchestration_scenario}|scenario|on_submission_change=on_submission_status_change|>.
    Runs on the GUI thread — safe to write state directly.
    """
    sub_status = details.get("submission_status", "")
    if sub_status == "COMPLETED":
        notify(state, "success", "Pipeline run completed.")
        state.refresh("orchestration_scenario")
        _sync_active_job_progress(state, load_results_on_done=True)
        _refresh_job_table(state)
        _refresh_dashboard(state)
    elif sub_status == "FAILED":
        notify(state, "error", "Pipeline run failed.")
        state.refresh("orchestration_scenario")
        _refresh_job_table(state)
    elif sub_status == "CANCELED":
        notify(state, "warning", "Pipeline run canceled.")
        state.refresh("orchestration_scenario")
        _refresh_job_table(state)

def on_submit_job(state):
    """Validate inputs, parse the file, then fire invoke_long_callback."""
    # Resolve bytes from per-session cache (preferred) or Taipy's bound variable (fallback)
    sid = get_state_id(state)
    raw_bytes, _slot = resolve_upload_bytes(state, _FILE_CACHE, sid)
    if not raw_bytes:
        notify(state, "warning", "Upload a CSV or Excel file first.")
        return

    fname = (_slot.get("name") or state.job_file_name or "")
    lowered = str(fname or "").lower()
    job_id = new_job_id()
    compute_backend = str(getattr(state, "job_compute_backend", "auto") or "auto")
    try:
        dask_min_rows = int(getattr(state, "job_dask_min_rows", 250000) or 250000)
    except Exception:
        dask_min_rows = 250000
    try:
        mongo_write_batch = max(500, int(getattr(state, "job_mongo_write_batch", 5000) or 5000))
    except Exception:
        mongo_write_batch = 5000
    config = build_job_config(
        job_id=job_id,
        operator=state.job_operator,
        entities=state.job_entities,
        threshold=state.job_threshold,
        chunk_size=state.job_chunk_size,
        spacy_model=state.job_spacy_model,
        compute_backend=compute_backend,
        dask_min_rows=dask_min_rows,
    )
    config["mongo_write_batch"] = mongo_write_batch
    raw_input_payload: Any
    row_count = 0

    if lowered.endswith(".csv"):
        # Out-of-core path: stage CSV file and let task read it directly.
        row_count = max(0, int(raw_bytes.count(b"\n")) - 1)
        if row_count <= 0:
            notify(state, "warning", "The uploaded CSV appears empty.")
            return
        try:
            csv_path = stage_csv_upload_for_job(job_id, fname or "upload.csv", raw_bytes)
        except Exception as e:
            (_log.exception("stage_csv_error"), notify(state, "error", "Could not prepare file for processing. Try re-uploading."))[1]
            return
        config["input_csv_path"] = csv_path
        config["input_format"] = "csv"
        config["cleanup_input_path"] = True
        config["row_count_hint"] = row_count
        raw_input_payload = {"source": "csv_path", "path": csv_path, "name": fname}
    else:
        # Excel path keeps the in-memory dataframe route.
        try:
            raw_df = parse_upload_to_df(raw_bytes, fname)
        except ValueError as e:
            notify(state, "error", str(e))
            return
        except Exception as e:
            notify(state, "error", f"Could not parse file: {e}")
            return

        if raw_df.empty:
            notify(state, "warning", "The uploaded file is empty.")
            return
        row_count = len(raw_df)
        raw_input_payload = raw_df

    # Track progress state
    state.active_job_id       = job_id
    state.job_is_running      = True
    state.job_active_submission_id = ""
    state.job_submission_status = "Submitting"
    state.job_progress_pct    = 0
    state.job_progress_msg    = f"Queuing job for {row_count:,} rows…"
    state.job_progress_status = "running"
    state.job_expected_rows   = row_count
    state.job_active_started  = time.time()
    state.job_view_tab        = "Results"
    state.job_quality_md = build_queue_quality_md(
        row_count=row_count,
        operator=state.job_operator,
        entity_count=len(state.job_entities),
    )
    # Seed initial queue progress so the monitor has totals before worker starts.
    _persist_progress(job_id, {
        "pct": 0.0,
        "processed": 0,
        "total": row_count,
        "message": state.job_progress_msg,
        "status": "running",
        "ts": datetime.now().isoformat(timespec="seconds"),
        "updated_at": time.time(),
    })

    # Link to a Kanban card if selected
    if state.job_card_id:
        linked_card = store.get_card(state.job_card_id)
        store.update_card(state.job_card_id,
                          status="in_progress",
                          job_id=job_id)
        store.log_user_action("user", "pipeline.link_job", "card", state.job_card_id,
                  f"Linked job {job_id}",
                  severity=_priority_to_severity(getattr(linked_card, "priority", "medium") if linked_card else "medium"))

    store.log_user_action("user", "job.submit", "job", job_id,
              f"{row_count:,} rows · {state.job_operator} · "
              f"{len(state.job_entities)} entity types")

    invoke_long_callback(
        state,
        user_function=_bg_submit_job,
        user_function_args=[raw_input_payload, config],
        user_status_function=_bg_job_done,
        period=_JOB_UI_POLL_MS,
    )

    # Release the upload slot — file bytes no longer needed in memory
    _FILE_CACHE.pop(sid, None)

    _refresh_job_table(state)
    notify(state, "info", f"Job {job_id[:8]} submitted — "
           f"{row_count:,} rows queued.")


def on_poll_progress(state):
    """Manual refresh — user clicks 'Refresh Progress' button."""
    if not _sync_active_job_progress(state, load_results_on_done=True):
        notify(state, "info", "No active job to poll.")


def on_job_adv_open(state):
    state.job_adv_open = True


def on_job_adv_close(state):
    state.job_adv_open = False


def _load_job_results(state, jid: str):
    sc = _SCENARIOS.get(jid)
    if not sc:
        return
    try:
        try:
            cfg = sc.job_config.read() or {}
            staged_path = str(cfg.get("input_csv_path", "") or "").strip()
            if staged_path and os.path.exists(staged_path):
                os.remove(staged_path)
        except Exception:
            pass
        stats_data = sc.job_stats.read()
        anon_df    = sc.anon_output.read()
        state.stats_entity_rows = build_entity_stats_df(stats_data)
        if not state.stats_entity_rows.empty and go is not None:
            sdf = state.stats_entity_rows.sort_values("Count", ascending=True)
            fig_stats = go.Figure(
                go.Bar(
                    x=sdf["Count"],
                    y=sdf["Entity Type"],
                    orientation="h",
                    marker=dict(color=mono_colorway[0]),
                    text=[str(int(v)) for v in sdf["Count"]],
                    textposition="outside",
                    cliponaxis=False,
                    hovertemplate="%{y}: %{x} detections<extra></extra>",
                )
            )
            fig_stats.update_layout(**stats_entity_chart_layout, showlegend=False, bargap=0.2)
            state.stats_entity_chart_figure = fig_stats
        else:
            state.stats_entity_chart_figure = {}
        state.job_quality_md = build_result_quality_md(stats_data, anon_df)
        if anon_df is not None and not anon_df.empty:
            preview = anon_df.head(50)
            state.preview_data         = preview
            state.preview_cols         = list(preview.columns)
            state.download_ready       = True
            state.download_scenario_id = jid
            state.download_rows        = len(anon_df)
            state.download_cols        = len(anon_df.columns)
        # Move linked card to review
        for c in store.list_cards():
            if getattr(c, 'job_id', None) == jid and c.status == "in_progress":
                store.update_card(c.id, status="review")
                store.log_user_action("system", "pipeline.auto_move", "card", c.id,
                          f"Auto-moved to review after job {jid[:8]} completed",
                          severity=_priority_to_severity(getattr(c, "priority", "medium")))
        _refresh_pipeline(state)
        _refresh_audit(state)
        _refresh_job_errors(state)
    except Exception as e:
        (_log.exception("load_results_error"), notify(state, "error", "Could not load job results. Refresh and try again."))[1]


def on_download(state):
    """Export the anonymized DataFrame for the active job as a CSV download."""
    jid = state.download_scenario_id or state.active_job_id
    sc = _SCENARIOS.get(jid)
    if not sc:
        notify(state, "warning", "No results available yet.")
        return
    try:
        anon_df = sc.anon_output.read()
        if anon_df is None or anon_df.empty:
            notify(state, "warning", "Results are empty.")
            return
        csv_bytes = anon_df.to_csv(index=False).encode("utf-8")
        fname = f"anonymized_{jid[:8]}.csv"
        download(state, content=csv_bytes, name=fname)
        store.log_user_action("user", "job.download", "job", jid,
                              f"Downloaded {len(anon_df):,} rows as {fname}")
        _refresh_audit(state)
        # Clean up scenario DataNode files (anon_output, job_stats, job_config)
        # now that the user has the CSV. raw_input is in-memory (already gone).
        try:
            tc.delete(sc.id)
            _SCENARIOS.pop(jid, None)
            _SUBMISSION_IDS.pop(jid, None)
            clear_progress(jid)
        except Exception:
            pass  # cleanup is best-effort; don't fail the download
    except Exception as e:
        (_log.exception("download_error"), notify(state, "error", "Download failed. Try again or contact support."))[1]


def on_select_job(state, var_name, value):
    row = _get_table_row_from_action_payload(state.job_table_data, value)
    jid = str(row.get("job_id", "") or "")
    if not jid:
        return
    state.active_job_id = jid
    state.job_view_tab = "Results"
    state.job_active_submission_id = str(_SUBMISSION_IDS.get(jid, "") or "")
    state.job_submission_status = "—"
    prog = _progress_from_sources(jid)
    state.job_progress_pct    = prog.get("pct", 0)
    state.job_progress_msg    = prog.get("message", "")
    state.job_progress_status = prog.get("status", "")
    state.job_expected_rows   = int(prog.get("total", 0) or 0)
    if state.job_progress_status != "running":
        state.job_active_started = 0.0
    _sync_active_job_progress(state, load_results_on_done=True)


def on_job_cancel(state):
    """Cancel the latest cancellable taipy job for the selected scenario job."""
    jid = state.active_job_id
    if not jid:
        notify(state, "warning", "Select a job in Job History first.")
        return
    sc = _SCENARIOS.get(jid)
    if not sc:
        notify(state, "warning", "Selected job scenario is not available.")
        return
    jobs = _jobs_for_scenario_id(sc.id)
    if not jobs:
        notify(state, "info", "No taipy jobs found for this scenario.")
        return

    target = latest_cancellable_job(jobs)
    if target is None:
        notify(state, "info", "No cancellable job found (already finished).")
        return

    try:
        tp.cancel_job(target)
        _persist_progress(jid, {
            "status": "error",
            "message": "Cancelled by user",
            "updated_at": time.time(),
        })
        store.log_user_action("user", "job.cancel", "job", jid, f"Canceled taipy job {target.id}")
        _refresh_job_table(state)
        _refresh_dashboard(state)
        _refresh_audit(state)
        notify(state, "warning", f"Cancellation requested for job {jid[:8]}.")
    except Exception as e:
        (_log.exception("cancel_job_error"), notify(state, "error", "Could not cancel the job."))[1]


def on_job_remove(state):
    """Delete completed/failed taipy jobs and local tracking for selected job."""
    jid = state.active_job_id
    if not jid:
        notify(state, "warning", "Select a job in Job History first.")
        return
    sc = _SCENARIOS.get(jid)
    if not sc:
        notify(state, "warning", "Selected job scenario is not available.")
        return
    jobs = _jobs_for_scenario_id(sc.id)
    if not all_jobs_done_like(jobs):
        notify(state, "warning", "Job still active. Cancel it first or wait until completion.")
        return

    try:
        for j in jobs:
            try:
                tp.delete_job(j, force=True)
            except Exception:
                pass
        try:
            latest_sub = tp.get_latest_submission(sc)
            if latest_sub:
                tp.delete(latest_sub.id)
        except Exception:
            pass
        try:
            tc.delete(sc.id)
        except Exception:
            pass
        _SCENARIOS.pop(jid, None)
        _SUBMISSION_IDS.pop(jid, None)
        clear_progress(jid)
        if state.active_job_id == jid:
            state.active_job_id = ""
            state.job_active_submission_id = ""
            state.job_submission_status = "—"
            state.job_progress_pct = 0
            state.job_progress_msg = ""
            state.job_progress_status = ""
            state.job_is_running = False
            state.job_expected_rows = 0
        state.download_ready = False
        state.download_scenario_id = ""
        state.preview_data = pd.DataFrame()
        state.stats_entity_rows = pd.DataFrame(columns=["Entity Type", "Count"])
        state.stats_entity_chart_figure = {}
        store.log_user_action("user", "job.remove", "job", jid, "Removed completed job entities")
        _refresh_job_table(state)
        _refresh_dashboard(state)
        _refresh_audit(state)
        notify(state, "success", f"Removed job {jid[:8]} from history.")
    except Exception as e:
        (_log.exception("remove_job_error"), notify(state, "error", "Could not remove the job."))[1]


def on_whatif_compare(state):
    selected_ids = list(dict.fromkeys(state.whatif_scenarios_sel or []))
    if len(selected_ids) < 2:
        notify(state, "warning", "Select at least two scenarios for comparison.")
        return

    scenario_by_id = {sc.id: sc for sc in _SCENARIOS.values()}
    scenarios = [scenario_by_id[sid] for sid in selected_ids if sid in scenario_by_id]
    if len(scenarios) < 2:
        notify(state, "warning", "Selected scenarios are no longer available.")
        return

    # Primary path: use Taipy scenario comparator output from core_config comparators.
    comparison_df = pd.DataFrame()
    try:
        comparisons = tp.compare_scenarios(*scenarios)
        comparison_df = _extract_whatif_comparison_df(comparisons)
    except Exception:
        comparison_df = pd.DataFrame()

    # Fallback path: build manual summary if comparator output is unavailable.
    if comparison_df.empty:
        rows = []
        for sc in scenarios:
            stats_data = {}
            try:
                stats_data = sc.job_stats.read() or {}
            except Exception:
                pass
            processed = int(stats_data.get("processed_rows", 0) or 0)
            entities = int(stats_data.get("total_entities", 0) or 0)
            rows.append({
                "Scenario": sc.id[:12],
                "Processed Rows": processed,
                "Entities": entities,
                "Entities / Row": round((entities / processed), 3) if processed else 0.0,
            })
        comparison_df = pd.DataFrame(
            rows,
            columns=["Scenario", "Processed Rows", "Entities", "Entities / Row"],
        )

    # Normalize columns for stable rendering in current table/chart controls.
    if "Scenarios" in comparison_df.columns and "Scenario" not in comparison_df.columns:
        comparison_df = comparison_df.rename(columns={"Scenarios": "Scenario"})
    if "scenario" in comparison_df.columns and "Scenario" not in comparison_df.columns:
        comparison_df = comparison_df.rename(columns={"scenario": "Scenario"})
    if "Scenario" not in comparison_df.columns and len(comparison_df.columns) > 0:
        comparison_df = comparison_df.rename(columns={comparison_df.columns[0]: "Scenario"})
    if "Entities" not in comparison_df.columns:
        for candidate in ("total_entities", "Total Entities", "entity_count", "Entity Count"):
            if candidate in comparison_df.columns:
                comparison_df = comparison_df.rename(columns={candidate: "Entities"})
                break

    state.whatif_compare_data = comparison_df
    if "Scenario" in comparison_df.columns and "Entities" in comparison_df.columns:
        chart_df = comparison_df[["Scenario", "Entities"]].copy()
        chart_df["Scenario"] = chart_df["Scenario"].astype(str)
        chart_df["Entities"] = pd.to_numeric(chart_df["Entities"], errors="coerce").fillna(0)
        state.whatif_compare_chart = chart_df
        if not chart_df.empty and go is not None:
            fig_whatif = go.Figure(
                go.Bar(
                    x=chart_df["Scenario"],
                    y=chart_df["Entities"],
                    marker=dict(color=mono_colorway[0]),
                    text=[str(int(v)) for v in chart_df["Entities"]],
                    textposition="outside",
                    cliponaxis=False,
                    hovertemplate="%{x}: %{y} entities<extra></extra>",
                )
            )
            fig_whatif.update_layout(
                **chart_layout,
                margin={"t": 20, "b": 72, "l": 48, "r": 14},
                xaxis={**chart_layout["xaxis"], "title": "Scenario", "tickangle": -20, "automargin": True},
                yaxis={**chart_layout["yaxis"], "title": "Entities", "rangemode": "tozero", "dtick": 1},
                showlegend=False,
            )
            state.whatif_compare_figure = fig_whatif
        else:
            state.whatif_compare_figure = {}
    else:
        state.whatif_compare_chart = pd.DataFrame(columns=["Scenario", "Entities"])
        state.whatif_compare_figure = {}

    if not comparison_df.empty:
        top = (
            state.whatif_compare_chart.sort_values("Entities", ascending=False).iloc[0]
            if not state.whatif_compare_chart.empty else None
        )
        if top is not None:
            state.whatif_compare_md = (
                f"Compared **{len(comparison_df)}** scenarios. Highest entity volume: "
                f"**{top['Scenario']}** with **{int(top['Entities']):,}** detections."
            )
        else:
            state.whatif_compare_md = f"Compared **{len(comparison_df)}** scenarios."
        state.whatif_compare_has_data = True
    else:
        state.whatif_compare_md = "No comparable stats available for selected scenarios."
        state.whatif_compare_has_data = False

    # Drive the native scenario_comparator widget.
    state.comparator_scenarios = scenarios


def on_promote_primary(state):
    """Promote the currently selected orchestration_scenario to primary for its cycle."""
    sc = state.orchestration_scenario
    if sc is None:
        notify(state, "warning", "Select a scenario in the Task Orchestration Interface first.")
        return
    try:
        tc.set_primary(sc)
        label = str(getattr(sc, "id", ""))[:12]
        notify(state, "success", f"Scenario {label} set as primary for its cycle.")
        _refresh_sdm(state)
    except Exception as e:
        (_log.exception("promote_scenario_error"), notify(state, "error", "Could not set primary scenario."))[1]


# ── Pipeline / Kanban ─────────────────────────────────────────────────────────
def on_card_new(state):
    state.card_id_edit = ""; state.card_title_f   = ""
    state.card_desc_f  = ""; state.card_status_f  = "backlog"
    state.card_assign_f = ""; state.card_priority_f = "medium"
    state.card_labels_f = ""; state.card_attest_f   = ""
    state.card_session_f = "(none)"
    state.card_session_opts = ["(none)"] + [
        f"{s.id[:8]} — {s.title[:35]}" for s in store.list_sessions()
    ]
    state.card_form_open = True


def on_card_save(state):
    if not state.card_title_f.strip():
        notify(state, "error", "Title is required."); return
    labels = [l.strip() for l in state.card_labels_f.split(",") if l.strip()]
    # Resolve selected session: "(none)" or "abc12345 — title"
    sel = state.card_session_f or "(none)"
    new_session_id = None if sel == "(none)" else sel.split(" — ")[0].strip()
    if state.card_id_edit:
        existing = store.get_card(state.card_id_edit)
        store.update_card(state.card_id_edit,
                          title=state.card_title_f, description=state.card_desc_f,
                          status=state.card_status_f, assignee=state.card_assign_f,
                          priority=state.card_priority_f, labels=labels,
                          attestation=state.card_attest_f,
                          session_id=new_session_id)
        store.log_user_action("user", "pipeline.update", "card", state.card_id_edit,
                  f"Updated '{state.card_title_f}'",
                  severity=_priority_to_severity(state.card_priority_f))        # Write SESSION_ATTACHED only when session actually changed
        if new_session_id and (not existing or existing.session_id != new_session_id):
            # Prevent duplicate: check no other card already holds this session
            all_cards = store.list_cards()
            already = any(
                c.id != state.card_id_edit and c.session_id == new_session_id
                for c in all_cards
            )
            if already:
                notify(state, "warning", "That session is already attached to another card.")
                return
            store.log_user_action("user", "session.attach", "card", state.card_id_edit,
                      f"Session {new_session_id} attached to '{state.card_title_f}'",
                      severity=_priority_to_severity(state.card_priority_f))
        notify(state, "success", "Card updated.")
    else:
        c = PipelineCard(title=state.card_title_f, description=state.card_desc_f,
                         status=state.card_status_f, assignee=state.card_assign_f,
                         priority=state.card_priority_f, labels=labels,
                         attestation=state.card_attest_f,
                         session_id=new_session_id)
        store.add_card(c)
        if new_session_id:
            store.log_user_action("user", "session.attach", "card", c.id,
                      f"Session {new_session_id} attached to '{state.card_title_f}'",
                      severity=_priority_to_severity(state.card_priority_f))
        notify(state, "success", f"Card '{state.card_title_f}' created.")
    state.card_form_open = False
    _refresh_pipeline(state)
    _refresh_audit(state)
    _refresh_dashboard(state)


def on_card_cancel(state):
    state.card_form_open = False


def on_card_edit(state):
    cid = _get_selected_card_id(state)
    if not cid:
        notify(state, "warning", "Select a card first."); return
    c = store.get_card(cid)
    if not c:
        return
    state.card_id_edit   = c.id;    state.card_title_f    = c.title
    state.card_desc_f    = c.description
    state.card_status_f  = c.status; state.card_assign_f  = c.assignee
    state.card_priority_f = c.priority
    state.card_labels_f  = ", ".join(c.labels)
    state.card_attest_f  = c.attestation
    sessions = store.list_sessions()
    state.card_session_opts = ["(none)"] + [
        f"{s.id[:8]} — {s.title[:35]}" for s in sessions
    ]
    if c.session_id:
        match = next((s for s in sessions if s.id.startswith(c.session_id[:8])), None)
        state.card_session_f = f"{c.session_id[:8]} — {match.title[:35]}" if match else "(none)"
    else:
        state.card_session_f = "(none)"
    state.card_form_open = True


def on_card_forward(state):
    cid = _get_selected_card_id(state)
    if not cid:
        notify(state, "warning", "Select a card."); return
    c = store.get_card(cid)
    if not c:
        notify(state, "warning", "Card not found."); return
    order = ["backlog", "in_progress", "review", "done"]
    try:
        idx = order.index(c.status)
    except ValueError:
        idx = 0
    if idx < len(order) - 1:
        store.update_card(cid, status=order[idx + 1])
        notify(state, "success", f"→ {order[idx+1].replace('_',' ').title()}")
        _refresh_pipeline(state); _refresh_audit(state); _refresh_dashboard(state)
    else:
        notify(state, "info", "Already in Done.")


def on_card_back(state):
    cid = _get_selected_card_id(state)
    if not cid:
        notify(state, "warning", "Select a card."); return
    c = store.get_card(cid)
    if not c:
        notify(state, "warning", "Card not found."); return
    order = ["backlog", "in_progress", "review", "done"]
    try:
        idx = order.index(c.status)
    except ValueError:
        idx = len(order) - 1
    if idx > 0:
        store.update_card(cid, status=order[idx - 1])
        notify(state, "success", f"← {order[idx-1].replace('_',' ').title()}")
        _refresh_pipeline(state); _refresh_audit(state); _refresh_dashboard(state)
    else:
        notify(state, "info", "Already in Backlog.")


def on_card_delete(state):
    cid = _get_selected_card_id(state)
    if not cid:
        notify(state, "warning", "Select a card."); return
    store.delete_card(cid)
    _clear_selected_card(state, clear_selection_vars=True)
    notify(state, "success", "Card deleted.")
    _refresh_pipeline(state); _refresh_audit(state); _refresh_dashboard(state)


def on_attest_open(state):
    cid = _get_selected_card_id(state)
    if not cid:
        notify(state, "warning", "Select a card."); return
    state.attest_cid = cid
    state.attest_note = ""; state.attest_by = ""
    state.attest_open = True


def on_attest_confirm(state):
    if not state.attest_by.strip():
        notify(state, "error", "Name required."); return
    card = store.get_card(state.attest_cid)
    if not card:
        notify(state, "error", "Card not found."); return

    attested_by = state.attest_by.strip()
    attested_at = _now()
    attestation_note = (state.attest_note or "").strip()
    payload = build_attestation_payload(
        card=card,
        attested_by=attested_by,
        attested_at=attested_at,
        attestation_note=attestation_note,
    )
    sig = sign_attestation_payload(payload)
    if signature_required() and not sig.signed:
        notify(state, "error", f"Attestation signature required: {sig.error}"); return

    store.update_card(
        state.attest_cid,
        attested=True,
        attested_by=attested_by,
        attested_at=attested_at,
        attestation=attestation_note,
        attestation_sig_alg=sig.algorithm if sig.signed else "",
        attestation_sig_key_id=sig.key_id,
        attestation_sig=sig.signature_b64,
        attestation_sig_public_key=sig.public_key_b64,
        attestation_sig_payload=sig.payload_json,
        attestation_sig_payload_hash=sig.payload_hash,
        attestation_sig_verified=bool(sig.verified),
        attestation_sig_error=sig.error,
    )
    state.attest_open = False
    if sig.signed:
        notify(state, "success", f"Attestation recorded and signed ({sig.algorithm}, key {sig.key_id}).")
    else:
        notify(state, "warning", f"Attestation recorded without signature: {sig.error}")
    _refresh_pipeline(state); _refresh_audit(state); _refresh_dashboard(state)


def on_attest_cancel(state):
    state.attest_open = False


def on_card_history(state):
    """Open the per-card audit trail dialog for the selected card."""
    cid = _get_selected_card_id(state)
    if not cid:
        notify(state, "warning", "Select a card first."); return
    all_audit = store.list_audit(limit=1000)
    rows = [
        {"Time": e.timestamp[11:19], "Action": e.action,
         "Actor": e.actor, "Details": (e.details or "")[:80]}
        for e in all_audit if e.resource_id == cid
    ]
    state.card_audit_data = pd.DataFrame(
        rows or [{"Time": "—", "Action": "No history yet", "Actor": "", "Details": ""}],
        columns=["Time", "Action", "Actor", "Details"],
    )
    state.card_audit_open = True


def on_card_history_close(state):
    state.card_audit_open = False


# ── Schedule ──────────────────────────────────────────────────────────────────
def on_appt_new(state):
    state.appt_id_edit = ""; state.appt_title_f = "PII Review"
    state.appt_desc_f  = ""; state.appt_date_f  = None
    state.appt_time_f  = "10:00"; state.appt_dur_f = 30
    state.appt_att_f   = ""; state.appt_card_f   = ""
    state.appt_status_f = "scheduled"
    state.appt_form_open = True


def on_appt_save(state):
    if not state.appt_title_f.strip():
        notify(state, "error", "Title required."); return
    if not state.appt_date_f:
        notify(state, "error", "Date required."); return
    # appt_date_f is a datetime from the date picker
    d = state.appt_date_f
    date_str = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
    sf = f"{date_str}T{state.appt_time_f}:00"
    atts = [a.strip() for a in state.appt_att_f.split(",") if a.strip()]
    if state.appt_id_edit:
        store.update_appointment(state.appt_id_edit,
                          title=state.appt_title_f, description=state.appt_desc_f,
                          scheduled_for=sf, duration_mins=state.appt_dur_f,
                          attendees=atts,
                          pipeline_card_id=state.appt_card_f or None,
                          status=state.appt_status_f)
        notify(state, "success", "Appointment updated.")
    else:
        a = Appointment(title=state.appt_title_f, description=state.appt_desc_f,
                        scheduled_for=sf, duration_mins=state.appt_dur_f,
                        attendees=atts,
                        pipeline_card_id=state.appt_card_f or None)
        store.add_appointment(a)
        notify(state, "success", f"'{a.title}' scheduled.")
    state.appt_form_open = False
    _refresh_appts(state); _refresh_audit(state); _refresh_dashboard(state)


def on_appt_cancel(state):
    state.appt_form_open = False


def on_appt_select(state, var_name, value):
    row = _get_table_row_from_action_payload(state.appt_table, value)
    aid = str(row.get("id", "") or "")
    if aid:
        state.sel_appt_id = aid


def on_appt_edit(state):
    aid = state.sel_appt_id
    if not aid:
        notify(state, "warning", "Select an appointment."); return
    a = store.get_appointment(aid)
    if not a:
        return
    parts = a.scheduled_for.split("T")
    state.appt_id_edit  = a.id; state.appt_title_f = a.title
    state.appt_desc_f   = a.description
    try:
        state.appt_date_f = datetime.fromisoformat(parts[0]) if parts and parts[0] else None
    except (ValueError, TypeError):
        state.appt_date_f = None
    state.appt_time_f   = parts[1][:5] if len(parts) > 1 else "10:00"
    state.appt_dur_f    = a.duration_mins
    state.appt_att_f    = ", ".join(a.attendees)
    state.appt_card_f   = a.pipeline_card_id or ""
    state.appt_status_f = a.status
    state.appt_form_open = True


def on_appt_delete(state):
    aid = state.sel_appt_id
    if not aid:
        notify(state, "warning", "Select an appointment."); return
    store.delete_appointment(aid)
    state.sel_appt_id = ""
    notify(state, "success", "Deleted.")
    _refresh_appts(state); _refresh_audit(state); _refresh_dashboard(state)


# ── Audit ─────────────────────────────────────────────────────────────────────
def on_audit_filter(state):
    _refresh_audit(state)

def on_audit_clear(state):
    state.audit_search = ""; state.audit_sev = "all"
    _refresh_audit(state)


# ── Dashboard ────────────────────────────────────────────────────────────────
def on_dash_filters_change(state, var_name=None, value=None):
    _refresh_dashboard(state)


def on_refresh_dashboard(state):
    _refresh_dashboard(state)
    _refresh_pipeline(state)
    _refresh_appts(state)
    _refresh_audit(state)
    _refresh_job_table(state)
    notify(state, "info", "Dashboard refreshed.")


def on_ui_demo_filters_change(state, var_name=None, value=None):
    if isinstance(var_name, str) and value is not None and hasattr(state, var_name):
        setattr(state, var_name, value)
    _refresh_ui_demo(state)
    _refresh_plotly_playground(state)


def on_ui_demo_refresh(state):
    _refresh_ui_demo(state)
    _refresh_plotly_playground(state)
    notify(state, "info", "Plotly view refreshed.")


def on_dash_go_analyze(state):
    navigate(state, "analyze")
    _refresh_sessions(state)


def _demo_seed_fallback_entities(text: str) -> List[Dict[str, Any]]:
    """Deterministic fallback entities for dashboard demo seeding."""
    specs = [
        ("Jane Doe", "PERSON"),
        ("03/15/1982", "DATE_TIME"),
        ("987-65-4321", "US_SSN"),
        ("jane.doe@hospital.org", "EMAIL_ADDRESS"),
        ("+1-800-555-0199", "PHONE_NUMBER"),
        ("4111-1111-1111-1111", "CREDIT_CARD"),
        ("Dr. Robert Kim", "PERSON"),
        ("192.168.1.101", "IP_ADDRESS"),
        ("Seattle WA", "LOCATION"),
        ("Austin TX", "LOCATION"),
        ("A12345678", "US_PASSPORT"),
        ("B2345678", "US_DRIVER_LICENSE"),
    ]
    entities: List[Dict[str, Any]] = []
    lower_text = text.lower()
    used_until: Dict[str, int] = {}
    for needle, entity_type in specs:
        token = needle.lower()
        start_from = used_until.get(token, 0)
        start = lower_text.find(token, start_from)
        if start < 0:
            start = lower_text.find(token)
        if start < 0:
            continue
        end = start + len(needle)
        used_until[token] = end
        entities.append(
            {
                "entity_type": entity_type,
                "text": text[start:end],
                "score": 0.99,
                "start": start,
                "end": end,
                "recognizer": "fallback_seed",
            }
        )
    entities.sort(key=lambda e: int(e.get("start", 0)))
    return entities


def _demo_seed_fallback_anonymized(text: str, entities: List[Dict[str, Any]], operator: str) -> str:
    """Apply lightweight fallback anonymization from deterministic entities."""
    op = str(operator or "replace").strip().lower()
    anon_text = text
    for ent in sorted(entities, key=lambda e: int(e.get("start", 0)), reverse=True):
        start = int(ent.get("start", -1))
        end = int(ent.get("end", -1))
        etype = str(ent.get("entity_type", "PII") or "PII")
        if start < 0 or end <= start or end > len(anon_text):
            continue
        if op == "redact":
            replacement = ""
        elif op == "mask":
            replacement = "*" * max(4, min(20, end - start))
        elif op == "hash":
            replacement = f"<{etype}_HASH>"
        else:
            replacement = f"<{etype}>"
        anon_text = anon_text[:start] + replacement + anon_text[end:]
    return anon_text


def _seed_demo_texts():
    """Return a list of (title, text) pairs for bulk demo seeding.

    Uses Faker when available for name/address variety; falls back to
    hard-coded values so the function never raises.
    """
    try:
        from faker import Faker
        fk = Faker()
        Faker.seed(42)

        def _person():  return fk.name()
        def _email():   return fk.email()
        def _phone():   return fk.phone_number()
        def _ssn():     return fk.ssn()
        def _dob():     return fk.date_of_birth(minimum_age=25, maximum_age=70).strftime("%m/%d/%Y")
        def _city():    return fk.city()
        def _ip():      return fk.ipv4_private()
        def _card():    return "4111-1111-1111-1111"
        def _iban():    return "GB29NWBK60161331926819"
    except Exception:
        def _person():  return "Jane Doe"
        def _email():   return "jane.doe@example.com"
        def _phone():   return "+1-800-555-0199"
        def _ssn():     return "987-65-4321"
        def _dob():     return "03/15/1982"
        def _city():    return "Seattle, WA"
        def _ip():      return "192.168.1.101"
        def _card():    return "4111-1111-1111-1111"
        def _iban():    return "GB29NWBK60161331926819"

    return [
        (
            "Medical Record",
            (
                f"Patient: {_person()}, DOB: {_dob()}\n"
                f"SSN: {_ssn()} | Email: {_email()}\n"
                f"Phone: {_phone()} | Card: {_card()}\n"
                f"Physician: Dr. {_person()} | IP: {_ip()}\n"
                f"Facility: {_city()} Medical Center\n"
                f"Passport: A12345678 | License: B2345678"
            ),
        ),
        (
            "HR Personnel File",
            (
                f"Employee: {_person()} | DOB: {_dob()}\n"
                f"SSN: {_ssn()} | Email: {_email()}\n"
                f"Phone: {_phone()} | Driver License: GA-9876543\n"
                f"Manager: {_person()} | Office: {_city()}"
            ),
        ),
        (
            "Financial Statement",
            (
                f"Account holder: {_person()} | DOB: {_dob()}\n"
                f"IBAN: {_iban()} | Card: {_card()}\n"
                f"Phone: {_phone()} | Email: {_email()}\n"
                f"SSN: {_ssn()} | Branch: {_city()}"
            ),
        ),
        (
            "Insurance Claim",
            (
                f"Claimant: {_person()} | Passport: US-PASS-A87654321\n"
                f"Phone: {_phone()} | Email: {_email()}\n"
                f"Provider: {_city()} Health Insurance | IP: {_ip()}\n"
                f"DOB: {_dob()}"
            ),
        ),
        (
            "Legal Brief",
            (
                f"Client: {_person()} | Email: {_email()}\n"
                f"Phone: {_phone()} | SSN: {_ssn()}\n"
                f"DOB: {_dob()} | Domicile: {_city()}\n"
                f"Passport: B98765432 | Bank acct: 001234567890"
            ),
        ),
        (
            "Customer Support Ticket",
            (
                f"Customer: {_person()} | Account: 0987654321\n"
                f"Email: {_email()} | Phone: {_phone()}\n"
                f"Card: {_card()} | IP: {_ip()}\n"
                f"City: {_city()} | DOB: {_dob()}"
            ),
        ),
        (
            "Research Consent Form",
            (
                f"Participant: {_person()} | Study ID: 2025-MED-447\n"
                f"Email: {_email()} | Phone: {_phone()}\n"
                f"DOB: {_dob()} | SSN: {_ssn()}\n"
                f"Institution: {_city()} University Medical Center"
            ),
        ),
        (
            "Vendor Contract",
            (
                f"Vendor contact: {_person()} | Tax ID: 11-2345678\n"
                f"Email: {_email()} | Phone: {_phone()}\n"
                f"IBAN: {_iban()} | IP: {_ip()}\n"
                f"Registered city: {_city()}"
            ),
        ),
    ]


def on_dash_seed_demo(state):
    """Seed one deterministic session so empty dashboard charts populate instantly."""
    state.qt_input = (
        "Patient: Jane Doe, DOB: 03/15/1982\n"
        "SSN: 987-65-4321 | Email: jane.doe@hospital.org\n"
        "Phone: +1-800-555-0199 | Card: 4111-1111-1111-1111\n"
        "Physician: Dr. Robert Kim | IP: 192.168.1.101\n"
        "Facility: Seattle Medical Center, Seattle WA\n"
        "Referral office: Austin Health Hub, Austin TX\n"
        "Passport: A12345678 | License: B2345678"
    )
    operator = getattr(state, "qt_operator", "replace")
    threshold = float(getattr(state, "qt_threshold", 0.35) or 0.35)
    ents_cfg = getattr(state, "qt_entities", ALL_ENTITIES)

    entities: List[Dict[str, Any]] = []
    anonymized = state.qt_input
    used_fallback = False
    proc_ms = 0.0
    try:
        t0 = time.perf_counter()
        res = engine.anonymize(state.qt_input, ents_cfg, operator, threshold)
        proc_ms = (time.perf_counter() - t0) * 1000.0
        entities = list(getattr(res, "entities", []) or [])
        anonymized = str(getattr(res, "anonymized_text", "") or state.qt_input)
    except Exception:
        used_fallback = True

    if not entities:
        used_fallback = True
        entities = _demo_seed_fallback_entities(state.qt_input)
        anonymized = _demo_seed_fallback_anonymized(state.qt_input, entities, operator)

    state.qt_anonymized_raw = anonymized
    state.qt_anonymized = _format_anon_md(anonymized)
    state.qt_highlight_md = highlight_md(state.qt_input, entities)
    counts = _set_qt_entity_state(state, entities)

    session = PIISession(
        title="Demo medical record",
        original_text=state.qt_input,
        anonymized_text=anonymized,
        entities=state.qt_entity_rows.to_dict("records"),
        entity_counts=dict(counts),
        operator=operator,
        source_type="text",
        processing_ms=round(proc_ms, 2),
    )
    try:
        store.add_session(session)
        store.log_user_action(
            "user",
            "session.save",
            "session",
            session.id,
            "Seeded demo session from dashboard",
        )
    except Exception as exc:
        state.qt_session_saved = False
        notify(
            state,
            "error",
            "Demo session could not be saved. If Mongo is selected, confirm it is reachable or switch Store to In Memory. "
            f"({type(exc).__name__})",
        )
        return

    state.qt_session_saved = True
    _refresh_sessions(state)
    _refresh_dashboard(state)
    _refresh_ui_demo(state)
    _refresh_plotly_playground(state)
    _refresh_audit(state)
    if used_fallback:
        notify(state, "warning", f"Demo session generated with fallback detector ({session.id[:8]}).")
    else:
        notify(state, "success", f"Demo session generated ({session.id[:8]}).")


# ═══════════════════════════════════════════════════════════════════════════════
#  PAGE DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════════

pages = PAGES
gui = Gui(pages=pages, css_file="app.css")
gui.load_config({"title": "Anonymous Studio"})

# ═══════════════════════════════════════════════════════════════════════════════
#  LAUNCH
# ═══════════════════════════════════════════════════════════════════════════════
def run_app():
    orchestrator = None
    taipy_host = os.environ.get("TAIPY_HOST", "").strip()
    taipy_port = (os.environ.get("TAIPY_PORT", "") or os.environ.get("PORT", "")).strip()

    def _env_flag(*names: str, default: bool = False) -> bool:
        truthy = {"1", "true", "yes", "on"}
        falsy = {"0", "false", "no", "off"}
        for name in names:
            raw = os.environ.get(name)
            if raw is None or str(raw).strip() == "":
                continue
            normalized = str(raw).strip().lower()
            if normalized in truthy:
                return True
            if normalized in falsy:
                return False
            warnings.warn(
                f"Invalid boolean env value for {name}='{raw}'. Using default {default}.",
                RuntimeWarning,
                stacklevel=1,
            )
            return default
        return default

    use_reloader = _env_flag("ANON_GUI_USE_RELOADER", "TAIPY_USE_RELOADER", default=False)
    debug_mode = _env_flag("ANON_GUI_DEBUG", "TAIPY_DEBUG", default=False)
    _start_live_dashboard_thread(gui)
    try:
        APP_CTX.event_processor = EventProcessor(gui)
        APP_CTX.event_processor.broadcast_on_event(callback=on_taipy_event)
        APP_CTX.event_processor.start()
    except Exception:
        APP_CTX.event_processor = None
    # ── Prometheus telemetry (opt-in via ANON_METRICS_PORT) ───────────────────
    try:
        _metrics_port = int(os.environ.get("ANON_METRICS_PORT", "0") or "0")
        if _metrics_port > 0:
            from services.telemetry import register_telemetry, start_metrics_server
            if APP_CTX.event_processor is not None:
                register_telemetry(APP_CTX.event_processor)
            start_metrics_server(_metrics_port)
    except Exception as _tele_exc:
        _log.warning("[Telemetry] Failed to start metrics: %s", _tele_exc)
    try:
        run_kwargs = dict(
            title="Anonymous Studio",
            dark_mode=True,
            stylekit=DASH_STYLEKIT,
            run_browser=False,
            margin="0px",
            system_notification=False,
            notification_duration=4500,
            watermark="Anonymous Studio",
            data_url_max_size=50 * 1024 * 1024,
            use_reloader=use_reloader,
            debug=debug_mode,
        )
        if taipy_host:
            run_kwargs["host"] = taipy_host
        if taipy_port:
            try:
                run_kwargs["port"] = int(taipy_port)
            except ValueError:
                warnings.warn(
                    f"Invalid TAIPY_PORT/PORT value '{taipy_port}'. Falling back to Taipy default port.",
                    RuntimeWarning,
                    stacklevel=1,
                )
        # Run GUI with Orchestrator so submitted scenarios are dispatched/executed.
        # `gui.run()` alone does not start taipy.core execution services.
        orchestrator = tp.Orchestrator()
        try:
            tp.run(gui, orchestrator, **run_kwargs)
        except Exception as exc:
            # In rare dev-reload cases the Orchestrator may already be running.
            if exc.__class__.__name__ == "OrchestratorServiceIsAlreadyRunning":
                gui.run(**run_kwargs)
            else:
                raise
    finally:
        if APP_CTX.event_processor is not None:
            try:
                APP_CTX.event_processor.stop()
            except Exception:
                pass
            APP_CTX.event_processor = None
        if orchestrator is not None:
            try:
                orchestrator.stop(wait=False)
            except Exception:
                pass
        _stop_live_dashboard_thread()


if __name__ == "__main__":
    run_app()
