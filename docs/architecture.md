# E-Commerce Analytics Platform — Architecture

## Product scope

Build a user-authenticated analytics platform for user-uploaded tabular data. The initial vertical demonstration uses the Kaggle E-Commerce Behavior Data from Multi-Category Store. The application remains schema-driven and must not assume every uploaded dataset has the Kaggle schema. Initial ingestion supports browser CSV uploads and public Kaggle dataset imports; the source interface remains modular so authorized APIs, databases, and streams can be added later. No live connector or streaming runtime is part of this release.

All figures, charts, and natural-language findings must derive from uploaded/processed data and carry enough provenance to inspect the computation. If the data cannot support a metric, the UI and agent explain the limitation. No sample dashboards, dummy records, or fabricated insights.

## System architecture

```text
Browser
  └── Next.js App Router (React, TypeScript, Tailwind CSS, reusable component system, Recharts)
        ├── Supabase Auth client (email/password, Google OAuth, recovery)
        └── FastAPI API (Bearer JWT verification; user-scoped operations)
              ├── Ingestion adapters (CSV upload and public Kaggle sources)
              ├── Background processing jobs (initially worker process + PostgreSQL job state)
              ├── ELT / profiling / quality / type inference (Polars)
              ├── Deterministic analytics catalog (Polars)
              ├── AI planner/orchestrator (constrained tools; provider adapter)
              └── Supabase PostgreSQL + private Supabase Storage
```

Use a modular monolith for the first release: separate packages and boundaries without introducing distributed services prematurely. FastAPI is the trusted application backend for processing and AI. The browser holds the Supabase user session and sends its access token to FastAPI. FastAPI validates the JWT, derives the user identity from verified claims, and applies user ownership checks on every dataset, job, result, and conversation operation. Never trust a caller-supplied `user_id`.

## Repository layout

```text
apps/
  web/                         # Next.js App Router UI
    src/app/(auth)/             # sign-in, sign-up, recovery
    src/app/(app)/              # protected dashboard routes
    src/components/             # shared UI and visualizations
    src/components/              # app shell, dataset workflows, charts, agent UI
    src/lib/                    # Supabase clients and authenticated API client
services/
  api/                          # FastAPI service
    app/api/v1/                 # identity and job routes
    app/core/                   # settings and JWT authentication
    app/db/                     # Supabase REST/storage client
    app/datasets/                # CSV upload, preview, profiling
    app/analytics/               # deterministic analytics and evidence
    app/agent/                   # constrained planning and grounded answers
    app/workers/                 # background ELT worker and pipeline
    migrations/                  # SQL schema, Storage bucket, and RLS policies
  tests/                         # data and API unit tests
docs/                            # architecture and setup
```

## Authentication and request flow

1. Unauthenticated visitors see sign-in/sign-up; routes under `/(app)` require a valid Supabase session.
2. Email/password and Google OAuth use Supabase Auth. Recovery uses Supabase reset links and configured redirect URLs.
3. The web API client attaches the current Supabase access token to FastAPI requests. FastAPI validates signature, issuer, audience, and expiry using Supabase's supported JWT verification configuration.
4. The backend maps verified `sub` to `auth.users.id`; profile records are created on signup via a database trigger or idempotent profile upsert.
5. Sign-out clears the Supabase session. Refresh and recovery callbacks are handled through server-compatible Next.js routes.
6. Supabase RLS protects browser-accessible profile/metadata rows. Backend privileged access, if used, is isolated to server secrets and every route independently enforces owner scoping. The Supabase secret key (or legacy service-role JWT) never reaches the browser.

## Data model (Supabase PostgreSQL)

- `profiles`: `id` (auth user FK), display name, timestamps.
- `datasets`: `id`, `owner_id`, name, original filename, nullable storage object key, byte size, content hash, source type and metadata, status, detected schema JSON, row/column counts, active version, created/updated timestamps.
- `dataset_versions`: `id`, `dataset_id`, owner scope through dataset, version number, raw/derived object keys, schema snapshot, row count, transformation config, created timestamp.
- `processing_jobs`: `id`, `dataset_id`, `owner_id`, version, status, stage, progress, started/finished timestamps, error code/message (sanitized), retry count.
- `processing_logs`: `id`, `job_id`, stage, severity, structured details, timestamp.
- `data_quality_reports`: `id`, `dataset_version_id`, summary and column-level quality JSON, generated timestamp.
- `dataset_analytics_snapshots`: `dataset_id`, `dataset_version_id`, owner, bounded computed analytics JSON, created timestamp.
- `analysis_runs`: `id`, dataset/version, owner, question/plan, method/tool versions, status, result JSON, evidence index, timestamps.
- `agent_conversations`: `id`, owner, dataset context, title, timestamps.
- `agent_messages`: `id`, conversation, owner, role, content, tool call/result references, evidence IDs, timestamp.

