# User Story Migrator Agent Memory — Anonymous Studio

## Session 1 (2026-03-06): Initial audit of Streamlit→v2 migration gaps

### Repo Locations
- v2 (Taipy): `/home/51nk0r5w1m/school/capstone/v2_anonymous-studio`
- Archived Streamlit app: NOT found locally. Notes dir at `capstone/notes` was
  access-denied. Legacy code was moved to that dir in commit 2e4a22ab.
  The Streamlit PoC is referenced in README.md (line 193) but no source files
  remain in the working tree.

### How User Stories Were Reconstructed
Since Streamlit source is inaccessible, stories were inferred from:
1. v2 README "Streamlit PoC workflow" reference (line 193)
2. Services present in v2 that were clearly ported from PoC
   (synthetic.py, geo_signals.py, auth0_rest.py, attestation_crypto.py)
3. Features explicitly referenced as PoC patterns in README / comments
4. Standard Streamlit PII-anonymization PoC features that appear absent in v2

### v2 Pages (confirmed from definitions.py + app.py)
- /dashboard (DASH) — metrics, charts, geo map, perf panel
- /analyze   (QT)   — inline text PII detection + anonymization
- /jobs       (JOBS) — CSV/Excel batch upload, progress, download
- /pipeline   (PIPELINE) — Kanban (Backlog/In Progress/Review/Done)
- /schedule   (SCHEDULE) — review appointments
- /audit      (AUDIT) — immutable filtered log
- /telemetry  (TELEMETRY) — Prometheus metrics, lifecycle charts
- /ui_demo    (UI_DEMO) — Plotly playground (dev/demo only)

### Key Feature Gaps Found (needs migration — see full report)
1. User authentication / login gate (Auth0 UI flow — REST JWT only, no GUI guard)
2. Column-level PII field selector in batch jobs (UI to pick which CSV cols to scan)
3. Side-by-side original vs. anonymized diff viewer (text page)
4. Per-column operator assignment (different operator per CSV column)
5. Export to Excel (XLSX) — only CSV download exists in v2
6. Synthesize operator in batch jobs (only available in Analyze Text, not JOBS page)
7. Named/saved anonymization presets (reusable config profiles)
8. Regex custom recognizer builder (UI for adding custom PII patterns)
9. Session comparison / diff between two saved PII sessions
10. Multi-file batch upload (only single-file upload in v2)
11. Email notification on job completion (Streamlit PoC had basic alerts)
12. Role-based access control (admin vs. analyst vs. reviewer roles)

### Investigation Constraints
- Bash tool was denied (no git log access, no grep across directories)
- Glob denied for paths outside v2_anonymous-studio (can't search capstone/)
- Read denied for capstone/notes (access denied to legacy files)
- All findings are inferred from v2 codebase cross-referenced with README

### Files Read This Session
- README.md (full)
- pages/definitions.py (full)
- app.py (lines 1–900, 1150–1250)
- store/models.py (full)
- services/telemetry.py, synthetic.py, auth0_rest.py,
  geo_signals.py, attestation_crypto.py, jobs.py, app_context.py
- tests/test_store.py, test_pii_engine.py (partial)
- config.toml, requirements.txt, Makefile, main.py, rest_main.py
