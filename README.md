# Career Overfitter

An AI-powered job market intelligence and CV decision-support product, built on [104 Job Bank](https://www.104.com.tw/) data.

## Who this is for

Career Overfitter is built for **early-career and transitioning data/business professionals in Taiwan who are unsure whether their background actually fits Product Analytics, BI, Growth, or Product Management roles**, and who currently have no reliable way to translate scattered, inconsistent job postings into an actionable next step.

That framing drives the concrete choices in this repo: why the data source is 104 rather than a global job board, why the crawler is scoped to a Product Data Analyst-centered keyword set rather than "all jobs," why the taxonomy normalizes role/skill naming instead of showing raw postings, and why the CV Fitting Tool is the centerpiece rather than a generic job search UI.

## What this is (and isn't)

Career Overfitter is an **AI-enabled job market intelligence and CV decision-support product** — a structured data pipeline plus retrieval-augmented (RAG) generation, surfaced through a Streamlit app.

It is **not** an autonomous agent. There is no multi-step task planning, no dynamic tool selection based on intermediate results, no proactive clarifying questions, and no action execution/verification loop. Each feature (AI advice, semantic search, job matching) is a single retrieval-then-generate call, not an agentic loop. The README and UI intentionally avoid the terms "AI agent," "agentic," or "autonomous advisor" for this reason — a true multi-turn conversational advisor is listed as a not-yet-built roadmap item, not a current capability.

## Product Decisions

**Initial hypothesis:** job seekers in this segment don't primarily lack job listings — they lack a reliable way to connect their actual experience to fragmented, inconsistently worded market demand.

**MVP priorities, in order:**

1. Build a structured, deduplicated market dataset from real postings (crawler → cleaner → taxonomy).
2. Surface role and skill demand patterns before offering any individual advice (Skill Dashboard).
3. Ground personalized recommendations in real postings via retrieval, not just aggregated statistics (RAG).
4. Preserve a deterministic, rule-based fallback for every AI-dependent feature so the product still works when the LLM API is unavailable or misconfigured.

**Explicitly deprioritized** (not built, and not accidental gaps):

- Automatic mass applications
- Fully generative resume rewriting (rule-based rewrite suggestions are intentional, not a stopgap)
- Cover-letter generation
- Multi-turn conversational advisor
- Salary predictions unsupported by retrieved postings

## Table of Contents

- [Who this is for](#who-this-is-for)
- [What this is (and isn't)](#what-this-is-and-isnt)
- [Product Decisions](#product-decisions)
- [Features](#features)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Data Pipeline](#data-pipeline)
- [Crawler Scope](#crawler-scope)
- [RAG System](#rag-system-retrieval-augmented-generation)
- [GitHub Actions Workflows](#github-actions-workflows)
- [Maintenance Notes](#maintenance-notes)
- [Roadmap](#roadmap)

## Features

### 🔍 Job Search

- Structured filters: title keyword, company nature (foreign / local, listed / unlisted), industry, role category, salary floor, minimum education, remote preference
- **AI semantic search**: describe the job you want in a sentence (e.g. *"looking for a role doing marketing analytics in Python without heavy engineering"*) and get results ranked by vector similarity against real job descriptions, independent of the structured filters
- Skill tags, quality score, and a direct link back to the original 104 posting on every result
- One-click CSV export

### 📊 Skill Dashboard

- Top-N in-demand skills by frequency
- Median salary by role
- Industry distribution and remote-work ratio
- Sortable raw data table

### 📄 CV Fitting Tool

- Paste resume text or upload a `.txt` / `.md` file
- Extracts canonical skills via a boundary-safe alias matcher (`skill_alias.csv`), with evidence-weight down-ranking for ambiguous short English tokens (e.g. `AI`, `PM`, `UX`) to reduce false positives
- Computes a weighted fit score against every role in the taxonomy, with matched/gap skill breakdowns
- Rule-based rewrite suggestions, always available offline
- **AI advice (Gemini)**: best-fit role, why-it-fits reasoning, key skill evidence, biggest gaps, rewrite suggestions, and next learning actions — generated on demand, with a rule-based fallback if the API is unavailable
- **Recommended real postings**: a separate, independent action that retrieves the actual job postings (not just an aggregated role profile) most similar to your resume via vector search, each with a link to the original 104 listing
- CSV export for both fit scores and skill evidence

## Architecture

```
                     ┌──────────────────┐
  104 Job Bank  ───▶ │  scraper_104.py  │ ───▶  jd_raw (Supabase)
                     └──────────────────┘
                                                     │
                                                     ▼
                                            ┌──────────────────┐
                                            │    cleaner.py     │  rule-based role
                                            │                    │  classification +
                                            └──────────────────┘  skill extraction
                                                     │
                                                     ▼
                                            job_posting (Supabase)
                                                     │
                              ┌──────────────────────┼──────────────────────┐
                              ▼                      ▼                      ▼
                     backfill_embeddings.py   Streamlit app (app.py)   pgvector column
                              │                      │                      │
                              └──────────────────────┼──────────────────────┘
                                                     ▼
                                     utils/rag_retrieval.py + llm_advisor.py
                                        (Gemini generateContent + embedContent)
```

Two independent Gemini API surfaces are used, sharing one `GEMINI_API_KEY`:

- **Embeddings** (`gemini-embedding-001`, via `utils/embeddings.py`) — turn job postings and user queries into vectors, stored in Supabase's `pgvector` extension
- **Generation** (`gemini-2.5-flash`, via `utils/llm_advisor.py`) — turn structured diagnosis + retrieved postings into the AI advice shown on the CV Fitting Tool page

## Project Structure

```
Career_Overfitter/
├── app.py                          # Streamlit entry point (home page)
├── pages/
│   ├── 1_Job_Search.py             # Job browser + AI semantic search
│   ├── 2_Skill_Dashboard.py        # Market-wide skill/salary/industry stats
│   └── 3_CV_Fitting_Tool.py        # CV parsing, fit score, AI advice, job matching
├── utils/
│   ├── supabase_client.py          # Cached Supabase REST queries
│   ├── cv_parser.py                # Skill extraction + fit score computation
│   ├── ui_taxonomy.py              # Shared filter/taxonomy helpers for the UI
│   ├── llm_advisor.py              # Gemini generateContent wrapper (AI advice)
│   ├── embeddings.py               # Gemini embedContent/batchEmbedContents wrapper
│   └── rag_retrieval.py            # Vector search against job_posting via Supabase RPC
├── scraper_104.py                  # 104 crawler → jd_raw
├── cleaner.py                      # jd_raw → job_posting (rule-based classification)
├── backfill_embeddings.py          # Batch-computes embeddings for existing job_posting rows
├── clear_supabase_data.py          # Wipes jd_raw + job_posting (used by the truncate option)
├── sql/
│   └── 001_enable_pgvector_rag.sql # Enables pgvector, adds embedding column, RPC function
├── Job_taxonomy_forsearch.csv      # Active crawler keyword list (currently 12 keywords)
├── Job_taxonomy_forsearch_full.csv # Full 147-keyword backup for re-expanding scope
├── Job_taxonomy_forsearch_marketing_analytics_backup.csv  # Previous scope snapshot
├── Job_taxonomy_byRole.csv         # Role taxonomy used for classification
├── skill_alias.csv                 # Canonical skill alias table
├── skill_taxonomy.csv              # Skill category taxonomy
├── role_alias.csv                  # Role name aliases
├── .github/workflows/
│   ├── cleaner-weekly.yml          # Main pipeline: scrape → clean → backfill embeddings
│   ├── clean-only.yml              # Standalone: re-run cleaner without re-scraping
│   └── test.yml                    # Lightweight single-keyword smoke test
├── requirements.txt
└── .env                            # Local secrets — never commit
```

## Getting Started

### Prerequisites

- Python 3.11+
- A Supabase project (free tier works)
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey) (optional but required for AI advice, semantic search, and job matching)

### Installation

```bash
pip install -r requirements.txt
```

### Environment variables

Create a `.env` file in the project root:

```env
SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co/rest/v1
SUPABASE_KEY=your_anon_or_service_role_key

# Optional — enables AI advice, semantic search, and RAG job matching
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
GEMINI_EMBEDDING_DIM=768
```

If deploying on Streamlit Community Cloud, paste the same key/value pairs into the app's **Settings → Secrets** in TOML format instead — root-level entries there are also exposed as environment variables, so no code changes are needed.

### Required CSV files

These must exist at the project root (already included in this repo):

- `skill_alias.csv`, `skill_taxonomy.csv`
- `Job_taxonomy_byRole.csv`, `role_alias.csv`
- `Job_taxonomy_forsearch.csv` (crawler only)

### Run locally

```bash
streamlit run app.py
```

Open http://localhost:8501.

## Data Pipeline

1. **`scraper_104.py`** reads keywords strictly from `Job_taxonomy_forsearch.csv`, queries 104's list + detail APIs, and upserts raw postings into the `jd_raw` Supabase table. It includes backoff and a blocked-traffic detector (`FAKE_404_THRESHOLD` / `FAKE_404_PAUSE`) since 104 rate-limits aggressively.
2. **`cleaner.py`** reads from `jd_raw`, applies rule-based role classification (against `Job_taxonomy_byRole.csv`) and skill extraction (against `skill_alias.csv`), computes a quality score, and upserts the result into `job_posting`. Run with `--limit` set comfortably above the total `jd_raw` row count and `--only-new` to sweep the entire backlog rather than only the most recently scraped rows.
3. **`backfill_embeddings.py`** computes a Gemini embedding for every `job_posting` row missing one and writes it back, enabling RAG search.

## Crawler Scope

The crawler originally used all 147 keywords across 18 role categories in `Job_taxonomy_forsearch.csv`, split across 8 parallel GitHub Actions matrix shards — total request volume was high enough that 104 started blocking traffic (see the `FAKE_404_THRESHOLD` handling in `scraper_104.py`).

Scope has been narrowed twice:

1. First to `Marketing / Brand / Growth` + `Analytics / Data / BI` (18 keywords) — preserved in `Job_taxonomy_forsearch_marketing_analytics_backup.csv`.
2. Currently centered on **Product Data Analyst** (12 keywords) across `Product Management` and `Analytics / Data / BI`.

The full 147-keyword list is preserved in `Job_taxonomy_forsearch_full.csv` for re-expansion. `cleaner-weekly.yml` currently runs a single matrix shard to match the reduced keyword count.

**To expand or re-focus scope:**

1. Confirm the current scope has been running without repeated blocking.
2. Copy the desired categories/keywords from `Job_taxonomy_forsearch_full.csv` (or a `*_backup.csv` snapshot) into `Job_taxonomy_forsearch.csv`.
3. Adjust `matrix.include` in `cleaner-weekly.yml` — keep each shard around 15–20 keywords, adding shards as needed.

Recommended approach: expand gradually (1–2 categories at a time) rather than reverting to the full list at once, and let the weekly schedule accumulate postings over time within the current scope — dataset growth doesn't require adding keywords, just repeated runs against the same ones.

## RAG System (Retrieval-Augmented Generation)

Three features are grounded in real job postings via vector search rather than aggregated statistics alone:

- **AI advice** (CV Fitting Tool) — retrieves the postings most relevant to the user's resume and target role, and instructs Gemini to prioritize their actual wording over the aggregated skill-weight statistics when generating advice.
- **Recommended real postings** (CV Fitting Tool) — surfaces the retrieved postings directly as a ranked, linked list, independent of the AI advice generation step.
- **Semantic search** (Job Search) — lets users query in natural language instead of exact keyword matching.

### How it works

1. `utils/embeddings.py` calls Gemini's `gemini-embedding-001` (`embedContent` for single queries, `batchEmbedContents` for bulk backfill), truncated to 768 dimensions via `outputDimensionality`. 429 responses are retried with exponential backoff.
2. Vectors are stored in a `job_posting.embedding` column (Postgres `vector(768)`, via the pgvector extension).
3. `utils/rag_retrieval.py` embeds the query text and calls the `match_job_postings` Postgres RPC (cosine similarity, exposed automatically through PostgREST) to retrieve the top-N most similar postings.
4. Every RAG-dependent feature checks availability first and falls back to its non-RAG behavior (rather than erroring) if pgvector isn't set up yet.

### Setup

1. In the Supabase Dashboard, open **SQL Editor** and run the entirety of `sql/001_enable_pgvector_rag.sql` (idempotent — safe to re-run).
2. Backfill embeddings for existing data:
   ```bash
   python backfill_embeddings.py --limit 200
   ```
   Re-run with a larger `--limit` if the row count exceeds it. `cleaner-weekly.yml` runs this automatically after every cleaning pass (`continue-on-error: true`, so a missing migration doesn't fail the whole pipeline).
3. Confirm `GEMINI_API_KEY` is set — no other configuration is required. Every RAG-powered UI section detects availability automatically.

## GitHub Actions Workflows

| Workflow | Trigger | Purpose |
|---|---|---|
| `cleaner-weekly.yml` | Manual (`workflow_dispatch`) | Full pipeline: optional data wipe → scrape → clean (`--limit 20000 --only-new`) → backfill embeddings |
| `clean-only.yml` | Manual | Re-run `cleaner.py` alone (with configurable `limit`/`only_new`/`quality_threshold`) plus an embedding backfill, without re-scraping |
| `test.yml` | Manual | Single-keyword, single-page smoke test of the full scrape → clean pipeline |

Required repository secrets: `SUPABASE_URL`, `SUPABASE_KEY`, `GEMINI_API_KEY`.

`cleaner-weekly.yml` also exposes a `truncate_before_run` checkbox (default off). When enabled, `clear_supabase_data.py` wipes **all** rows from both `job_posting` and `jd_raw` before the pipeline runs. This is irreversible — double-check which Supabase project the secrets point to before enabling it.

## Maintenance Notes

- **Supabase free-tier pausing**: projects with no database activity for 7 days are automatically paused, and the API stops resolving entirely until manually resumed from the dashboard. If the weekly pipeline's cadence isn't frequent enough to count as activity, consider a lightweight keep-alive ping or upgrading to a paid plan.
- **Gemini free-tier rate limits**: embedding backfills batch requests and retry on `429` with exponential backoff; if you still hit limits, reduce `EMBED_BATCH_SIZE` in `backfill_embeddings.py` or increase the sleep between batches.
- **`cleaner.py` defaults**: without `--limit` set high enough, only the most recently scraped rows in `jd_raw` are considered, and older un-cleaned rows can be permanently skipped as they fall out of that window. `cleaner-weekly.yml` and `clean-only.yml` both pass a generous `--limit` to avoid this.
- **Config drift**: `Job_taxonomy_forsearch.csv` is scraper-critical and easy to lose if the repo is fully overwritten from a partial file delivery — always diff or verify file counts after a bulk copy-paste update.

## Roadmap

Implemented: RAG-grounded AI advice, semantic job search, direct CV-to-posting matching.

Under consideration, not yet built (distinct from the [explicitly deprioritized](#product-decisions) list above — these are candidates for future work, not rejected ideas):

- Hybrid skill extraction — supplement the rule-based `skill_alias.csv` matcher with embedding similarity to catch skills phrased outside the alias table, while keeping the rule-based matcher as the primary signal
- Duplicate/near-duplicate posting detection via embedding similarity, to prevent repeated listings from skewing Skill Dashboard aggregates
- Multi-turn conversational career advisor with re-retrieval on every follow-up question — this is the step that would justify calling the product "agentic"; until it exists, the product is described as AI-enabled/RAG-based, not agentic (see [What this is](#what-this-is-and-isnt))