Use UUID primary keys, foreign keys, indexes on owner and parent identifiers, and checks/enums for states. Store large raw and transformed files in private Storage buckets; store metadata and bounded analytical outputs in Postgres. RLS is enabled on all user-owned tables. Policies bind ownership to `auth.uid()` either directly or through the parent dataset/conversation. Storage paths begin with the owner UUID and bucket policies enforce the same ownership. Migrations are version-controlled and reviewed with the application.

## Large public Kaggle imports

The UI obtains the CSV file manifest from Kaggle's public API and lets the user select files. FastAPI validates the Kaggle host and dataset handle, confirms that every selected file appears in the public manifest, checks configured byte limits and available worker scratch disk, then queues an owner-scoped job. The worker downloads one Kaggle ZIP at a time, extracts only the requested CSV into temporary disk, validates consistent columns across monthly files, and converts each file to a temporary streaming-friendly Parquet part. It scans those parts as a single dataset and calculates the supported dashboard and agent catalog once. It stores only a compact versioned analytics snapshot and quality summary in PostgreSQL; it does not upload raw CSVs or Parquet parts to Supabase. All temporary files are removed on success or failure. Configure worker scratch disk to at least 1.5× selected uncompressed bytes; the setting is checked both before enqueue and on the worker.

For this large-source path, exact duplicate-row detection, per-column exact distinct counts, and outlier scans are explicitly marked not measured to avoid expensive/high-memory operations over tens of gigabytes. Missing-cell and row counts are computed. The supported analytics snapshot includes actual global event, user/session, funnel, product/category/brand, time, cohort, customer aggregate, and eligible numeric correlation results. Agent ranking queries use bounded per-dimension/per-event ranking arrays in that snapshot. If a result is not in the snapshot's deterministic catalog, the agent reports that it cannot answer from the retained analytics; it never invents a result. Re-fetching a source to run a newly added analysis is an explicit future capability.

## CSV ELT pipeline

1. **Upload/extract:** backend creates an owner-scoped upload intent; the browser uploads directly to the private Storage bucket through resumable TUS chunks, then calls a completion endpoint. The backend verifies object size, reads a bounded byte range for the preview, and validates the CSV header. Processing starts only after the user reviews the preview and chooses to continue.
2. **Load:** preserve the exact original object and its hash. Record metadata before processing. A background job reads in chunks where practical and reports stage/progress.
3. **Profile:** the worker infers data types and candidate semantic roles; calculates row/column counts, missingness, duplicate rows, distinct values, numeric summaries, and IQR outlier candidates over the dataset.
4. **Transform:** create a new version as typed Parquet, flag missing values/duplicates/outliers, and offer suggested actions in the quality report. This release does not silently delete or impute rows; the original remains preserved.
5. **Features:** normalize recognized e-commerce role values inside deterministic analytics. General schema profiling is reusable, and unavailable domain analytics explain missing roles. Manual field mapping and user-approved transformations are future additions.
6. **Publish:** mark the version ready only when the pipeline completes. Failed jobs retain structured errors and can be retried without corrupting the raw object.

Processing status is persisted, so the UI can poll job status initially and later switch to server-sent events without changing job semantics. Set configurable file/row/column limits and benchmark the agreed local deployment target before claiming capacity.

## Analytics strategy

The backend returns typed metric objects with value, unit, definition, filters, time window, source version, computation timestamp, and evidence reference. Visualizations consume these API results; chart components do not define metric values.

The implemented profile reports schema, inferred types, row/column counts, missingness, distinct values, duplicate rows, numeric summaries, and IQR outlier candidates. Current analytics APIs provide event/funnel metrics, product/brand/category rankings and conversion, hourly/daily event trends, descriptive user engagement and session-return counts, first-observed-activity monthly cohorts, and pairwise Pearson correlations for eligible numeric fields. Customer engagement bands are descriptive tertiles, not predictive customer classifications. Each feature returns an explicit unavailable reason when required roles or data are missing. The AI agent's current deterministic tool catalog supports overview metrics, dimension rankings, and hourly/daily trends; the dashboard exposes the other analytics separately.

For the Kaggle event data, purchase-event `price` aggregates can be reported as observed purchase-event value, with limitations about event/order identity. Conversion/abandonment denominators and session windows must be defined explicitly. Do not call event price sums verified merchant revenue without order/transaction semantics. Missing fields produce an unavailable state with a reason.

All statistical computations run in deterministic Python tools, are unit tested against known reference calculations, and record method/version/parameters. Statistical checks include sample size and applicable assumptions; where assumptions fail, report caveats or an eligible alternative. Forecasting and predictive models remain opt-in and must report validation and leakage constraints.

## AI analytics agent

