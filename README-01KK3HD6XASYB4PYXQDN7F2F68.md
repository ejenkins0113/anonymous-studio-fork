---
runme:
  document:
    relativePath: README.md
  session:
    id: 01KK3HD6XASYB4PYXQDN7F2F68
    updated: 2026-03-07 02:03:20-05:00
---

# Anonymous Studio — De-Identified Data Pipelines

**CPSC 4205 | Group 3 | Spring 2026**
*Carley Fant · Sakshi Patel · Diamond Hogans · Elijah Jenkins*

---

## Taipy Studio (Recommended)

Taipy Studio is a VS Code extension that makes building Taipy apps significantly faster. Install it before writing any new pages or modifying `core_config.py`.

### What it gives you

**Configuration Builder** — a point-and-click editor for taipy.core config files (`.toml`). Instead of manually writing DataNode, Task, and Scenario declarations, you build them visually and Taipy Studio generates the config. Opens in the VS Code Secondary Side Bar under "Taipy Configs".

**GUI Helper** — IntelliSense inside the Taipy Markdown DSL (`<|...|component|prop=value|>`). As you type visual element properties in `.md` files or Python strings, it autocompletes component names, property names, and variable references. Also includes a variable explorer and code navigation.

### Install

1. Make sure Taipy 3.0+ is installed in your venv (it is — `requirements.txt` pins `taipy>=3.1.0`)
2. Open VS Code → Extensions (`Ctrl+Shift+X`) → search **"Taipy"**
3. Install **Taipy Studio** — it automatically pulls in both sub-extensions

> Taipy Studio 2.0+ is required for Taipy 3.x. If you see a 1.x version in the marketplace, make sure you select 2.0 or later.

### Relevance to this project

| Taipy Studio feature | Where it helps in Anonymous Studio |
|---------------------|------------------------------------|
| Config Builder | Editing DataNodes / Tasks in `core_config.py` visually |
| GUI Helper IntelliSense | Writing page strings (`DASH`, `JOBS`, `PIPELINE`, etc.) in `app.py` |
| Variable explorer | Seeing all reactive state variables without reading the full file |
| `.toml` config view | If you migrate from inline `Config.configure_*` calls to a `.toml` file |

### Migrating to a `.toml` config (optional)

Right now `core_config.py` declares everything in Python. Taipy also supports `.toml` configuration files, which the Config Builder edits visually. If you want to use the GUI for your DataNode and Scenario setup:

```bash
# Export current config to toml (run once inside the venv)
python -c "from core_config import *; from taipy import Config; Config.export('config.toml')"
```

Then open `config.toml` in VS Code — Taipy Studio will show it in the Taipy Configs panel.

---

```ini
┌─────────────────────────────────────────────────────────┐
│  Taipy GUI  (app.py)                                    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐    │
│  │Dashboard │ │Upload/   │ │Pipeline  │ │Schedule/ │    │
│  │          │ │Jobs      │ │Kanban    │ │Audit     │    │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘    │
└───────┼────────────┼────────────┼────────────┼──────────┘
        │            │ invoke_    │            │
        │            │ long_      │            │
        ▼            ▼ callback   ▼            ▼
┌───────────────────────────────────────────────────────┐
│  taipy.core  (core_config.py)                         │
│                                                       │
│  DataNode: raw_input  ──┐                             │
│  DataNode: job_config ──┤──► Task: anonymize_task     │
│                          │      │                     │
│  DataNode: anon_output ◄─┤      └── tasks.py          │
│  DataNode: job_stats   ◄─┘          run_pii_          │
│                                     anonymization()   │
│  Scenario: pii_pipeline                               │
│  Orchestrator (development | standalone)              │
└───────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────┐
│  pii_engine.py           │
│  Presidio Analyzer       │
│  + AnonymizerEngine      │
│  (offline spaCy, no net) │
└──────────────────────────┘
```

## How Background Jobs Work

1. **User uploads** a CSV/Excel file on the Jobs page
2. __`invoke_long_callback`__ fires — the GUI stays fully responsive
3. The callback thread calls __`cc.submit_job(df, config)`__
4. `submit_job` creates a fresh __taipy.core Scenario__, writes the two input DataNodes (`raw_input`, `job_config`), and calls `tc.submit(scenario)`
5. The Orchestrator picks up the job and runs __`run_pii_anonymization`__ (in `tasks.py`):
   - Auto-detects text/PII columns
   - Processes in configurable chunks (default 500 rows)
   - Writes per-chunk progress to __`PROGRESS_REGISTRY`__ dict
   - Returns `(anonymized_df, stats)` → written to output DataNodes

