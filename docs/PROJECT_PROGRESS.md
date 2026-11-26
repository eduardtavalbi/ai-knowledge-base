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
- Active branches: `feat/atomic-document-rollback-tests`, `feat/frontend-accessibility-ux`, `feat/rag-safe-abstention`, `feat/postgres-backup-restore-runbook`, `feat/frontend-container-deployment`, `feat/rag-retrieval-evaluation`.
- PR #7 remains open, Draft and unmerged. Its application-code head is `04c298b`; current branch checkpoint `35db90b` is a documentation-only progress update.
- Backend CI #437 (run ID `45727990991`) passed on exact PR #7 checkpoint `35db90b`: **204 tests in 7.95s**, PostgreSQL and migrations included.
- Frontend CI #274 (run ID `45727990866`) passed on the same PR #7 checkpoint.
- `main` remains at `0c1afe6c2223b261e886d901207288f3abd60e0a`; no PR has been merged during this work.
- PRs #4–#6 are already merged. Their merge commits and CI evidence remain in GitHub history.


### Completed and integrated

- PRs #1–3: core application foundation, account/authentication and initial product functionality — merged.
- PR #4: production configuration and operational hardening — merged; CI passed.
- PR #5: PostgreSQL migration integrity tests — merged; CI passed.
- PR #6: concurrent document deduplication protection — merged; CI passed.

### PR #7 — implemented and verified on current head, pending integration

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

PR #7 is **not integrated** until the user explicitly authorizes merge and the merge is confirmed.

### Area inventory — initial, to be audited against the current repository

| Area | Known state | Remaining verification / work |
|---|---|---|
| Backend product flows | FastAPI document/account flows and API validation are implemented; backend CI exercises PostgreSQL, migrations and 204+ tests | Audit end-to-end user journeys and API error contracts; record only concrete gaps |
| Frontend product flows | React + TypeScript + Vite; PR #8 adds accessible mobile navigation and duplicate-export prevention; PR #11 provides a containerized Nginx frontend with CSP/security headers | Browser-level auth/document/search/answer/export journeys are still not covered by E2E tests |
| RAG quality | Multilingual embeddings, hybrid PostgreSQL/pgvector + FTS, RRF, citation validation and abstention tests; real-embedding benchmark v2 now reports Recall@5/MRR@5 and no-answer retrieval | Expand from synthetic to reviewed anonymized domain documents; evaluate live answer grounding, citations and abstention |
| Security & reliability | Tenant isolation, auth/session/recovery, parser limits, upload size/rate limits, transaction rollback and concurrency have substantial tests | Finish targeted security review; preserve verified work and reopen only on concrete regression |
| Infrastructure & operations | Docker Compose, migrations, health/readiness, frontend container, automated PostgreSQL backup/restore and corruption rejection are verified in CI | Production off-site encryption, retention, scheduled restore drills, RPO/RTO, structured logs and alerts |
| Demo & release readiness | README/setup instructions, deployment container and operational recovery runbook exist | Clean-start production-like install, browser smoke suite, demo account/dataset, reverse-proxy/TLS review and release checklist |

This area inventory is not yet a percentage. Convert it into a weighted deliverable checklist after inspecting the actual frontend, API, RAG evaluation and deployment workflows. Do not infer completion from README claims alone.

## Active feature branches and current work

