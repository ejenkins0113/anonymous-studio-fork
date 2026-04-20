## Sprint 4 Retrospective

**Team Name:** Group 3 - Anonymous Studio

**Sprint Number:** 4

**Date Range:** 03/23/26 - 04/05/26

**Team Members:** Carley Fant, Diamond Hogans, Sakshi Patel, Elijah Jenkins

---

## Sprint Summary

This sprint focused on improving system functionality and implementing new features related to PII detection, pipeline workflows, and API integration. Key work included implementing new features, fixing bugs, and integrating APIs into the system.

**Carley Fant:** This sprint focused on delivering pipeline export filtering (#112), saving and downloading de-identification session results (#14), and resolving critical bugs that were blocking the entire team from running the app locally — including a dead FastAPI stub silently corrupting PII results, a missing `schedule` dependency, a dashboard NameError, and a scheduler typo. A CI guard was also added to block incompatible FastAPI code from being merged in future PRs.

**Diamond Hogans:** [Summary]

**Sakshi Patel:** This sprint focused on improving system functionality and implementing new features related to PII detection, pipeline workflows, and API integration. Key work included implementing new features, fixing bugs, and integrating APIs into the system.

**Elijah Jenkins:** [Summary]

---

## GitHub Project Board Review

### Board View

![Sprint 4 Project Board - Board View](../../images/sprint4-board-view.png)

### Table View

![Sprint 4 Project Board - Table View](../../images/sprint4-table-view.png)

| Metric | Count |
|--------|-------|
| Tasks Planned at Sprint Start | |
| Tasks Completed | |
| Tasks Not Completed | |

### Completed Tasks

**Carley Fant:**
- **Issue #112** — Pipeline history export with status filter: status dropdown (All / backlog / in_progress / review / done) on Pipeline page; filename reflects selection (e.g. `pipeline_in_progress.csv`); 10/10 tests passing; merged in PR #114
- **Issue #14** — Save & download de-identification run results: save sessions with full metadata, load back into UI, download anonymized `.txt` + entity `.csv` directly from saved record without reloading; merged in PR #114; closed 2026-04-05
- **Bug fix** — Removed dead FastAPI stub introduced by teammate that was overwriting real PII detection results and breaking local dev for all team members
- **Bug fix** — Fixed `raw_labels` NameError crashing dashboard perf chart
- **Bug fix** — Fixed `list_appointment` → `list_appointments` typo in scheduler sync
- **Dependency fix** — Added missing `schedule>=1.2.0` to `requirements.txt` (teammates could not run locally)
- **CI guard** — Added GitHub Actions check blocking `from fastapi` / `import fastapi` in `app.py` on all PRs to main

**Diamond Hogans:** [Completed tasks]

**Sakshi Patel:** [Completed tasks]

**Elijah Jenkins:** [Completed tasks]

### Not Completed

- **Issue #98** — Enforce OpenFGA permission checks in Taipy workflow actions (assigned to Elijah Jenkins) — no work started; carry forward
- **Issue #42** — Schedule review appointments linked to pipeline cards (assigned to Elijah Jenkins) — no work started; carry forward

### Scope Changes

[Brief explanation of any mid-sprint additions or removals]

---

## Sprint Planning vs. Reality

### Planned vs. Completed Work

**Carley Fant:** Both planned issues (#112 and #14) were completed. Mid-sprint additions included removing a dead FastAPI stub introduced by a teammate that was silently corrupting PII detection results and blocking the app from running locally. A CI check was added to prevent it from being re-introduced. The `schedule` dependency fix also unblocked teammates from running the app at all.

**Sakshi Patel:** The sprint was successfully executed with all planned issues completed. Unlike earlier sprints where tasks were delayed or not started, this sprint showed strong alignment between planning and execution. Tasks were well-defined and manageable, allowing steady progress throughout the sprint.

**Diamond Hogans:** [Planning vs. reality]

**Elijah Jenkins:** [Planning vs. reality]

### Contribution Distribution

Based on GitHub contributor data for this sprint:

- **Carley Fant:** 2 issues closed (#112, #14), 7 commits merged to `main` via PR #114 and PR #117, CI workflow update, dependency fix, 3 bug fixes, retrospective documentation
- **Diamond Hogans:** [Contribution summary]
- **Sakshi Patel:** [Contribution summary]
- **Elijah Jenkins:** [Contribution summary]

---

## What Went Well

- All assigned issues for Carley Fant were completed successfully
- Pull requests were created, tested, and merged without major issues
- CI guard added to enforce no-FastAPI rule automatically going forward
- `schedule` dependency fix unblocked all teammates from running locally
- 10/10 pipeline export tests passing

[Additional team items]

---

## What Didn't Go Well

- FastAPI code introduced by a teammate broke the app for all local developers and had to be removed and guarded against mid-sprint
- Issues #98 and #42 (assigned to Elijah Jenkins) had no work started during the sprint
- Teammates were unable to run the app locally due to missing documentation/dependencies

[Additional items]

---

## Action Items for Next Sprint

- **Improve local setup documentation** — Assigned to: Carley Fant
- **Each team member must run and test the app locally before opening a PR** — Assigned to: All team members
- **Complete Issue #98 (OpenFGA enforcement)** — Assigned to: Elijah Jenkins
- **Complete Issue #42 (Schedule review appointments)** — Assigned to: Elijah Jenkins

[Additional items]

---

## Individual Reflections

**Carley Fant:**
This sprint I completed both assigned issues (#112 and #14) and resolved several unplanned critical bugs that were blocking the whole team — including a FastAPI stub a teammate introduced that was silently corrupting PII detection output and preventing local setup. Adding a CI guard ensures this class of issue can't make it into main again. Compared to Sprint 3 where team imbalance limited overall output, this sprint felt more productive on my end despite having to absorb teammate cleanup work. For next sprint I want to see teammates self-sufficient enough to run and test locally before opening PRs.

**Diamond Hogans:** [2-4 sentences]

**Sakshi Patel:** In this sprint, my primary contribution was completing issues where I worked on implementing features, fixing bugs, and integrating APIs into the application. Compared to earlier sprints where I had limited contribution, I significantly improved by actively coding, testing my work, and submitting pull requests. This sprint helped me gain confidence and better understand the project. For the next sprint, I want to focus on maintaining consistency and improving communication with my team.

**Elijah Jenkins:** [2-4 sentences]
