# Pulso — Build Prompt

> **How to use:** Create an empty folder called `pulso`, put this file in it, open Claude Code in that folder, and say:
> "Read PULSO_BUILD_PROMPT.md and follow it."

## Amendment log

Only owner-approved decisions are applied to this file. Proposed defaults live in `docs/DECISIONS.md` until the owner approves them. Amended text is tagged *(A-n)* where it appears.

| # | Date | Section | Change | Decision |
|---|---|---|---|---|
| A-1 | 2026-10-22 | §0 Working rules | The repo lives at `C:\dev\pulso`, outside OneDrive. Until Railway go-live, the owner's Windows PC is the single collector host. Only its main checkout runs Celery Beat and live collectors; agent worktrees never do. A Postgres advisory lock enforces a single scheduler. | DEC-001, DEC-002, DEC-005 |
| A-2 | 2026-10-22 | §0 Working rules | Every feature and aspect of the site is tracked as its own note in the Obsidian vault. `docs/` keeps the five files listed in §3. | DEC-006 |
| A-3 | 2026-10-22 | §1 Users | v1 market: US only, prices in USD. | DEC-004 |
| A-4 | 2026-10-22 | §1 Brand and design | Dark SaaS look with a green accent, big-tech polish and polished motion, combined with the data-dense terminal views. | DEC-007 |
| A-5 | 2026-10-22 | §2 Frontend | Motion (`motion/react`) for shell, page and layout transitions and micro-interactions, under strict performance and reduced-motion rules. | DEC-007 |
| A-6 | 2026-10-22 | §2 Hosting | Railway for all services. Go-live is deferred: until then all collectors and schedules run on the owner's home PC, with gap detection and a nightly `pg_dump` to OneDrive (optionally R2). | DEC-001 |
| A-7 | 2026-10-22 | §4.3 #1 | The owner accepts the Shopify ToS risk. The crawler follows §4.2 strictly and runs from the home PC. If it is blocked after a move to Railway, it turns itself off. | DEC-003 |
| A-8 | 2026-10-22 | §5 settings, §6.18 | Settings default to US and USD. | DEC-004 |
| A-9 | 2026-10-22 | §6 intro | The §11 phases stay the scope. Research-backed enhancements are tracked in vault feature notes as "[Added — pending approval]" and are out of scope until approved. | DEC-008 |
| A-10 | 2026-10-22 | §11 Phase 1, Phase 8 | Phase 1 collection runs on the home PC until go-live, and gaps are accepted, detected and flagged. Railway is prepared so go-live can happen at any time. | DEC-001 |
| A-11 | 2026-10-22 | §0 Working rules, §6 intro, §11 | Continuous build: phases run in order, but phase gates no longer stop the build. At each phase end the summary goes to PROGRESS.md and the vault, and work moves on to the next phase; I review asynchronously and can stop it any time. "[Added — pending approval]" items are in scope when their phase is built unless I veto them. Hard stops remain for paid services, keys and accounts, ToS/compliance, deploys, destructive data operations and the collector host. | DEC-049 |

---

## 0. Instructions to Claude Code

You are the lead engineer building **Pulso**, a web app for dropshipping product research, vendor intelligence, and trend forecasting. This document is the source of truth.

**Before writing any code:**
1. Read this entire document.
2. Copy it to `docs/SPEC.md`. That copy is the living spec, so update it whenever a decision changes.
3. Reply with (a) any gaps, risks, or contradictions you see, and (b) your plan for Phase 0. Then wait for my go-ahead.

**Working rules**
- Build one phase at a time (Section 11). Do not start the next phase until I approve. *(A-11: superseded — continuous build; phase gates no longer stop the build, I review asynchronously.)*
- At the end of every phase, run lint, typecheck and tests; all must pass. Then update `docs/PROGRESS.md` and summarize what was built, what's left, and anything I need to do (API keys, accounts, approvals).
- Record every non-obvious technical choice in `docs/DECISIONS.md` (date, decision, alternatives considered, why).
- Keep `docs/BACKLOG.md` for ideas and deferred work.
- Never put secrets in code. Use `.env` (gitignored) and keep `.env.example` current.
- Ask before adding any paid service or dependency with a monthly cost.
- No fake data in production code paths. Dev seed data lives only in clearly named seed scripts.
- Prefer boring, well-documented tools. Use small, focused modules, typed everywhere.
- I develop on **Windows**. Local dev must work with Docker Desktop (WSL2 backend). Give PowerShell-friendly commands.
- *(A-1)* The repo lives at `C:\dev\pulso`, outside OneDrive. Until Railway go-live, my Windows PC is also the single **collector host**. Only its main checkout runs Celery Beat and live collectors (`PULSO_SCHEDULER=on`). Agent worktrees (Orca) never run Beat or live collectors. A Postgres advisory lock enforces a single scheduler.
- *(A-2)* Every feature and every aspect of the site is tracked as its own note in the Obsidian vault at `C:\Users\Xody2\OneDrive\Desktop\Vaults\Pulso Vault`. Agents read and update it by absolute path. `docs/` keeps the five files listed in §3.

