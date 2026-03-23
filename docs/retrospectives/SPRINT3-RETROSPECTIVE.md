## Sprint 3 Retrospective

**Team Name:** Group 3 - Anonymous Studio

**Sprint Number:** 3

**Date Range:** 3/9/26 - 3/22/26

**Team Members:** Carley Fant, Diamond Hogans, Sakshi Patel, Elijah Jenkins

---

## Sprint Summary

This sprint focused on two primary goals: (1) completing the auth proxy identity-binding work that was partially shipped in Sprint 2, and (2) beginning the role-based access control (RBAC) story (card-013 / issue #43) that was explicitly targeted as a Sprint 3 deliverable. A small UI enhancement, the detection rationale show/hide toggle (PR #63), was also merged. At the sprint's close, the detection logic toggle and the auth proxy validation (issue #94) were confirmed complete, but role-based authentication (issue #43) was not started and carried forward to Sprint 4. Five new OpenFGA/AuthZ issues (#95–#100) were scoped and added to the backlog at the end of the sprint to lay the groundwork for an authorization control plane. Contribution imbalance continued for the third consecutive sprint: all direct code contributions came from a single team member. Two of four team members made no direct code contributions despite previous action items requiring each teammember to merge at least one PR / sprint cycle.

---

## GitHub Project Board Review

### Board View

![Sprint 3 Project Board - Board View](../../images/sprint3-board-view.png)

### Table View

![Sprint 3 Project Board - Table View](../../images/sprint3-table-view.png)

| Metric | Count |
|--------|-------|
| Tasks Planned at Sprint Start | 3 |
| Tasks Completed | 2 |
| Tasks Not Completed | 1 |

### Completed Tasks:

- **PR #63** - Detection Rationale Toggle: Added user-controlled show/hide toggle for the Recognizer and Rationale columns in the Entity Evidence table on the Analyze Text page; merged to `main` on 2026-03-22
- **Issue #94** - Auth Proxy Integration Test: Auth proxy identity binding (`on_init` reads `X-Auth-Request-User/Email/Groups` headers; `on_attest_confirm` gates on `gui_auth_source == "proxy"`; nginx strips spoofed headers before forwarding) verified and closed on 2026-03-23

### Not Completed:

- **Issue #43** - Role-Based Authentication: Planned as the primary Sprint 3 feature (support for Admin, Compliance Officer, Developer, and Researcher roles with login/password, MongoDB-backed auth, and role-gated UI pages); assigned to Elijah Jenkins; no work started — carried forward to Sprint 4

### Scope Changes:

The following items were added to the backlog at the end of Sprint 3 and were not in the original sprint plan:

- **OpenFGA/AuthZ epic** — Five new issues (#96–#100) and one epic (#95) were created on 2026-03-22 to introduce OpenFGA as an authorization engine alongside Auth0 / oauth2-proxy authentication. Scope includes deploying OpenFGA + OpenFGA Studio, defining an authorization model for cards/sessions/audit exports/jobs/attestations, adding an OpenFGA client in Anonymous Studio, enforcing checks on sensitive actions, and building a stakeholder-facing demo flow.
- **PR #101 (open) — Stale-PR audit and integration**: A batch integration PR was opened to assess all nine open PRs targeting `main`, integrate three clean ones (before/after sample display, session-to-card attachment, chart/metric CSS fixes), and close out stale or superseded PRs.

Going forward, scope additions mid-sprint should be logged as Sprint 4 items immediately rather than being appended to the current sprint without capacity adjustments.

---

## Sprint Planning vs. Reality

### Planned vs. Completed Work

Two of three planned items were completed. The primary planned feature — role-based authentication (issue #43) — was not started. The delivered items were a UI polish feature (rationale toggle, PR #63) and a devops validation item (auth proxy test, issue #94). The sprint was therefore significantly under-delivered against the plan.

### Revised Sprint Planning vs. Reality

Sprint 3 was lighter than expected in both scope and delivery. The team added the OpenFGA epic at the end of the sprint, which is a meaningful architecture investment for Sprint 4, but it does not offset the failure to start the RBAC story that was the sprint's stated primary goal. The detection rationale toggle was a small, clean PR — the kind of task any team member could have taken on independently.

The Sprint 2 action items (at least one merged PR per team member, weekly written status updates, closing issues when features ship) were not followed through for the third consecutive sprint. Issue #43 was assigned to Elijah Jenkins but received no activity during the sprint.

### Contribution Distribution

Based on GitHub contributor data for this sprint:

- Carley Fant: 1 direct commit (merged PR #63 on 2026-03-22) + initiated GitHub Copilot coding-agent sessions (PR #101 stale-PR audit, PR #102 sprint-3 retro, issues #95–#100 OpenFGA epic)
- Diamond Hogans: 0 commits
- Sakshi Patel: 0 commits
- Elijah Jenkins: 0 commits

**Three out of four team members made no direct code contributions this sprint.** This is the third consecutive sprint with this pattern. Diamond Hogans has a specific subtask in the RBAC issue (#43: "Build user registration/login interface") that was not touched. Elijah Jenkins was the assignee for issue #43 and took no action. Sakshi Patel has an open schema-design issue (#67) that was also inactive.

### Task Scoping

The detection rationale toggle (PR #63) and auth proxy validation (issue #94) were appropriately sized — both could have been taken on by any team member independently. Role-based authentication (issue #43) is larger, but its subtasks are individually scoped and could have been picked up in parallel. Sprint 4 must open with explicit per-person assignments for the OpenFGA epic.

---

## What Went Well

1. **Detection rationale toggle delivered cleanly** — PR #63 was a focused, well-tested change (three files, two commits, one test added) and closed a carry-over item from the Sprint 2 board.
2. **Auth proxy identity binding validated** — Issue #94 confirmed that `on_init` correctly reads proxy headers and that `on_attest_confirm` blocks unauthenticated attestation. The full proxy chain (nginx stripping → oauth2-proxy injection → app receiving) was documented.
3. **OpenFGA/AuthZ epic scoped in detail** — Five issues and one epic provide a clear roadmap for introducing authorization into the platform in Sprint 4. The model scope (cards, sessions, audit exports, jobs, attestations) maps directly to existing app features.
4. **Stale-PR audit performed** — PR #101 assessed all nine open PRs targeting `main`, integrated three with clean and valuable changes, and produced a clear disposition for the remainder.

---

## What Didn't Go Well

1. **Contribution imbalance: third consecutive sprint** — Zero direct code contributions from Diamond Hogans, Sakshi Patel, and Elijah Jenkins. The Sprint 2 action item requiring each team member to merge at least one PR was not met by any of the three.
2. **Primary Sprint 3 feature not started** — Role-based authentication (issue #43, the main planned story) had zero activity during the sprint despite being explicitly called out in Sprint 2 action items and being assigned to Elijah Jenkins.
3. **Sprint 2 action items ignored again** — Weekly written status updates were not posted; issues were not closed when features shipped; sprint scope was not defined before sprint start. All four Sprint 2 action items went unmet.
4. **Very limited delivery** — Only one small UI enhancement was merged to `main`. Sprint 3 delivered substantially less than Sprint 2.
5. **No pipeline cards advanced** — card-007 (encrypt operator) remained `in_progress`; card-013 (role-based auth) remained `backlog`. No pipeline cards moved to `done` this sprint.

---

## Action Items for Next Sprint

1. **Each team member implements one issue from the OpenFGA epic (#96–#100)**
   - Assigned to: Diamond Hogans, Sakshi Patel, Elijah Jenkins
   - Each person must pick one of the five OpenFGA issues, implement it, and open a PR by the midpoint of Sprint 4 — no exceptions; this is the third time this action item has been carried
2. **Weekly written status update by Wednesday**
   - Assigned to: All team members
   - Post a brief update in the group channel: what you worked on, what's blocked, what's next; missed updates will be noted in the Sprint 4 retro
3. **Start role-based authentication (issue #43) in week one**
   - Assigned to: Elijah Jenkins (assignee), Diamond Hogans (login UI subtask), Sakshi Patel (DB schema subtask)
   - At minimum, Diamond's login UI subtask and Sakshi's DB schema subtask must have a draft PR open by the midpoint of Sprint 4
4. **Close GitHub issues when features are shipped**
   - Assigned to: Whoever merges the PR
   - Link the issue with `Closes #N` in the PR body; confirm it moves to Done on the board

---

## Individual Reflections

**Carley Fant:**
This sprint I merged the detection rationale toggle (PR #63), validated the auth proxy identity binding work, scoped the full OpenFGA/AuthZ epic into five trackable issues, and kicked off the stale-PR audit. The sprint was lighter than I wanted — the RBAC story should have landed. I opened the OpenFGA issues because a clear external authorization layer will make the demo much stronger for stakeholders, but I'm aware that I scoped that work without team input. For Sprint 4, my focus is on getting the rest of the team actively coding on these issues before I start driving Copilot sessions myself.

**Diamond Hogans:**
\[Please add 2-4 sentences describing your activity this sprint. If you did not make any direct code contributions, please say so and describe one specific thing you plan to deliver in Sprint 4 — your subtask in issue #43 (Build user registration/login interface) is waiting.\]

**Sakshi Patel:**
\[Please add 2-4 sentences. Zero direct contributions this sprint. Your issue #67 (Design schema for users, sessions, pipelines, appointments) has been open since Sprint 2 with no progress. Pick one subtask from issue #43 or issue #97 (OpenFGA authorization model) and open a draft PR in Sprint 4 week one.\]

**Elijah Jenkins:**
\[Please add 2-4 sentences. Issue #43 (Role-Based Authentication) was assigned to you for Sprint 3. No commits, comments, or PRs were opened against it. In Sprint 4 this is your primary responsibility — the whole sprint's RBAC delivery depends on your picking this up.\]

---

## Contribution Transparency Note

Per the assignment guidelines, we are documenting that three team members (Diamond Hogans, Sakshi Patel, and Elijah Jenkins) made no direct code contributions to the repository this sprint. This is the third consecutive sprint with this pattern, spanning Sprints 1, 2, and 3. The Sprint 4 action items above are not suggestions — they are minimum requirements for equitable participation. Diamond Hogans has a clearly assigned subtask in issue #43 and is called out separately here because that work is on the critical path for the RBAC feature.

Commit history: [View on GitHub](https://github.com/cpsc4205-group3/anonymous-studio/commits/main)
