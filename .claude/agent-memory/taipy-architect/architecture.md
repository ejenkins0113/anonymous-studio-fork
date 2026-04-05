# Anonymous Studio v2 — Architecture Reference

## Runtime Thread Model (important for safety)
- Main thread: Taipy GUI WebSocket server (Flask/SocketIO)
- Taipy GUI callback thread pool: on_change, on_submit_job, on_navigate, etc.
- Orchestrator thread(s): taipy.core job execution (anonymize_task)
- anon-scheduler thread (daemon): schedule library, 30s poll, fires _fire() on due appointments
- anon-live-dashboard thread (daemon): 3s poll, calls invoke_callback for each connected client

All threads share the same store singleton. Thread safety is required.

## Store Contract (store/base.py StoreBase)
Methods: add_session, get_session, list_sessions, add_card, update_card, delete_card,
get_card, list_cards, cards_by_status, add_appointment, get_appointment, update_appointment,
delete_appointment, list_appointments, upcoming_appointments, list_audit, log_user_action, stats

All methods are synchronous (async causes Taipy WebSocket hangs per base.py comment).

## Taipy Pipeline
- Scenario: pii_pipeline (WEEKLY frequency)
- Task: anonymize_task (function: tasks:run_pii_anonymization)
- DataNodes: raw_input (in_memory/mongo), job_config (pickle, 1d TTL),
  anon_output (pickle, 14d TTL), job_stats (pickle, 14d TTL)
- skippable=False on anonymize_task (correct for PII — never skip)
- Scenario comparator: core_config._compare_job_stats on job_stats

## Job Submission Flow
1. on_submit_job (GUI thread) — validate, stage file, build config, call invoke_long_callback
2. _bg_submit_job (background thread) — cc.submit_job -> create Scenario, write DataNodes, submit
3. _bg_job_done (GUI thread, periodic tick) — poll progress, on completion call _load_job_results
4. _load_job_results — read anon_output + job_stats DataNodes, update UI, move linked card to review

## DuckDB Schema
Tables: pii_sessions(id, created_at, payload), pipeline_cards(id, updated_at, payload),
appointments(id, scheduled_for, payload), audit_log(id, timestamp, payload)
All domain data stored as JSON in payload column — no normalized columns except sort keys.

## Config Management
- config.toml: exported Taipy config (authoritative: core_config.py)
- .env: secrets (MONGODB_URI, OPENAI_API_KEY, ANON_DUCKDB_PATH, etc.)
- Environment variables override config at runtime

## Telemetry
- Optional: prometheus_client (prometheus_client PyPI package)
- Enabled via ANON_METRICS_PORT env var
- In-process counters always available (get_telemetry_snapshot())
- Taipy EventProcessor hook: _on_telemetry_event in services/telemetry.py
