# Career Overfitter

An AI-powered job market intelligence and CV decision-support product, built on [104 Job Bank](https://www.104.com.tw/) data.

## Who this is for

Career Overfitter is built for **people who know they want to work in analytics but don't know that "analytics" hides behind dozens of different job titles and departments** — a Business Analyst, a Product Analyst, and a Data Scientist may all spend their day doing the same underlying work, and someone scanning job boards by title alone has no way to see that. This is the core insight behind the product's current framing as a **"Google Maps for Analytics Careers"**: instead of starting from a job list, the product starts from a map of the analytics landscape, lets the user pick a path, understand what that path actually involves, and only then shows them individual job postings.

That framing drives the concrete choices in this repo: why the data source is 104 rather than a global job board, why the crawler covers four analytics domains (Business / Product / Marketing / Operations Analytics) rather than one, why there's a curated taxonomy overlay (`analytics_career_map.csv`) mapping raw job titles onto a domain x technical-depth grid, and why the Career Map and Resume pages — not a generic job search box — are the centerpiece.

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
- [The Analytics Career Map](#the-analytics-career-map)
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

## The Analytics Career Map

The product organizes every analytics-flavored job title along two axes, defined in `utils/career_taxonomy.py` and `analytics_career_map.csv` (a curated overlay on top of the 280-row `Job_taxonomy_byRole.csv` classification taxonomy — it doesn't change how jobs get classified, it just re-organizes the analytics-relevant subset of `role_normalized` values into a browsable map):

- **Domain (business application), 4 values**: Business Analytics, Product Analytics, Marketing Analytics, Operations Analytics — *what kind of problem the role analyzes*
- **Technical depth, 4 tiers**: BA → DA → DS → DE (Business Analyst → Data Analyst → Data Scientist → Data Engineer) — *how close the role sits to modeling/engineering*

72 raw role titles (role_normalized) are mapped across the four domains at the data level, but the map displays 40 consolidated sub-role titles (display_role) — near-synonym or over-fragmented raw titles (e.g. BI Analyst / Business Intelligence Analyst / Reporting Analyst, or Data Engineer / Data Pipeline Engineer / ETL Developer) are merged into a single node, with job counts summed across all underlying raw titles so no postings are dropped (the merge mapping lives in the `display_role` column of `analytics_career_map.csv`). For example, Product Analytics contains Product Analyst, Growth Product Analyst, Marketplace Analyst, CRM & Lifecycle Analyst, Data Scientist, and others. Two titles — **Marketplace Analyst** and **CRM & Lifecycle Analyst** — don't appear in standard 104 postings verbatim often enough to have existed in the original taxonomy and were added specifically to give Product Analytics a complete sub-role set; `CRM & Lifecycle Analyst` is named distinctly from the pre-existing `CRM Analyst` (an IT/CRM-systems-implementation role under a different parent category) to avoid conflating the two.

Titles that aren't analytics-flavored (Product Manager, Sales roles, generic HR/Finance roles, etc.) are deliberately excluded from this map — the map's purpose is surfacing analytics work hiding under unfamiliar titles, not cataloguing every job function.

## Features

### 🗺️ Explore Careers

- The landing view of the Analytics Career Map: an X/Y landscape plot, domain on one axis and technical depth on the other, bubble size showing how many current postings fall in each quadrant
- Click or select a domain to drill into its named sub-roles with live counts and median salary, before looking at any individual job

### 🧭 Career Map

- A sunburst hierarchy (Analytics → Domain → Sub-role) — click through from the whole landscape down to one specific title
- Selecting a role shows, **in this order**: what people in this role actually do (plain-language bullets), common related titles, market demand, median salary, top skills, top companies, your resume fit (if you've used the Resume page), and — last, not first — real job postings for that title

### 📄 Resume

- Paste resume text or upload a `.txt` / `.md` file
- Extracts canonical skills via a boundary-safe alias matcher (`skill_alias.csv`), with evidence-weight down-ranking for ambiguous short English tokens (e.g. `AI`, `PM`, `UX`) to reduce false positives
- Computes a weighted fit score against every role in the taxonomy; scores are written to session state so the Career Map page can show "Resume Fit" for whichever role you're looking at, without recomputing
- Rule-based rewrite suggestions, always available offline
- **Career Advisor (Gemini)**: not a generic "ask AI" box — answers scoped career-decision questions (why does this path fit, what skills are missing, how does BI differ from Product Analytics), grounded in retrieved real postings where available, with a rule-based fallback if the API is unavailable
- **Recommended real postings**: a separate, independent action that retrieves the actual job postings most similar to your resume via vector search, each linked to the original 104 listing
- CSV export for both fit scores and skill evidence

### 📈 Market Trends

- **Compare Career Paths**: not a "Top SQL / Top Python" leaderboard — a skill x domain star-rating matrix, so you can see how important a given skill is on each path relative to the others, which is the question people actually have ("which path should I go down") rather than "what's popular"
- Median salary by role, industry distribution, remote-work ratio

### 🎯 Jobs

- Filtering starts from **Career Path** (pick a domain, then its sub-roles), not a raw job-title keyword box
- "What kind of work do you want to do?" — describe your interests in a sentence and the product first tells you which Career Path(s) that sounds like, then lists the matching postings underneath (path, not keyword search, is the product)
- Skill tags, quality score, and a direct link back to the original 104 posting on every result; CSV export

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
                                                     │
                                                     ▼
                                   utils/career_taxonomy.py (domain x tech-depth
                                   overlay, from analytics_career_map.csv) drives
                                   Explore Careers / Career Map / Market Trends / Jobs
```

Two independent Gemini API surfaces are used, sharing one `GEMINI_API_KEY`:

- **Embeddings** (`gemini-embedding-001`, via `utils/embeddings.py`) — turn job postings and user queries into vectors, stored in Supabase's `pgvector` extension
- **Generation** (`gemini-2.5-flash`, via `utils/llm_advisor.py`) — turn structured diagnosis + retrieved postings into the Career Advisor output shown on the Resume page

## Project Structure

```
Career_Overfitter/
├── app.py                          # Streamlit entry point (home page, flow overview)
├── pages/
│   ├── 1_Explore_Careers.py        # Domain x tech-depth market landscape (XY plot)
│   ├── 2_Career_Map.py             # Sunburst hierarchy + per-role detail panel
│   ├── 3_Resume.py                 # CV parsing, fit score, Career Advisor, job matching
│   ├── 4_Market_Trends.py          # Compare Career Paths (skill x domain matrix), salary, industry
│   └── 5_Jobs.py                   # Career Path-first job browser + NL path routing
├── utils/
│   ├── supabase_client.py          # Cached Supabase REST queries
│   ├── cv_parser.py                # Skill extraction + fit score computation
│   ├── ui_taxonomy.py              # Shared filter/taxonomy helpers for the UI
│   ├── career_taxonomy.py          # Analytics Career Map overlay (domain x tech-depth)
│   ├── llm_advisor.py              # Gemini generateContent wrapper (Career Advisor)
│   ├── embeddings.py               # Gemini embedContent/batchEmbedContents wrapper
│   └── rag_retrieval.py            # Vector search against job_posting via Supabase RPC
├── scraper_104.py                  # 104 crawler → jd_raw
├── cleaner.py                      # jd_raw → job_posting (rule-based classification)
├── backfill_embeddings.py          # Batch-computes embeddings for existing job_posting rows
├── clear_supabase_data.py          # Wipes jd_raw + job_posting (used by the truncate option)
├── sql/
│   └── 001_enable_pgvector_rag.sql # Enables pgvector, adds embedding column, RPC function
├── Job_taxonomy_forsearch.csv      # Active crawler keyword list (42 keywords, 4 domains)
├── Job_taxonomy_forsearch_full.csv # Full 147-keyword backup for re-expanding scope
├── Job_taxonomy_forsearch_marketing_analytics_backup.csv  # Previous scope snapshot
├── Job_taxonomy_byRole.csv         # Role taxonomy used for classification (280 rows)
├── analytics_career_map.csv        # role_normalized → (domain, tech_depth) overlay for the map
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

Scope has since been adjusted three times:

1. First narrowed to `Marketing / Brand / Growth` + `Analytics / Data / BI` (18 keywords) — preserved in `Job_taxonomy_forsearch_marketing_analytics_backup.csv`.
2. Narrowed further to **Product Data Analyst** only (12 keywords) across `Product Management` and `Analytics / Data / BI`.
3. **Currently expanded to 42 keywords across four domains** — `Product Management`, `Analytics / Data / BI` (12 keywords, unchanged), plus new `Business Analytics`, `Marketing Analytics`, and `Operations Analytics` categories (30 new keywords) — so the Analytics Career Map (see below) has real market data across all four analytics domains instead of only Product.

The full 147-keyword list is preserved in `Job_taxonomy_forsearch_full.csv` for reference. `cleaner-weekly.yml` runs 3 matrix shards of ~14 keywords each (`offset 0/14/28`, `limit 14`) to cover the current 42-keyword scope; shard count was deliberately kept low (3 large shards rather than more, smaller ones) to minimize per-shard checkout/setup overhead, at a slightly higher per-shard risk of 104 rate-limiting than the previous single 12-keyword shard. Watch `scrape-104` job logs for `FAKE_404` warnings after this change — if blocking recurs, split into more, smaller shards (e.g. 6 shards of ~7) rather than cutting keywords.

**To expand or re-focus scope further:**

1. Confirm the current 4-domain scope has been running without repeated blocking.
2. Add or replace keywords in `Job_taxonomy_forsearch.csv` (or copy more categories from `Job_taxonomy_forsearch_full.csv`).
3. Adjust `matrix.include` in `cleaner-weekly.yml` — keep each shard around 14–20 keywords, adding shards as needed.

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