---

## 1. Product overview

**Pulso finds winning dropshipping products early and tells you whether they'll keep winning.**

**Positioning:** Most tools (Sell The Trend, Minea, Dropship.io, Koala Inspector, AutoDS and others) show what's trending *right now*. Pulso's edge is **calibrated forecasting**: a probability that a product is still growing in 14 and 30 days, backed by a public, honest track record of how accurate those forecasts have been. Every number in the app must be traceable to its source data.

**Users**
- **v1:** a single user (me), running my own Shopify stores.
- **Later:** a paid SaaS. Make the data model multi-tenant ready from day one (every user-owned row has `workspace_id`), but don't build billing until Phase 8.
- *(A-3)* **Market (v1):** US only, prices in USD.

**Brand and design**
- Name: **Pulso**, meaning "the pulse of what's selling."
- Visual direction: dark-first and data-dense, with a trading-terminal feel (like TradingView, but for products). Clean and modern, not cluttered. Light mode supported.
- *(A-4)* The overall look is a SaaS product with a dark theme and a green accent: super clean, polished as if designed by a big-tech UI designer, with polished animations, transitions and motion. Data views keep the dense trading-terminal feel above.
- Logo idea: a heartbeat line that ends in an upward trend arrow.
- Colors: one bright pulse accent (for example electric green) for positive momentum, red for decline, amber for warnings.
- Tabular or monospace numerals in tables and stat cards.
- Mobile responsive and installable as a PWA.

---

## 2. Tech stack

| Layer | Choice |
|---|---|
| Monorepo | pnpm workspaces (JS), `uv` (Python) |
| Frontend `apps/web` | Next.js (App Router) + TypeScript + Tailwind + shadcn/ui; TanStack Query; TanStack Table; Recharts **or** Apache ECharts (pick one and record it in DECISIONS.md); typed API client generated from FastAPI's OpenAPI schema. *(A-5)* Motion (`motion/react`) for shell, page and layout transitions and micro-interactions: transform and opacity only, never on virtualized table rows, and `prefers-reduced-motion` honoured |
| API `apps/api` | Python, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2 |
| Workers `apps/workers` | Python collectors and jobs; Celery with Redis broker; Celery Beat for schedules |
| ML `packages/ml` | pandas/polars, scikit-learn, LightGBM, SHAP |
| Database | PostgreSQL with the **pgvector** extension |
| Cache / queue | Redis |
| Object storage | S3-compatible: MinIO locally, Cloudflare R2 in production (raw source payloads and images) |
| Auth | Clerk (free tier) in Next.js; FastAPI verifies Clerk JWTs via JWKS |
| AI | Anthropic Claude API. Model IDs live in env vars (`CLAUDE_MODEL_FAST`, `CLAUDE_MODEL_SMART`): the fast model for bulk work (review summaries, tagging), the smart model for analysis, creative work and Ask Pulso |
| Image matching | OpenCLIP embeddings in pgvector + perceptual hashing (pHash) |
| Hosting *(A-6)* | **Railway** for all services: web, API, Celery worker, Celery Beat, Redis, and Postgres + pgvector (production object storage stays R2, as above). **Go-live is deferred:** until I decide, all collectors and schedules run on my Windows PC (Docker Desktop + WSL2), the single collector host. Gaps while the PC is off are accepted; they are detected and flagged in Data Health and in features. A nightly `pg_dump` goes to a OneDrive folder (optionally also R2). Railway is prepared in full (Dockerfiles, service layout, env, deploy docs) so go-live can happen at any time. Keep everything Dockerized so it stays portable. |
| Quality | Ruff + mypy + pytest (Python); ESLint + tsc + Vitest (web); a few Playwright end-to-end smoke tests; GitHub Actions CI running all of it |

