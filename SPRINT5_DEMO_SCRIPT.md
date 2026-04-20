# Sprint 5 Demo Script - Anonymous Studio
**Capstone Project | CPSC 4205 | Spring 2026**

---

## Opening (2 min)

### The Problem
"Healthcare and legal organizations need to anonymize PII in large datasets. Manual redaction is error-prone, slow, and doesn't scale. They need automated detection, multiple anonymization strategies, audit trails, and role-based access control."

### What We Built
"Anonymous Studio is a production-ready PII anonymization platform built with Taipy, Presidio, and OpenFGA. It handles real-time text analysis, batch processing of large datasets, fine-grained authorization, and maintains complete audit trails."

---

## System Architecture (2 min)

### Tech Stack
- **Frontend/Backend**: Taipy GUI + Core (reactive UI, background job orchestration)
- **PII Detection**: Microsoft Presidio (15+ entity types)
- **Authorization**: OpenFGA (fine-grained, relationship-based)
- **Storage**: Multi-backend (Memory, DuckDB, MongoDB)
- **Infrastructure**: Docker Compose for auth/monitoring services

### Key Features
- Real-time PII detection and anonymization
- Batch processing with progress tracking
- Role-based access control (Admin, Analyst, Reviewer, Guest)
- Pipeline management with Kanban workflow
- Complete audit logging
- Notification system with user preferences

---

## Live Demo (12 min)

### 1. Quick Text Analysis (2 min)
**Navigate to: Analyze Text page**

**Say**: "Let me show you real-time PII detection..."

**Actions**:
1. Paste sample text with SSN, email, phone number
2. Click "Analyze"
3. Show detected entities highlighted
4. Demonstrate 4 operators:
   - **Replace**: `<EMAIL_ADDRESS>`
   - **Redact**: _(text deleted)_
   - **Mask**: `********************`
   - **Hash**: `a665a45920...` (SHA-256, consistent)
5. Download anonymized result

**Key Point**: "The hash operator uses SHA-256 with a salt, so the same PII always produces the same hash - enabling cross-record correlation without exposing original data."

---

### 2. Batch Job Processing (3 min)
**Navigate to: Upload & Jobs page**

**Say**: "For large datasets, we have background job processing with progress tracking..."

**Actions**:
1. Upload CSV file with PII
2. Show file integrity hash (SHA-256)
3. Configure job settings (chunk size, operator)
4. Submit job
5. Show progress bar updating
6. Pipeline card auto-created in "In Progress"
7. View anonymized output in preview table
8. Download results

**Key Point**: "Jobs run in background threads using Taipy's orchestrator. For production, we support Dask for datasets over 250k rows and MongoDB for distributed worker access."

---

### 3. Authorization System (3 min)
**Navigate to: Auth page**

**Say**: "Sprint 5 focused heavily on security hardening. Let me demonstrate our OpenFGA-based authorization..."

**Actions**:
1. Show demo mode role switcher
2. Switch roles and show permission differences:
   - **Admin**: Can delete cards, export audit logs, cancel jobs
   - **Analyst**: Can submit jobs, create cards
   - **Reviewer**: Can update cards, view audit
   - **Guest**: Read-only access
3. Try to export audit log as Guest → DENIED
4. Switch to Admin → SUCCESS

**Key Point**: "Sprint 5 closed critical security gaps - we found that legacy audit export handlers were bypassing OpenFGA checks. Now all export paths enforce proper authorization."

---

### 4. Pipeline Management (2 min)
**Navigate to: Pipeline page**

**Say**: "The pipeline uses a Kanban workflow for compliance tracking..."

**Actions**:
1. Show Kanban board: Backlog → In Progress → Review → Done
2. Drag a card between statuses
3. Click card to show details (attestation, compliance officer)
4. **Sprint 4 feature**: Use status filter dropdown
5. Export filtered cards (e.g., only "Review" status) as CSV

**Key Point**: "Pipeline cards are automatically created when jobs complete. Compliance officers can attest to review completion, and everything is logged."

---

### 5. Settings & Notifications (1 min)
**Navigate to: Settings page**

**Say**: "We integrated a notification system with user preferences..."

**Actions**:
1. Show email notification toggle
2. Show in-app notification toggle
3. Toggle settings and save

**Key Point**: "This was integrated from PR #120 - adds scheduler improvements and centralized notification flushing during navigation."

---

### 6. Audit Log (1 min)
**Navigate to: Audit page**

