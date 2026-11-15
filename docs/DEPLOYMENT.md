# Deploy FINN: Vercel + Render Free + durable Supabase

## Separate database password (recommended)

In Render, paste the original Supabase Session-pooler URI into `FINN_DATABASE_URL`, keeping `[YOUR-PASSWORD]` unchanged. Add `FINN_DATABASE_PASSWORD` with the raw database password; do not percent-encode it. The backend inserts and encodes it safely without exposing the value. An already encoded complete URI still works when the separate variable is absent. Recopy a malformed URI rather than manually editing its hostname.

## Fixed submission configuration

The submission no longer depends on Hyde. Set `FINN_LLM_ENABLED=false`, `FINN_SNAPSHOT_MODE=true`, `FINN_AUTO_REFRESH_ENABLED=false`, and `FINN_BOOTSTRAP_ENABLED=false`. Omit all `HYDE_*` and `FINN_LLM_API_KEY` variables. The user has successfully imported 102 objects and 5,849 rows into Supabase; do not rerun the empty-target import. Research remains primary evidence/retrieval/calculations only and is honestly labeled evidence-only, without model synthesis. Snapshot mode disables automatic and UI-triggered source downloads; historical digest and rule evaluation remain interactive.

## Current status

Configuration is prepared. No hosted service has been created or verified yet. Account access, the Supabase project, and secret values are required. Never send credentials in chat or commit them to the repository.

The frontend and synthetic demo workspace open without a login. Visitors share demo settings. This is not production investor authentication; never import real private contact/portfolio information. Operator-only ingestion and private source storage remain protected.

## Free hosting with durable data

| Component | Service | Plan | Data after Render restart |
|---|---|---|---|
| React static assets | Vercel | Hobby/free within applicable usage terms | Redeployed from GitHub |
| FastAPI, one worker | Render | **Free**, explicitly set in `render.yaml` | Compute may sleep/restart; no financial data is stored on its disk |
| Relational data/search | Supabase Postgres | Free within quota | Stored independently of Render |
| Source bytes | Supabase Storage, **private** bucket | Free within quota | Stored independently of Render |
| Optional synthesis | Hyde/OpenAI-compatible | Your provider account | Inference is separately billed; leave unconfigured for evidence-only mode |