---

## 3. Repo structure

```
pulso/
  apps/
    web/            # Next.js frontend
    api/            # FastAPI
    workers/        # Celery collectors + scheduled jobs
  packages/
    core/           # shared Python: db models, schemas, settings, AI wrapper
    ml/             # feature store, training, backtests, scoring
    sources/        # one adapter per data source
  infra/
    docker-compose.yml
  docs/
    SPEC.md  PROGRESS.md  DECISIONS.md  BACKLOG.md  DATA_SOURCES.md
  CLAUDE.md         # conventions + commands for future Claude Code sessions
  .env.example
```

---

## 4. Data sources and collector framework

### 4.1 Collector framework (build this before any individual source)

Every source is an adapter that implements:
- `fetch(params)` returns raw payloads. Store each raw payload (JSON/HTML) in object storage with timestamp, source and request params.
- `parse(raw)` returns normalized records.
- `upsert(records)` must be **idempotent**: re-running the same job never duplicates data.
- Config: schedule, rate limit, enabled flag (a feature flag per source), retries with exponential backoff.
- Every run writes a `collector_runs` row: source, start/finish time, status, rows fetched/inserted/updated, and error message.

Snapshots are **append-only**. Never overwrite history; a new value is a new snapshot row.

### 4.2 Compliance rules (non-negotiable)
- Prefer official APIs. Document each source's access method, terms and limits in `docs/DATA_SOURCES.md`.
- Respect robots.txt and rate limits, and identify with an honest User-Agent.
- No CAPTCHA solving, no scraping behind logins, no anti-bot evasion, and no rotating proxies to dodge blocks. If a source blocks us, disable the adapter and log it.
- Every source has a **manual CSV import** fallback so I can still load data by hand.
- Before building each adapter, check the source's current official docs and terms (they change) and record what you found in DATA_SOURCES.md.

### 4.3 Sources (priority order)

| # | Source | What we get | Access | Phase |
|---|---|---|---|---|
| 1 | Competitor Shopify stores | catalog, prices, variants, images, new product launches | many stores expose a public `/products.json`; poll politely. *(A-7)* I accept the Shopify ToS risk to my own merchant accounts. §4.2 applies strictly: honest User-Agent, rate-limited, turns itself off when blocked, CSV/URL-paste fallback. It runs from the home-PC collector host (residential IP). If it moves to Railway later and is blocked, it turns itself off and is not re-routed. | 1 |
| 2 | CJ Dropshipping | supplier products, cost, inventory, shipping cost/time by country | official developer API | 1 |
| 3 | Google Trends | search interest over time, by country, related queries | official Google Trends API if I have access; otherwise an unofficial client with heavy caching | 1 |
| 4 | AliExpress | products, price, order counts, ratings, store info, shipping | AliExpress Open Platform (affiliate/dropshipping APIs; app approval needed) | 3 |
| 5 | Amazon | best-seller / movers rank, price, reviews | official API where available (verify current terms); otherwise manual import | 3 |
| 6 | Meta Ad Library | ads, start dates, active status, creatives | official API covers EU-delivered ads; non-EU via manual import | 8 |
| 7 | TikTok Creative Center | top products, top ads | no general public API; manual import first, review terms before automating | 8 |
| 8 | Keepa (optional, paid) | Amazon price/rank history | paid API; ask me before enabling | later |

### 4.4 Product matching (entity resolution)
The same physical product shows up under different names across suppliers and stores. Build a matching pipeline:
- Compute a pHash and a CLIP embedding for each listing's main images; normalize and embed titles.
- Find candidate matches with pgvector nearest-neighbour search, then confirm with a combined score (image similarity, title similarity, price sanity check).
- Group listings into one canonical `product` with a match confidence. Anything below the threshold goes to a "possible match" review queue.
- Provide an admin UI to merge and split products manually. Manual decisions always override the algorithm.

---

## 5. Data model (starting point; refine in Phase 0 and record changes)

**Core**
- `workspaces`, `users`, `workspace_members`
- `sources` (name, type, enabled, config)
- `collector_runs`
- `raw_payloads` (pointer to object storage + metadata)

