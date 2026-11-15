# Security, privacy, and content boundaries

## Implemented boundaries

- Default mode accepts loopback clients only. The deployment command disables forwarded-header trust; a proxy cannot authenticate a request by supplying `X-Forwarded-For`.
- Hosted **reviewer mode** requires a server-side code of at least 32 characters, constant-time bearer comparison, and an exact Origin allowlist. All portfolio, source, PUSH, research, and Network endpoints use the gate; health and API schemas expose no workspace content. Missing configuration fails startup. CORS is not treated as authentication.
- The frontend asks for the code at runtime. It is kept in module memory only, cleared on reload/lock, and excluded from localStorage/sessionStorage, URLs, analytics, and build-time variables. Session locking unmounts private views and clears resource caches. HTTPS is required on hosting.
- Reviewer mode enforces shared request/write/research budgets and one active research request. These are single-process controls and reset on restart, not a substitute for provider spend caps or an API gateway.
- Raw PDF download is disabled in reviewer mode. Citation links open the original issuer document. GitHub/source ZIP exclude source bytes, local databases, private logs/captures, `.env`, keys, assignment PDFs, and chat exports. No financial-content redistribution license is implied by public URLs or private access codes.
- Source downloads use reviewed hosts/paths, bounded size and redirects, timeouts, throttles, safe failure messages, SHA integrity checks, and conservative identity checks. Additional issuer hosts require operator review and public-address DNS resolution. No exchange challenge/cookie bypass or undocumented scraping API is used.
- Cloud SQL uses the backend connection only. FINN enables RLS and revokes PUBLIC/browser-role grants on its own tables and sequences. Private object bytes use a **private bucket** and a server-only service-role credential. The browser receives neither database credentials nor Supabase service keys. Do not add anonymous Storage policies.
- Source files are content-addressed; the backend verifies their hash before consuming them. Original/final URLs, fetch dates, actual issuer dates, and page numbers remain available. Date-only evidence never acquires an invented timestamp.
- API responses disable browser/shared-cache storage and set `nosniff` and no-referrer headers. Vercel adds frame, CSP, and device-permission restrictions. React renders model/source text as text, without arbitrary HTML rendering.
- API/model/storage failure responses do not return raw upstream bodies or credentials. Settings redact secrets and hide validation input values. Avoid enabling verbose HTTP wire logging or putting secrets in request URLs. The release scanner is heuristic, not a formal secret-audit guarantee.

## Network consent and owner isolation

Every demo profile, employer history, education record, expertise label, relationship edge, and strength is synthetic. Professional histories are not attached to identifiable real people. Only explicit synthetic relationship edges establish reachability; shared employment/education never creates an acquaintance. Scores explain their components and are not probabilities, endorsements, proof of management access, or permission to solicit inside information.

Network queries scope a fixed demo owner and reject cross-owner graph edges. Non-synthetic profiles are excluded. There is no real-contact import endpoint, LinkedIn scrape, messaging, email/SMS delivery, or autonomous introduction.

**Not implemented:** real investor identity, per-user authentication/sessions, consent collection/withdrawal, profile correction/export/deletion, and audited real-data imports. A shared reviewer code grants access to one synthetic workspace, so reviewers share saved demo rules. It must not be marketed as multi-tenant production security.

A production system must separately establish consent to store a profile and consent to store the investor's private relationship; a public biography does not grant both. Authenticate the owner, authorize every object, audit access, restrict service roles, and implement consent revocation across profiles, roles, edges, derived matches, caches, and backups before admitting real network data.

## LLM boundary

Only the question and retrieved **public primary-document passages** go to the configured inference service. No contacts, relationship paths, private notes, portfolio ownership, storage credentials, or database passwords enter the prompt. Questions may themselves contain sensitive information; production requires provider/data-processing review and an explicit policy for that input.

The model selects indexed source sentences. The server reconstructs quotations and verifies exact passage membership, document/page identity, and citation URLs. Free-form model limitations cannot introduce uncited financial claims. Prompt documents are treated as untrusted data. Traceability establishes what a source says; it is not independent verification that management's statement is true or that retrieved evidence is complete. Numerical comparisons never use model arithmetic.

## Retention and recovery

Current retention is **until operator deletion**, not timed expiry. Source/model TTLs control cache reuse, not deletion. Local files remain in SQLite/blob storage until removed. Cloud records and objects persist outside Render across API restarts; deletion of the Supabase project or provider retention policies is a separate event. Free plans can pause and are not a backup/availability commitment.

For this synthetic submission, retain the workspace only for the review period. Afterwards revoke the reviewer code, remove the cloud project/bucket if no longer needed, remove local copies and private exports, and rotate/revoke unused provider keys. Do not put private backups or chat histories in GitHub. Production needs scheduled retention, verified delete/export, legal holds, short redacted operational-log retention, encrypted backups, documented backup expiry, and restoration tests. None of those production workflows are claimed complete.

## Remaining deployment checks

Supabase credentials/account access are not available in this session. Private Storage transport is tested with mocked HTTP, and Postgres persistence/RLS/search is tested on an isolated real Postgres server. Actual cloud role grants, bucket policies, TLS connection, frontend CORS, and persistence after a Render restart still need live verification. Raw-source usage rights must be appropriate for the intended review audience; use licensed content for broader distribution.