**Say**: "Every action is logged with timestamp, user, severity, and details..."

**Actions**:
1. Show audit entries
2. Filter by severity (info, warning, error)
3. Show export functionality (Admin only)

**Key Point**: "The audit log is immutable and uses MongoDB capped collections in production for append-only guarantees."

---

## Technical Deep Dive (3 min)

### Testing & Quality
- **82+ passing tests**
- Integration tests covering full workflow
- **Sprint 5**: Added OpenFGA seed validation tests
- **Sprint 5**: Extended authz tests for audit export denial scenarios

### Security (Sprint 5 Focus)
✅ **Fixed authorization bypass** in audit export handlers  
✅ **Aligned OpenFGA model** with runtime enforcement  
✅ **Added regression tests** for security gaps  
✅ **Dependency updates** for vulnerability fixes  

**Say**: "Sprint 5 was about production readiness - closing security gaps, ensuring our authorization model matches actual enforcement, and adding comprehensive regression tests."

### Performance
- Handles **300k+ row datasets**
- Dask integration for parallel processing
- MongoDB batching for memory efficiency
- Configurable chunk sizes (500-5000 rows)

### Production Architecture
- **Docker Compose stacks** for OpenFGA (PostgreSQL backend), Auth0 proxy (Redis sessions), Grafana monitoring
- **Multi-backend storage**: Memory (dev), DuckDB (local), MongoDB (production)
- **Auth0 integration** ready with JWT validation
- **Prometheus metrics** for observability

---

## Sprint 5 Contributions Summary

### Security Hardening (Critical)
- Fixed authorization bypass in audit export handlers
- Aligned OpenFGA seed model with runtime job permissions
- Added comprehensive authz regression tests
- Closed enforcement gaps in `can_submit` and `can_cancel` permissions

### System Integration
- Merged notification system improvements (PR #120)
- Integrated settings UI for user notification preferences
- Enhanced scheduler logging and reliability
- Resolved merge conflicts from multiple concurrent PRs

### Quality Assurance
- Extended `tests/test_authz.py` with deny/unauthenticated tests
- Added `tests/test_openfga_seed.py` for model validation
- Dependency security updates (Dependabot PRs)
- Documentation updates in OpenFGA README

---

## Closing Statement

**Say**: "This system went from concept to production-ready in one semester. It handles enterprise-grade PII detection with 15+ entity types, enforces fine-grained authorization with OpenFGA, processes large datasets efficiently with Dask, and maintains complete audit trails. Sprint 5 ensured it's secure and reliable enough to actually deploy in a real healthcare or legal environment."

### What Makes This Production-Ready
✅ Comprehensive authorization with OpenFGA  
✅ Complete audit logging (immutable, append-only)  
✅ Multi-backend storage for scalability  
✅ Background job processing with progress tracking  
✅ Security-hardened with regression tests  
✅ Docker infrastructure for supporting services  
✅ 82+ tests covering critical workflows  

---

## Quick Commands Reference

```bash
# Start the app
export ANON_GUI_USE_RELOADER=1
export ANON_GUI_DEBUG=1
taipy run main.py

# Open browser
http://localhost:5000

# Start OpenFGA (optional, for auth demo)
cd deploy/openfga
docker compose up -d
bash seed.sh

# Run tests
pytest tests/
```

---

## Sample Data for Demo

### Quick Text Sample
```
Patient John Doe (SSN: 123-45-6789) contacted us at john.doe@email.com 
or call 555-123-4567. Credit card: 4532-1234-5678-9010.
```

### Expected Detections
- PERSON: John Doe
- US_SSN: 123-45-6789
- EMAIL_ADDRESS: john.doe@email.com
- PHONE_NUMBER: 555-123-4567
- CREDIT_CARD: 4532-1234-5678-9010

---

## Backup Talking Points (If Needed)

### If Asked About Team Contributions
"This was a collaborative effort with contributions across sprints. My focus areas included the authorization system integration, pipeline export features, security hardening in Sprint 5, and overall system architecture."

### If Asked About Challenges
"The biggest challenge was integrating OpenFGA's relationship-based authorization model with Taipy's callback system. We had to ensure every UI action properly checked permissions without blocking the reactive interface."

### If Asked About Future Work
"Next steps would include: containerizing the main Taipy app, adding more PII entity types, implementing data retention policies, and building a REST API for headless operation."

---

**Good luck! You built something impressive. Own it.** 🚀
