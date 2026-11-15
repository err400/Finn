# Source audit and release verification · 16 November 2026

**Update:** The user subsequently requested a public no-login demo. The reviewer gate described in the original audit below was removed; budgets, private storage, raw-source restrictions and operator-ingestion token remain. The legacy reviewer mode is a compatibility alias to public_demo.

The actual API/services/providers/models/frontend and regression tests were inspected. This is an engineering prototype audit, not independent financial or penetration-test certification.

## Findings and fixes, ordered by severity

| Priority | Finding | Resolution / remaining risk |
|---|---|---|
| High | Local-only guards prevented a hosted frontend from using the API; proxy-based loopback assumptions were insufficient for public hosting | Added explicit reviewer mode, bearer gate on every workspace route, exact Origin checks, no forwarded-header trust, startup validation, private runtime entry. Shared demo access remains unsuitable for real multi-user investors. |
| High | SQLite/files on Render Free would not preserve saved data across restarts | Added Postgres retrieval/connection support, private Supabase file adapter, RLS/browser-grant hardening, one-time local copy with sequence preservation. Real Postgres integration passed. Actual cloud provisioning/restart test is pending. |
| High | Historical Custom search excluded replay records; a broad range misleadingly showed zero | `mode=all` includes both origins without relabeling historical events. Added per-company archive coverage and regression coverage. Genuine archive expanded to 22 events, not a synthetic historical dataset. |
| High | Conflicting latest financial values could silently leave an older quarter presented as the current comparable value | Suppress the affected metric's latest comparison and expose a conflict warning. Regression verifies conflicting primary inputs yield no fabricated replacement comparison. |
| High | Free-form model limitations could contain ungrounded financial claims despite exact-citation validation on main claims | Replaced model limitation prose with a controlled evidence-gap message; invalidated old answer cache version. Added injection regression. |
| Medium | An unmapped BSE research ticker raised an uncaught provider error | Maps the error to a validation response instead of HTTP 500. Unsupported valid NSE symbols still return explicit insufficient evidence. |
| Medium | Concurrent research could duplicate model work or race first-time indexing/cache writes | One active research slot, explicit HTTP 429/Retry-After, shared reviewer request budgets, saved-rule cap. Limits are process-local; use a gateway/provider spend cap for production. |
| Medium | Source refresh repeatedly retried failed feeds for holdings, and stale/error presentation conflated cache expiry with source failure | Shared background refresh, persisted cooldown/negative cache, conditional GET and source-status receipts. Source outage preserves earlier evidence, never fabricates new records. |
| Medium | Incomplete corpus and unsupported financial layouts could look like complete research | Explicit document kinds/coverage, missing-evidence states, conservative numeric parsing, exact source dates, historical labels. Comprehensive primary-document discovery is still not implemented. |
| Medium | Database schema lifecycle and operational backups are incomplete | Additive initialization and empty-target copier only. Reviewed schema migrations, least-privilege dedicated DB role, backups/restoration, and distributed jobs remain production work. |
| Medium | Mobile visual quality/accessibility not fully verified in a real browser | Component flows at mobile/desktop state widths, accessible labels, keyboard tabs, focus-trapped drawers, reduced motion and responsive CSS tested/inspected. Browser-control permission denied. User desktop screenshots inspected; mobile paint/contrast audit remains pending. |
| Low | Replay banner showed only the archive start date | Now shows the actual start/end publication range. |
| Low | Data status claimed the LLM was always disconnected | Reports actual configuration state without exposing credentials. |

## Workflow evaluation

**PUSH:** complete prototype digest, custom/default windows, deterministic categorization/priorities, routine collapse, exact source excerpts, review prompts, citations and contextual people. Saved EOD price/volume/category rules work, with trigger values, baselines and provenance. Not real-time and not a complete market archive. Source availability differs by hosting region/IP.

**PULL:** primary annual/report/transcript/results parsing, page chunks, company-scoped SQL search, exact-citation model selection, calculated comparable values, evidence/error states and contextual Network work. Numerical parser is deliberately narrow. Snapshot is demonstrated; multi-year trajectory and guidance-to-actual conclusions depend on evidence and are not generally automated. Exact quotation grounding proves traceability, not independent truth or completeness.