6. The GUI polls __`PROGRESS_REGISTRY`__ when the user clicks "Refresh Progress"
7. On completion, results load into the preview table; the linked Kanban card auto-advances to **Review**

### Switching to True Parallel Workers (Production)

```bash
export ANON_MODE=standalone
export AN**********=8
export ANON_RAW_INPUT_BACKEND=mongo
export ANON_
MO*************db://lo*****st:27017/anon_studio
export AN***********************00
taipy run main.py
```

No code changes needed — `core_config.py` reads the env vars.  
`ANON_RAW_INPUT_BACKEND=auto` also works (it resolves to `mongo` in standalone).

### Current Mode and Defaults

- `ANON_MODE` supports:
   - `development` (default)
   - `standalone`

- If `ANON_MODE` is not set in `.env` or your shell, the app runs in `development`.
- Source of truth: `MODE = os.environ.get("ANON_MODE", "development")` in `core_config.py`.

Quick check:

```bash
echo "${ANON_MODE:-development}"

# Ran on 2026-03-07 02:02:44-05:00 for 5.983s exited with 0
de*******nt
```

---

## Pages

| Page | Description |
|------|-------------|
| **Dashboard** | Live job counts, pipeline status, upcoming reviews, recent audit |
| **PII Text** | Inline text analysis — highlights + anonymizes without file upload |
| **Upload & Jobs** | Submit large CSV/Excel as background jobs; progress bar; result preview + download |
| **Pipeline** | Kanban board (Backlog → In Progress → Review → Done) linked to job status |
| **Schedule** | Book and track PII review appointments, linked to pipeline cards |
| **Audit Log** | Filterable immutable log of every system and user action |

---

## Getting Started

### 1. Clone the repo

```bash
git clone ht***************************************************it
cd anonymous-studio
```

### 2. Check your Python version

```bash
python --version
```

**You need Python 3.9, 3.10, 3.11, or 3.12.** Python 3.13+ is not supported with this Taipy range (`taipy>=3.1.0,<4.2`) and install/runtime will fail.

If you have only Python 3.13+, install 3.12 from [python.org](ht**************rg) and use it explicitly in the next step.

### 3. Create and activate a virtual environment

```bash
# Use py******12 explicitly to avoid picking up 3.14 if both are installed
py******12 -m venv .venv

# Activate — run this every time you open a new terminal
source .venv/bin/activate        # Mac / Linux
.venv\Scripts\activate           # Windows
```

You'll see `(.venv)` at the start of your prompt when it's active. Run `python --version` inside the venv to confirm it shows 3.**.x.

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

### 5. Download the spaCy NER model (recommended)

Run this **while the venv is active** so the model installs into `.venv` and not system Python.

```bash
python -m spacy download en_core_web_lg
```

This enables detection of free-text entity types: `PERSON`, `LOCATION`, and `ORGANIZATION`. Without it the app still works but will only detect structured PII (emails, SSNs, phone numbers, credit cards, etc.).

In **Analyze Text**, use **Settings → NLP model** to switch runtime model mode:

- `auto` (default, best available installed model)
- `en_core_web_lg`
- `en_core_web_md`
- `en_core_web_sm`
- `en_core_web_trf`
- `blank` (regex-only fallback)

In **Batch Jobs**, use **Advanced Options → NLP model for this job** to pick the model per run (matches the Streamlit PoC workflow).

For standalone multi-worker runs, set `SPACY_MODEL` before startup so every worker resolves the same model.

> **Can't download right now?** Skip this step. The app falls back to a blank model automatically and shows a warning banner in the UI.

### 6. Run

```bash
taipy run main.py
```

Open **ht*****************00** in your browser.

If your shell does not resolve `taipy`, run:

```bash
python -m taipy run main.py
```

### 6.1 Auto-refresh during development

Taipy CLI supports hot-reload flags:

- `--use-reloader` / `--no-reloader`
- `--debug` / `--no-debug`

This repo reads these from environment variables in `app.py`:

