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

- Current `main`: `c95f13c1f901725df4b19652ddd658c7443ac2af`; PRs #7–#12 are integrated, including PR #10 backup/restore automation.
- PRs #7, #8, #9, #11 and #12 are merged into `main`; exact merge commits are recorded in the integration log below.
- No integration-batch PRs remain open. The next active work is encrypted off-site backup and restore reliability on `feat/offsite-backup-reliability`.
- The full-stack deployment path from PR #11 is verified: Compose PostgreSQL/API/Nginx startup, Alembic migrations, readiness, CPU-only PyTorch, real account/document seeding, and browser-level registration/login/refresh/read/delete/export/tenant-isolation.
### Completed and integrated

- PRs #1–3: core application foundation, account/authentication and initial product functionality — merged.
- PR #4: production configuration and operational hardening — merged; CI passed.
- PR #5: PostgreSQL migration integrity tests — merged; CI passed.
- PR #6: concurrent document deduplication protection — merged; CI passed.

### PR #7 — merged and integrated

The following work is present in PR #7; the latest full CI passed on documentation checkpoint `35db90b` (application code unchanged from `04c298b`):
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

PR #7 was squash-merged into `main` at `f926111790ebf84102626b717621808e45d6e764`.

### Area inventory — initial, to be audited against the current repository

| Area | Known state | Remaining verification / work |
|---|---|---|
| Backend product flows | FastAPI document/account flows and API validation are implemented; backend CI exercises PostgreSQL, migrations and 204+ tests | Audit end-to-end user journeys and API error contracts; record only concrete gaps |
| Frontend product flows | React + TypeScript + Vite; PR #8 adds accessible mobile navigation and duplicate-export prevention; PR #11 provides a containerized Nginx frontend with CSP/security headers | Mocked-API UI E2E and a full-stack Compose browser journey against real FastAPI/PostgreSQL now cover auth, refresh, search, upload, edit, delete, export and tenant isolation |
| RAG quality | Multilingual embeddings, hybrid PostgreSQL/pgvector + FTS, RRF, citation validation and abstention tests; real-embedding benchmark v2 now reports Recall@5/MRR@5 and no-answer retrieval | Expand from synthetic to reviewed anonymized domain documents; evaluate live answer grounding, citations and abstention |
| Security & reliability | Tenant isolation, auth/session/recovery, parser limits, upload size/rate limits, transaction rollback and concurrency have substantial tests | Finish targeted security review; preserve verified work and reopen only on concrete regression |
| Infrastructure & operations | Docker Compose, migrations, health/readiness, frontend container, automated PostgreSQL backup/restore and corruption rejection are verified in CI | Production off-site encryption, retention, scheduled restore drills, RPO/RTO, structured logs and alerts |
| Demo & release readiness | README/setup instructions, deployment container and operational recovery runbook exist | Clean-start production-like install, browser smoke suite, demo account/dataset, reverse-proxy/TLS review and release checklist |

This area inventory is not yet a percentage. Convert it into a weighted deliverable checklist after inspecting the actual frontend, API, RAG evaluation and deployment workflows. Do not infer completion from README claims alone.

## Active feature branches and current work

- PR #7 — merged: `f926111790ebf84102626b717621808e45d6e764`.
- PR #8 — merged: `a21c0f8093fec5d1a6855e0f15a85d59b6781dec`.
- PR #9 — merged: `807b8385620146eaaf6bfa1b766f2e1b122f88c2`.
- PR #11 — merged: `7a4b761341dbd64c8773ec7fcd725de09d30950b`.
- PR #12 — merged: `0cebc1f2af958c0d4d48ef4439ce8f31402bf9b0`.
- PR #10 — [PostgreSQL backup and restore automation](https://github.com/eduardtavalbi/ai-knowledge-base/pull/10), branch `feat/postgres-backup-restore-runbook`; being rebased onto current `main`, then its backup/restore CI must pass on the exact new head before merge.
## Frontend audit — initial findings