**NETWORK:** explicit synthetic graph, direct/two-degree traversal, exact name/alias matching with ambiguity, company/peer/topic ranking and explanations integrated with Push/Pull. No relevant contacts returns an honest empty list. Fixed synthetic owner, no actual personal-data import or production consent system.

**Data/architecture:** 18-company EOD history, provenance and timestamped caches; reviewed primary PDFs and RSS; modular file/model/source adapters. SQLite locally and Postgres/private Storage for hosted use. Query/search implementation differs by database but keeps citation and company boundaries. Some unused foundation models remain; production migrations are not complete.

**Cost:** no model for source polling, classification, alerts or graph ranking. Cached primary sentence selection is the only LLM task. Free hosting configuration is explicit; provider inference cost and free-tier quotas are separate. No always-on guarantee while Render sleeps or Supabase pauses.

## Verified results

- Backend unit/integration suite, including a real isolated Postgres database: **52 passed**. One upstream Starlette/httpx deprecation warning remains.
- Frontend integration/reviewer-access tests: **13 passed**; TypeScript and Vite production build passed.
- Real uvicorn startup against a disposable database, health and 18-company seed: passed.
- `pip check`: passed. Publication allowlist/credential-pattern scan: passed; this is a heuristic scan, not proof of absence of every possible secret.
- Real local frontend/API/CORS/event-to-person smoke passed. New Pidilite primary-source synthesis completed: **10 passages, 6 verified source-quotation claims**. See `docs/verification/submission-local-smoke.json`.
- Postgres integration verifies local-to-Postgres migration, sequence continuity, RLS flag, search/page citations, and persistence after reconnecting a new pool. Private Storage HTTP transport tests verify correct authenticated path, hashing, idempotent upload, and redacted failure. These do **not** claim a live Supabase test.
- Actual local coverage: 1,872 EOD rows, 32 documents, 22 filings; see `docs/verification/submission-coverage.json`. Earlier verification reports describe earlier dataset sizes and are historical receipts, not current counts.

## Critical edge-case matrix

| Requested edge | Result |
|---|---|
| Unsupported/invalid ticker | Valid unknown NSE symbol returns insufficient evidence; malformed or unmapped BSE input returns validation error |
| Missing financial report | Source coverage/limitations shown; no invented answer; synthesis withheld when prerequisite kinds absent |
| Inaccessible filing source | Recorded error/cooldown, stale provenance retained, no invented announcement |
| No relevant network connection | Empty recommendations, no manufactured relationship |
| Conflicting/incomplete financial evidence | Affected values/comparisons withheld; explicit evidence gap/conflict |
| Invalid thresholds incl. zero, negative, NaN/Infinity | HTTP 422, no rule saved |
| Empty portfolio digest | Zero stored records with honest coverage message |
| Failed/invalid LLM request | Evidence retained, synthesis unavailable/withheld, no cached fabricated answer or raw provider error |

## Not yet verified / submission blockers

No hosted frontend/backend URL exists yet. User is completing dashboard account setup. Actual cloud SQL/Storage credentials, bucket policies, migration, CORS, deployment readiness and persistence after a Render restart still need live checks. Actual chat export and final email submission remain user actions. The detailed source inspection and passing local tests do not turn the prototype into production financial infrastructure.


## Hosted verification and latency update

The deployed frontend is https://finn-three-brown.vercel.app and the backend is https://finn-zqtt.onrender.com. Live checks verified 18 companies, 1,872 EOD rows, 32 documents, 22 announcements, Vercel CORS, contextual people and evidence-only research (8 primary passages). The live bundle uses the actual backend URL and has no access-code screen. Hyde is disabled as requested. Cloud latency exposed repeated per-company/contact/chunk reads; the overview now batches six SQL reads, the digest reuses an owner-scoped prefetched network, and retrieval loads candidate citations in bulk. Regression tests assert bounded query counts and unchanged ranking/owner isolation. Current local suite: 68 passed, 1 optional Postgres test skipped; frontend: 12 passed and production build passed. Initial PostgreSQL integration had previously passed locally and in GitHub CI. Full browser/mobile paint checks remain unverified.