**Catalog**
- `products`: canonical product (name, category, tags, first_seen_at, main_image, status)
- `listings`: one per product per place it appears (source, external_id, url, title, price, currency, supplier/store reference, product_id, match_confidence)
- `listing_snapshots`: listing_id, captured_at, price, orders_total, rating, review_count, rank, stock
- `images`: listing_id, url, storage_key, phash, embedding (vector)
- `categories`

**Vendors**
- `suppliers`: name, platform, url, rating, years_active, country, reliability_score
- `supplier_offers`: supplier_id, product_id, unit_cost, moq, bulk_tiers (jsonb), warehouse_country
- `shipping_options`: offer_id, destination_country, cost, min_days, max_days, method
- `stores`: competitor stores (domain, platform, first_seen, theme, detected_apps, tracked). Store products use `listings` + `listing_snapshots`.

**Signals**
- `search_trends`: keyword, country, date, interest
- `product_keywords`: product_id, keyword, relevance
- `ads`: platform, external_id, advertiser, product_id, first_seen, last_seen, active, creative_url, text, landing_url
- `ad_snapshots`
- `reviews`: listing_id, rating, text, date, source
- `review_insights`: product_id, complaints (jsonb), praise (jsonb), quality_risk, generated_at, model

**Analytics**
- `product_daily_features`: point-in-time feature store (product_id, date, every computed feature)
- `scores`: product_id, date, trend_score, saturation_score, opportunity_score, risk_score, refund_risk, lifecycle_stage, explanation (jsonb), model_version
- `forecasts`: product_id, made_at, horizon_days, probability, model_version, features_hash. **Immutable: never updated or deleted.**
- `forecast_outcomes`: forecast_id, resolved_at, outcome, metric_values
- `model_versions`: version, trained_at, params, metrics (jsonb), status (candidate / active / retired)
- `backtests`

**Workspace (user-owned)**
- `watchlists`, `watchlist_items`, `boards`, `notes`, `tags`
- `saved_screens`
- `alert_rules`, `alerts`
- `tests`: testing board (product_id, status, start/end, ad_spend, revenue, orders, cpa, roas, notes, kill_reason)
- `sample_orders`
- `shopify_connections`, `shopify_orders`, `ad_spend_entries`
- `ai_generations`: type, input, output, model, tokens, cost
- `settings`: default country, currency, fee assumptions, target margin, AI budget. *(A-8)* Defaults: country `US`, currency `USD`.

---

## 6. Feature specification

Priority tags: **[v1]** = Phases 1–4 · **[v2]** = Phases 5–7 · **[v3]** = Phase 8+

*(A-9)* **Scope:** the phases in §11 stand. Research-backed enhancements are tracked in the vault feature notes, marked "[Added — pending approval]" with a target phase. They are out of scope until I approve them, and I can veto any of them.

### 6.1 Daily Pulse (home dashboard)
- [v1] Top emerging products today, biggest movers (up and down), new products detected in tracked stores, triggered alerts.
- [v1] Watchlist summary with sparklines.
- [v2] "Model picks": top forecast probabilities for the day.
- [v2] Daily Pulse digest by email and Discord.

### 6.2 Discover (trending feed)
- [v1] Feed of trending products across all sources: image, name, price range, velocity, trend score, saturation, lifecycle stage, best margin.
- [v1] Filter by category, country, price and source; sort by any metric.
- [v1] Quick actions: add to watchlist, add to board, start a test.

### 6.3 Product Screener
- [v1] Stock-screener-style filtering on every metric: margin %, velocity, acceleration, saturation, shipping days to a country, supplier rating, lifecycle stage, risk score, price, and forecast probability [v2].
- [v1] Save screens. [v2] Alert when a new product matches a saved screen.

### 6.4 Product Page (the core page)

**Overview tab**
- [v1] Key stats: price range, best supplier cost, estimated margin, velocity, trend score, saturation, lifecycle stage, first seen.
- [v2] Forecast card: probability still growing at 14 and 30 days, top reasons (from SHAP), link to the Track Record page.
- [v1] Notes, tags, watchlist toggle.

**Trends tab**
- [v1] Time-series charts: order velocity, search interest, price, ad count, store count. Overlay toggles; 7 / 30 / 90 day and all-time ranges.
- [v1] Search keywords people use to find it.
- [v2] Seasonality: whether it spikes at the same time each year.
- [v2] Country breakdown: where demand is growing.