- Core auth, document list/detail/edit/delete, upload, search/answer, source display, export and account deletion flows are implemented in `frontend/src/App.tsx`.
- Existing safeguards include request IDs to ignore stale results, single-flight refresh-token rotation, focus trapping/Escape handling for dialogs, and source chunk deduplication in document cards.
- PR #8 fixes the compact mobile sidebar's missing accessible names, adds a navigation landmark, status announcements and prevents duplicate account export requests.
- Frontend TypeScript/Vite build and ESLint passed on PR #8 exact head `ebff9b1`.
- `frontend/package.json` has no frontend automated test runner. Browser-level journey tests remain an explicit gap; do not treat build/lint as end-to-end verification.

## RAG audit — current findings

- Existing tests cover valid/missing/malformed/unknown citations, empty or blocked responses, provider failures, query-expansion fallback/deduplication, conflicting sources, hybrid retrieval, duplicate suppression, per-document chunk caps, Russian/English retrieval and PostgreSQL HNSW behavior.
- PR #9 allows a narrow Russian/English insufficient-evidence response when retrieved context is irrelevant, without fabricating a citation. Factual claims and mixed refusal-plus-claim responses still require valid citations.
- PR #12 adds a repeatable real-embedding retrieval evaluation. It isolates retrieval ranking by disabling Gemini query rewriting; it does not measure answer-generation quality.
- The current synthetic benchmark is a technical baseline only. A controlled live Gemini groundedness/citation evaluation and reviewed anonymized product-domain corpus remain necessary.


## RAG retrieval benchmark — expanded corpus verified

- PR #12 version 2 contains **14 synthetic documents and 17 bilingual queries**: 14 answerable and 3 explicitly unanswerable. Hard cases include employee/contractor VPN policies, a superseded 2024 leave policy, customer-data handling and no-answer questions.
- The benchmark uses the production `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` model with PostgreSQL hybrid vector/FTS retrieval; Gemini query rewriting is disabled to isolate ranking.
- Expanded RAG evaluation #14 passed on latest PR #12 head `d98ead0`. Metrics: **Recall@5 1.00**, **MRR@5 0.9286**, 0 misses; **0/3** unanswerable queries retrieved context (0% no-answer retrieval rate). Artifact ID `15075816487`.
- Added a query-intent-aware supersession penalty: explicitly outdated/superseded sources are down-ranked only for current/latest-policy questions and remain searchable for historical queries. This moved both Russian and English current-leave queries to the current 2026 policy at rank 1 and improved MRR from 0.8571 to 0.9286.
- Two near-duplicate remote-access/contractor queries still rank the relevant source second, though it remains in top 2. This is a known cross-lingual ambiguity to address with deterministic bilingual lexical expansion or better document metadata.
- Backend CI #447 passed **212 tests** on the same PR #12 head, including ORM mapper registration and bilingual current-vs-historical ranking regression coverage.
- This remains a small synthetic corpus, not a commercial-domain quality guarantee or release gate. Next step is reviewed anonymized data and live answer/citation/abstention evaluation.


## Operations audit — backup/restore implementation verified on PR #10; main integration pending

- `/health` is a liveness check; `/ready` checks PostgreSQL connectivity. Compose starts the API after database health and applies Alembic migrations before Uvicorn.
- PR #10 provides `scripts/backup_postgres.sh` and `scripts/verify_postgres_backup.sh`: custom-format archive, SHA-256 sidecar, checksum verification, temporary-database restore, Alembic/schema checks and cleanup.
- Backend CI #439 passed on exact PR #10 head `308e2f7`: **204 tests in 8.31s**, isolated Compose PostgreSQL, migrations, backup creation, checksum, temporary restore, Alembic version `9f4c2e7a1b60`, `public.documents` verification and corrupted-archive rejection. Frontend CI #275 passed.
- CI isolation uses unique Compose project/volume/host port per run while preserving the existing production volume name and default port.
- Production readiness still requires encrypted off-site backups, retention, scheduled restore drills, explicit RPO/RTO, structured logs and alerting.


## Next actions — continue here

