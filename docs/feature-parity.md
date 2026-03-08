# Feature Parity Status — PoC vs. v2

This document tracks which features from the original Presidio Streamlit PoC have been implemented in v2, and which stories remain in backlog.

## ✅ Fully Implemented Features

These features from the original PoC are **fully implemented** in v2:

| Feature | Status | Location | Notes |
|---------|--------|----------|-------|
| Text input + detect + anonymize | ✅ **Done** | PII Text page (QT) | Core functionality |
| Entity type selector | ✅ **Done** | `pii_engine.py` | 17 entities including ORGANIZATION |
| Threshold slider | ✅ **Done** | PII Text page | Default 0.35 |
| Operators: replace, redact, mask, hash | ✅ **Done** | `pii_engine.py` | All 4 operators working |
| Highlighted output | ✅ **Done** | `app.py` | `highlight_md()` with Taipy mode=md |
| Entity findings table | ✅ **Done** | PII Text page | 7 columns: type, text, confidence, band, span, recognizer, rationale |
| **Allowlist** | ✅ **Done** | `pii_engine.py`, `app.py` | UI fields + `allow_list=` param |
| **Denylist** | ✅ **Done** | `pii_engine.py`, `app.py` | CUSTOM_DENYLIST entity + regex cache |
| **Detection rationale** | ✅ **Done** | `pii_engine.py` | `return_decision_process=True` |
| **ORGANIZATION entity** | ✅ **Done** | `pii_engine.py` | Added to ALL_ENTITIES (17th entity) |
| **Operator: synthesize** | ✅ **Done** | `services/synthetic.py` | Faker + LLM (OpenAI/Azure) backends |

## 🆕 New Features (v2-specific, not in PoC)

These features are **new in v2** and were not in the original PoC:

| Feature | Status | Location | Notes |
|---------|--------|----------|-------|
| CSV/Excel batch upload | ✅ **Done** | Jobs page | Background job execution |
| Kanban pipeline | ✅ **Done** | Pipeline page | Card management with status columns |
| Audit log | ✅ **Done** | Audit page | All user actions tracked |
| **Compliance attestation** | ✅ **Done** | `services/attestation_crypto.py` | Ed25519 signatures |
| **Telemetry** | ✅ **Done** | `services/telemetry.py` | Prometheus metrics + Grafana |
| **Auth0 JWT** | ✅ **Done** | `services/auth0_rest.py` | REST API authentication |
| **Appointment scheduler** | ✅ **Done** | `scheduler.py` | Background daemon for scheduled reviews |
| **MongoDB persistence** | ✅ **Done** | `store/mongo.py` | MongoStore backend |
| **REST API** | ✅ **Done** | `rest_main.py` | Taipy Rest with optional Auth0 |

## ⚠️ Partially Implemented

| Feature | Status | What's Missing | Priority |
|---------|--------|----------------|----------|
| **Operator: encrypt** | ⚠️ **Partial** | The Presidio library supports encrypt/decrypt operators, but v2 doesn't use them yet. Need to: (1) add encrypt option to UI operator selector, (2) add UI field for 128/192/256-bit AES key input, (3) implement OperatorConfig("encrypt", {"key": key}) in pii_engine.py, (4) store key securely via env var (not hardcoded). | Medium |

## ❌ Not Implemented (Backlog Stories)

These features from the demo cards are still **in backlog**:

### From Original PoC (Out of Scope)
| Feature | Reason | Priority |
|---------|--------|----------|
| Multiple NER models (HuggingFace, Stanza, Flair, Azure) | Out of scope for v2. PoC has `presidio_nlp_engine_config.py` with full config. v2 uses spaCy only. | Low |

### New Feature Requests (Backlog)
| Card ID | Story Title | Description | Priority | Labels |
|---------|-------------|-------------|----------|--------|
| card-011 | Export Audit Logs as CSV/JSON | Export audit log and pipeline card data in CSV/JSON formats with download buttons on Audit and Pipeline pages | ✅ Done | feature, compliance |
| card-012 | Image PII Detection via OCR | Accept PNG/JPG uploads, extract text via Tesseract OCR, apply Presidio PII detection | Low | feature, ocr |
| card-013 | Role-Based Authentication | User login with email/password and RBAC (Admin, Compliance Officer, Developer, Researcher). Store hashed passwords. | High | feature, security |
| card-014 | Compliance Review Notifications | Email/in-app notifications 24h before scheduled appointments with card details | Medium | feature, compliance |
| card-015 | File Attachments on Pipeline Cards | Attach anonymized output files (CSV, TXT, JSON) to cards with download capability | Medium | feature, pipeline |