**Vendors → Suppliers tab**
- [v1] Table of every matched supplier: platform, unit cost, shipping cost and days to the selected country, rating, orders, years active, MOQ and bulk tiers, warehouse location, link.
- [v1] "Best margin" and "Fastest shipping" picks highlighted. Selecting a supplier updates the profit calculator.
- [v2] Supplier reliability score (ratings, complaint rate, stock-outs, price stability over time).
- [v2] AI-drafted supplier outreach message (samples, bulk pricing, custom packaging).
- [v2] Sample order tracker.

**Vendors → Sellers tab**
- [v1] Every store selling it: store, price, date started, still listed, still running ads.
- [v1] Price spread (min / average / max retail) and a suggested price band.
- [v2] Price-war alert when sellers start undercutting each other.

**Ads tab**
- [v3] Ads for this product: platform, start date, days running, active status, creative preview, landing page. (Manual ad imports can populate this earlier.)
- [v3] AI summary of the winning hooks, angles and formats.

**Reviews tab**
- [v2] Review intelligence: top complaints, top praise, quality risk score, and complaint-based ad angles ("unlike cheap versions, ours doesn't…").

**Profit tab**
- [v1] Calculator: supplier cost, shipping, payment and Shopify fees, estimated CPA (user input with defaults) → gross margin, net profit per order, break-even ROAS, break-even CPA. Scenario sliders.
- [v2] Pricing strategy: suggested price points, bundle and quantity-break pricing, compare-at price.

**Risk tab**
- [v1] Saturation score.
- [v2] Refund risk (complaints, fragility, sizing issues, shipping time).
- [v2] Ad policy and legal flags: trademarks and brand names, knockoffs, restricted categories on Meta/TikTok, shipping restrictions (batteries, liquids, magnets).

**Related tab**
- [v2] Similar products and upsell / bundle candidates.

### 6.5 Product Compare
- [v3] Compare 2–4 products side by side across all key metrics.

### 6.6 Store Spy
- [v1] Track competitor Shopify stores by domain.
- [v1] Store page: product launch timeline, price changes, catalog size over time.
- [v1] Alert when a tracked store launches a new product.
- [v2] Detected theme and apps; estimated best sellers (clearly labeled as estimates, with the method shown).
- [v2] Landing page analyzer: AI critique of a competitor's product page (offer, pricing, bundles, trust elements, upsells).

### 6.7 Ad Intelligence
- [v3] Searchable ad library across sources; filter by platform, country, days running, active status.
- [v3] "Long runners": ads running 30+ days (a strong profitability signal).

### 6.8 Niche Explorer
- [v3] Category heatmap: rising and falling categories, average margin, saturation.

### 6.9 Seasonality Calendar
- [v3] Upcoming holidays and events, the products that historically spike before them, and when to start testing.

### 6.10 Watchlists, Boards and Alerts
- [v1] Watchlists with sparklines.
- [v1] Boards (collections of product ideas).
- [v1] Alert rules: velocity spike %, price drop, new competitor seller, supplier price change, saturation crossing a threshold; [v2] forecast probability crossing a threshold.
- [v1] In-app notifications. [v2] Email and Discord webhook.

### 6.11 Testing Board
- [v1] Kanban: Idea → Researching → Testing → Winner / Killed.
- [v1] Per test: dates, ad spend, revenue, orders, CPA, ROAS, notes, kill reason.
- [v2] Launch checklist per product (supplier sample, product page, creatives, pricing, ads).
- [v2] Test results feed back into the model as extra labeled outcomes.

### 6.12 Creative Studio (AI)
- [v2] Product titles and descriptions, ad scripts and hooks, UGC video briefs, email copy, product page sections.
- [v2] Uses review insights and ad insights as context. Every generation is saved.

### 6.13 Ask Pulso (AI analyst)
- [v2] Chat that answers questions about Pulso's own data, for example "pet products rising in the UK with over 50% margin and fewer than 10 competing stores."
- Implementation: Claude calls safe, parameterized query endpoints as tools (preferred), or uses a read-only DB role with strict row and time limits if text-to-SQL is used. Every answer shows the filters and data it used.