[Render Free](https://render.com/docs/free) sleeps after idle periods and has an ephemeral filesystem. [Supabase Free](https://supabase.com/pricing) can pause inactive projects after a week and has capacity/egress limits; free service is not an availability or backup guarantee. Do not select paid services, disks, or upgrades. Configure provider spend limits before enabling Hyde. Check each dashboard's current limits before submission.

## 1. Supabase: persistent database and files

1. Create a **Free** project at https://supabase.com/dashboard. Save its database password privately.
2. Create a Storage bucket named **`finn-private`**. Keep **Public bucket OFF**. Allow at least the prototype's 50 MiB bounded source download size if your plan permits. Add no anonymous read/write policies.
3. From **Connect**, select the **Session pooler**, port **5432**, which supports IPv4. Do not use the IPv6-only direct endpoint or transaction pooler for this deployment. [Connection guide](https://supabase.com/docs/guides/database/connecting-to-postgres).
4. Backend URL format: `postgresql+psycopg://USER:URL_ENCODED_PASSWORD@SESSION_POOLER:5432/postgres?sslmode=require`. Use the actual supplied username/host. Standard `postgresql://` and `postgres://` prefixes are also accepted and normalized to the psycopg driver automatically. URL-encode reserved password characters. This URL is a secret.
5. Get the project URL `https://PROJECT.supabase.co` and **server-only legacy `service_role` key** from project API settings. The storage adapter sends it only from FastAPI; never use it in Vercel/browser code.
6. Keep the Supabase Data API disabled if you do not need it. FINN uses SQL connections and the private Storage API. On initialization FINN enables RLS and revokes PUBLIC/`anon`/`authenticated` access on its own tables and sequences. The server database owner can operate those tables. There are no public storage policies.

### Import the existing local dataset before starting Render

Run from the project root, in your own terminal:

```sh
backend/.venv/bin/python scripts/import_cloud_data.py
```

The helper privately prompts for the connection URI, project URL, and service-role (or new server secret) key, then uploads SHA-addressed source files and copies the local SQLite tables. You can leave `[YOUR-PASSWORD]` in the URI: it then asks for the database password separately and percent-encodes it automatically. Run `backend/.venv/bin/python scripts/import_cloud_data.py --check-only` from the project root to check the database, empty destination and private bucket without uploading or copying data. Failures return controlled codes such as `database_auth`, `database_network`, `bucket_missing`, or `storage_auth`, never raw exceptions. It prints counts, not credentials. Credentials are not written to disk. It preserves IDs and resets Postgres sequences. The target tables must be **empty**; stop any API using that destination. It never clears a populated destination or alters the source database. Source files upload before the metadata transaction; interrupted uploads can be safely retried.

If you already started Render and it seeded the destination, do not delete tables casually. Create a fresh empty project/schema or use reviewed export/migration procedures. An alternative is `FINN_BOOTSTRAP_ENABLED=true`, which downloads the reviewed real sources into the seeded durable store in the background; no existing portfolio/rules are erased. Source access can fail, so importing the verified local workspace is preferable. Set bootstrap back to false after completion.

## 2. Render: deploy backend on Free

1. Sign in at https://dashboard.render.com, connect GitHub, and choose **New → Blueprint** for https://github.com/err400/Finn. Use `render.yaml`.
2. Confirm service plan **Free**. No persistent disk or paid database should be added.
3. Enter the environment variables below in Render's private environment settings. Set `FINN_ACCESS_MODE=public_demo`. The previous `reviewer` value is accepted as a compatibility alias; it no longer requires a code.
4. Initially set `FINN_CORS_ORIGINS` to your intended frontend origin. It must be a JSON array of exact origins with no trailing slash. Update it after Vercel assigns the real URL.
5. Deploy. Backend health is `https://YOUR-SERVICE.onrender.com/api/v1/health`. Database connectivity must report `ok`. Do not paste environment values or logs containing connection information publicly.

Exact build/start commands (root directory `backend`):

```sh
pip install -r requirements-lock.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --loop asyncio --workers 1 --no-proxy-headers
```

One worker is required for this release's refresh locks, graph/index writes, research concurrency limit, and in-process budgets. Supabase is durable; the local `data` folder is used only for process locks in cloud mode.

## 3. Vercel: deploy frontend

1. Sign in at https://vercel.com/new, import `err400/Finn`, and choose root directory **`frontend`**, framework **Vite**, Hobby/free.
2. Set **only public configuration**:
   - `VITE_API_BASE_URL=https://YOUR-SERVICE.onrender.com/api/v1`
   - No access-code variable is needed. Remove old `VITE_REVIEWER_MODE`; it is ignored by this version.
3. Build `npm run build`, output `dist`, install `npm ci`. These defaults and security headers are in `frontend/vercel.json`.
4. Deploy. Copy the actual production URL into Render's `FINN_CORS_ORIGINS`, e.g. `["https://your-finn.vercel.app"]`; redeploy/restart the backend after environment changes.
5. Vite variables are embedded at build time. Redeploy Vercel after changing them. Do not put `HYDE_*`, passwords, bearer codes, or storage keys into Vercel.

The CSP permits API connections to `https://*.onrender.com`; tighten to your exact Render origin once known. If using a custom API domain, update `connect-src`. Routing uses URL hashes, so no SPA catch-all rewrite is needed. Preview domains are not automatically authorized; add an exact trusted preview origin only when needed.

## Environment reference

| Variable | Where | Required/default | Purpose |
|---|---|---|---|
| `FINN_DATABASE_URL` | Backend, secret | SQLite locally; Postgres session-pooler URI hosted | Persistent relational store |
| `FINN_ACCESS_MODE` | Backend | `local` / hosted `public_demo` | Loopback guard or public synthetic demo |
| `FINN_REVIEWER_TOKEN` | Deprecated | Not used; remove from dashboard | No access code is required |
| `FINN_CORS_ORIGINS` | Backend | JSON list of exact frontend origins | Browser allowlist; not authentication |
| `FINN_STORAGE_BACKEND` | Backend | `local` / hosted `supabase` | Source-blob adapter |
| `FINN_STORAGE_URL` | Backend | Supabase project HTTPS URL in cloud mode | Private Storage API origin |
| `FINN_STORAGE_BUCKET` | Backend | `finn-private` | Private bucket |
| `FINN_STORAGE_KEY` | Backend, secret | Required for Supabase storage | Server-side `service_role` JWT |
| `FINN_DATA_DIR` | Backend | `backend/data` | Local blob path or temporary lock folder |
| `HYDE_INFERENCE_API_KEY` | Backend, secret | Optional | Synthesis credential |
| `HYDE_BASE_URL` | Backend | Optional, e.g. `https://inference.hyde.tech/v1` | OpenAI-compatible inference origin |
| `HYDE_MODEL` | Backend | Optional, verified `hyde/glm-5.3-flash` | Model identity |
| `FINN_LLM_API_KEY`, `FINN_LLM_BASE_URL`, `FINN_LLM_MODEL` | Backend | Optional aliases; HYDE variables take precedence | Alternative compatible model |
| `FINN_INGEST_TOKEN` | Backend, secret | Optional; empty disables operator HTTP ingestion | Additional guard on `/data/refresh`; not needed by UI |
| `FINN_AUTO_REFRESH_ENABLED` | Backend | true | Periodic source checks while API is awake |
| `FINN_SOURCE_REFRESH_SECONDS` | Backend | 300 locally; 900 hosted, minimum 300 | Source polling interval |
| `FINN_BOOTSTRAP_ENABLED` | Backend | false; optional fresh-source recovery | Re-ingest reviewed portfolio data, not fabricated fixtures |
| `FINN_EPHEMERAL_STORAGE` | Backend | **false** | Fails closed if public demo lacks durable adapters; true is only an explicitly temporary test alternative |
| `FINN_PRIMARY_CATALOG_PATH` | Backend | Optional path | Operator-reviewed alternative catalog |
| `FINN_REVIEWED_PRIMARY_HOSTS` | Backend | Optional JSON list | Additional reviewed exact PDF hosts |
| `PYTHON_VERSION` | Render | `3.12.12` | Build runtime |
| `PORT` | Render | Platform supplied | Bind public ASGI server |
| `VITE_API_BASE_URL` | Vercel, public | Required hosted API URL including `/api/v1` | Browser API base |
| `VITE_REVIEWER_MODE` | Deprecated | Not used; remove | No login screen |
| `FINN_TEST_POSTGRES_URL` | Test runner only | Optional disposable DB named `finn_audit` | Destructive isolated integration test; never production |

Settings read process environment directly; `.env` is optional and ignored by Git. Health reveals model/configuration status, never keys. Backend environment changes need restart. Database and service-role credentials grant significant privileges; rotate them if exposed.

## 4. Verify the actual deployment

Run from `backend`; no access code is needed:

```sh
.venv/bin/python scripts/verify_deployment.py \
  --frontend https://YOUR-FRONTEND.vercel.app \
  --backend https://YOUR-SERVICE.onrender.com \
  --research --report ../docs/verification/deployed-smoke.json
```

This checks real frontend delivery, backend readiness, public-demo API access, CORS/preflight, portfolio counts, archive coverage, event-to-person integration, and one primary-grounded research request. `--research` may incur inference cost. The report contains no access code. Do not label local smoke reports as deployed verification.

Manually check at 390px and desktop widths: direct app access, digest/filter/routine expansion, citation links and drawer focus, alerts save/pause, research success/failure, keyboard navigation, and source freshness. Then **restart Render** and confirm the same rule IDs, document counts, and citations still exist. Verify that anonymous Supabase table and bucket requests fail. This final cloud persistence/access check is pending account provisioning.

## Maintenance and recovery

The one-time copier is not a general schema migration system. Tables are created additively; existing schema alterations need reviewed migrations. Configure backups/exports, retain them privately, and test restoration. Supabase free-tier pausing is an availability limitation; resume the project before the review. Render can cold-start; do not use artificial keep-alive traffic to evade free-tier policies. Background alerts do not run while the API sleeps. Service deletion/account expiry is different from a Render restart; free hosting is not a retention guarantee.