- PR #7 — [Harden document persistence and embedding initialization](https://github.com/eduardtavalbi/ai-knowledge-base/pull/7), branch `feat/atomic-document-rollback-tests`, current head `35db90b0528a16506c7c022694aed3038c292d1d`, Draft, unmerged. Backend #437 (204 tests) and Frontend #274 passed on this exact head.
- PR #8 — [Improve frontend accessibility and export UX](https://github.com/eduardtavalbi/ai-knowledge-base/pull/8), branch `feat/frontend-accessibility-ux`, head `c6cc4e4f2f87604c79666aec09fb13e11b4f679f`, Draft, stacked on PR #7. Backend #377 and Frontend #248 passed on its exact head; branch is behind the latest PR #7 base and needs synchronization before merge.
- PR #9 — [Allow safe RAG abstention when retrieved context is insufficient](https://github.com/eduardtavalbi/ai-knowledge-base/pull/9), branch `feat/rag-safe-abstention`, head `3b75fd4b3cfb7946c4317d25d9a831bf4817b2b2`, Draft, stacked on PR #7. Backend #378 passed (**207 tests**) and Frontend #249 passed; branch is behind the latest PR #7 base and needs synchronization before merge.
- PR #10 — [PostgreSQL backup and restore automation](https://github.com/eduardtavalbi/ai-knowledge-base/pull/10), branch `feat/postgres-backup-restore-runbook`, head `308e2f7557c95d39dbc388af3c9ea6ac96db4efe`, Draft, stacked on PR #7. Backend #439 passed (**204 tests in 8.31s**) and Frontend #275 passed. CI created a custom-format backup, verified its SHA-256, restored to an isolated temporary DB, checked Alembic version/schema, cleaned up and rejected a corrupted archive.
- PR #11 — [Containerized frontend deployment](https://github.com/eduardtavalbi/ai-knowledge-base/pull/11), branch `feat/frontend-container-deployment`, head `f126903398dfa70c05e03cc69c31c5ed752a35ef`, Draft, based on `main`. Backend #403 and Frontend #262 passed; Docker image/Nginx smoke test and CSP restricted to configured API origin.
- PR #12 — [Bilingual RAG retrieval evaluation](https://github.com/eduardtavalbi/ai-knowledge-base/pull/12), branch `feat/rag-retrieval-evaluation`, head `fc3d94ccd7ad7b3dce5151fb7761befc1fc248ab`, Draft, stacked on PR #7. Backend #436 passed (**211 tests**) and RAG evaluation #10 passed on the same head; artifact `15075631573`. Branch is behind the latest PR #7 base and needs synchronization before merge.
- All PRs remain Draft/unmerged. No merge is authorized unless the user explicitly says so.


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


## Operations audit — backup/restore verified

- `/health` is a liveness check; `/ready` checks PostgreSQL connectivity. Compose starts the API after database health and applies Alembic migrations before Uvicorn.
- PR #10 provides `scripts/backup_postgres.sh` and `scripts/verify_postgres_backup.sh`: custom-format archive, SHA-256 sidecar, checksum verification, temporary-database restore, Alembic/schema checks and cleanup.
- Backend CI #439 passed on exact PR #10 head `308e2f7`: **204 tests in 8.31s**, isolated Compose PostgreSQL, migrations, backup creation, checksum, temporary restore, Alembic version `9f4c2e7a1b60`, `public.documents` verification and corrupted-archive rejection. Frontend CI #275 passed.
- CI isolation uses unique Compose project/volume/host port per run while preserving the existing production volume name and default port.
- Production readiness still requires encrypted off-site backups, retention, scheduled restore drills, explicit RPO/RTO, structured logs and alerting.


## Next actions — continue here

1. The progress ledger has been synchronized into stacked PRs #8, #9, #10 and #12; verify their latest heads remain aligned with PR #7 before any future merge. Do not merge.
2. PR #11: full-stack Compose browser journey is implemented but not yet verified. Latest head `aa4e9b8` runs Frontend CI #304 and Backend CI #494; verify CPU-only PyTorch image build, real registration/login/refresh, PostgreSQL document read/delete/export and tenant isolation, then fix any failures. Earlier mocked-API frontend E2E and 189-test Backend CI passed on head `d151ad7`.
3. RAG: extend the benchmark to a reviewed anonymized corpus; add a controlled live Gemini evaluation for answer correctness, source support, citation validity and abstention. Improve the remaining English contractor/remote-access ranking ambiguity.
4. Operations: add encrypted off-site backup storage, retention policy, scheduled restore drills and RPO/RTO targets; keep production data out of CI.
5. Audit clean-start deployment, reverse-proxy/TLS/HSTS, structured logging, monitoring/alerts and production configuration.
6. Finish targeted PR #7 security/reliability review; do not reopen completed work without a demonstrated regression.
7. Keep all PRs Draft/unmerged until explicit user authorization. The overall percentage remains **unassessed** until all six areas have auditable weighted deliverable inventories.


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