### 6.14 Shopify Integration
- [v2] Connect my store using the Shopify Admin GraphQL API, following Shopify's current recommended app setup.
- [v2] One-click push: product with AI title, description, images, variants, price and compare-at price.
- [v2] Order sync for the profit dashboard.

### 6.15 Profit Dashboard
- [v2] Real P&L per product and per store: revenue, cost of goods, shipping, fees, ad spend, net profit, ROAS.
- [v2] Ad spend by manual entry or CSV first. [v3] Meta and TikTok ad account APIs.

### 6.16 Track Record (public page)
- [v2] Forecast accuracy over time: hit rate, Brier score, calibration chart, precision@20 by week, broken down by model version and category.
- Built **only** from the immutable `forecasts` log, never from backfilled predictions.

### 6.17 Data Health (admin)
- [v1] For every source: last run, status, rows, error rate, data freshness; manual re-run; enable/disable toggle.
- [v1] Matching queue to confirm, merge or split possible product matches.

### 6.18 Global
- [v1] Ctrl+K command palette and global search (products, stores, suppliers).
- [v1] Settings: default country, currency, fee assumptions, target margin. *(A-8)* Defaults: US, USD.
- [v1] CSV export on every table.
- [v1] Responsive layout and PWA install.
- [v3] Browser extension that overlays Pulso data on AliExpress listings and Shopify stores.
- [v3] Billing (Stripe), plans, team seats, public API.

---

## 7. Score definitions

All scores run 0–100, are versioned, and store an `explanation` JSON with each component's contribution. Keep the definitions in code (with docstrings) and in `docs/SPEC.md`.

- **Velocity:** change in orders (or the best available demand proxy) over the trailing 7 days. **Acceleration:** change in velocity.
- **Trend Score v0** (heuristic, Phase 4): weighted, winsorized z-scores of velocity growth, acceleration, search-interest slope and ad-count growth, minus a saturation penalty. Weights live in config.
- **Saturation Score:** number of stores selling it + active ads + growth in sellers, normalized by category.
- **Lifecycle Stage:** emerging / rising / peaking / declining / dead, from documented velocity and acceleration thresholds.
- **Opportunity Score:** combines forecast probability (or Trend Score before forecasts exist), margin, saturation and risk.
- **Risk Score / Refund Risk:** from review insights, policy flags and shipping time.
- **Supplier Reliability:** ratings, complaint rate, stock-outs, price stability.

---

## 8. Forecasting system (the edge; treat it with rigor)

**Goal:** P(product is still growing at t+14 and t+30 days).

- **Label definition** (configurable and versioned): for example, 7-day velocity at t+h ≥ (1 + x%) × 7-day velocity at t, with a minimum-volume floor. Document the exact definition in SPEC.md.
- **Point-in-time correctness:** features for date t may only use data captured at or before t. Build the feature store (`product_daily_features`) plus a **leakage test** that fails CI if any feature touches future data.
- **Baselines:** a naive momentum baseline and Trend Score v0. A model is promoted only if it beats both on the holdout.
- **Validation:** walk-forward by week. A **sealed holdout** (the most recent N weeks) is never used during development and is evaluated only for promotion decisions.
- **Models:** start with logistic regression, then LightGBM. Calibrate with isotonic or Platt scaling. Use SHAP for per-product explanations.
- **Metrics:** Brier score, log loss, AUC, calibration table by decile, precision@20 per week, hit rate by category.
- **Guardrails:** minimum sample sizes per segment before a forecast is shown; no promotion if calibration gets worse; every run logged in `model_versions` and `backtests`.
- **Cold start:** until roughly 6–8 weeks of history exist, show Trend Score v0 labeled "Beta" and no probabilities.
- **Live prediction log:** every forecast shown in the app is written to `forecasts` when it is made and resolved later in `forecast_outcomes`. This feeds the Track Record page.
- **Feedback loop:** my testing-board results are stored as separate labeled outcomes alongside the market label.

---

## 9. AI layer

- One `ai` module: prompt templates in versioned files, Pydantic-validated structured outputs, retries, caching by input hash, cost tracking per call (`ai_generations`), and a monthly budget limit setting.
- Bulk review summarization runs as background jobs with the fast model.
- AI output is never presented as data. Label AI-generated content in the UI.

---

## 10. Pages / routes