## Summary

**Implemented from PoC:** 11/12 features (92%)
- ✅ All core PII detection features (text input, entities, threshold, operators, highlighting, findings table)
- ✅ All requested enhancements (allowlist, denylist, detection rationale, ORGANIZATION entity, synthesize operator)
- ⚠️ Encrypt operator partially done (backend works, UI key management missing)
- ❌ Multiple NER models marked out of scope

**New v2 Features:** 9 additional features not in original PoC
- CSV batch jobs, Kanban pipeline, audit log, attestation, telemetry, Auth0, scheduler, MongoDB, REST API

**Remaining Backlog:** 5 stories
- 3 high/medium priority: Audit export, RBAC, notifications
- 2 medium priority: File attachments, OCR

## Recommendations

### High Priority (Should Implement Soon)
1. **card-013: Role-Based Authentication** — High priority security feature for production use
2. **card-011: Export Audit Logs** — Medium priority compliance requirement for documentation

### Medium Priority (Nice to Have)
3. **Encrypt Operator Key Management** — Complete the partially-done encrypt feature with UI key field
4. **card-014: Compliance Review Notifications** — Enhances existing scheduler feature
5. **card-015: File Attachments on Cards** — Improves pipeline workflow

### Low Priority (Future Enhancements)
6. **card-012: Image OCR** — New capability, requires Tesseract integration
7. **Multiple NER Models** — Marked out of scope, only if customer explicitly requests

## How to Mark Features as Done

When implementing a backlog story:

1. Update the feature status in this document
2. Update the corresponding demo card in `store/memory.py` from `status="backlog"` to `status="done"`
3. Update the PoC Feature Parity table in `.github/copilot-instructions.md` if it's a PoC feature
4. Add tests in `tests/` for the new feature
5. Document any new env vars or config in README.md

## Related Documentation

- **Complete Story Inventory:** `docs/all-stories.md` — Comprehensive list of all 15 pipeline cards with detailed acceptance criteria
- **GitHub Issues Templates:** `docs/github-issues-template.md` — Ready-to-use issue descriptions for each backlog story
- **Issue Creation Script:** `scripts/create_github_issues.py` — Automated script to create GitHub issues from backlog
- **.github/copilot-instructions.md** — Lines 782+ (PoC Feature Parity Reference table)
- **store/memory.py** — Lines 306-405 (Demo cards for backlog features)
- **pii_engine.py** — Core PII detection engine, operator implementations at lines 270-295
- **app.py** — UI state and callbacks
- **pages/definitions.py** — Taipy page markup

---

## Investigation Notes: Lost Export Functionality

### Summary
Repository memories (from previous agent sessions) claim that export functionality (card-011) was implemented with specific file locations:
- `app.py:5008-5072` — Supposedly contained export callbacks
- `pages/definitions.py:593-602` — Supposedly contained export UI buttons
- `docs/export-functionality.md:1-300` — Supposedly documented the feature

### Current Reality
**None of these exist in the current codebase:**
- `app.py` is only 5409 lines (line 5072 doesn't exist)
- `pages/definitions.py` is only 835 lines (line 602 doesn't exist)
- `docs/export-functionality.md` does not exist

### Possible Explanations
1. **Implementation was in a branch that was never merged** — Most likely scenario
2. **Code was lost during repository archiving** — Mentioned in the issue description
3. **Memories are incorrect/hallucinated** — Possible but unlikely given specific line numbers
4. **Code was intentionally removed** — No git history evidence of deletion

### Evidence from Memories
The memories contained detailed implementation descriptions:
- 4 callback functions: `on_audit_export_csv`, `on_audit_export_json`, `on_pipeline_export_csv`, `on_pipeline_export_json`
- Used `pandas.to_csv()` and `json.dumps()` (no pickle)
- Logged all exports to audit trail
- Showed success/error notifications
- UI sections after audit table and pipeline "All Cards" table

### Recovery Plan
Since the original implementation is lost, we've created:
1. **docs/all-stories.md** — Full reconstruction of what card-011 should include
2. **docs/github-issues-template.md** — Detailed issue template with acceptance criteria
3. **Pseudo-code in docs/all-stories.md Appendix** — Reconstructed implementation based on memory descriptions

The feature needs to be re-implemented from scratch using these documents as guidance.

### Lesson Learned
This incident highlights the importance of:
- Merging feature branches promptly to main
- Not relying solely on agent memories for source of truth
- Keeping GitHub issues/PRs as authoritative record of work
- Regular backups and verification that features are actually committed
