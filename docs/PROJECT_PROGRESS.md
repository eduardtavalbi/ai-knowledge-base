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
- Active development branches: `feat/atomic-document-rollback-tests`, `feat/frontend-accessibility-ux`, `feat/rag-safe-abstention`, `feat/postgres-backup-restore-runbook`, `feat/frontend-container-deployment`, `feat/rag-retrieval-evaluation`
- Active PR: [#7 — Harden document persistence and embedding initialization](https://github.com/eduardtavalbi/ai-knowledge-base/pull/7)
- PR #7 status: open, Draft, not merged. Do not merge without explicit user authorization.
- PR #7 application-code head at this checkpoint: `04c298bf33a675f94f6422d656c1cb5d0e0000a8`; a subsequent ledger-only commit advances the branch without changing application code.
- PR #7 Backend CI: run #361, run ID `45724290016`, exact head above — **success**. Docker Compose validation, lightweight test dependency install, PostgreSQL connection, Alembic migrations and **204 tests passed in 5.77s**; cleanup completed.
- PR #7 Frontend CI: run #232, run ID `45724289706`, exact same head — **success**. TypeScript/Vite build and ESLint passed.
- Previous full-runtime baseline: run #344 on `0132489`, 203 tests passed in 19.68s.
- PRs #4, #5 and #6 are merged into `main`. Their exact merge commits and CI evidence are recorded in the project handoff notes / GitHub history; verify against GitHub before making claims in a future report.

### Completed and integrated

- PRs #1–3: core application foundation, account/authentication and initial product functionality — merged.
- PR #4: production configuration and operational hardening — merged; CI passed.
- PR #5: PostgreSQL migration integrity tests — merged; CI passed.
- PR #6: concurrent document deduplication protection — merged; CI passed.

### PR #7 — implemented and verified on current head, pending integration

The following work is present in PR #7 and its full CI passed on `04c298b`:
- rollback protection and regression test for partial document/chunk persistence;
- lazy, thread-safe embedding model initialization and focused tests;
- PostgreSQL concurrency test for duplicate content on concurrent document updates;
- ASGI upload request-size limit, including streamed/chunked request bodies, with boundary tests;
- configurable upload rate limits per IP and authenticated identity;
- global per-user upload rate-limit semantics across different IPs;
- atomic concurrent rate-limit test against PostgreSQL;
- protection against stale rate-limit windows moving the active bucket backwards, with regression coverage;
- delayed requests are counted against the active bucket rather than bypassing its limit;
- `Retry-After` is calculated from the effective active rate-limit window, including when an older in-flight request arrives after the window has advanced; regression test covers the stale-window race.
- export download cleanup waits before revoking the Blob URL, avoiding premature release;
- retrieval score UI is labelled as a relative result weight, not as answer confidence.

### CI test-runtime optimization — implemented and verified

- `.github/workflows/ci.yml` creates a test-only requirements file excluding `sentence-transformers`; production `requirements.txt` and Docker installation remain unchanged.
- `tests/conftest.py` provides deterministic 384-dimensional chunk embeddings for API tests; `tests/test_documents.py` mocks both document-level and chunk-level embedding calls.
- First attempt (run #345) exposed ten tests that implicitly loaded the real model. The fixtures were corrected rather than weakening or skipping those tests.
- Final run #353: **203 passed in 7.42s**, without CUDA/Torch packages in CI. The suite no longer depends on downloading the production model.

PR #7 is **not integrated** until the user explicitly authorizes merge and the merge is confirmed.

### Area inventory — initial, to be audited against the current repository

| Area | Known state | Remaining verification / work |
|---|---|---|
| Backend product flows | Core FastAPI and document/account flows exist; CI exercises backend | Audit end-to-end user journeys and API error contracts; record concrete gaps only |
| Frontend product flows | React + TypeScript + Vite frontend; PR #8 adds mobile navigation accessible names, navigation landmark, status announcements and duplicate-export prevention; TypeScript build and ESLint pass | Core auth/document/search journeys still need browser-level end-to-end verification; no dedicated component/E2E test suite is present |
| RAG quality | Chunking, multilingual embeddings, hybrid PostgreSQL/pgvector + FTS retrieval, multi-query retrieval, RRF and Gemini answers; PR #9 adds strict Russian/English insufficient-evidence abstention with citation enforcement for factual claims; backend CI passes 207 tests | Build a repeatable labelled evaluation corpus and measure retrieval quality with real embeddings; run a controlled live Gemini groundedness/citation evaluation |
| Security & reliability | Tenant isolation, auth/session/recovery controls, parser limits, upload limits and rate limiting have substantial implementation and tests; PR #7 CI passed | Finish targeted security review; integrate PR #7 only with authorization; verify any remaining gaps with tests |
| Infrastructure & operations | Docker Compose, PostgreSQL, Alembic migrations, environment configuration, health/readiness and CI; PR #10 adds a backup/restore runbook; PR #11 adds a multi-stage Nginx frontend container and Compose service | Verify frontend container smoke tests; execute the documented database restore against a temporary PostgreSQL database; review structured logging, metrics/alerts and production deployment |
| Demo & release readiness | README, setup instructions and screenshots exist | Repeatable clean install, smoke test, production-like deployment, demo dataset/account and final release checklist |

This area inventory is not yet a percentage. Convert it into a weighted deliverable checklist after inspecting the actual frontend, API, RAG evaluation and deployment workflows. Do not infer completion from README claims alone.

## Active feature branches and current work

- PR #7 — [Harden document persistence and embedding initialization](https://github.com/eduardtavalbi/ai-knowledge-base/pull/7), branch `feat/atomic-document-rollback-tests`, head `04c298bf33a675f94f6422d656c1cb5d0e0000a8`, open Draft, unmerged. Backend #361 and Frontend #232 both passed on this exact SHA.
- PR #8 — [Improve frontend accessibility and export UX](https://github.com/eduardtavalbi/ai-knowledge-base/pull/8), branch `feat/frontend-accessibility-ux`, head `ebff9b1a8e9680ecb591213e424d7825beccdd90`, Draft, stacked on PR #7. Backend #362 and Frontend #233 both passed on this exact head.
- PR #9 — [Allow safe RAG abstention when retrieved context is insufficient](https://github.com/eduardtavalbi/ai-knowledge-base/pull/9), branch `feat/rag-safe-abstention`, head `44e6ce3ec6f95c686e690926cf78fa8923d085e9`, Draft, stacked on PR #7. Backend #364 passed (**207 tests in 8.29s**) and Frontend #235 passed. An earlier run failed only because a test expected the old prompt wording; the assertion was corrected and the exact latest head passed.
- PR #10 — [Document PostgreSQL backup and restore procedures](https://github.com/eduardtavalbi/ai-knowledge-base/pull/10), branch `feat/postgres-backup-restore-runbook`, head `db313fbe3a1c2df29738a1b94e8ee07de8ee4a59`, Draft, stacked on PR #7. Runbook content commit `6fe8a22`; local `backups/` artifacts ignored in `d7d1e24`. Documentation commands have not yet been executed against a live or temporary database.
- PR #11 — [Add containerized frontend to Docker Compose](https://github.com/eduardtavalbi/ai-knowledge-base/pull/11), branch `feat/frontend-container-deployment`, head `645fa0a43ab9dc3a61b93fd0a655d6a8adebb488`, Draft, based on `main`. Backend #366 passed (**189 tests in 7.05s**); Frontend #237 passed, including Docker image build and Nginx SPA smoke test.
- PR #12 — [Add reproducible bilingual RAG retrieval evaluation](https://github.com/eduardtavalbi/ai-knowledge-base/pull/12), branch `feat/rag-retrieval-evaluation`, head `c92f38239bd671f368ab8d6e456f18f65115c3ce`, Draft, stacked on PR #7. Backend #368 passed (**208 tests in 8.36s**) and Frontend #239 passed; the real-embedding benchmark has not been executed.
- All PRs remain unmerged. PRs #8–#10 and #12 are stacked on PR #7; PR #11 is based on `main`. Do not merge any PR without explicit user authorization.

## Frontend audit — initial findings

- Core auth, document list/detail/edit/delete, upload, search/answer, source display, export and account deletion flows are implemented in `frontend/src/App.tsx`.
- Existing safeguards include request IDs to ignore stale results, single-flight refresh-token rotation, focus trapping/Escape handling for dialogs, and source chunk deduplication in document cards.
- PR #8 fixes the compact mobile sidebar's missing accessible names, adds a navigation landmark, status announcements and prevents duplicate account export requests.
- Frontend TypeScript/Vite build and ESLint passed on PR #8 exact head `ebff9b1`.
- `frontend/package.json` has no frontend automated test runner. Browser-level journey tests remain an explicit gap; do not treat build/lint as end-to-end verification.

## RAG audit — initial findings

- Existing tests cover valid/missing/malformed/unknown citations, empty or blocked responses, provider failures, query expansion fallback/deduplication, conflicting sources, hybrid retrieval, duplicate suppression, per-document chunk caps, Russian/English retrieval and PostgreSQL HNSW behavior.
- PR #9 fixes the abstention defect: when retrieved context is irrelevant, the model may return one narrowly matched Russian or English insufficient-evidence response without fabricating a citation.
- Factual claims and mixed refusal-plus-claim responses still require valid citations. Latest PR #9 Backend CI passed 207 tests; Frontend CI passed on the same head.
- Remaining quality work is a labelled corpus and real-embedding benchmark (Recall@K/MRR), followed by controlled groundedness/citation evaluation; unit tests alone are not a live model-quality benchmark.

## RAG retrieval benchmark — verified technical baseline

- PR #12 adds an 8-query Russian/English labelled corpus with 11 synthetic documents and distractors.
- The opt-in benchmark uses the real `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` embeddings and PostgreSQL hybrid vector/FTS retrieval, with Gemini query expansion disabled to isolate ranking.
- RAG retrieval evaluation #3 passed on head `34a9f1c`: all 8 relevant documents ranked first; Recall@5 = 1.00, MRR@5 = 1.00, misses = 0. The JSON report is uploaded as artifact `mindbase-rag-retrieval-evaluation` (run #3).
- Backend CI #407 passed 209 tests on the same PR #12 head. The benchmark initially exposed missing `UserSession` ORM registration; explicit model imports and a mapper-configuration regression test were added before the successful run.
- This is only a technical baseline on a small synthetic corpus, not evidence of commercial-domain retrieval quality. Next quality step is a larger reviewed, anonymized corpus with realistic ambiguous, contradictory and no-answer cases.

## Operations audit — backup/restore verification pending

- `/health` is a liveness check; `/ready` checks PostgreSQL connectivity. Compose starts the API only after database health and applies Alembic migrations before Uvicorn.
- PR #10 now includes executable `scripts/backup_postgres.sh` and `scripts/verify_postgres_backup.sh`. The first creates and validates a custom-format dump plus SHA-256 checksum; the second verifies the checksum, restores into a temporary database and checks the Alembic version and `public.documents` table before cleanup.
- Backend CI #405 passed Compose validation, DB connectivity/migrations and 204 tests but failed at the SQLAlchemy migration connection. The next revision moved the SQLAlchemy connectivity precheck after Compose DB startup, isolates project/volume/port per run, and adds a corrupted-archive rejection test. Latest PR #10 head is `4768d28`; no successful run on that head is available yet.
- Both shell scripts pass `bash -n`; local Docker execution is unavailable, so the disposable-PostgreSQL CI run remains the required end-to-end verification.

## Next actions — continue here

1. PR #10: get the isolated Compose backup/restore workflow passing on the latest head `4768d28`. The run must prove archive creation, checksum validation, restore into a temporary database, schema checks, cleanup and rejection of a corrupted archive.
2. PR #11: container deployment and security headers are verified on head `f126903` (Frontend CI #262 and Backend CI #403 passed). Move on to browser-level journeys: registration/login, session refresh, upload, document CRUD, search, AI answer, export and mobile navigation.
3. PR #12: real-embedding smoke benchmark is verified (Recall@5/MRR@5 = 1.00 on 8 synthetic queries). Expand to a reviewed, anonymized corpus with realistic ambiguous, contradictory and no-answer examples before using metrics as a release gate.
4. Finish targeted PR #7 security/reliability review; the Retry-After race fix remains verified, and do not reopen completed work without a concrete regression.
5. Audit clean-start deployment, reverse-proxy/TLS/HSTS configuration, backups/restore, logs/monitoring and recovery assumptions against an actual production-like environment.
6. Keep PRs #7–#12 Draft/unmerged until explicit user authorization. Do not calculate an overall percentage until all six areas have auditable deliverable inventories.

## Update log

| Date | Change | Evidence |
|---|---|---|
| 2026-11-26 | Created persistent progress ledger; recorded PR #7 checkpoint and separated implemented/verified/integrated states. | PR #7 head `4802a29`; CI run #342 (`45722270626`) successful. |
| 2026-11-26 | Fixed frontend export URL lifetime and clarified RAG score label. | Commit `0132489`; Frontend CI #215 and Backend CI #344 passed; 203 tests passed. |
| 2026-11-26 | Made CI tests independent of the production embedding runtime using deterministic fixtures; excluded SentenceTransformers/Torch from test-only installs while preserving production requirements. | Commits `3e359e0`, `710e288`, `4bbd332`; CI #353 passed: 203 tests in 7.42s; Frontend CI #224 passed. |
| 2026-11-26 | Corrected stale-window `Retry-After` calculation to use the effective active bucket; added delayed-request regression test. | Commits `12514a0` and `4be5126`; Backend CI #359 passed on head `c41f3c1`: 204 tests in 7.87s; Frontend CI #230 passed. |
| 2026-11-26 | Added a PostgreSQL backup/restore runbook and README link; added strict Russian/English RAG abstention regression coverage; improved mobile navigation and export UX. | PR #8 head `ebff9b1`: Backend #362 and Frontend #233 passed; PR #9 head `44e6ce3`: Backend #364 (207 tests) and Frontend #235 passed; PR #10 head `db313fb`, restore procedure not yet executed. |
| 2026-11-26 | Added containerized frontend deployment and an opt-in bilingual retrieval benchmark. | PR #11 head `645fa0a`, Backend #366 (189 tests) and Frontend #237 passed; PR #12 head `c92f382`, Backend #368 (208 tests) and Frontend #239 passed; real-embedding benchmark not yet run. |
| 2026-11-26 | Added CI branch filters for stacked feature PRs and a dedicated real-embedding RAG evaluation workflow with a disposable pgvector database and JSON artifact. | PR #7 head `09227f7`; Backend CI #395 and Frontend CI #260 passed; RAG workflow #1 exposed missing `UserSession` mapper registration. |
| 2026-11-26 | Added explicit `UserSession`/refresh-token model imports to the benchmark and a mapper-configuration regression test. | PR #12 commits `9f3cba1` and `34a9f1c`; RAG benchmark reruns #2/#3 pending; no metric is claimed yet. |
| 2026-11-26 | Added executable PostgreSQL backup and temporary restore verification scripts; isolated Compose CI resources by run ID after authentication collisions. | PR #10 head `379f66a`; both scripts pass `bash -n`; CI #405 pending after earlier failures #393/#399. |
| 2026-11-26 | Hardened frontend container CSP/Permissions-Policy and restricted `connect-src` to the configured API origin. | PR #11 head `f126903`; previous Frontend CI #258 and Backend CI #391 passed before the final CSP-origin tightening; latest #262/#403 pending. |
| 2026-11-26 | Executed the first real-embedding RAG benchmark against disposable pgvector PostgreSQL; fixed missing ORM registration and added mapper regression coverage. | PR #12 head `34a9f1c`; RAG evaluation #3 passed: 8/8 relevant docs at rank 1, Recall@5 1.00, MRR@5 1.00, misses 0; artifact `15075381093`; Backend CI #407 passed 209 tests. |
| 2026-11-26 | Completed strict frontend CSP origin binding and verified frontend container behavior. | PR #11 head `f126903`; Frontend CI #262 and Backend CI #403 passed; CSP allows only the configured `VITE_API_URL` for connections. |
| 2026-11-26 | Added checksum verification and corrupted-archive rejection coverage to PostgreSQL backup/restore workflow. | PR #10 head `4768d28`; prior run #405 failed at SQLAlchemy DB connection after 204 tests; latest workflow rerun not yet available. |
