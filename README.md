# RetailIQ – Intelligent Retail Analytics

**RetailIQ** is an intelligent e-commerce data analytics platform built using Next.js, TypeScript, Python, FastAPI, and Supabase. The application provides data processing, customer analytics, visualizations, and machine learning-based insights through an interactive analytics dashboard.

The application interface is named **Meridian Analytics**.

See the [Architecture and Phase Plan](docs/architecture.md).

## 1. Project Overview

RetailIQ aims to simplify e-commerce data analysis by providing tools for:

- E-commerce dataset uploading and processing.
- Customer analytics and engagement analysis.
- RFM (Recency, Frequency, Monetary) analysis.
- Customer segmentation using K-Means clustering.
- Interactive analytics dashboards and visualizations.
- Product, category, and brand performance analysis.
- Data quality checks and cleaning suggestions.
- AI-assisted analytical insights.

## 2. Prerequisites

Before running the project, ensure that the following software and services are available:

- **Node.js** – JavaScript runtime.
- **pnpm** – Frontend package manager.
- **Python** – Backend and machine learning environment.
- **Git** – Version control system.
- **Supabase account** – Database, authentication, and storage services.
- **Internet connection** – Required for installing dependencies and accessing configured services.

## 3. Technologies and Dependencies

The project uses the following technologies:

| Component | Technology |
|---|---|
| Frontend | Next.js, React, TypeScript |
| Backend | Python, FastAPI |
| Database | Supabase PostgreSQL |
| Authentication | Supabase Auth |
| Storage | Supabase Storage |
| Data Processing | Pandas, Parquet |
| Machine Learning | Scikit-learn |
| Data Analysis | Python |
| Package Management | pnpm, pip |
| Background Processing | ELT Worker |

Project dependencies are maintained in `package.json` and the backend Python project configuration.

## 4. Repository Structure

The repository is organized into the following main directories:

- `apps/` – Frontend application.
- `services/` – Backend API and background processing services.
- `ml/` – Machine learning scripts, datasets, models, and outputs.
- `docs/` – Project architecture and documentation.
- `README.md` – Project setup and execution instructions.

## 5. Installation and Setup

Follow these steps to configure the project locally.

### Step 1: Configure Environment Variables

Copy the root `.env.example` file to `apps/web/.env.local` and configure the Supabase project URL and publishable/anon key.

Copy `services/api/.env.example` to `services/api/.env` and configure backend JWT verification and service-only credentials.

**Security note:** Never expose the Supabase service role key through a `NEXT_PUBLIC_` environment variable or commit private environment files to GitHub.

### Step 2: Configure the Database

Apply the following SQL migration files to your Supabase project:

- `services/api/migrations/0001_initial_schema.sql`
- `services/api/migrations/0002_kaggle_ephemeral_import.sql`

### Step 3: Install Frontend Dependencies

Run the following command from the repository root:

```bash
pnpm install
```

### Step 4: Configure the Python Backend

Navigate to the backend directory:

```bash
cd services/api
```

Create and activate a Python virtual environment, then install the project dependencies:

```bash
python -m venv .venv
```

For Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Install the backend dependencies:

```bash
pip install -e ".[dev,data]"
```

## 6. Running the Project

The project requires the frontend, backend API, and background worker to run.

### Frontend

From the repository root, execute:

```bash
pnpm dev:web
```

### Backend API

From the `services/api` directory, execute:

```bash
uvicorn app.main:app --reload --port 8000
```

### Background Worker

Open another terminal at the repository root and execute:

```bash
pnpm dev:worker
```

Analytics processing requires completed ELT jobs.

### Authentication Configuration

Configure Email and Google authentication providers and their redirect URLs in Supabase Auth before using those sign-in options.

An LLM API key and model are optional and are only required for provider-assisted planning and narrative features. Local catalog analysis does not require an LLM API key.

## 7. Dataset Information

No dataset or analytics are automatically seeded by the application.

Smaller CSV files can be uploaded through the browser and stored in private Supabase Storage.

For large public datasets, use **Datasets → Import from Kaggle**.

The worker discovers the current CSV manifest, downloads selected files one at a time to temporary worker storage, converts them to temporary Parquet files, computes the analytics snapshot, and removes both raw and transformed temporary files.

Only source metadata, schema and quality summaries, processing lineage, and bounded analytics results are retained.

The worker requires temporary free disk space of approximately 1.5 times the selected uncompressed dataset size.

The following environment variables can be configured for deployment:

- `MAX_KAGGLE_IMPORT_BYTES`
- `KAGGLE_TEMP_DISK_FACTOR`

For large source imports, exact duplicate scans, per-column distinct counts, and outlier scans are skipped and reported as not measured.

The available Kaggle manifest should be checked in the application because its file list can change.

### Dataset Reference

The project uses the following reference e-commerce dataset:

[Online Retail / E-commerce Behavior Dataset – Kaggle](https://www.kaggle.com/datasets/mkechinov/ecommerce-behavior-data-from-multi-category-store)

Additional documentation:

- [Kaggle Dataset Download API](https://github.com/Kaggle/kaggle-cli/blob/main/docs/datasets.md)
- [Supabase Resumable Upload Guide](https://supabase.com/docs/guides/storage/uploads/resumable-uploads)
- [Supabase File Size Limits](https://supabase.com/docs/guides/storage/uploads/file-limits)

## 8. Analytics and Processing

Background jobs persist in PostgreSQL and are claimed and processed by the worker.

Uploaded datasets retain the original file and typed Parquet version.

Kaggle imports retain neither raw nor transformed files. Their dashboards and supported AI queries use a versioned analytics snapshot computed from all selected months.

Supported analytics include:

- Event and funnel metrics.
- Product, category, and brand rankings.
- Time-based trends.
- Customer engagement and return metrics.
- Activity cohorts.
- Pearson correlations for eligible numerical fields.

Unsupported analyses explain which fields are missing.

Data cleaning suggestions are provided for review. No rows are automatically removed.

## 9. Testing and Validation

The following commands can be used to validate the frontend.

Run from the repository root:

```bash
pnpm --dir apps/web exec eslint src
```

```bash
pnpm --dir apps/web exec next build
```

For backend validation, run from `services/api`:

```bash
.venv/bin/ruff check app tests
```

```bash
.venv/bin/pytest -q
```

## 10. Security and Configuration

- Keep API keys and private credentials in environment files.
- Do not commit `.env` or `.env.local` files.
- Use Supabase authentication and appropriate access controls.
- Never expose service-role credentials in frontend code.
- Configure deployment-specific environment variables before running the application in production.

## 11. Project Repository

**GitHub Repository:**  
https://github.com/Cherrysonsale23/RetailIQ-Intelligent-Retail-Analytics

---

**Project:** RetailIQ – Intelligent Retail Analytics  
**Purpose:** E-commerce Data Analytics and Customer Segmentation  
**Technologies:** Next.js, TypeScript, Python, FastAPI, Supabase, Pandas, and Scikit-learn
