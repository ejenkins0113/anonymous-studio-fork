## Sprint 2 Retrospective

**Team Name:** Group 3 - Anonymous Studio

**Sprint Number:** 2

**Date Range:** 2/23/26 - 3/8/26

**Team Members:** Carley Fant, Diamond Hogans, Sakshi Patel, Elijah Jenkins

---

## Sprint Summary

This sprint focused on a **full rewrite of Anonymous Studio** from the Streamlit PoC (v1) to a production-grade Taipy GUI + taipy.core platform (v2). The team aimed to achieve complete feature parity with v1 while adding new capabilities: background batch job execution, a multi-backend persistence layer (Memory / MongoDB / DuckDB), a Kanban pipeline, a compliance audit trail, Ed25519 attestation, a REST API with Auth0 JWT, Prometheus telemetry, and an appointment scheduler. Eight out of nine planned pipeline cards were delivered, with the encrypt operator (card-007) carrying forward due to a missing UI key-input field. The sprint was also impacted by an early repository archiving incident that required a story recovery effort to reconstruct pipeline card definitions and re-implement the lost export functionality (card-011). Despite these setbacks, the sprint closed at 95.8% feature completion with 239 tests across 14 test files. As in Sprint 1, contribution imbalance remained a challenge — most direct commits came from one team member, with heavy use of GitHub Copilot coding agent to accelerate delivery.

---

## GitHub Project Board Review

### Board View

![Sprint 2 Project Board - Board View](../images/sprint2-board-view.png)

### Table View

![Sprint 2 Project Board - Table View](../images/sprint2-table-view.png)

| Metric | Count |
|--------|-------|
| Tasks Planned at Sprint Start | 9 |
| Tasks Completed | 8 |
| Tasks Not Completed | 1 |

### Completed Tasks:

- **card-001** - Q1 Customer Export Anonymization: De-identify customer names, emails, and SSNs from Q1 export; card advanced to `review`
- **card-002** - HR Records PII Scrub: Remove all PII from historical HR records prior to archival; card advanced to `in_progress` with core anonymization complete
- **card-003** - Research Dataset Anonymization: Apply de-identification with k-anonymity preprocessing; card moved to `done` and Ed25519-attested
- **card-006** - Allowlist / Denylist Support: UI fields and PIIEngine integration for allow_list= and CUSTOM_DENYLIST entity; card moved to `done`
- **card-008** - ORGANIZATION Entity Support: Added ORGANIZATION as the 17th entity in ALL_ENTITIES with spaCy ORG mapping; card moved to `done`
- **card-009** - REST API for PII Detection: Taipy Rest entrypoint with Auth0 JWT middleware; card moved to `done`
- **card-010** - MongoDB Persistence Layer: Full MongoStore backend implementing StoreBase contract; card moved to `done`
- **card-011** - Export Audit Logs as CSV/JSON: Four export callbacks (on_audit_export_csv/json, on_pipeline_export_csv/json) with UI buttons and 7 tests; card moved to `done`

### Scope Changes:

Several tasks were added mid-sprint that were not in the original plan:

- **Repository archiving incident recovery** — The repo was cleaned early in the sprint, removing documentation and the card-011 export implementation. A story recovery effort reconstructed all 15 pipeline card definitions and re-implemented the lost callbacks.
- **GitHub Copilot coding agent adoption** — The team adopted GitHub Copilot as a primary development accelerator, resulting in a large number of automated PRs driving feature delivery.
- **DuckDB store backend** — Added as a third persistence option (alongside Memory and MongoDB) to provide a fast local-file alternative.
- **Audit trail bug fix** — Discovered and fixed a bug where `update_appointment` and `delete_appointment` left no audit entries in all three store backends.
- **Dependency and DevOps updates** — Dependabot bumped `pandas`, `chardet`, `openpyxl`, `actions/labeler`, `actions/checkout`, `actions/github-script`, and `actions/setup-python`. CodeQL workflow was removed due to incompatibility.

Going forward, we will account for repository maintenance and recovery overhead when planning sprint capacity.

---

## Sprint Planning vs. Reality

### Planned vs. Completed Work

Eight out of nine planned pipeline cards were completed. The planned feature work mapped closely to the 23/24 features delivered (95.8%), with the single miss being the encrypt operator UI key field (card-007). However, the distribution of work was again heavily skewed toward one team member.

### Revised Sprint Planning vs. Reality

The actual technical delivery exceeded what was originally scoped — the team shipped not just the v1 feature parity items but nine entirely new capabilities (batch jobs, Kanban pipeline, audit log, attestation, telemetry, Auth0, scheduler, MongoDB, REST API). However, similar to Sprint 1, the workload did not distribute evenly across the team. The majority of direct code commits and Copilot-agent sessions were driven by a single team member. Issue assignments in the GitHub board were not followed through on in terms of code contributions.

The sprint also consumed significant capacity on unplanned recovery work (repository archiving incident, export re-implementation, story documentation). These activities were necessary but were not budgeted in the original sprint plan.

### Contribution Distribution

Based on GitHub contributor data for this sprint:

