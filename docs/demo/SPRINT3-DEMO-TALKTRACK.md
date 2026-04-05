# Sprint 3 Demo — Talk Track

**Anonymous Studio · Group 3 · CPSC 4205 · Spring 2026**
**Presenter: Carley Fant**

> **Target runtime: 8–12 minutes**
> Architecture walk = ~3 min · Live demo = ~7 min

---

## BEFORE YOU START — Setup Checklist

- [ ] App is running: `cd v2_anonymous-studio && python app.py`
- [ ] MongoDB is up (local or Atlas — check `.env`)
- [ ] LikeC4 interactive view open in a second browser tab:

```bash
cd ~/servers
npx likec4@1.53.0 serve .
# opens http://localhost:5173
```

- [ ] Demo seed data loaded: `python scripts/demo_seed.py`
- [ ] Exported PNGs ready in `docs/demo/exports/` (see ticket for export commands)
- [ ] VS Code has `anonymous_studio.c4` open as fallback if serve fails

---

## PART 1 — Architecture Walk (LikeC4) · ~3 min

> *Switch to LikeC4 browser tab (localhost:5173)*

---

### SLIDE 1 · L1 System Context (`asContext`)

**Say:**

> "Before I show you the app, I want to give you 30 seconds of big picture.
> Anonymous Studio sits between the data analyst — who needs to de-identify sensitive data —
> and three external systems: Auth0 for identity, Prometheus for metrics, and Grafana for observability.
> Everything flows through one platform."

**Click:** Zoom into `studio` box.

---

### SLIDE 2 · L2 Containers (`asContainers`)

**Say:**

> "Inside the platform there are five major containers.
> The Taipy GUI is what the user sees — six pages.
> Behind it, Taipy Core manages a DAG of tasks — it's the job orchestration engine.
> The PII Engine is Presidio plus spaCy — that's the actual detection and anonymization brain.
> The Task Worker runs those jobs in the background so the UI stays responsive.
> And everything lands in the Operational Store — backed by MongoDB in production."

**Point to:** `authSvc` → `extAuth0` arrow.

> "Auth0 JWT validation is wired in — the REST API is fully protected."

---

### SLIDE 3 · Dynamic: Batch Job Flow (`asBatchJobFlow`)

**Say:**

> "Here's what happens end to end when a compliance officer uploads a CSV.
> They upload through the Jobs page.
> The Job Service validates the file — magic byte check, 500MB cap, path traversal prevention.
> Taipy Core dispatches the anonymize task to the background worker.
> The PII Engine processes it chunk by chunk, writing progress back to a registry the UI polls.
> When done, the output is written back to the store, an audit entry is logged, and the analyst
> gets a signed download."

---

### SLIDE 4 · Dynamic: Attestation Flow (`asAttestationFlow`)

**Say:**

> "After a job completes, the compliance officer moves the pipeline card to Review and clicks Attest.
> That triggers an Ed25519 digital signature — the payload is hashed, signed with the private key,
> and the attestation record is written to the immutable audit log.
> The audit page shows a verification badge. That signature cannot be modified or deleted —
> it's a capped MongoDB collection."

---

## PART 2 — Live App Demo · ~7 min

> *Switch to app tab (localhost:5000)*

---

### STOP 1 · Dashboard (30 sec)

**Say:**

> "Dashboard loads live KPIs — total sessions processed, entity count, average job duration,
> and success rate. The pipeline summary shows how many cards are in each stage right now."

**Point to:** entity heatmap if visible.

> "Entity heatmap breaks down what types of PII we're seeing across all sessions —
> names, emails, SSNs, phone numbers."

---

### STOP 2 · Analyze Text (90 sec)

**Say:**

> "This is the quick-analysis page. I'll paste in some sample text."

**Action:** Paste — `"Patient John Smith, DOB 01/14/1985, SSN 412-34-5670, called from 555-867-5309 regarding account #98234."`

> "I'll select the entity types I care about — names, SSNs, phone numbers — and pick an anonymization operator.
> I'll use **replace** so the entity type label substitutes in."

**Click Analyze.**

> "Presidio detected five entities. Watch the highlighted output."

**Switch operator to mask.**

> "Now with mask, everything redacts to asterisks. This operator choice gets saved with the session."

**Click Save Session.**

> "Session is persisted to MongoDB. I can attach it to a pipeline card next."

---

### STOP 3 · Pipeline Board (90 sec)

**Say:**

> "This is the compliance workflow Kanban — Backlog, In Progress, Review, Done.
> I'll create a new card for the dataset I just processed."

**Action:** Create card, attach the saved session.

> "Session attached — the card now knows which anonymization run it's tracking.
> I'll move it to In Progress."

**Action:** Move card right.

> "Status transition is enforced. You can only move forward one stage or back one.
> Every move writes an audit event — we'll see that in a moment."

**Action:** Move to Review, click Attest.

> "Attestation signs the payload. The Ed25519 signature is stored on the card record."

---

### STOP 4 · Audit Log (60 sec)

**Say:**

> "Every action in the system lands here — immutable, append-only.
> Card created, status changed, session attached, attestation signed — all timestamped and actor-tagged."

**Filter by:** card resource type.

> "I can filter by resource, actor, or severity.
> This is the compliance officer's source of truth."

> "And from here — export." *(click export if implemented)*

---

### STOP 5 · Jobs / File Upload (60 sec) — *if implemented by demo day*

**Say:**

> "For batch processing, the Jobs page accepts CSV or plain text uploads.
> The file is validated, parsed, and submitted as a Taipy Core scenario.
> Progress is polled live. When complete, the analyst gets a signed download of the anonymized file."

---

### STOP 6 · Schedule (30 sec)

**Say:**

> "Finally the Schedule page — compliance officers can book review appointments
> linked directly to pipeline cards. The scheduler daemon auto-advances cards
> when the appointment time arrives."

---

## CLOSING (30 sec)

**Say:**

> "So what Sprint 3 delivered: a complete compliance workflow —
> detect, anonymize, track, attest, audit, export.
> The architecture you saw at the start is fully realized.
> Every layer from the LikeC4 diagram is live in this app."

---

## FALLBACK NOTES

| If... | Then... |
|-------|---------|
| MongoDB isn't up | Switch `STORE_BACKEND=memory` in `.env`, restart — MemoryStore has demo seed |
| LikeC4 serve fails | Open `anonymous_studio.c4` in VS Code — extension renders inline |
| Attestation errors | Check `ATTESTATION_PRIVATE_KEY_PATH` in `.env` — run `python scripts/generate_attestation_key.py` first |
| App crashes on start | `pip install -r requirements.txt` then `python -m spacy download en_core_web_lg` |

---

## Q&A PREP

| Question | Answer |
|----------|--------|
| "Why Taipy instead of Flask?" | Taipy gives us the job orchestration DAG for free — scenarios, data nodes, background workers. Flask would need Celery + Redis for the same thing. |
| "Is this production-ready?" | Auth0 JWT validation is wired in, secrets are env-var gated, audit log is capped and append-only. The deploy/ folder has nginx + Auth0 proxy Docker Compose. Yes for a capstone scope. |
| "What's the Reflex folder?" | Experimental UI rewrite prototype — not in scope for this sprint, just exploratory. |
| "Who built what?" | *(see Sprint 3 retro for contribution transparency note)* |
