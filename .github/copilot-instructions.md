# Anonymous Studio — Copilot Instructions

This is **v2** — a full rewrite of the PoC ([cpsc4205-group3/anonymous-studio](https://github.com/cpsc4205-group3/anonymous-studio)) that replaces Streamlit with **Taipy GUI + taipy.core** for non-blocking background job execution.

## Running the App

```bash
python3.12 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m spacy download en_core_web_lg   # optional but recommended
taipy run main.py
# → http://localhost:5000
```

**Requires Python 3.9–3.12.** Python 3.13+ is not supported (`taipy>=3.1.0,<4.2` has no wheels).

### Production mode
```bash
export ANON_MODE=standalone
export ANON_WORKERS=8
export ANON_RAW_INPUT_BACKEND=mongo
export ANON_MONGO_URI=mongodb://localhost:27017/anon_studio
taipy run main.py
```

### Linting & Testing
```bash
# CI runs syntax check only:
find . -name '*.py' ! -path './.venv/*' -exec python -m py_compile {} +

# Tests (pytest + fixtures in tests/):
pytest tests/

# Stress tests (large datasets):
make stress
```

Max line length is **120**. Tests live in `tests/` with 11 test files covering store, PII engine, attestation, auth, synthetic text, progress snapshots, and Taipy smoke tests.

---

## Branching & PR Workflow

| Branch | Purpose |
|--------|---------|
| `main` | Production-ready — PRs only, no direct pushes |
| `feature/<short-name>` | New features |
| `bugfix/<short-name>` | Bug fixes |
| `docs/<short-name>` | Documentation only |

PRs require 1 approving review and all status checks passing. Prefer *Squash and merge*.

---

## Architecture

Modular Python app. No web framework — all UI is **Taipy GUI** (Markdown DSL with reactive state).

```
anonymous_studio/
├── main.py              Taipy CLI entrypoint (`taipy run main.py`)
├── app.py               App state, callbacks, and runtime wiring
├── rest_main.py         REST API entrypoint (Taipy Rest + optional Auth0 JWT)
├── core_config.py       taipy.core: DataNodes, Task, Scenario, Orchestrator
├── tasks.py             run_pii_anonymization() — the batch pipeline function
├── pii_engine.py        Presidio Analyzer + Anonymizer wrapper; spaCy model resolution
├── scheduler.py         Background appointment scheduler (daemon thread)
├── pages/
│   ├── __init__.py
│   └── definitions.py   Taipy page markup strings (DASH, JOBS, PIPELINE, SCHEDULE, AUDIT, QT)
├── store/
│   ├── __init__.py      Factory (get_store) + public exports
│   ├── base.py          Abstract StoreBase contract (all backends implement this)
│   ├── models.py        PIISession, PipelineCard, Appointment, AuditEntry dataclasses
│   ├── memory.py        MemoryStore (in-process dict-based, default)
│   ├── mongo.py         MongoStore (persistent MongoDB backend)
│   └── duckdb.py        DuckDBStore (optional alternative)
├── services/
│   ├── app_context.py   AppContext dataclass — shared mutable runtime registries
│   ├── attestation_crypto.py  Ed25519 signing for compliance attestations
│   ├── auth0_rest.py    Auth0 JWT validation middleware for REST endpoints
│   ├── geo_signals.py   Geographic location normalization & city mapping
│   ├── job_progress.py  Job progress registry (get/clear/persist)
│   ├── jobs.py          Job lifecycle helpers (upload, staging, result parsing)
│   ├── progress_snapshots.py  Durable JSON-based progress IPC (worker → GUI)
│   ├── synthetic.py     Faker/LLM-based text synthesis for de-identification
│   └── telemetry.py     Prometheus metrics exporter & Grafana integration
├── ui/
│   └── theme.py         Plotly chart theme/styling
├── tests/               pytest test suite (11 test files)
├── scripts/             Utility scripts (key generation, mongo check, stress)
├── deploy/
│   ├── auth-proxy/      oauth2-proxy + nginx reverse proxy starter
│   └── grafana/         Prometheus + Grafana stack
└── requirements.txt
```

| Core File | Role |
|-----------|------|
| `main.py` | Taipy CLI entrypoint — delegates to `app.run_app()` |
| `app.py` | All Taipy GUI state variables, callbacks, and runtime wiring |
| `core_config.py` | taipy.core DataNodes, Task, Scenario, Orchestrator bootstrap |
| `tasks.py` | `run_pii_anonymization()` — the function the Orchestrator executes |
| `pii_engine.py` | Presidio Analyzer + Anonymizer wrapper; spaCy model resolution |
| `store/` | Multi-backend data store package (memory, MongoDB, DuckDB) |
| `services/` | Extracted business logic (attestation, auth, geo, jobs, telemetry) |
| `pages/` | Taipy Markdown DSL page definitions |

### Background job flow

```
on_submit_job() in app.py
  → invoke_long_callback(_bg_submit_job)   ← keeps UI non-blocking
      → cc.submit_job(df, config)           ← core_config.py
          → tc.create_scenario(pii_scenario_cfg)
          → scenario.raw_input.write(df)
          → scenario.job_config.write(config)
          → tc.submit(scenario)
              → run_pii_anonymization()     ← tasks.py, Orchestrator thread
                  writes PROGRESS_REGISTRY[job_id] per chunk
                  returns (anonymized_df, stats) → output DataNodes
  ← _bg_job_done(state, status, result)    ← GUI thread, updates card + table
```

The GUI polls `PROGRESS_REGISTRY` (in-process dict) when the user clicks "Refresh Progress". On completion, the linked Kanban card auto-advances to `review`.

### taipy.core DataNodes (all `Scope.SCENARIO` — isolated per job)

| DataNode | Contents |
|----------|----------|
| `raw_input` | Uploaded DataFrame |
| `job_config` | `{job_id, operator, entities, threshold, chunk_size}` |
| `anon_output` | Anonymized DataFrame |
| `job_stats` | `{total_entities, entity_counts, duration_s, errors, sample_before, sample_after}` |

---

## Key Conventions

### Taipy GUI state
All module-level variables in `app.py` are reactive state bound by name in the Markdown DSL (`<|{variable}|>`). Update state inside callbacks with `state.variable = value`. Never shadow a state variable with a local of the same name inside a callback. Use `notify(state, "success"|"warning"|"error"|"info", "message")` for toasts.

### File upload — bytes live outside state
Taipy serializes state to JSON, so raw bytes can't be stored in a state variable. `on_file_upload` writes to the `AppContext.file_cache` dict (via `services/app_context.py`). `state.job_file_content` holds only the filename string as a non-None flag.

### `invoke_long_callback` signature
```python
invoke_long_callback(
    state,
    user_function=_bg_submit_job,               # runs in background thread — no state access
    user_function_args=[None, raw_df, config],  # passed verbatim as positional args
    user_status_function=_bg_job_done,          # called on GUI thread when done/periodic
    period=0,                                   # ms between periodic status calls; <500 = off
)
```
**Critical:** the background function does NOT receive `state` — Taipy does not inject it. All args are passed exactly as given in `user_function_args`. In the app, `None` is the first arg because `_bg_submit_job(state_id, raw_df, config)` accepts but ignores `state_id`. If the background function needs to call back into the GUI mid-run (not just on completion), pass `get_state_id(state)` and the `gui` object explicitly, then use `invoke_callback(gui, state_id, fn)`.

Status function signature: `(state, status_or_count, *user_status_function_args, function_result)` where `status_or_count` is `True` on success, `False` on exception, or an `int` period count. The background function's **return value** is `function_result`.

### `store/` public interface is a stable contract
`store/` is a package with an abstract `StoreBase` class and multiple backends (memory, mongo, duckdb). `app.py` imports from the package:
```python
from store import get_store, describe_store_backend, get_store_backend_mode
from store import PIISession, PipelineCard, Appointment, _now, _uid
```

The `StoreBase` abstract class defines the full public API — change backend internals freely, keep these signatures stable:

**Sessions:** `add_session`, `get_session`, `list_sessions`
**Cards:** `add_card`, `update_card`, `delete_card`, `get_card`, `list_cards`, `cards_by_status`
**Appointments:** `add_appointment`, `get_appointment`, `update_appointment`, `delete_appointment`, `list_appointments`, `upcoming_appointments`
**Audit:** `list_audit`, `log_user_action`
**Stats:** `stats`

Backend selection via `ANON_STORE_BACKEND` env var: `memory` (default), `mongo`, `duckdb`, `auto`.

**Known store bugs (as of Sprint 3-1):**
- `update_appointment` and `delete_appointment` leave no audit trail.

### spaCy model resolution
`pii_engine.py::_find_spacy_model()` tries in order: `$SPACY_MODEL` env var → `en_core_web_lg` → `md` → `sm` → `trf` → blank fallback. The blank fallback is intentional for offline/restricted environments. To override, set `SPACY_MODEL` or run `python -m spacy download <name>` and restart.

### config.toml is documentation only
`core_config.py` registers all DataNodes/Tasks/Scenarios programmatically. `config.toml` exists only for the Taipy Studio VS Code extension — it is **not loaded at runtime** because Taipy 4.x doesn't auto-convert TOML scope strings to `Scope` enums.

### MongoDB swap
`store/` supports MongoDB natively via `store/mongo.py`. Set `ANON_STORE_BACKEND=mongo` and `MONGODB_URI` to switch. The UI also provides a runtime store-switching dialog (Settings → Store Settings). `MongoStore` sets `serverSelectionTimeoutMS=3000` for fast failure feedback. `pymongo[srv]>=4.7` is in `requirements.txt`.

### Security
- **Never log raw user text** — it contains PII.
- All credentials (`MONGODB_URI`, `AZURE_*`, etc.) must come from environment variables or `.env` — never hard-coded.
- `.env` is gitignored; add it to `.gitignore` if not present.

---

## What NOT to Change Without Good Reason

- **`invoke_long_callback` in `on_submit_job()`** — replacing with a direct `tc.submit()` call will block the UI thread.
- **`Scope.SCENARIO` on all DataNodes** — changing to `GLOBAL` makes concurrent jobs overwrite each other's data.
- **`_find_spacy_model()` resolution order** — the blank fallback at the end is required for restricted/offline environments.
- **Flat root layout** — `taipy run main.py` expects imports at root. Do not wrap in a `src/` directory.
- **`StoreBase` abstract interface** — all backends must implement these methods. Change internals freely, keep signatures stable.

---

## Known Limitations

- **Kanban is rendered as tables** — Taipy has no native Kanban widget. Cards are table rows; users move them with Forward/Back buttons. Intentional, not a bug.
- **`PROGRESS_REGISTRY` is in-process** — in `standalone` mode (separate worker subprocesses), the dict is invisible to the GUI process. Real-time progress in production requires `services/progress_snapshots.py` (durable JSON-based IPC) or polling the `job_stats` DataNode.
- **In-memory store resets on restart** — all pipeline cards, appointments, and audit entries are lost. Switch to `ANON_STORE_BACKEND=mongo` or `duckdb` for persistence.
- **No authentication in GUI** — suitable for course demo; use the `deploy/auth-proxy/` starter or a middleware proxy. REST API supports Auth0 JWT via `services/auth0_rest.py`.

---

## Design Tokens

| Token | Value |
|-------|-------|
| Background | `#0E1117` |
| Secondary bg | `#262730` |
| Card bg | `#1E2335` |
| Border | `#272D3E` |
| Primary (red) | `#FF2B2B` |
| Accent (purple) | `#8A38F5` |
| Text | `#F0F2F8` |
| Muted | `#7A819A` |
| Fonts | Syne (headings), IBM Plex Mono (code/output) |

---

## Taipy Reference

> Sourced from https://github.com/Avaiga/taipy-doc — concepts most relevant to this project.

---

### GUI — Markdown DSL Syntax

Every visual element uses `<|...|element_type|prop=value|>` syntax in page strings.

```
<|{variable}|>                          # display text (default: text element)
<|{variable}|input|>                    # editable text input
<|{variable}|slider|min=0|max=100|>     # slider
<|Label|button|on_action=my_callback|>  # button
<|{df}|table|>                          # table from DataFrame
<|{df}|chart|x=col1|y=col2|>           # chart
<|{flag}|toggle|>                       # toggle (bool)
<|{value}|selector|lov={options}|>      # dropdown/selector
<|{open}|dialog|title=My Dialog|        # dialog block
content
|>
```

**Property shorthand:** The first fragment is always the *default property* of that element type (usually `value`). These are equivalent:
```
<|{x}|slider|>
<|{x}|slider|value={x}|>
```

**Expressions work inline:**
```
<|{x * 2:.2f}|>       # formatted expression
<|{len(items)}|>      # function call
```

**In Python Builder API** (`import taipy.gui.builder as tgb`), variables must use string f-syntax to create reactive bindings:
```python
tgb.slider("{value}")          # ✅ reactive binding — updates when value changes
tgb.slider(value=my_var)       # ❌ sets once at definition time, never updates
```

---

### GUI — State & Variable Binding

- Every module-level variable in the file where `Gui()` is created is **reactive state**.
- Callbacks receive a `State` object. Read and write variables through it: `state.x = 42`.
- The `State` object is **per-user** — in a multi-user deployment each connection gets its own state.
- **Never assign complex mutable objects and expect automatic re-render.** After mutating a list/dict in place, call `state.refresh("variable_name")` to propagate the change to the frontend.
- To update state from a lambda (where assignment is forbidden), use `state.assign("var", value)`.

**Variable lookup order:** Taipy first searches the module where the page is defined, then falls back to `__main__`. Pages defined in separate modules can bind to their own local variables.

---

### GUI — Callback Signatures

| Callback | When called | Signature |
|----------|-------------|-----------|
| `on_init(state)` | New browser connection | `(state)` |
| `on_change(state, var_name, var_value)` | Any bound variable changes | `(state, name, value)` |
| `on_action(state, id)` | Button pressed / action triggered | `(state, id)` |
| `on_navigate(state, page_name) -> str` | User navigates to a page | return page name to redirect |
| `on_exception(state, function_name, ex)` | Unhandled exception in a callback | `(state, fn_name, ex)` |

**Control-specific callbacks** override the global one. Preferred pattern for large apps:
```
<|{value}|slider|on_change=on_slider_change|>
```
The per-control callback only receives `state` (not `var_name`/`var_value`) since the variable is already known.

---

### GUI — Long-Running Callbacks (`invoke_long_callback`)

Use when a callback would take more than a fraction of a second. Keeps the UI responsive.

```python
from taipy.gui import invoke_long_callback

def background_fn(state_id, arg1, arg2):
    # Runs in a background thread — DO NOT access state here
    result = do_heavy_work(arg1, arg2)
    return result                   # returned to status_fn as `result`

def on_done(state, status, result):
    # Runs back on the GUI thread — CAN access state
    # status: True = success, False = error; or int = period tick count
    state.output = result
    notify(state, "success", "Done!")

def on_action(state):
    invoke_long_callback(
        state,
        user_function=background_fn,
        user_function_args=[None, arg1, arg2],  # None = state_id placeholder
        user_status_function=on_done,
        period=5000,   # optional: call status_fn every 5s while running
    )
```

**Alternatively**, manage threads manually with `invoke_callback(gui, state_id, fn)` to call back into the GUI thread from any thread:
```python
from taipy.gui import get_state_id, invoke_callback

def thread_fn(state_id, gui):
    do_work()
    invoke_callback(gui, state_id, update_ui_fn)

def on_action(state):
    Thread(target=thread_fn, args=[get_state_id(state), gui]).start()
```

---

### GUI — Notifications

```python
from taipy.gui import notify

notify(state, "success", "Saved!")
notify(state, "warning", "Check inputs.")
notify(state, "error",   "Job failed.")
notify(state, "info",    "Processing…")

# Permanent (stays until user closes):
notify(state, "info", "Long task running…", duration=0, id="job_notif")

# Close programmatically:
from taipy.gui import close_notification
close_notification(state, id="job_notif")
```

---

### GUI — Pages & Multi-Page Apps

Register multiple pages by passing a dict to `Gui`:
```python
Gui(pages={
    "/":          root_page,
    "dashboard":  dash_page,
    "jobs":       jobs_page,
}).run()
```

Page content can be:
- A **Markdown string** — most common, used in this project
- A **`tgb.Page()` builder block**
- An **HTML string**

Pages defined in separate modules can bind to their own local variables. Variables in `__main__` are accessible from any page without importing.

**Navigate between pages** by changing `state.active_page` or calling `navigate(state, "page_name")`. Use `on_navigate` to intercept navigation and redirect.

---

### taipy.core — Config vs Entity (Critical Distinction)

| Concept | Object | Created by | When |
|---------|--------|-----------|------|
| **Config** | `DataNodeConfig`, `TaskConfig`, `ScenarioConfig` | Developer via `Config.configure_*()` | App startup / import time |
| **Entity** | `DataNode`, `Task`, `Scenario`, `Job` | Taipy at runtime via `tc.create_scenario()` etc. | Each run |

One config can generate many entities. Configs describe *how*; entities are *instances* of that description.

**After the Orchestrator is started, configs are locked** — no more `Config.configure_*()` calls.

---

### taipy.core — Scenario Lifecycle

```python
import taipy.core as tc
from taipy import Config

# 1. Configure (once, at import time)
dn_cfg   = Config.configure_pickle_data_node("my_dn", scope=Scope.SCENARIO)
task_cfg = Config.configure_task("my_task", function=my_fn, input=[dn_cfg], output=[...])
sc_cfg   = Config.configure_scenario("my_scenario", task_configs=[task_cfg])

# 2. Create entity (each job run)
sc = tc.create_scenario(sc_cfg)

# 3. Write inputs
sc.my_dn.write(some_data)

# 4. Submit
submission = tc.submit(sc)

# 5. Read outputs (after completion)
result = sc.output_dn.read()
```

---

### taipy.core — Scope

`Scope` controls how many scenario instances share a DataNode instance.

| Scope | DataNode is shared across… | Use case |
|-------|---------------------------|----------|
| `Scope.SCENARIO` | Only the scenario it was created with | ✅ Isolated per-job data (used in this project) |
| `Scope.CYCLE` | All scenarios in the same time cycle | Shared reference data per time period |
| `Scope.GLOBAL` | All scenarios of the same config | Shared lookup tables, model weights |

**This project uses `Scope.SCENARIO` on all DataNodes.** Never change this to `GLOBAL` — concurrent jobs would overwrite each other's inputs/outputs.

---

### taipy.core — Job Status Lifecycle

```
SUBMITTED → PENDING → RUNNING → COMPLETED
                 ↘ BLOCKED (input deps not ready) → PENDING → RUNNING
                                                              ↘ FAILED
         → CANCELED (by user, before RUNNING)
         → ABANDONED (downstream of a cancelled job)
         → SKIPPED (task marked skippable + inputs unchanged)
```

Access status: `job.status` — compare to `from taipy.core import Status`:
```python
from taipy.core import Status
if job.status == Status.COMPLETED: ...
if job.status == Status.FAILED:    print(job.stacktrace)
if job.status == Status.RUNNING:   ...
```

**Get jobs:**
```python
tc.get_jobs()                    # all jobs ever created
tc.get_latest_job(task)          # latest job for a specific task
tc.get(job_id)                   # by id
```

**Cancel a job** (only when SUBMITTED / PENDING / BLOCKED):
```python
tc.cancel_job(job)
```

---

### taipy.core — Subscribing to Job Status Changes

```python
def on_job_status_change(scenario, job):
    print(f"Job {job.id} status: {job.status}")

tc.subscribe_scenario(on_job_status_change)              # all scenarios
tc.subscribe_scenario(on_job_status_change, my_scenario) # specific scenario
tc.unsubscribe_scenario(on_job_status_change)
```

This is an alternative to polling `PROGRESS_REGISTRY`. In `standalone` mode (separate worker processes), subscriptions persist across process boundaries — but `PROGRESS_REGISTRY` does not.

---

### taipy.core — DataNode Read/Write

```python
sc.my_data_node.write(value)   # write any Python object
value = sc.my_data_node.read() # read it back
```

Pickle DataNodes serialize arbitrary Python objects. The file is stored at the path configured in `ANON_STORAGE` (default `/tmp/anon_studio`).

---

### taipy.core — Execution Modes

Configured via `Config.configure_job_executions()` before starting the Orchestrator:

```python
# Development (default) — synchronous, single process
Config.configure_job_executions(mode="development")

# Standalone — true parallel subprocesses
Config.configure_job_executions(mode="standalone", max_nb_of_workers=4)
```

In `development` mode, `tc.submit()` executes the task synchronously in the same process. In `standalone` mode, the Orchestrator spawns worker subprocesses — `PROGRESS_REGISTRY` (an in-process dict) will not be visible to the GUI process.

---

### GUI — Styling

Every Taipy visual element generates an HTML element with a CSS class `taipy-<element_type>` (e.g. `taipy-button`, `taipy-table`). Add custom CSS via a `.css` file placed next to the app or passed to `Gui(..., css_file="style.css")`.

Add extra classes to any element with `class_name`:
```
<|Label|button|class_name=my-btn|>
```

Pass many properties cleanly via a dict with `properties`:
```python
props = {"title": "My Dialog", "labels": "Cancel;OK"}
# <|{open}|dialog|properties=props|>
```


---

## Presidio Reference

> Sourced from https://microsoft.github.io/presidio/ — the upstream library this project wraps.

---

### Architecture

```
AnalyzerEngine
  ├── NlpEngine (spaCy model — provides tokens/lemmas for ML-based entities)
  ├── RecognizerRegistry (all PII recognizers)
  └── ContextAwareEnhancer (boosts score when context words appear near PII)

AnonymizerEngine
  └── Operators: replace, redact, mask, hash, encrypt, keep, custom
```

`pii_engine.py` wraps both engines. `AnalyzerEngine` → `AnonymizerEngine` is the two-step flow.

---

### Entity Detection Methods

Entities split into two families — important because the blank spaCy fallback breaks ML-based ones:

| Method | Entities | Requires NLP model |
|--------|----------|--------------------|
| Pattern match / regex / checksum | `EMAIL_ADDRESS`, `PHONE_NUMBER`, `CREDIT_CARD`, `US_SSN`, `US_PASSPORT`, `US_DRIVER_LICENSE`, `US_ITIN`, `US_BANK_NUMBER`, `IP_ADDRESS`, `URL`, `IBAN_CODE`, `DATE_TIME`, `MEDICAL_LICENSE` | ❌ No |
| Custom logic + NLP context | `PERSON`, `LOCATION`, `NRP`, `ORGANIZATION` | ✅ Yes — blank fallback skips these |

**Conclusion:** without `en_core_web_lg` installed, the 4 ML-dependent entities (`PERSON`, `LOCATION`, `NRP`, `ORGANIZATION`) are silently skipped. The model status banner in the UI surfaces this.

---

### Additional Entities Presidio Supports (not yet in the app)

The app's 17 entities are a subset. Presidio also supports: `CRYPTO` (Bitcoin), `MAC_ADDRESS`, `UK_NHS`, `UK_NINO`, `ES_NIF`, `ES_NIE`, `IT_FISCAL_CODE`, `IN_AADHAAR`, `IN_PAN`, `AU_TFN`, and many more. To add them: append to `ALL_ENTITIES` in `pii_engine.py`.

---

### Analyzer — Key Parameters

```python
results = analyzer.analyze(
    text="...",
    entities=["PERSON", "EMAIL_ADDRESS"],   # subset of ALL_ENTITIES, or omit for all
    language="en",
    score_threshold=0.35,                   # min confidence (0–1); app default is 0.35
    return_decision_process=True,           # attaches explanation to each RecognizerResult
)
```

`return_decision_process=True` enables the **Detection Rationale** feature (project board item). Each `RecognizerResult` then has an `.analysis_explanation` attribute describing why that span was matched.

---

### Anonymizer — Operator Config

```python
from presidio_anonymizer.entities import OperatorConfig

operators = {
    "PERSON":        OperatorConfig("replace", {"new_value": "<PERSON>"}),
    "EMAIL_ADDRESS": OperatorConfig("redact",  {}),
    "CREDIT_CARD":   OperatorConfig("mask",    {"chars_to_mask": 12, "masking_char": "*", "from_end": False}),
    "US_SSN":        OperatorConfig("hash",    {"hash_type": "sha256", "salt": "my-salt"}),
    "PHONE_NUMBER":  OperatorConfig("encrypt", {"key": "WmZq4t7w!z%C&F)J"}),
    "DEFAULT":       OperatorConfig("replace", {}),  # fallback for unlisted entity types
}
```

If `new_value` is omitted from `replace`, the default is `<ENTITY_TYPE>` (e.g. `<EMAIL_ADDRESS>`).

**⚠️ Hash operator breaking change (v2.2.361+):** hash now uses a **random salt by default**. Same PII text produces different hashes each run. For referential integrity (consistent pseudonymization across multiple runs/records), pass an explicit `salt` parameter.

---

### Batch Processing

For CSV de-identification, use `BatchAnonymizerEngine` instead of looping the regular engine — it handles DataFrames natively:

```python
from presidio_anonymizer import BatchAnonymizerEngine

batch_engine = BatchAnonymizerEngine()
anonymized_df = batch_engine.anonymize_dict(
    analyzer_results,
    operators=operators,
)
```

The current `run_pii_anonymization` in `tasks.py` does this manually in chunks. `BatchAnonymizerEngine` is a cleaner alternative if refactoring.

---

### Custom Recognizers

Add a regex-based recognizer (e.g. internal employee IDs):

```python
from presidio_analyzer import PatternRecognizer, Pattern

emp_id_recognizer = PatternRecognizer(
    supported_entity="EMPLOYEE_ID",
    patterns=[Pattern("Employee ID", r"EMP-\d{6}", score=0.85)],
    context=["employee", "staff", "id"],
)
engine.analyzer.registry.add_recognizer(emp_id_recognizer)
```

The PoC has `azure_ai_language_wrapper.py` showing a `RemoteRecognizer` for calling Azure AI Language PII service.

---

### Decision Process (Detection Rationale — Done)

`pii_engine.py` passes `return_decision_process=True` to the Presidio analyzer. Each `RecognizerResult` then has an `.analysis_explanation` attribute. The entity evidence table in the UI shows 7 columns: Entity Type, Text, Confidence, Confidence Band, Span, Recognizer, Rationale.

The `fast=True` parameter in `analyze()` disables `return_decision_process` for performance in batch jobs.

---

## Testing Reference

Tests live in `tests/` and use pytest. Run with `pytest tests/` or `make stress` for large-dataset tests.

### Test files

| Test file | What it covers |
|-----------|---------------|
| `test_store.py` | Store backends (sessions, cards, appointments, audit) |
| `test_store_duckdb.py` | DuckDB-specific store backend |
| `test_pii_engine.py` | PII detection/anonymization core |
| `test_attestation_crypto.py` | Ed25519 signing/verification |
| `test_auth0_rest.py` | Auth0 JWT validation |
| `test_synthetic.py` | Synthetic text generation (Faker, LLMs) |
| `test_progress_snapshots.py` | Job progress snapshot I/O |
| `test_app_file_upload_download.py` | File upload/download workflows |
| `test_taipy_mockstate_smoke.py` | Taipy GUI state/callback smoke tests |
| `test_tasks_large.py` | Large batch job simulation |

### Testing `store/` (pure Python, no Taipy needed)

```python
from store import get_store, PipelineCard

def test_add_and_get_card():
    store = get_store()
    c = PipelineCard(title="Test", status="backlog")
    store.add_card(c)
    assert store.get_card(c.id).title == "Test"
```

### Testing `pii_engine.py`

```python
from pii_engine import get_engine

def test_email_detected():
    engine = get_engine()
    results = engine.analyze("Contact jane@example.com", entities=["EMAIL_ADDRESS"])
    assert any(r.entity_type == "EMAIL_ADDRESS" for r in results)
```

### Testing Taipy Callbacks

Mock `store` and test business logic directly without running the UI:

```python
from unittest.mock import patch, MagicMock

def test_on_card_save_empty_title():
    mock_state = MagicMock()
    mock_state.card_title_f = ""
    with patch("app.notify") as mock_notify:
        on_card_save(mock_state)
        mock_notify.assert_called_with(mock_state, "error", "Title is required.")
```

---

## GUI Actions Quick Reference

All importable from `taipy.gui`:

```python
from taipy.gui import (
    notify,               # toast notification
    navigate,             # programmatic page navigation
    download,             # trigger browser file download
    invoke_long_callback, # background thread with GUI callback on completion
    invoke_callback,      # call a function on the GUI thread from any thread
    get_state_id,         # get state ID for cross-thread callbacks
    hold_control,         # disable a control (by id) during processing
    resume_control,       # re-enable a held control
    close_notification,   # close a persistent notify(duration=0) by id
)
```

### `download()` — for CSV export

```python
from taipy.gui import download

def on_download(state):
    sc = _SCENARIOS.get(state.download_scenario_id)
    anon_df = sc.anon_output.read()
    csv_bytes = anon_df.to_csv(index=False).encode()
    download(state, content=csv_bytes, name="anonymized_output.csv")
```

### `hold_control()` / `resume_control()` — prevent double-clicks

```python
def on_submit_job(state):
    hold_control(state, "submit_btn")      # disable the submit button
    invoke_long_callback(state, _bg_submit_job, ..., user_status_function=_bg_done)

def _bg_done(state, status, result):
    resume_control(state, "submit_btn")    # re-enable after job queued
```

---

## Runtime Context (`AppContext`)

`services/app_context.py` defines an `AppContext` dataclass that consolidates all mutable runtime registries into a single object (`APP_CTX` in `app.py`):

| Field | Type | Purpose |
|-------|------|---------|
| `scenarios` | `Dict[str, Any]` | Scenario reference for result loading (keyed by job_id) |
| `submission_ids` | `Dict[str, str]` | Maps job_id → Taipy submission_id |
| `file_cache` | `Dict[str, Dict]` | Uploaded file bytes per state_id (bytes can't live in Taipy state) |
| `burndown_cache` | `Dict[str, Any]` | Dashboard burndown chart cache |
| `live_state_ids` | `Set[str]` | Active browser connections (for live push) |
| `live_state_lock` | `Lock` | Thread safety for live_state_ids |
| `live_stop_event` | `Event` | Signal to stop background live-update thread |
| `live_thread` | `Optional[Thread]` | Background live-push thread |
| `event_processor` | `Any` | Taipy EventProcessor for job lifecycle events |

All fields are safe in single-process (`development`) mode. In `standalone` mode with multiple worker processes, the dict fields are not shared — use MongoDB or shared filesystem instead.


---

## PoC Feature Parity Reference

> The original Presidio Streamlit demo (`cpsc4205-group3/anonymous-studio`, itself based on https://microsoft.github.io/presidio/samples/python/streamlit/) defined the feature set. This table maps each PoC feature to its v2 status.

| PoC Feature | v2 Status | Notes |
|-------------|-----------|-------|
| Text input + detect + anonymize | ✅ Done | PII Text page (QT — Quick Test) |
| Entity type selector | ✅ Done | 17 entities including ORGANIZATION |
| Threshold slider | ✅ Done | Default 0.35 |
| Operators: replace, redact, mask, hash | ✅ Done | |
| Highlighted output | ✅ Done | `highlight_md()` — Taipy `mode=md` |
| Entity findings table | ✅ Done | entity_type, text, confidence, span, recognizer, rationale |
| CSV/Excel batch upload + background job | ✅ Done (v2 new) | |
| Kanban pipeline | ✅ Done (v2 new) | |
| Audit log | ✅ Done (v2 new) | |
| **Allowlist** | ✅ Done | `allow_list=` param in `pii_engine.analyze()` |
| **Denylist** | ✅ Done | `CUSTOM_DENYLIST` entity + regex cache |
| **Detection rationale** | ✅ Done | `return_decision_process=True` → recognizer/rationale in entity table |
| **ORGANIZATION entity** | ✅ Done | Added to `ALL_ENTITIES`; uses spaCy `ORG` → `ORGANIZATION` mapping |
| **Operator: encrypt** | ⚠️ Partial | Listed in docs but `OperatorConfig("encrypt", {"key": key})` needs UI key field |
| **Operator: synthesize** | ✅ Done | `services/synthetic.py` — Faker + LLM (OpenAI/Azure) backends |
| **Compliance attestation** | ✅ Done (v2 new) | Ed25519 signatures via `services/attestation_crypto.py` |
| **Telemetry** | ✅ Done (v2 new) | Prometheus metrics via `services/telemetry.py` |
| **Auth0 JWT** | ✅ Done (v2 new) | REST API auth via `services/auth0_rest.py` |
| **Appointment scheduler** | ✅ Done (v2 new) | Background daemon via `scheduler.py` |
| Multiple NER models (HuggingFace, Stanza, Flair, Azure) | ❌ Out of scope | PoC has `presidio_nlp_engine_config.py` with full config for all |

---

### Allowlist / Denylist Implementation (Done)

Both are implemented in `pii_engine.py`. The `analyze()` and `anonymize()` methods accept `allowlist` and `denylist` parameters:

```python
# Allowlist — words that should NOT be flagged as PII
results = engine.analyze(text, entities=entities, allowlist=["John", "Smith"])

# Denylist — words that MUST be flagged as CUSTOM_DENYLIST
results = engine.analyze(text, entities=entities, denylist=["Acme Corp", "Project X"])
```

Internally, denylist uses `CUSTOM_DENYLIST` entity type with a regex pattern cache (`_DENYLIST_PATTERN_CACHE`). Allowlist uses Presidio's native `allow_list=` parameter.

---

### Synthesize Operator (Done)

Implemented in `services/synthetic.py`. Supports two backends:
- **Faker** — offline, deterministic fake data generation (no API key needed)
- **LLM** — OpenAI or Azure OpenAI for more realistic synthesis

Env vars for LLM mode: `OPENAI_KEY` (OpenAI) or `AZURE_OPENAI_KEY` + `AZURE_OPENAI_ENDPOINT` + `AZURE_OPENAI_DEPLOYMENT` + `OPENAI_API_VERSION` (Azure OpenAI). The feature is gated — if no key is set, Faker is used as fallback.

---

### ORGANIZATION Entity (Done)

`ORGANIZATION` has been added to `ALL_ENTITIES` in `pii_engine.py` (17th entity). The NlpEngineProvider config maps spaCy's `ORG` tag → `ORGANIZATION`. Requires a trained spaCy model (`en_core_web_lg` recommended) — the blank fallback skips NER-based entities.

---

### Encrypt Operator — Key Management

The PoC uses a hardcoded demo key `"WmZq4t7w!z%C&F)J"`. For real use, the encrypt key must be:
- 128-bit (16 chars), 192-bit (24 chars), or 256-bit (32 chars) AES key
- Stored securely (env var, not hardcoded)
- The same key used for `DeanonymizeEngine` to reverse the encryption

```python
from presidio_anonymizer import DeanonymizeEngine
from presidio_anonymizer.entities import OperatorResult, OperatorConfig

deengine = DeanonymizeEngine()
original = deengine.deanonymize(
    text=anonymized_text,
    entities=[OperatorResult(start=..., end=..., entity_type="PERSON")],
    operators={"DEFAULT": OperatorConfig("decrypt", {"key": encryption_key})},
)
```