1. Finish PR #10 integration: verify the rebased backup/restore scripts and Compose CI on the exact PR head, merge only after all checks pass, and verify the merge commit.
2. Then implement the next operations block: encrypted off-site backup storage, retention/rotation policy, scheduled backup verification and restore drills, and explicit RPO/RTO targets. Keep provider-specific credentials external and configurable.
3. Complete deployment operations: HTTPS reverse proxy/TLS/HSTS, production secret injection, structured log collection, monitoring/alerting, and scheduled audit-retention cleanup.
4. Evaluate live answer-generation quality separately from the synthetic retrieval benchmark, including grounded answers, citations, abstention, conflicting sources, and Russian/English behavior.
5. Finish a six-area evidence inventory and calculate the weighted project score only from unique, verified deliverables. Do not repeat completed work or reuse historical rough percentages.
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
| 2026-11-26 | Completed PostgreSQL backup/restore CI end-to-end, including checksum and corrupted-archive rejection. | PR #10 code head `84a307e`; Backend CI #429 passed 204 tests, temporary restore, Alembic/schema checks and corrupt archive rejection; Frontend CI #271 passed; PR base restored to #7, latest head `4b3adfd`. |
| 2026-11-26 | Expanded the RAG benchmark to 17 queries across 14 documents, including 3 no-answer cases; added separate no-answer retrieval false-positive metric and clarified that it does not measure answer abstention. | PR #12 head `fc3d94c`; expanded RAG evaluation #10 and Backend CI #436 running; earlier 8-query score explicitly retained as historical only. |
| 2026-11-26 | Improved current-policy retrieval ranking and reran expanded RAG benchmark on the latest head. | PR #12 head `d98ead0`: RAG #14 Recall@5 1.00, MRR@5 0.9286, no-answer retrieval 0/3, artifact `15075816487`; Backend #447 212 tests. Superseded 2024 leave policy now ranks below current 2026 policy for Russian and English queries. |
| 2026-11-26 | Completed browser UI E2E and frontend container verification. | PR #11 head `d151ad7`; Frontend CI #287 passed TypeScript/build, ESLint, Playwright login/refresh/search/upload/edit/delete/export/logout, Docker image build and Nginx smoke; Backend CI #463 passed 189 tests with PostgreSQL and migrations. UI E2E mocks the API; full-stack Compose E2E remains open. |
| 2026-11-26 | Verified accessibility/export UX and safe RAG abstention branches. | PR #8 code head `72410ad`: Frontend CI #282 and Backend CI #458 passed (204 tests); latest head `e35d297` is progress-ledger sync only. PR #9 code head `96a7294`: Backend CI #448 passed (207 tests); latest head `37b1c4a` is progress-ledger sync only. Both remain Draft and stacked on PR #7. |
| 2026-11-26 | Implemented full-stack Compose browser harness and production-image dependency split; verification pending. | PR #11 head `aa4e9b8`: added `requirements-prod.txt`, CPU-only PyTorch 2.9.1+cpu, backend Docker build-context pruning, real API account/document seeding, and Playwright full-stack journey. Frontend CI #304 and Backend CI #494 are running; previous head `d151ad7` passed Frontend #287 and Backend #463 (189 tests). |

| 2026-11-26 | Squash-merged PR #7, #8 and #9 after rebasing stacked branches onto current main; no PR was merged without green exact-head CI. | Merge commits: #7 `f926111`, #8 `a21c0f8`, #9 `807b838`. |
| 2026-11-26 | Merged PR #12 after combining its bilingual query-expansion changes with the already merged safe-abstention implementation. | Merge commit #12 `0cebc1f`; Backend CI #510: 216 tests; RAG evaluation #21: Recall@5 1.00, MRR@5 0.9286, no-answer retrieval 0/3. |
| 2026-11-26 | Merged PR #11 after full-stack Compose verification and fixing production Alembic password rendering. | Merge commit #11 `7a4b761`; Frontend CI #320 passed full-stack registration/login/refresh/document/export/tenant-isolation journey; Backend CI #518: 218 tests; API image verified PyTorch `2.9.1+cpu`. |
| 2026-11-26 | Rebased PR #10 backup/restore automation onto current main while preserving PR #11 Compose deployment and PR #12 RAG changes. | New tree is based on main `7a4b761`; backup/restore CI pending on new exact head. |
| 2026-11-26 | Implemented the first provider-neutral encrypted off-site backup workflow. | Branch `feat/offsite-backup-reliability`: age client-side encryption, rclone upload, encrypted-object SHA-256, age-based retention, fallback across older archives during restore drills, deployment runbook and CI shell syntax checks. Exact-head CI and behavior tests pending. |