The LLM is a planner and language layer, not a calculator or database authority.

1. Resolve the active conversation and dataset from authenticated, server-side context.
2. Read schema/profile metadata and ask a clarifying question if the request is ambiguous or unsupported.
3. Produce a constrained structured plan: intent, required columns, selected catalog method, filters/time grain, eligibility requirements, and output form.
4. Validate the plan against a server-owned tool registry and dataset schema. No arbitrary SQL, shell, Python, or unrestricted file access is exposed to the model.
5. Execute parameterized, deterministic analytics functions scoped to the authorized dataset/version.
6. Return results with evidence IDs, definitions, filters, limitations, and optional chart/table specification. The LLM may phrase only those supplied facts; claims without tool evidence are rejected or marked unsupported.
7. Persist conversation messages, plan, tool results, model/provider metadata, and evidence references under the user. Follow-ups use bounded conversation context and re-run computations when needed.

Provider credentials are optional environment secrets. The system supports an explicit unavailable/configuration state when no LLM is configured; deterministic dashboard analytics and supported catalog operations continue to work. Use quotas, timeouts, bounded result sizes, prompt-injection-resistant tool boundaries, and audit logs that avoid storing secrets or raw sensitive rows.

## API outline (v1)

- `GET /health` — liveness/readiness without secrets.
- `POST /datasets/upload-intents`, `POST /datasets/{id}/complete-upload` — create owner-scoped upload metadata, then validate the completed Storage object and persist a bounded preview.
- `GET /datasets/kaggle/files`, `POST /datasets/kaggle/import` — list public CSVs and queue selected files for an ephemeral large-source import.
- `GET /datasets`, `GET /datasets/{id}`, `GET /datasets/{id}/preview` — owner-scoped library/details/limited preview.
- `POST /datasets/{id}/process` — create/retry ELT job.
- `GET /jobs/{id}`, `GET /jobs/{id}/logs`, `GET /datasets/{id}/quality` — processing status and lineage.
- `GET /datasets/{id}/analytics/overview`, `/products`, `/time`, `/customers`, `/cohorts`, `/correlations` — actual computed analytics with explicit unavailable fields.
- `GET /agent/status`, `GET|POST /agent/conversations`, `GET /agent/conversations/{id}/messages`, `POST /agent/conversations/{id}/messages` — scoped agent history and tool-backed question execution.

Use Pydantic request/response models, pagination, request IDs, consistent error shapes, rate limits, idempotency for upload completion/job enqueue, and generated OpenAPI contracts.

## Security and privacy

- Supabase Auth owns identity; validate all bearer tokens server-side.
- Enforce owner checks in every backend repository/service operation, even when RLS is also enabled.
- Private storage, short-lived signed URLs, upload size/type limits, safe filenames, content hashes, and no public buckets.
- Apply RLS to profiles, datasets, versions, jobs/logs, reports, runs, conversations, and messages; test cross-user denial.
- Secrets live only in environment configuration. Commit `.env.example` with placeholders, never credentials.
- Parameterized queries, allow-listed analytics tools, bounded compute/time/memory, upload parser isolation, and sanitized error responses.
- Minimize retention of raw data in logs and prompts. Do not send raw records to an LLM by default; aggregate/slice server-side and disclose provider use.

## Delivery phases and acceptance gates

1. **Foundation:** monorepo, local development setup, Supabase migrations/RLS, auth routes and protected shell. Gate: registered/logged-in user identity is propagated to FastAPI and a second user cannot read first-user records.
2. **Upload/library:** CSV upload, private raw storage, validation, preview, ownership and progress. Gate: original bytes/hash preserved and malformed uploads produce actionable errors.
3. **ELT/quality:** background jobs, schema inference, quality report, transformations/versioning/logs. Gate: known fixture metrics match reference calculations; raw version remains intact.
4. **Analytics:** schema-aware APIs and dashboard visualizations with unavailable states. Gate: each displayed value traces to a processed dataset/version and computation.
5. **Agent:** structured planner, method validator, deterministic tools, evidence-grounded responses, conversation history. Gate: unsupported question/tool requests are rejected; supported answers match tool output and respect user scope.
6. **Evaluation/packaging:** benchmark tasks, robustness and security checks, deployment docs and optional Docker. Gate: report profiling/selection/numerical correctness, grounding, failures, and measured limits.

## Open operational inputs

Implementation can start with environment placeholders. To run the integrated cloud flow, the project owner will need to configure a Supabase project URL/anon key and backend-only service credentials, Google OAuth settings in Supabase, and an LLM provider key if agent-generated natural-language phrasing is desired. The Kaggle CSV is not assumed to be present locally; users can upload it through the app, or the owner can supply a local copy for reproducible development fixtures. No credentials or data are committed to the repository.