- `AN*******************=1` enables hot reload (preferred)
- `AN************=1` enables debug mode (preferred)
- Backward-compatible aliases are also supported: `TAIPY_USE_RELOADER`, `TAIPY_DEBUG`

Defaults are off (`0`) for stable production behavior, so restart is required unless you enable them.

Example (development only):

```bash
export AN*******************=1
export AN************=1
taipy run main.py
```

### 7. Add to `.gitignore`

```sh
.venv/
__pycache__/
*.pyc
user_data/
/tmp/anon_studio_blank_en/
```

`user_data/` is where taipy.core writes DataNode pickles (job inputs and outputs). `/tmp/anon_studio_blank_en/` is the blank spaCy model fallback. Neither should be committed.

---

### Optional: real MongoDB

Mongo can be used for both:

1. Persistent app store (cards, appointments, audit): set `ANON_STORE_BACKEND=mongo` and `MONGODB_URI`
2. Raw input DataNode backend for standalone workers: set `ANON_RAW_INPUT_BACKEND=mongo` and `ANON_MONGO_URI` (or `ANON_MONGO_DB` + host fields)

```bash
export ANON_STORE_BACKEND=mongo
export MO***************db://lo*****st:27017/anon_studio
export ANON_RAW_INPUT_BACKEND=mongo
export AN******************db://lo*****st:27017/anon_studio
export AN***********************00
```

### Where Mongo DataNode Connects (Taipy Core)

If you are switching to Mongo mode and asking "where do I connect the DataNode?", the connection is configured in `taipy.core` (not in the UI store settings):

- Connection parsing: `core_config.py::_mongo_config_from_env()`
   - Reads `ANON_MONGO_URI` (or `MONGODB_URI`) and fallback fields like `ANON_MONGO_DB`, `ANON_MONGO_HOST`, `ANON_MONGO_PORT`.

- DataNode type selection: `core_config.py::_configure_raw_input_data_node()`
   - Uses `ANON_RAW_INPUT_BACKEND` (`auto | memory | mongo | pickle`).
   - In `development`, `auto -> memory`; in `standalone`, `auto -> mongo`.

- Runtime writes: `core_config.py::submit_job()`
   - For Mongo backend, raw input is converted to Mongo documents and written in batches (`ANON_MONGO_WRITE_BATCH`) via `write()` + `append()`.

Important separation:

- `ANON_STORE_BACKEND=mongo` configures the app's operational store (cards/audit/schedule).
- `ANON_RAW_INPUT_BACKEND=mongo` configures Taipy `raw_input` DataNode persistence for job input payloads.

---

## Auth0 Proxy Starter (GUI + REST)

For a lightweight Auth0 integration (without full BFF/KrakenD), use:

- `oa********xy` for OIDC login/session
- `nginx` for route protection and forwarding
- optional `redis` for shared session storage

Starter files:

- `deploy/auth-proxy/docker-compose.yml`
- `deploy/auth-proxy/nginx.conf`
- `deploy/auth-proxy/.env.auth-proxy.example`
- `deploy/auth-proxy/README.md`

Quick start:

```bash
cp deploy/auth-proxy/.env.auth-proxy.example deploy/auth-proxy/.env.auth-proxy
make proxy-cookie-secret   # paste into OA**********************ET

# Terminal A (GUI)
taipy run main.py

# Terminal B (REST on port 5001)
TA***********01 taipy run rest_main.py

# Terminal C (auth proxy)
make auth-proxy-up
```

Open `ht*****************80`.

Stop:

```bash
make auth-proxy-down
```

### Direct Auth0 JWT Auth for REST (optional)

If you prefer token validation inside `rest_main.py` (instead of a proxy-only model),
set these env vars:

```bash
AN***************=1
AU************************s.au*****om
AU*****************ht************************pi
```

Optional:

```bash
# Defaults to RS256
AN**************************56
# Space/comma separated scopes required for every REST request
ANON_AUTH_REQUIRED_SCOPES=read:jobs
# Keep specific routes open (for probes, etc.)
ANON_AUTH_EXEMPT_PATHS=/healthz
```

Then run:

```bash
TA***********01 taipy run rest_main.py
```

By default (`AN***************=0`), no token is required, which keeps local development flow unchanged.

---