- Carley Fant: 4 direct commits + primary driver of ~27 GitHub Copilot coding-agent PRs
- Diamond Hogans: 0 commits
- Sakshi Patel: 0 commits
- Elijah Jenkins: 0 commits

**Three out of four team members made no direct code contributions this sprint.** The use of GitHub Copilot coding agent enabled strong delivery velocity, but it does not substitute for hands-on engagement from all team members. As a team, we need to discuss how to ensure everyone is actively participating in Sprint 3.

### Task Scoping

The nine pipeline card stories were appropriately sized. The broader platform rewrite was ambitious for a two-week sprint — the team relied heavily on the Copilot agent to close the gap. Future sprints should scope more conservatively (6–7 stories) to leave room for review, testing, and documentation.

---

## What Went Well

1. **Full Taipy rewrite succeeded** — The complete migration from Streamlit to Taipy GUI + taipy.core was delivered in a single sprint. Background job execution via `invoke_long_callback`, `Scope.SCENARIO`-isolated DataNodes, and reactive state binding all worked as intended with a non-blocking UI.
2. **Feature parity with v1 achieved** — All 11 core PoC features (text detection, entity selector, threshold slider, operators, highlighted output, findings table, allowlist, denylist, detection rationale, ORGANIZATION entity, synthesize operator) were re-implemented and extended.
3. **Clean modular architecture** — The `store/` package (abstract base + three backends), `services/` layer (attestation, auth, telemetry, synthetic, jobs), and `pages/` DSL separation all landed without coupling issues. The `StoreBase` contract makes backend swaps invisible to `app.py`.
4. **Strong test coverage** — 239 tests across 14 test files with dedicated coverage for every major subsystem. `mongomock` made MongoDB tests fast and isolated without requiring a live database.
5. **Export functionality recovered and delivered** — card-011 was reconstructed and fully re-implemented after the archiving incident. Four export callbacks with UI buttons and 7 tests were delivered before sprint close.

---

## What Didn't Go Well

1. **Contribution imbalance persisted from Sprint 1** — Three of four team members made zero direct code contributions. The action items from the Sprint 1 retro (weekly check-ins, 1 merged PR per week) were not followed through on.
2. **Repository archiving incident** — The repository was cleaned early in the sprint, deleting documentation and the card-011 export implementation. This required an unplanned recovery effort and cost 1–2 days of sprint capacity.
3. **Encrypt operator left incomplete (card-007)** — The Presidio `encrypt` backend is fully supported, but the UI key-input field and `OperatorConfig("encrypt", {"key": key})` wiring were not implemented. The story was partially started and carried forward without a clear handoff.
4. **Issue tracking not kept up to date** — Several features that were fully implemented (detection rationale, REST API, batch jobs) were never closed as GitHub issues. The project board did not accurately reflect sprint status throughout the sprint.
5. **Sprint capacity underestimated** — The unplanned work (archiving recovery, DuckDB backend, audit trail bug fix, dependency updates) consumed roughly 20% of sprint capacity that was not budgeted in the plan.

---

## Action Items for Next Sprint

1. **Each team member submits at least one merged PR for a Sprint 3 feature**
   - Assigned to: Diamond Hogans, Sakshi Patel, Elijah Jenkins
   - Pick one open issue from the Sprint 3 backlog, implement it, and open a PR — no exceptions
2. **Weekly written status update by Wednesday**
   - Assigned to: All team members
   - Post a brief update in the group channel: what you worked on, what's blocked, what's next
3. **Close GitHub issues when features are shipped**
   - Assigned to: Whoever merges the PR
   - When a PR closes a feature, link the issue with `Closes #N` and confirm it moves to Done on the board
4. **Define and document the Sprint 3 scope before the sprint starts**
   - Assigned to: Carley Fant (facilitate), All (participate)
   - Agree on 6–7 stories for Sprint 3 before the sprint begins; do not add scope mid-sprint without removing something else

---

## Individual Reflections

**Carley Fant:**
This sprint I drove the full platform rewrite from Streamlit to Taipy, set up the multi-backend store architecture, and used GitHub Copilot coding agent to accelerate delivery across all feature areas. The recovery from the archiving incident took significant time and is a reminder to be more careful with repository operations. For Sprint 3, I want to prioritize getting the rest of the team actively contributing code — I can't and shouldn't be carrying the full implementation load, even with Copilot's help.

**Diamond Hogans:**
\[Please add 2-4 sentences about your contribution this sprint and one thing you want to improve next sprint\]

**Sakshi Patel:**
\[Please add 2-4 sentences about your contribution this sprint and one thing you want to improve next sprint\]

**Elijah Jenkins:**
\[Please add 2-4 sentences about your contribution this sprint and one thing you want to improve next sprint\]

---

## Contribution Transparency Note

Per the assignment guidelines, we are documenting that three team members (Diamond Hogans, Sakshi Patel, and Elijah Jenkins) made no direct code contributions to the repository this sprint. This is a continuation of the imbalance identified in the Sprint 1 retro. The team is addressing this through the action items above for Sprint 3, specifically the requirement for each team member to merge at least one PR.

Commit history: [View on GitHub](https://github.com/cpsc4205-group3/anonymous-studio/commits/main)
