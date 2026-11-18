# Meridian Analytics

A user-scoped e-commerce data analytics platform built with Next.js, TypeScript, FastAPI, and Supabase. See [the architecture and phase plan](docs/architecture.md).

## Local setup

1. Copy the root `.env.example` to `apps/web/.env.local` and set the Supabase project URL and publishable/anon key. Copy `services/api/.env.example` to `services/api/.env` and set backend JWT verification and service-only credentials. Never put the service role key in a `NEXT_PUBLIC_` variable.
2. Apply `services/api/migrations/0001_initial_schema.sql` and `services/api/migrations/0002_kaggle_ephemeral_import.sql` to the Supabase project.
3. Install frontend dependencies with `pnpm install` from the repository root.
4. Start the web app with `pnpm dev:web`.
5. In `services/api`, create a virtual environment, install the project (`pip install -e '.[dev,data]'`), then run `uvicorn app.main:app --reload --port 8000`.
6. Start the worker in another terminal with `pnpm dev:worker`; analytics require completed ELT jobs.
7. Configure Email and Google providers plus redirect URLs in Supabase Auth before using those sign-in options. Configure an LLM key/model only if you want optional provider-assisted planning and narrative; local catalog analysis does not require one.

No dataset or analytics are seeded by the application. Smaller CSVs can still be uploaded through the browser and stored in private Supabase Storage. For large public files, use **Datasets → Import from Kaggle**: the worker discovers the current CSV manifest, downloads selected files one at a time to temporary worker storage, converts them to temporary Parquet, computes the analytics snapshot, and removes both raw and transformed temporary files. Only source metadata, schema/quality summary, processing lineage, and bounded analytics results are kept. The worker needs temporary free disk space of approximately 1.5× the selected uncompressed size; configure `MAX_KAGGLE_IMPORT_BYTES` and `KAGGLE_TEMP_DISK_FACTOR` for deployment. Dataset-specific exact duplicate scans, per-column distinct counts, and outlier scans are skipped for these large source imports and shown as not measured. The reference Kaggle manifest should be checked in the UI because its available file list can change. See the [Kaggle dataset card](https://www.kaggle.com/datasets/mkechinov/ecommerce-behavior-data-from-multi-category-store), [Kaggle dataset download API docs](https://github.com/Kaggle/kaggle-cli/blob/main/docs/datasets.md), [Supabase resumable upload guide](https://supabase.com/docs/guides/storage/uploads/resumable-uploads), and [Supabase file size limits](https://supabase.com/docs/guides/storage/uploads/file-limits).

Background jobs persist in PostgreSQL and are claimed by the worker. Uploaded datasets retain the original and typed Parquet version. Kaggle imports retain neither raw nor transformed files; their dashboard and supported AI queries use a versioned analytics snapshot computed from all selected months. Supported analytics include event/funnel metrics, product/category/brand rankings, time trends, descriptive customer engagement and return metrics, activity cohorts, and Pearson correlations for eligible numeric fields. Unsupported analyses explain which fields are missing. Cleaning suggestions are reported for review; no rows are automatically removed.

For validation, run `pnpm --dir apps/web exec eslint src`, `pnpm --dir apps/web exec next build`, and from `services/api` run `.venv/bin/ruff check app tests && .venv/bin/pytest -q`.
