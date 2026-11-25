# Mindbase — Project Progress Ledger

This file is the source of truth for project progress across work sessions and chat handoffs.
Update it after each substantial implementation/audit block. Do not restart from an old roadmap or count the same deliverable twice.

## Progress rules

1. Track deliverables, not activity. A commit, test run, or repeated review is not a new feature.
2. Every completed item must have evidence: merged PR/commit, exact CI run on that SHA, or a reproducible manual verification.
3. Keep implementation and integration separate:
   - `Implemented`: code is present on a working branch.
   - `Verified`: relevant tests/checks passed on the exact commit.
   - `Integrated`: merged into `main`.
4. Never mark a whole area complete because its CI is green. CI proves the checked behavior, not product completeness.
5. A completed deliverable never becomes incomplete just because the conversation changes. Reopen it only when a regression or changed requirement is demonstrated.
6. Do not silently expand the release scope. New requirements must be added as explicit deliverables with a reason.
7. Calculate the overall percentage from the weighted deliverables in the release scope, not from intuition or how much code was written. Keep the same weights between updates; only change weights when scope is explicitly revised.
8. Report the delta since the previous checkpoint: what moved from not done → implemented → verified → integrated, what is blocked, and the next concrete task.
9. Do not repeat completed roadmap items. Start from **Next actions** below and refresh the repository state before acting.

## Release scope and scoring model

The release-readiness score is based on six areas. The weights sum to 100 points:

| Area | Weight | What counts |
|---|---:|---|
| Backend product flows | 20 | Document CRUD/upload, account flows, API validation and error handling |
| Frontend product flows | 20 | Authentication, document management, search/answer experience, responsive UX and accessibility |
| RAG quality | 20 | Chunking, embeddings, hybrid retrieval, citations, relevance, grounded answers and evaluation |
| Security & reliability | 15 | Tenant isolation, auth/session safety, concurrency, rollback, abuse controls and parser limits |
| Infrastructure & operations | 15 | Docker, migrations, configuration, health checks, CI, logging/monitoring and operational recovery |
| Demo & release readiness | 10 | Clean-start verification, production-like deployment, smoke tests, documentation and repeatable demo |

For each area, maintain an explicit checklist of deliverables. A deliverable's points are earned only once:
- 0%: not implemented;
- 50%: implemented but not verified on the current relevant code;
- 100%: verified; for integration-dependent work, merged into main.

Area score = earned deliverable points / total deliverable points in that area. Overall score = sum(area score × area weight).

If an area has not yet been fully inventoried, label its score **unassessed**; do not invent a percentage. The historical **78%** was the last user-facing estimate, but it did not have a saved auditable breakdown. Preserve it as historical context, not as a hardcoded score or a reason to suppress real progress. Establish the first auditable breakdown from the current repository and this checklist, then calculate future deltas from it.

## Current checkpoint — 2026-11-26

### Repository state

- Repository: `eduardtavalbi/ai-knowledge-base`
- Active branch: `feat/atomic-document-rollback-tests`
- Active PR: [#7 — Harden document persistence and embedding initialization](https://github.com/eduardtavalbi/ai-knowledge-base/pull/7)
- PR #7 status: open, Draft, not merged. Do not merge without explicit user authorization.
- PR #7 head at checkpoint: `4802a29ba45d75604599d18614f7d9e684a6e31a`
- PR #7 CI: run #342, run ID `45722270626`, exact head above — **success**. Docker Compose validation, dependency installation, PostgreSQL connection, migrations, full test suite and cleanup all completed successfully.
- PRs #4, #5 and #6 are merged into `main`. Their exact merge commits and CI evidence are recorded in the project handoff notes / GitHub history; verify against GitHub before making claims in a future report.

### Completed and integrated

- PRs #1–3: core application foundation, account/authentication and initial product functionality — merged.
- PR #4: production configuration and operational hardening — merged; CI passed.
- PR #5: PostgreSQL migration integrity tests — merged; CI passed.
- PR #6: concurrent document deduplication protection — merged; CI passed.

### PR #7 — implemented and verified on current head, pending integration

The following work is present in PR #7 and its full CI passed on `4802a29`:
- rollback protection and regression test for partial document/chunk persistence;
- lazy, thread-safe embedding model initialization and focused tests;
- PostgreSQL concurrency test for duplicate content on concurrent document updates;
- ASGI upload request-size limit, including streamed/chunked request bodies, with boundary tests;
- configurable upload rate limits per IP and authenticated identity;
- global per-user upload rate-limit semantics across different IPs;
- atomic concurrent rate-limit test against PostgreSQL;
- protection against stale rate-limit windows moving the active bucket backwards, with regression coverage;
- delayed requests are counted against the active bucket rather than bypassing its limit.

PR #7 is **not integrated** until the user explicitly authorizes merge and the merge is confirmed.

### Area inventory — initial, to be audited against the current repository

| Area | Known state | Remaining verification / work |
|---|---|---|
| Backend product flows | Core FastAPI and document/account flows exist; CI exercises backend | Audit end-to-end user journeys and API error contracts; record concrete gaps only |
| Frontend product flows | React + TypeScript + Vite frontend exists; screenshots are in the repository | Audit every core journey, responsive behavior, accessibility and API integration |
| RAG quality | Chunking, multilingual embeddings, hybrid PostgreSQL/pgvector + FTS retrieval, multi-query retrieval, RRF, relevance filtering and Gemini answers are implemented | Build a representative evaluation set; verify grounded answers, missing-answer behavior, contradictory/irrelevant context and citation correctness |
| Security & reliability | Tenant isolation, auth/session/recovery controls, parser limits, upload limits and rate limiting have substantial implementation and tests; PR #7 CI passed | Finish targeted security review; integrate PR #7 only with authorization; verify any remaining gaps with tests |
| Infrastructure & operations | Docker Compose, PostgreSQL, Alembic migrations, environment configuration and CI exist | Review structured logging, metrics/alerts, backups/restore, production deployment and clean-start procedure |
| Demo & release readiness | README, setup instructions and screenshots exist | Repeatable clean install, smoke test, production-like deployment, demo dataset/account and final release checklist |

This area inventory is not yet a percentage. Convert it into a weighted deliverable checklist after inspecting the actual frontend, API, RAG evaluation and deployment workflows. Do not infer completion from README claims alone.

## Next actions — continue here

1. Refresh PR #7 state and CI head before any further work. CI #342 passed on `4802a29`; if the branch has moved, verify the newer exact SHA.
2. Finish the PR #7 reliability/security review. Investigate concrete issues only; avoid speculative changes.
3. Keep PR #7 Draft and unmerged until explicit user authorization.
4. Audit the frontend core journeys and record each deliverable with evidence.
5. Create a small RAG evaluation set covering: answer present in sources, answer absent, conflicting sources, irrelevant context, Russian/English queries, and citation/source correctness. Run it and record results.
6. Audit operations: clean Docker start, migrations from an empty database, restart behavior, health/readiness, logs, backup/restore and deployment assumptions.
7. Once the six areas have been inventoried, calculate the first auditable weighted percentage. Thereafter update only the deliverables that actually changed and report the exact percentage delta.

## Update log

| Date | Change | Evidence |
|---|---|---|
| 2026-11-26 | Created persistent progress ledger; recorded PR #7 checkpoint and separated implemented/verified/integrated states. | PR #7 head `4802a29`; CI run #342 (`45722270626`) successful. |
