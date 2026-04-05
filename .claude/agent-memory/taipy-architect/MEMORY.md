# Anonymous Studio v2 — Taipy Architect Memory

## Project Identity

- Capstone CPSC 4205 Group 3, Spring 2026
- PII anonymization pipeline built on Taipy 3.1+ (config.toml shows core_version 4.1.1)
- Single-tenant academic application; scale is demo/classroom, not enterprise

## Architecture

- GUI: Taipy GUI with Markdown page definitions in pages/definitions.py, 5473-line app.py
- Pipeline: taipy.core Scenario/Task/DataNode via core_config.py; single Task (anonymize_task)
- Store: pluggable backend — MemoryStore (default), DuckDBStore, MongoStore
- Background jobs: invoke_long_callback for file anonymization; schedule library for appointments
- REST: rest_main.py (Flask)
- See architecture.md for full detail

## Critical Bugs Found (session 2026-03-06)

1. DuckDBStore has NO thread lock — scheduler daemon writes from a separate thread, causing
   potential corruption. Fix: add threading.RLock, wrap all self._conn.execute calls.
2. MemoryStore has NO thread lock — same scheduler cross-thread write risk.
   Fix: add threading.RLock to all mutation methods.
3. DuckDBStore._list_payloads interpolates table/order_col directly into SQL string.
   Both come from an internal dict so not immediately exploitable, but is a structural
   injection surface. Fix: validate both against _SORT_COLUMN whitelist before interpolation.
4. cc.MONGO_WRITE_BATCH is mutated globally from _bg_submit_job background thread — race
   if two jobs are submitted concurrently.

## Key File Paths

- /home/51nk0r5w1m/school/capstone/v2_anonymous-studio/app.py (5473 lines — read in sections)
- /home/51nk0r5w1m/school/capstone/v2_anonymous-studio/store/duckdb.py
- /home/51nk0r5w1m/school/capstone/v2_anonymous-studio/store/memory.py
- /home/51nk0r5w1m/school/capstone/v2_anonymous-studio/store/memory.py
- /home/51nk0r5w1m/school/capstone/v2_anonymous-studio/services/jobs.py
- /home/51nk0r5w1m/school/capstone/v2_anonymous-studio/scheduler.py
- /home/51nk0r5w1m/school/capstone/v2_anonymous-studio/core_config.py
- /home/51nk0r5w1m/school/capstone/v2_anonymous-studio/config.toml

## Store Backend Selection

- ANON_STORE_BACKEND=memory (default) -> MemoryStore (seed=True auto-populates demo data)
- ANON_STORE_BACKEND=duckdb -> DuckDBStore (path from ANON_DUCKDB_PATH or /tmp/anon_studio.duckdb)
- ANON_STORE_BACKEND=mongo + MONGODB_URI -> MongoStore

## Scheduler Pattern

- schedule library daemon thread (30s poll interval)
- _fire() in scheduler.py calls store methods cross-thread — this is the source of the
   thread-safety requirement in MemoryStore and DuckDBStore
- Appointments with status="scheduled" and future scheduled_for are registered at startup via sync()

## Performance Notes

- _refresh_dashboard rebuilds all Plotly figures on every 3-second live tick
- DuckDBStore.stats() does 3 full table scans + Python-level aggregation
- DuckDBStore.upcoming_appointments fetches all appointments then filters in Python

## Patterns Confirmed Working

- File upload path traversal protection in services/jobs.py (realpath + allowed_roots check)
- MAX_UPLOAD_BYTES cap (500 MB default, configurable via ANON_MAX_UPLOAD_MB)
- Magic-byte validation for CSV/XLSX/XLS uploads
- AuditEntry immutability convention (never delete from audit_log)
- PIISession, PipelineCard, Appointment, AuditEntry all use dataclasses with ISO-8601 string timestamps

## UI Design System (SigNoz-Inspired)

**Completed** (March 6, 2026):
- SigNoz coral (#F56565) + Mraimo true black (#000000) palette
- Global CSS token system in app.css (:root with semantic naming)
- Consistent layout grid (--grid-gap: 16px, --section-gap: 24px)
- Uniform card sizing (--card-padding: 20px, --card-radius: 8px)
- Subtle shadow elevation (--shadow-sm/md/lg with rgba(0,0,0,0.06-0.12))
- Dashboard ticker cards as independent grid items with 16px gaps (not borders)
- Hover states with translateY(-1px) lift + shadow-md
- Professional sizing: 36px min-height buttons, consistent input padding
- All panels/cards have box-shadow: var(--shadow-sm) for visual depth

**Planned Improvements**:
- Metrics cards with trend/delta indicators
- Trace/waterfall view for job execution (spans with timestamps)
- Service dependency map (App → Orchestrator → Workers → Store)
- Alert panel (rule-based threshold alerts, SLA breach detection)
- Job result trace detail (hierarchical spans, partition events)

## User Preferences

- **Concise output** with file:line references (no verbose explanations)
- **SigNoz aesthetic**: dark theme, metric cards, trace timelines, service maps
- **Layout over color**: Consistent spacing, uniform card sizes, grid alignment prioritized
- **Professional appearance**: Even, balanced visual rhythm — no clutter

## Taipy-Specific Patterns

- **State management**: All module-level variables in app.py are reactive state
- **Inline gaps**: Page definitions use gap=16px or gap=24px explicitly — CSS .taipy-layout { gap } override doesn't affect inline values
- **File upload workaround**: Raw bytes stored in module-level _FILE_CACHE dict (JSON serialization limitation)
- **Long callbacks**: invoke_long_callback() for background tasks — first arg is state_id placeholder (not injected by Taipy)
- **Scope.SCENARIO**: All DataNodes use Scope.SCENARIO for per-job isolation
- **Hard refresh required**: Browser caches CSS aggressively — Ctrl+Shift+R after style changes

## Common Pitfalls

- Changing inline gap= values requires editing pages/definitions.py, not just app.css
- Dashboard ticker uses grid layout — flex may break card sizing consistency
- Removing box-shadow: var(--shadow-sm) from cards makes UI look flat/unprofessional
- Tables need explicit 36px header height + 44px row min-height for SigNoz appearance