`/` Daily Pulse · `/discover` · `/screener` · `/products/[id]` · `/compare` · `/stores` · `/stores/[id]` · `/ads` · `/niches` · `/calendar` · `/watchlists` · `/boards` · `/alerts` · `/testing` · `/studio` · `/ask` · `/profit` · `/track-record` · `/admin/data-health` · `/admin/matching` · `/settings`

---

## 11. Build phases

Every phase ends with passing lint/typecheck/tests, an updated PROGRESS.md, a summary to me, and a **stop for my approval**. *(A-11: no stop — after the summary, the build continues into the next phase.)*

**Phase 0: Foundation**
Monorepo; docker-compose (Postgres + pgvector, Redis, MinIO); FastAPI skeleton with a health check; Next.js skeleton with Clerk auth and the app shell (sidebar, dark theme, Ctrl+K stub); SQLAlchemy models and the first Alembic migration; settings management; CI; CLAUDE.md; docs folder.
*Done when:* `docker compose up` plus the dev servers start, I can log in and see an empty dashboard, and CI is green.

**Phase 1: Data engine**
Collector framework, raw payload storage, append-only snapshots, Celery Beat schedules, CSV import, adapters for competitor Shopify stores, CJ Dropshipping and Google Trends, and the Data Health page.
*Done when:* collectors run on schedule, re-runs are idempotent, and Data Health shows real runs and errors. **Start collecting data as early as possible: history is what the forecasts will be trained on.**
*(A-10)* Until Railway go-live, collection runs on my home PC, the single collector host. Gaps while it is off are accepted, detected (missed-run detection) and flagged in Data Health and in features. A nightly `pg_dump` goes to a OneDrive folder (optionally R2). Railway is prepared (Dockerfiles, service layout, env, deploy docs) so go-live can happen whenever I choose.

**Phase 2: Core product experience**
Product matching v1 (pHash + CLIP + title), matching queue UI, Discover feed, Product page (Overview, Trends, Suppliers, Sellers, Profit), global search, settings.
*Done when:* I can find a product, see its suppliers and sellers, and calculate margin from real data.

**Phase 3: Signals expansion**
AliExpress and Amazon adapters, search keywords, Store Spy pages, new-launch detection.

**Phase 4: Scores and workflow**
Trend Score v0, saturation, lifecycle stage, opportunity score, Screener with saved screens, watchlists, boards, in-app alerts, Testing Board, Daily Pulse dashboard, CSV export.
*Done when:* the dashboard surfaces real candidates every day and I can run my whole product-testing workflow inside Pulso.

**Phase 5: AI layer**
AI module, review intelligence, risk and policy flags, Creative Studio, supplier outreach drafts, Ask Pulso, landing page analyzer.

**Phase 6: Forecasting v1** (start once there are at least 6–8 weeks of snapshots; the feature store and leakage test can be built earlier)
Labels, feature store, baselines, walk-forward backtests, calibrated model, SHAP explanations, forecast cards, immutable forecast log, Track Record page.

**Phase 7: Store operations**
Shopify connection, one-click product push, order sync, ad spend entry, Profit Dashboard, test results feeding the model, email/Discord alerts and the daily digest.

**Phase 8: Expansion and launch prep**
Meta Ad Library and TikTok sources with the Ads pages, Product Compare, Niche Explorer, Seasonality Calendar, production deployment, monitoring and backups. *(A-10)* The Railway deployment is prepared from Phase 1 and may go live earlier, whenever I choose. Then, if I decide to sell it: billing, plans, browser extension, marketing site.

---

## 12. Engineering standards

- Tests for every adapter's `parse()` (using saved fixture payloads), all score calculations, profit math, matching thresholds, the leakage test, and API endpoints.
- Schema changes only through Alembic migrations; never edit the database by hand.
- Structured JSON logging with request and job IDs.
- Money stored as integer minor units plus a currency code. All timestamps in UTC.
- Pagination and indexes on every list endpoint; snapshot tables indexed on (entity_id, captured_at).
- Feature flags for sources and unfinished features.
- Accessibility: fully keyboard navigable, sufficient contrast.
- Keep CLAUDE.md updated with the key commands (dev, test, lint, migrate, run one collector) and project conventions.

---

## 13. Start now

Read everything, save it to `docs/SPEC.md`, then reply with gaps and risks plus your Phase 0 plan. Wait for my approval before writing code.