## Large Dataset + Mongo Runbook

### Backend Matrix

| Environment | `ANON_MODE` | `ANON_RAW_INPUT_BACKEND` | `raw_input` DataNode behavior |
|---|---|---|---|
| Local dev | `development` | `auto` (default) | In-memory (no raw-input persistence across restart) |
| Production | `standalone` | `auto` | Mongo-backed collection (persistent, worker-safe) |
| Explicit Mongo | any | `mongo` | Mongo-backed collection |

### Data Node Explorer (what you should see)

When `pii_pipeline` is pinned in Taipy Data Node Explorer, these nodes are expected:

- `raw_input`
- `job_config`
- `anon_output`
- `job_stats`

`raw_input` will show large uploaded datasets. For large jobs with Mongo backend, writes are batched using `ANON_MONGO_WRITE_BATCH` to reduce memory spikes.

If the explorer shows `Pinned on ???`:

- No scenario is pinned yet, or no scenario has been created in this session.
- Submit one job from __Batch Jobs__ to create a `pii_pipeline` scenario.
- In Data Node Explorer, pin `pii_pipeline`, then enable __Pinned only__ if you want a filtered view.

### Raw Input DataNode — UI controls

In the **Jobs page → Advanced Options → Raw Input DataNode (MongoDB)** section:

| Control | What it does |
|---------|-------------|
| Status badge | Shows the resolved backend (`In Memory`, `Mongo`, `Pickle`) and env var context |
| Restart note | Reminds that `ANON_RAW_INPUT_BACKEND` is read at startup — backend changes require a restart |
| __MongoDB write batch slider__ | Sets the number of documents per MongoDB write (`500`–`50,000`, default `5,000`). Applied to `core_config.MONGO_WRITE_BATCH` in the background thread before the DataNode write. |

The write batch value is per-job — you can lower it for very large uploads to reduce memory pressure without restarting.

### Tuning for very large files

Use these settings first:

```bash
export ANON_MODE=standalone
export AN**********=8
export ANON_RAW_INPUT_BACKEND=mongo
export AN******************db://lo*****st:27017/anon_studio
export AN***********************00   # env var default; overridable per-job in UI
```

Then in the **Jobs page → Advanced Options**:

- **Chunk size (rows)**: higher for throughput (`2000`–`5000`), lower if you see memory pressure (`500`–`1000`).
- **MongoDB write batch**: lower (`1000`–`2000`) for very large uploads to avoid OOM on the DataNode write.
- **Compute backend**: `auto` (Dask when row count exceeds threshold) or `dask` to force Dask partitions.

Optional Dask compute backend for very large jobs:

```bash
pip install "dask[da*****me]>=2024.8.0"
export ANON_JOB_COMPUTE_BACKEND=auto   # auto | pandas | dask
export AN*********************00       # auto-switch threshold
```

`auto` keeps pandas for small jobs and uses Dask partitions only when row count exceeds `ANON_DASK_MIN_ROWS`.

CSV uploads now use a staged file-path pipeline into the Taipy task (instead of eager full DataFrame parsing in UI callbacks), so large CSV jobs can run with worker-side `dd.read_csv(...)` when Dask is enabled.

Detailed runbook: `docs/large_dataset_stress.md`.

One command quick check:

```bash
make stress
```

### Stress validation (current baseline)

Latest run (March 5, 2026):

- Route stress: `210` requests, `0` failures, `P95 6.**ms`, `P99 99***ms`
- Task stress: `300,000` DataFrame rows processed successfully
- Mongo-shaped payload stress: `250,000` rows processed successfully
- Full test suite: `82 passed`

### Taipy troubleshooting references (official docs)

- `invoke_long_callback` (periodic status updates): ht************************************************************************************ck/
- GUI callbacks guide: ht*************************************************ks/
- Mongo collection DataNode config: ht**************************************************************************************************************************de
- Core DataNode API (`write`, `append`, `read`): ht***************************************************************************************de/

---

## File Structure

```ini
anonymous_studio/
├── main.py          Taipy CLI entrypoint (`taipy run main.py`)
├── app.py           App state, callbacks, and runtime wiring
├── pages/
│   ├── __init__.py
│   └── definitions.py   Taipy page markup strings
├── core_config.py   taipy.core: DataNodes, Task, Scenario, Orchestrator
├── tasks.py         run_pii_anonymization() — the actual pipeline function
├── pii_engine.py    Presidio wrapper — analyze(), anonymize(), highlight_html()
├── store.py         In-memory store for Kanban cards, appointments, audit log
└── requirements.txt
```

