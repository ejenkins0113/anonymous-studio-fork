# Anonymous Studio — OpenFGA Authorization Stack

**Issues**: #95 (track), #96 (deploy), #97 (model), #98 (enforce), #99 (principals), #100 (demo)
**First-phase scope**: `can_attest` on `card` · `can_export` on `audit_log:global`

---

## Quick start

### Prerequisites
- Docker + Docker Compose (tested with Docker 25+)
- Python 3.9+ (for the seed script)

### 1 — Start OpenFGA

```bash
cd deploy/openfga
docker compose up -d
```

Wait ~10 s, then confirm it's healthy:

```bash
curl http://localhost:8080/healthz
# → {"status":"SERVING"}
```

**Open the Studio** in your browser:
→ **[http://localhost:3000](http://localhost:3000)**

---

### 2 — Seed the store, model, and demo tuples

```bash
python3 seed.py
```

Output:
```
==> Waiting for OpenFGA API at http://localhost:8080 …
    OpenFGA is up.
==> Creating store 'anonymous-studio' …
    Store ID: 01HVMB...
==> Uploading authorization model …
    Model ID: 01HVMC...
==> Writing demo authorization tuples …
    7 tuples written.
==> Wrote deploy/openfga/.env.openfga
```

This writes `deploy/openfga/.env.openfga` with the store and model IDs.

---

### 3 — Enable enforcement in Anonymous Studio

```bash
export OPENFGA_ENABLED=true
source deploy/openfga/.env.openfga   # sets OPENFGA_API_URL / STORE_ID / MODEL_ID
```

Then start the app normally:

```bash
ANON_STORE_BACKEND=memory .venv/bin/taipy run main.py
```

---

## Authorization model

File: [`model.fga`](model.fga)

```
type card
  can_attest  ← reviewer | compliance_officer | admin

type audit_log
  can_export  ← compliance_officer | admin
```

Current model summary:

- `card:can_attest` is granted to `reviewer`, `compliance_officer`, or `admin`
- `audit_log:can_export` is granted to `compliance_officer` or `admin`
- `session:can_view` is granted to `analyst` or `admin`
- `job:can_submit` is granted to `analyst` or `admin`

Only `admin` inherits `compliance_officer` in the current model. The other
roles are not a strict hierarchy.

---

## Demo personas

Seeded via [`seed_tuples.json`](seed_tuples.json):

| Email | Role on card:demo-card-001 | can_attest | can_export audit |
|---|---|---|---|
| `alice@example.com` | `reviewer` | ✅ | ❌ |
| `charlie@example.com` | `compliance_officer` | ✅ | ✅ |
| `bob@example.com` | `analyst` | ❌ | ❌ |
| `admin@example.com` | `admin` | ✅ | ✅ |

---

## Stakeholder demo flow (#100)

### Setup (~2 min)

```bash
# Terminal 1 — FGA stack
cd deploy/openfga && docker compose up -d && python3 seed.py

# Terminal 2 — Anonymous Studio with authz enabled
cd ../..
export OPENFGA_ENABLED=true && source deploy/openfga/.env.openfga
ANON_STORE_BACKEND=memory .venv/bin/taipy run main.py
```

### Scene 1 — Authorization Studio controls the app (analyst blocked)

1. Open **http://localhost:3000** → click the `anonymous-studio` store → **Playground** tab.
2. Run a check:
   - User: `user:bob@example.com`
   - Relation: `can_attest`
   - Object: `card:demo-card-001`
   - Expected: **`{"allowed": false}`**
3. In the Anonymous Studio app (logged in as `bob@example.com` via auth proxy):
   - Navigate to **Pipeline** → click Attest on `demo-card-001`
   - Hit **Confirm** → app shows red error: *"Authorization denied: you do not have the 'reviewer' or 'compliance_officer' role on this card."*
   - Store is never written.

### Scene 2 — Reviewer granted, attest succeeds

1. In OpenFGA Studio, write a new tuple:
   - User: `user:bob@example.com`
   - Relation: `reviewer`
   - Object: `card:demo-card-001`
2. Re-run the check → **`{"allowed": true}`**
3. Back in the app — Bob can now attest the card without code change.

### Scene 3 — Audit export gated to compliance_officer

1. As `bob@example.com` (analyst): go to **Audit Log** → click **Export CSV**
   → Red error: *"Authorization denied: 'compliance_officer' or 'admin' role required."*
2. As `charlie@example.com` (compliance_officer): same action succeeds and downloads the CSV.

---

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENFGA_ENABLED` | No | `false` | Set to `true` to activate enforcement |
| `OPENFGA_API_URL` | Yes (if enabled) | `http://localhost:8080` | OpenFGA HTTP API |
| `OPENFGA_STORE_ID` | Yes (if enabled) | — | Written by `seed.py` |
| `OPENFGA_MODEL_ID` | No | — | Pins to a specific model version |

When `OPENFGA_ENABLED=false` all checks return `True` (bypass mode for local dev / CI).

---

## Stopping the stack

```bash
cd deploy/openfga
docker compose down           # stop, keep data
docker compose down -v        # stop, wipe postgres volume (full reset)
```