## Entity Types Detected

`EMAIL_ADDRESS` · `PHONE_NUMBER` · `CREDIT_CARD` · `US_SSN` · `US_PASSPORT`
`US_DRIVER_LICENSE` · `US_ITIN` · `US_BANK_NUMBER` · `IP_ADDRESS` · `URL`
`IBAN_CODE` · `DATE_TIME` · `LOCATION` · `PERSON` · `NRP` · `MEDICAL_LICENSE`

## Anonymization Operators

| Operator | Example output |
|----------|---------------|
| `replace` | `<EMAIL_ADDRESS>` |
| `redact`  | _(text deleted)_ |
| `mask`    | `********************` |
| `hash`    | `a6******20...` (SH***56) |

The `hash` operator uses **SH***56 with salt `"anonymous-studio"`**. The same PII value always produces the same hash within this deployment, enabling cross-record correlation without exposing the original text.

---

## Store Backend

Two backends for operational data (pipeline cards, audit log, appointments, PII sessions):

| Backend | When to use |
|---------|-------------|
| `memory` (default) | Development and demos — fast, no external dependency, resets on restart |
| `mongo` | Persistent data across restarts |

### Switching at runtime

Click the **gear** in the top banner → Store Settings. Select **mongo**, enter a URI, click **Apply** — no restart needed.

```sh
mo***db://lo*****st:27***************************************************ss@cluster/anon_studio # Atlas
```

The Store Settings dialog also includes a **Job Data Nodes** explorer so you can inspect Taipy DataNode contents (raw input, anonymized output, stats) without navigating to the Audit page.

**Note:** The store backend (cards, audit, schedule) is separate from the Taipy DataNode backend (job I/O). See *Where Mongo DataNode Connects* above for DataNode configuration.

### MongoDB connection fast-fail

`MongoStore` sets `se*************************00`. If the server is unreachable the dialog shows an error within ~3 seconds and reverts to in-memory (default was 30 s, making Apply appear frozen).

### pymongo

`py***go[srv]>=4.7` is in `requirements.txt`. If missing, Store Settings shows:

```sh
pymongo is not installed. Run: pip install 'pymongo[srv]>=4.7'
```

---

## File Integrity Hash

After uploading a CSV or Excel file the Jobs page shows the **SH***56 of the original file bytes** beneath the filename:

```sh
filename.csv
SH***56  a3**********f9...
```

Verify locally before and after transfer to confirm the file was not altered:

```bash
sh*****um filename.csv          # Linux / WSL
shasum -a 256 filename.csv      # macOS
CertUtil -hashfile filename.csv SH**56   # Windows
```

---

## Security

See **[docs/security.md](docs/security.md)** for the full threat model, applied controls, and production hardening checklist.

**TL;DR — controls in place:**

| Control | Status |
|---------|--------|
| Path traversal on CSV input | Yes `ANON_UPLOAD_DIR` whitelist |
| File upload size cap | Yes 500 MB (`ANON_MAX_UPLOAD_MB`) |
| MIME-type validation | Yes Magic-byte check on xlsx/xls |
| MongoDB query injection | Yes Status / severity whitelists |
| Exception details in browser | Yes Sanitized; full trace server-side only |
| Temp file permissions | Yes `mo******00` |
| Audit log tamper-resistance | Yes MongoDB capped collection (append-only) |
| Authentication | No None — course demo, see security.md |

---

## Performance

See **[docs/performance.md](docs/performance.md)** for:

- Benchmark reference numbers (interactive text, batch jobs, dashboard)
- All applied optimizations with before/after code (OperatorConfig cache, denylist regex cache, `lru_cache` on model options, `store.stats()` rewrite, dashboard `list_sessions()` hoist, pipeline `list_cards()` elimination)
- Tuning knobs (`ANON_JOB_COMPUTE_BACKEND`, `ANON_DASK_MIN_ROWS`, entity filtering, `fast=True`, score threshold)
- spaCy model speed/accuracy tradeoff table
- Known remaining bottlenecks and mitigations
