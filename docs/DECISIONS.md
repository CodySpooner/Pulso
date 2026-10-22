# Pulso — Decisions

Every non-obvious technical or product choice, per SPEC §0: date, decision, alternatives considered, why, status.

**Statuses**
- **approved by owner 2026-10-22**: binding. Where it changes the spec, it is applied to `docs/SPEC.md` (see the Amendment log there).
- **proposed — pending Phase 0 approval**: a working default from the verified spec review (vault `Research/Spec Review 2026-10-22.md`, review defaults #0–38). Agents follow it unless it contradicts an explicit SPEC requirement or an approved decision. The owner can veto any of these when approving the Phase 0 plan.
- **pending owner**: an open question. The interim default is stated and used until the owner answers.
- **superseded**: replaced by a later entry, kept for history.

**Status clarification (DEC-049 / SPEC A-11):** the historical "pending Phase 0 approval" label above does not block the build. Proposed defaults are binding working defaults until vetoed; phase summaries receive asynchronous owner review. Explicit owner gates (including seeds, accounts/keys, paid services, ToS/compliance, deployments and collector-host operations) remain.

Source abbreviations: *Review* = Spec Review 2026-10-22 (B/H/M items, "default #n" = `review_synthesis.json` defaults). *SI* = Store Intelligence, *SF* = Supplier & Fulfillment Data Sources, *TA* = Trend & Ad Intelligence Sources, *VoC* = Voice of the Customer, *Syn* = 00 Research Synthesis (all in the vault's `Research/` folder).

New entries go at the bottom with the next number. Never renumber or delete; mark an entry superseded and point to its replacement.

## Index

| ID | Decision | Status |
|---|---|---|
| DEC-001 | Railway hosts everything; collection runs on the home PC until go-live | approved by owner 2026-10-22 |
| DEC-002 | One collector host, one scheduler (env flag + Postgres advisory lock) | approved by owner 2026-10-22 |
| DEC-003 | Shopify crawler: ToS risk accepted, strict §4.2 | approved by owner 2026-10-22 |
| DEC-004 | Markets: US only, USD | approved by owner 2026-10-22 |
| DEC-005 | Repo at C:\dev\pulso; vault stays in OneDrive | approved by owner 2026-10-22 |
| DEC-006 | Notes home: Obsidian vault, one note per feature and aspect | approved by owner 2026-10-22 |
| DEC-007 | UI: dark SaaS look with green, Motion library with strict rules | approved by owner 2026-10-22 |
| DEC-008 | Scope: spec phases, plus enhancements marked "pending approval" | approved by owner 2026-10-22 |
| DEC-009 | CJ account must transact every 30 days | pending owner |
| DEC-010 | Vendor-scraped demand data policy | pending owner |
| DEC-011 | Starter seed lists | pending owner |
| DEC-012 | Local dev runtime: infrastructure in compose, apps native | proposed — pending Phase 0 approval |
| DEC-013 | Collector host runtime, gap detection and update procedure | proposed — pending Phase 0 approval |
| DEC-014 | Railway service layout and configuration (for go-live) | proposed — pending Phase 0 approval |
| DEC-015 | Backups and restore drill | proposed — pending Phase 0 approval |
| DEC-016 | Celery and Beat settings | proposed — pending Phase 0 approval |
| DEC-017 | Python 3.14 and image composition | proposed — pending Phase 0 approval |
| DEC-018 | Repo hygiene before the first commit | proposed — pending Phase 0 approval |
| DEC-019 | Typed API client pipeline | proposed — pending Phase 0 approval |
| DEC-020 | Auth: Clerk JWT dependency and admin allowlist | proposed — pending Phase 0 approval |
| DEC-021 | AGENTS.md is canonical; CLAUDE.md imports it | proposed — pending Phase 0 approval |
| DEC-022 | Orca multi-agent working rules | proposed — pending Phase 0 approval |
| DEC-023 | Commit identity | proposed — pending Phase 0 approval |
| DEC-024 | Design system: two density zones and tokens | proposed — pending Phase 0 approval |
| DEC-025 | Motion rules (details under DEC-007) | proposed — pending Phase 0 approval |
| DEC-026 | Charts: Apache ECharts plus SVG sparklines | proposed — pending Phase 0 approval |
| DEC-027 | PWA: manifest only, no service worker | proposed — pending Phase 0 approval |
| DEC-028 | Scope of the first migration | proposed — pending Phase 0 approval |
| DEC-029 | Schema refinements to §5 | proposed — pending Phase 0 approval |
| DEC-030 | Money and AI-cost storage | proposed — pending Phase 0 approval |
| DEC-031 | A day is the UTC calendar date | proposed — pending Phase 0 approval |
| DEC-032 | Collector framework: block rule, CSV runs, schedules | proposed — pending Phase 0 approval |
| DEC-033 | Shopify adapter specifics | proposed — pending Phase 0 approval |
| DEC-034 | Google Trends access | proposed — pending Phase 0 approval |
| DEC-035 | CJ adapter error handling | proposed — pending Phase 0 approval |
| DEC-036 | FX: Frankfurter daily job | proposed — pending Phase 0 approval |
| DEC-037 | AliExpress: live lookup only | proposed — pending Phase 0 approval |
| DEC-038 | Vendor and candidate sources listed as disabled | proposed — pending Phase 0 approval |
| DEC-039 | Demand signal families and the label-source choice | proposed — pending Phase 0 approval |
| DEC-040 | Scores with missing inputs; append-only scores | proposed — pending Phase 0 approval |
| DEC-041 | Margin and Opportunity computed per workspace at query time | proposed — pending Phase 0 approval |
| DEC-042 | Matching persistence | proposed — pending Phase 0 approval |
| DEC-043 | Categories: Google Product Taxonomy | proposed — pending Phase 0 approval |
| DEC-044 | Forecasting rigor and cold-start gate | proposed — pending Phase 0 approval |
| DEC-045 | Track Record: public aggregates only | proposed — pending Phase 0 approval |
| DEC-046 | Alerts fire once per crossing | proposed — pending Phase 0 approval |
| DEC-047 | AI budgets and AI-derived facts | proposed — pending Phase 0 approval |
| DEC-048 | Unplaced §6 items and phase-end listing | proposed — pending Phase 0 approval |
| DEC-049 | Continuous build: phase gates don't stop the build; hourly lead automation in Orca | approved by owner 2026-10-22 |
| DEC-053 | Web foundation: pinned stack, Cache Components off, worktree-aware dev script | proposed (P0-WEB) |
| DEC-054 | Web auth gate: proxy + layout check, shared allowlist, dev-only E2E bypass | proposed (P0-WEB) |
| DEC-055 | App shell defaults: visible unbuilt routes, cookie-remembered rail, palette and motion details | proposed (P0-WEB) |
| DEC-056 | Phase 0 spine pins, build-script allowlist and environment names | proposed (P0-13) |
| DEC-057 | Backend cross-review safety defaults | proposed (P0-14) |
| DEC-058 | Typed client wiring, root dev scripts and the e2e job | proposed (P0-07) |

Superseded review defaults, not given entries: default #0 (move the repo) is done, see DEC-005. Default #2 (no local collection at all) is replaced by DEC-002. Default #15 (CSS-only motion) is replaced by DEC-007, and its remaining rules are in DEC-025. Review question D1 (Railway Pro from Phase 1) is answered by DEC-001, D2 by DEC-003, D3 by DEC-004, D5 by DEC-008 and D8 by DEC-006.

---

## Owner decisions (approved 2026-10-22)

### DEC-001 · Railway hosts everything; collection runs on the home PC until go-live
**2026-10-22 · approved by owner 2026-10-22** · Review H1, D1
- **Decision:**
  - Railway is the host for every service: web, api, Celery worker, Celery Beat, Redis, and Postgres with pgvector. Production object storage stays Cloudflare R2, as §2 already says.
  - Go-live is deferred, and the owner can call it at any time. Until then, all collectors and schedules run on the owner's Windows PC (Docker Desktop + WSL2), the single **collector host** (DEC-002).
  - Railway is prepared fully in the meantime: Dockerfiles, service layout, env inventory and deploy docs, so go-live is a deploy and not a port (DEC-014).
  - Gap mitigations:
    - power-plan guidance (never sleep while plugged in);
    - missed-run detection with gap flags in Data Health and in features (DEC-013);
    - a nightly `pg_dump` to a OneDrive folder as a free off-machine copy, optionally also to R2 (DEC-015).
- **Alternatives:** Railway Pro from the end of Phase 1 at about $50–70/mo, the review's recommendation. Railway Hobby first. The original §2 mix (Vercel, Railway or Fly, Neon or Supabase).
- **Why:**
  - The owner prefers no hosting bill before the product proves itself, and accepts gaps in history when the PC is off.
  - One vendor for all services keeps go-live simple.
- **Consequences:**
  - Gaps can't be backfilled. They reduce usable history for velocity (§7), labels and the §8 cold-start gate (DEC-044).
  - The Phase 1 done-when ("collectors run on schedule") and the daily-series coverage metric are judged on the collector host.

### DEC-002 · One collector host, one scheduler
**2026-10-22 · approved by owner 2026-10-22** · Review M18, default #2 (replaced)
- **Decision:**
  - The owner's main checkout `C:\dev\pulso` is the only place where `PULSO_SCHEDULER=on` and `COLLECTORS_LIVE=on`.
  - Orca and agent worktrees never run Celery Beat or live collectors. Both flags default to `off` everywhere else.
  - Beat takes a Postgres advisory lock (`pg_try_advisory_lock` on a fixed key) when it starts, and exits if the lock is already held.
- **Alternatives:** RedBeat or a Redis lock; convention only.
- **Why:** A second scheduler double-spends CJ's 50k points/day and the Shopify request budget (Syn §5.3), and splits history across databases.
- **Implementation notes (proposed details):**
  - Advisory locks are scoped to one database, so the lock only stops a second scheduler against the same database. Worktrees use their own databases, so they are covered by two other checks:
    - the env default (`off`);
    - a startup check that refuses `PULSO_SCHEDULER=on` inside a linked git worktree (`git rev-parse --git-dir` differs from `--git-common-dir`).
  - At Railway cutover, set `PULSO_SCHEDULER=off` on the PC **before** Railway Beat starts.

### DEC-003 · Shopify competitor-store crawler: ToS risk accepted, strict §4.2
**2026-10-22 · approved by owner 2026-10-22** · Review H2, D2
- **Decision:**
  - **Risk acceptance:** the owner accepts the risk under Shopify Terms of Service §1 item 9 to his own merchant accounts. This entry is the written risk acceptance the review asked for.
  - **Compliance:** the crawler follows §4.2 strictly:
    - an honest User-Agent with a contact URL, and robots.txt respected;
    - rate-limited (DEC-033), honouring `retry-after`;
    - never switches IP, never uses proxies, never evades bot detection;
    - turns itself off when blocked, with a Data Health alert;
    - CSV and URL-paste fallback.
  - **Where it runs:** from the collector host (home PC, residential IP).
  - **If blocked on Railway:** if the crawler moves to Railway after go-live and is blocked, it turns itself off. It is not re-routed to another network to get around the block. Whether it stays on the home PC after go-live is decided at go-live (open question in PROGRESS.md).
  - **Gate:** the source's enabled flag turns on only after two things:
    - the adapter's `parse()` passes fixture tests (§12);
    - the spike results are logged in `docs/DATA_SOURCES.md`. The spike is `/products.json?limit=1` once against about 10 target stores, about 20 requests in total, from the home PC, plus optionally from a throwaway Railway service to measure the go-live risk.
- **Alternatives:** keep the crawler off until a legal review, with Store Spy on CSV only. Accept the risk and add a home-PC fallback worker when Railway is blocked (review option 2, which bends §4.2).
- **Why:**
  - Store Spy, the Sellers tab, Saturation, launch alerts and the best free demand proxy all depend on this source.
  - Since 2026-09-29, cloud IPs get a 429 on the first `/products.json` request (SI §0.1, §2). A residential IP should fare better, but one forum thread also reports residential 429s, so the spike measures it rather than assuming.
  - Shopify API Terms §2.3.24 (no ML training on merchant-store data) must be reviewed before the Phase 7 Shopify app exists.

### DEC-004 · Markets: US only, USD
**2026-10-22 · approved by owner 2026-10-22** · Review M6, D3
- **Decision:**
  - The v1 destination market is the United States, and money displays in USD.
  - Settings defaults are `default_country = US` and `currency = USD`.
  - CJ freight quotes and the Google Trends geo use US only.
  - The Meta Ad Library stays in Phase 8: its API returns commercial ads only for EU/UK reach.
- **Alternatives:** US + EU + UK displayed in USD, which would move a Meta EU/UK collector to Phase 3. Another list of markets.
- **Why:**
  - The owner sells to the US.
  - Snapshot history for unused markets costs points and storage and can't be repurposed.
  - The US has had no de minimis since 2025-08-29 (made indefinite on 2026-06-24), so landed cost must show duty explicitly (SF §16).

### DEC-005 · Repo location
**2026-10-22 · approved by owner 2026-10-22** · Review H4, default #0
- **Decision:**
  - The repo lives at `C:\dev\pulso`, outside OneDrive.
  - The Obsidian vault stays at `C:\Users\Xody2\OneDrive\Desktop\Vaults\Pulso Vault`.
  - The Orca worktree root must also be outside OneDrive (DEC-022).
- **Alternatives:** stay in OneDrive; a Windows Dev Drive.
- **Why:** OneDrive ignores `.gitignore`. Syncing `node_modules`, `.venv`, `.next` and `.git` causes EPERM/EBUSY errors and risks corrupting `.git`. The repo had no commits yet, so moving it cost nothing.

### DEC-006 · Notes home: the Obsidian vault
**2026-10-22 · approved by owner 2026-10-22** · Review M19, D8
- **Decision:**
  - Every feature and every aspect of the site is tracked as its own note in the vault, under `Features/`, `Data/`, `Intelligence/`, `Platform/`, `Design/`, `Phases/`, `Agents/` and `Templates/`.
  - Repo `docs/` keeps only the five files §3 requires: SPEC, PROGRESS, DECISIONS, BACKLOG and DATA_SOURCES.
  - Agents in Orca worktrees read and update the vault by absolute path.
- **Alternatives:** `docs/features/` inside the repo, opened as a vault (the review's default); the vault mirrored from the repo by the lead agent at each phase gate.
- **Why:** The owner wants every aspect tracked in his existing vault.
- **Cost and mitigation:** vault edits aren't versioned or reviewed through PRs, and OneDrive resolves simultaneous writes by creating conflict copies. The vault note `Agents/Agent Collaboration Protocol` therefore sets two rules:
  - each agent edits only the notes of its claimed task;
  - shared logs are append-only.

### DEC-007 · UI direction and the Motion library
**2026-10-22 · approved by owner 2026-10-22** · Review M21, default #15 (overridden)
- **Decision:**
  - **Look:** a SaaS look with a dark theme and green accent. Super clean and "designed by a big-tech UI designer", with polished animations, transitions and motion, combined with §1's data-dense trading-terminal views.
  - **Library:** the Motion library (`motion`, imported from `motion/react`) for shell, page and layout transitions and for micro-interactions.
  - **Strict rules:**
    - animate `transform` and `opacity` only;
    - no animation on virtualized table rows;
    - honour `prefers-reduced-motion` both in Motion (`MotionConfig reducedMotion="user"`) and with a global CSS rule.
  - **Bundle size (proposed detail):** load Motion features lazily (`LazyMotion` with the `m` component).
- **Alternatives:** CSS-only motion with tw-animate-css (the review's default); Motion everywhere without rules.
- **Why:** Meets the owner's polish bar, while the rules keep dense tables fast, honest and accessible. The remaining rules are in DEC-025.

### DEC-008 · Scope: spec phases plus enhancements pending approval
**2026-10-22 · approved by owner 2026-10-22** · Review M20, D5
- **Decision:**
  - The §11 phases stay the scope.
  - Research-backed enhancements (the review's 13 enhancements plus research gaps) are folded into the relevant vault feature notes. Each is marked **"[Added — pending approval]"** with a target phase and its evidence, so the owner can veto it.
  - Pending items are not built until approved, at the latest at the gate of their target phase.
  - Ideas not folded into a note go to `docs/BACKLOG.md`.
  - "Fully polished" means each phase's end-of-phase UI checklist passes (AGENTS.md).
- **Alternatives:** spec scope only, with all research extras in BACKLOG (the review's default); building toward SaaS parity from v1.
- **Why:** The owner asked for "fully polished features" and "the best dropshipping toolkit in the world". Markers make additions visible and vetoable instead of silently expanding scope.

---

## Pending owner decisions

### DEC-009 · CJ account must transact every 30 days
**2026-10-22 · pending owner** · Review M3, D4
- **Question:** Does the CJ account whose API key Pulso uses place at least one real order every 30 days?
- **Why it matters:**
  - CJ disables API access after 30 consecutive days with zero transaction amount (error `1600014`), and reactivation is manual (SF §2).
  - CJ is the Phase 1 supplier source and the Phase 2 margin source.
- **Interim default:**
  - Build the CJ adapter in Phase 1 against fixtures.
  - Error `1600014` shows in Data Health as "CJ API disabled: 30 days without orders".
  - If the key doesn't come from a transacting account, supplier offers come in through CSV import until this is resolved.
- **Options:** (a) yes, my stores fulfil through CJ; (b) no, but I'll place a small order every month; (c) no, use CSV until CJ grants an exemption.

### DEC-010 · Vendor-scraped demand data policy
**2026-10-22 · pending owner** · Review H3, M5, D6
- **Question:** May Pulso ever buy logged-out vendor-scraped data as the forecast's demand series, for example TikTok Shop sold counts via Apify at about $70–180/mo?
- **Why it matters:**
  - No Phase 1 source reports order counts.
  - TikTok's US Terms of Service §3.4 bans automated extraction.
  - §4.2 forbids our own evasion but says nothing about buying data (TA §2.4, §2.15; Syn §5.5).
- **Interim default:** official sources plus manual CSV only. Revisit at Phase 1 exit with the measured coverage numbers (DEC-039) and a vendor quote.

### DEC-011 · Starter seed lists
**2026-10-22 · pending owner** · Review M6, D7
- **Question:** Approve the drafted starter lists or supply your own.
- **Interim default:**
  - Agents draft about 30 competitor store domains, 10 CJ categories and 50 US keywords in the vault note `Data/Seed Lists`. The owner adds his own store domains and approves.
  - Seeds live in `sources.config`, loaded from a versioned seed file.
  - No live collection against unapproved seeds.
- **Why:** CJ `listV2` costs 50 points per call and returns at most 6,000 results per query (Syn §5.3). History collected against the wrong seeds can't be backfilled.

---

## Proposed defaults (pending Phase 0 approval)

### DEC-012 · Local dev runtime
**2026-10-22 · proposed — pending Phase 0 approval** · default #1, Review B1
- **Decision:**
  - For development and agents, Docker Compose runs **infrastructure only**, on named volumes:
    - `pgvector/pgvector:0.8.7-pg18-trixie`;
    - Redis;
    - a pinned RustFS 1.0.x as the S3 emulator.
  - Web, api and workers run natively through `pnpm` and `uv run`.
  - The local Celery worker uses `--pool=solo`.
  - The collector host differs; see DEC-013.
- **Alternatives:** fully native Windows services; the whole app in containers for development; Celery `--pool=threads`.
- **Why:**
  - pgvector has no Windows build, and Redis has no official one.
  - MinIO is archived (last release 2025-10-15).
  - Celery's prefork pool doesn't run on Windows. Prefork is exercised on Linux in CI and in the collector containers.

### DEC-013 · Collector host runtime, gap detection and update procedure
**2026-10-22 · proposed — pending Phase 0 approval** · implements DEC-001 and DEC-002
- **Decision:**
  - **Separate compose project.** The collector host runs its own compose project (for example `pulso-collector`) with its own volumes and ports. It runs Postgres, Redis, the object-store emulator, and the `worker` and `beat` containers built from the **same Dockerfiles as Railway**, with `restart: unless-stopped`.
  - **Built images, not live code.** Collectors run from built images, so editing source in the main checkout changes nothing until the collector host is updated.
  - **Update procedure.** Done by the owner, or by an agent at the owner's explicit request:
    1. `git pull` on `main`;
    2. take a backup;
    3. `alembic upgrade head` against the collector database;
    4. rebuild and restart the collector containers;
    5. check Data Health.
  - **Isolation from development.** The agent/dev stack (DEC-012) is a different compose project. Agents never run compose, migrations or `down -v` against `pulso-collector`.
  - **Missed-run detection:**
    - Each schedule declares its expected cadence.
    - A check (`audit.schedule`) runs at Beat start and every 15 minutes. It compares expected slots with `collector_runs` and records each missed slot in `collection_gaps` (one row per source and slot; schema in the vault note `Data/Data Model`).
    - Data Health shows a per-source gap calendar.
    - `product_daily_features` carries per-source-family coverage and gap flags for each day.
  - **Catch-up:** when Beat starts, each job whose last successful run is older than its period runs **once**. Older slots aren't replayed, because past storefront and supplier states can't be fetched. Google Trends history can be backfilled separately.
  - **PC guidance** (detail in the vault note `Platform/Collector Host`):
    - power plan sleep = Never while plugged in;
    - Docker Desktop set to "start when you sign in";
    - Windows Update active hours set.
    - Docker Desktop only starts after sign-in, so a reboot to the lock screen means a gap. Auto sign-in is the owner's choice and a security trade-off.
- **Alternatives:** native Celery on Windows with `--pool=solo` for collection; one shared compose project for dev and collection.
- **Why:**
  - Containers give Railway parity, prefork on Linux and automatic restart.
  - A separate project stops an agent's `docker compose down -v` from destroying irreplaceable history.

### DEC-014 · Railway service layout and configuration (for go-live)
**2026-10-22 · proposed — pending Phase 0 approval** · defaults #3, #5; Review M17
- **Decision:**
  - **Services:** web, api, worker, beat (one replica), Redis, Postgres, and one cron service for the nightly `pg_dump`.
  - **Postgres:**
    - image `pgvector/pgvector:0.8.7-pg18-trixie` on a volume;
    - start command `postgres -c dynamic_shared_memory_type=mmap`, which HNSW index builds need;
    - no public TCP proxy;
    - the same tag in compose, CI and Railway.
  - **Configuration in the Railway dashboard, never in `railway.json` or `railway.toml`:**
    - one Dockerfile per image;
    - repo-root build context;
    - `RAILWAY_DOCKERFILE_PATH`;
    - watch paths;
    - Alembic as the api pre-deploy command (never in a Dockerfile);
    - "Wait for CI" on;
    - no PR environments.
  - **Optional snapshot:** a `railway.ts` snapshot through `railway config pull`, only if the owner wants the config versioned.
  - **Plan:** chosen at go-live with a cost estimate for the owner's approval (§0). The review estimated about $50–70/mo on Pro with a $100 hard usage limit, a guess and not measured.
  - **Re-check:** Railway's docs are re-checked at go-live.
- **Alternatives:** Railway's stock Postgres (it lacks pgvector); `railway.ts` as the source of truth; Railway Buckets instead of R2.
- **Why:**
  - Railway's docs (verified 2026-10-22) mark Config as Code deprecated, and existing files stop being read on 2026-12-01.
  - Infrastructure as Code (`.railway/railway.ts`) is GA but more than a single-user v1 needs.
  - R2 has lifecycle rules and 10 GB free, while Railway Buckets have no lifecycle rules.

### DEC-015 · Backups and restore drill
**2026-10-22 · proposed — pending Phase 0 approval** · default #4 (adjusted for DEC-001)
- **Decision:**
  - **From the first live collection on the collector host:**
    - A nightly `pg_dump -Fc` of the collector database, written to a temp file and then moved into a OneDrive folder, so OneDrive never syncs a half-written dump. The folder path is a guess pending owner confirmation, for example `C:\Users\Xody2\OneDrive\Pulso Backups\db\`.
    - Keep the last 14 daily plus 8 Sunday dumps (a guess; watch the OneDrive quota, which is 5 GB on the free plan).
    - Optionally also upload each dump to an R2 `backups/` prefix with a 35-day lifecycle rule.
    - The job is a Windows Task Scheduler task (03:30 local, run as soon as possible after a missed start) running `infra/scripts/backup.py`. `pg_dump` runs inside the Postgres container and `docker compose cp` copies the file out, so PowerShell never touches the binary, and the backup still runs when Beat is down. It is logged in `collector_runs` (source `backup`) so Data Health shows backup health. *(Revised 2026-10-22 in the planning consistency pass to match the vault notes; it was a Beat task.)*
  - **Restore drill:** one drill before Phase 1 exit. Restore the latest dump into a scratch database, compare row counts, and record the result here.
  - **At go-live:** Railway daily and weekly volume backups, plus a nightly `pg_dump` to R2 with 35-day retention.
- **Alternatives:** no backup until Phase 8; WAL-G point-in-time recovery; a Beat task with the OneDrive folder bind-mounted (stops whenever Beat stops).
- **Why:**
  - Snapshot history and the immutable `forecasts` log can't be re-fetched.
  - Railway volume backups restore only into the same project, and wiping a volume deletes them.

### DEC-016 · Celery and Beat settings
**2026-10-22 · proposed — pending Phase 0 approval** · default #6
- **Decision:**
  - Beat runs as one replica with crontab-only schedules (no `timedelta` schedules, whose state is lost on redeploy), plus the advisory lock from DEC-002.
  - The SQLAlchemy engine is created per worker process (`worker_process_init`).
  - ML tasks run on a concurrency-1 queue with lazy `torch` imports.
  - Celery's default (early) acks.
- **Alternatives:** RedBeat; `task_acks_late`.
- **Why:** Idempotent upserts (§4.1) make a rare duplicate harmless. Late acks would create Redis visibility-timeout redelivery problems.

### DEC-017 · Python 3.14 and image composition
**2026-10-22 · proposed — pending Phase 0 approval** · default #7
- **Decision:**
  - Pin Python 3.14: `.python-version` and `requires-python >=3.14,<3.15`.
  - Install `torch` from uv's pytorch-cpu index on Linux.
  - Three images: web, api and worker. The worker image is reused for Beat.
  - The worker image installs `libgomp1` and bakes in the OpenCLIP weights.
  - The api image excludes `torch` and `lightgbm`.
- **Alternatives:** Python 3.12; downloading the weights at runtime.
- **Why:** PyPI checks found 3.14 wheels for every ML dependency. These are standard fixes for image size and startup time.

### DEC-018 · Repo hygiene before the first commit
**2026-10-22 · proposed — pending Phase 0 approval** · default #8
- **Decision:**
  - `.gitattributes` with `* text=auto eol=lf`.
  - pnpm pinned through `packageManager`, with the `sharp` and `esbuild` build scripts allow-listed.
  - Next `outputFileTracingRoot` set to the repo root.
  - Web env in `apps/web/.env.local`.
  - One uv workspace with explicit members.
- **Alternatives:** keep the tool defaults.
- **Why:** System `core.autocrlf=true`, so CRLF would break container entrypoints. pnpm blocks build scripts by default.

### DEC-019 · Typed API client pipeline
**2026-10-22 · proposed — pending Phase 0 approval** · default #9
- **Decision:**
  - `openapi-typescript` + `openapi-fetch` + `openapi-react-query`.
  - The OpenAPI schema is exported without running the server.
  - Operation IDs are stable.
  - Both generated files are committed, with a CI drift check.
- **Alternatives:** `@hey-api/openapi-ts`; Orval.
- **Why:** The smallest generated surface and the fewest merge conflicts between worktrees.

### DEC-020 · Auth: Clerk JWT dependency and admin allowlist
**2026-10-22 · proposed — pending Phase 0 approval** · default #10, Review M11
- **Decision:**
  - **JWT check:** one FastAPI dependency using PyJWT `PyJWKClient`, RS256, checking `iss`, `exp`, `nbf` and `azp`. It creates the user and workspace on first login.
  - **Routing:** the browser calls the API through Next `/api/*` rewrites, so no CORS is needed.
  - **Access gate:** a `PLATFORM_ADMIN_USER_IDS` allowlist gates the whole app in v1, and Clerk sign-ups are restricted.
  - **Clerk instance:** a development instance until a domain exists.
- **Alternatives:** `clerk-backend-api`; Clerk webhooks; a roles column now.
- **Why:** Skipping `azp` opens CSRF. Once deployed, any Clerk sign-up would otherwise see everything. Team seats are v3.

### DEC-021 · AGENTS.md is canonical; CLAUDE.md imports it
**2026-10-22 · proposed — pending Phase 0 approval** · default #11 (files written during planning)
- **Decision:**
  - `AGENTS.md` holds every agent rule and command.
  - `CLAUDE.md` is `@AGENTS.md` plus Claude-only notes.
  - Keep AGENTS.md under 32 KiB, Codex's default read cap.
- **Alternatives:** two files maintained by hand.
- **Why:** Codex reads only AGENTS.md, and two hand-kept copies drift.

### DEC-022 · Orca multi-agent working rules
**2026-10-22 · proposed — pending Phase 0 approval** · default #12, Review M18
- **Decision:**
  - **Pace and gates:** phases stay serial, and tasks within a phase may run in parallel. One task is one branch, one worktree and one PR. The owner approves each phase boundary. (superseded in part by DEC-049)
  - **Worktrees:** the Orca worktree root is outside OneDrive, for example `C:\dev\pulso-worktrees\`.
  - **Environment:** ports, `DATABASE_URL` (database `pulso_<slug>`) and `REDIS_URL` (`/N`) come from env vars. A worktree-create script that writes each worktree's `.env.local` arrives when parallel work starts (BACKLOG).
  - **Migrations and generated files:** one Alembic migration per PR, with CI asserting a single head. Lockfiles and generated clients are regenerated, never hand-merged.
  - **Claiming and protocol:** tasks are claimed in the phase's vault note before work starts. The full protocol is in the vault note `Agents/Agent Collaboration Protocol`.
  - **No GitHub Pro:** Railway's "Wait for CI" guards production.
- **Alternatives:** worktree slot allocation now; GitHub Pro ($4/mo) for branch protection on the private repo.
- **Why:** Ports, a shared database at different migration revisions, multiple Alembic heads and lockfile conflicts are the predictable collisions between two agents.

### DEC-023 · Commit identity
**2026-10-22 · proposed — pending Phase 0 approval** · default #13
- **Decision:** A repo-local git identity of `CodySpooner` with the GitHub noreply email. The repo stays private.
- **Alternatives:** the owner's personal email.
- **Why:** Keeps the personal email out of commit history. The owner confirms (owner to-do).

### DEC-024 · Design system: two density zones and tokens
**2026-10-22 · proposed — pending Phase 0 approval** · default #14 (within DEC-007)
- **Decision:**
  - **Themes:** dark by default. Light mode works but stays unpolished until Phase 8.
  - **Tokens:** separate `--brand`, `--positive` and `--negative` tokens, so brand green and "up" green can differ.
  - **Primary buttons:** neutral (open question for the owner: neutral or brand green).
  - **Two density zones:**
    - chrome areas get SaaS spacing;
    - data views get terminal density: compact rows, tabular numerals, right-aligned numbers, sticky headers.
  - **Deltas:** show a sign plus ▲/▼, never colour alone.
  - **Contrast:** AA, checked in both themes.
  - **Fonts:** Geist Sans and Geist Mono.
  - **Usage:** only tokens in components, never raw colour values.
- **Alternatives:** one style everywhere; green primary buttons.
- **Why:** Reconciles the §1 terminal direction with the owner's SaaS polish wish, and stops two agents drifting into different styles.

### DEC-025 · Motion rules
**2026-10-22 · proposed — pending Phase 0 approval** · default #15 (remaining rules after DEC-007)
- **Decision:**
  - **Timing:** duration tokens of 120, 200 and 280 ms, plus one shared easing set.
  - **Charts:** animate only on first render, never on refetch.
  - **No fake liveness:**
    - no perpetual tickers, pulses or count-ups pretending data is live;
    - a value may transition once when the underlying data actually changes;
    - show "as of" timestamps.
  - **Budget:** under reduced motion, transitions become instant or crossfades. Any frame-rate regression on data views is a bug.
- **Alternatives:** no rules beyond DEC-007.
- **Why:** Data refreshes hourly or daily. Motion must signal change honestly, not imply a live feed.

### DEC-026 · Charts: Apache ECharts plus SVG sparklines
**2026-10-22 · proposed — pending Phase 0 approval** · default #16; §2 requires the choice
- **Decision:**
  - ECharts with modular imports, loaded client-side and themed from the design tokens.
  - Sparklines in tables and watchlists are a small inline SVG polyline.
- **Alternatives:** Recharts; TradingView Lightweight Charts.
- **Why:** Synced multi-pane time series, zoom, heatmaps and calibration charts in one library. Lightweight Charts only does time axes.

### DEC-027 · PWA: manifest only
**2026-10-22 · proposed — pending Phase 0 approval** · default #17
- **Decision:** Next's `app/manifest.ts` plus icons, with no service worker. The manifest lands by Phase 4 at the latest.
- **Alternatives:** Serwist; next-pwa.
- **Why:** No offline need, offline caching risks showing stale data, and next-pwa is unmaintained.

### DEC-028 · Scope of the first migration
**2026-10-22 · proposed — pending Phase 0 approval** · default #18
- **Decision:**
  - The first migration covers Core, Catalog, Vendors, the collector tables, `fx_rates` and `settings` only.
  - Every observation row carries `captured_at`, `observed_for` and a `raw_payload_id` foreign key, unique on `(entity_id, raw_payload_id)`.
  - The migration runs `CREATE EXTENSION IF NOT EXISTS vector`.
- **Alternatives:** model all of §5 now.
- **Why:** Avoids freezing v2/v3 tables before they're designed, makes re-runs idempotent, and makes every number traceable (§1).

### DEC-029 · Schema refinements to §5
**2026-10-22 · proposed — pending Phase 0 approval** · default #19, Review M7, M10
- **Decision:**
  - **Scope line:** tables outside the Workspace group are global market data. Every Workspace table, child rows included, carries `workspace_id NOT NULL`, indexed.
  - **`search_trends`:** append-only per fetch, with `source`, `captured_at`, `raw_payload_id`, `window` and `is_partial`.
  - **Variants:** add `listing_variants` and `variant_snapshots`.
  - **Sales counts:** `listing_snapshots.orders_total` becomes `sold_count`, plus `orders_window` with `window_days`, plus the raw displayed value.
  - **`listings`:**
    - gains `first_seen_at`, `last_seen_at`, `delisted_at` and `source_created_at`;
    - gains `store_id` and `supplier_id` foreign keys with a CHECK;
    - a listing is marked delisted only by a complete crawl (`collector_runs.complete`).
  - **Supplier offers and shipping:**
    - `supplier_offers` becomes a 1:1 extension of a supplier listing (`listing_id` primary and foreign key, `moq`, `bulk_tiers`, `warehouse_country`);
    - cost and stock come from snapshots;
    - `shipping_options` references `listing_id` and is append-only with `captured_at`.
  - **Workspace choices:** replace `stores.tracked` with `workspace_tracked_stores`, and `products.tags` with `product_tags`.
  - **Deferred:** drop `stores.theme` and `stores.detected_apps` until v2.
- **Alternatives:** keep §5 as written.
- **Why:**
  - Prevents history being overwritten and fake mass delistings.
  - Removes a second source of truth for supplier cost.
  - Keeps per-user choices off global tables.

### DEC-030 · Money and AI-cost storage
**2026-10-22 · proposed — pending Phase 0 approval** · default #20, Review M9
- **Decision:**
  - Money is stored as `<name>_minor BIGINT` plus `currency CHAR(3)`, and bulk tiers inherit the offer's currency.
  - AI cost is stored as `cost_usd_micros`.
  - CPA and ROAS are computed, not stored.
  - A currency-exponent table has one test covering JPY, USD and KWD.
- **Alternatives:** numeric columns.
- **Why:** §12 requires integer minor units, and integer cents would round each AI call down to zero.

### DEC-031 · A day is the UTC calendar date
**2026-10-22 · proposed — pending Phase 0 approval** · default #21
- **Decision:**
  - Features for date *d* use only observations with `captured_at < d+1 00:00Z`.
  - Trends requests use `tz=0`.
  - Nightly scoring runs after the collectors.
  - Gap flags (DEC-013) are per UTC day.
- **Alternatives:** the owner's local timezone.
- **Why:** Follows §12 (all UTC) and keeps features point-in-time correct.

### DEC-032 · Collector framework: block rule, CSV runs, schedules
**2026-10-22 · proposed — pending Phase 0 approval** · default #22
- **Decision:**
  - **Block rule:** each adapter defines one. N consecutive 429/430/403 responses, or a source-specific code, means auto-disable plus a Data Health alert.
  - **Adapter behaviour:**
    - honours `retry-after`;
    - never switches IP;
    - stores the last status code;
    - refreshes its token from the expiry in the response.
  - **CSV imports:** a CSV import is a collector run with `trigger=csv`, reusing `parse()` and the idempotent upsert.
  - **Schedules:** live in Beat code and check `sources.enabled`.
- **Alternatives:** an encrypted credentials table; a separate import pipeline.
- **Why:** §4.2 says to disable a blocked adapter, but §4.1 never defines "blocked".

### DEC-033 · Shopify adapter specifics
**2026-10-22 · proposed — pending Phase 0 approval** · default #23 (adjusted for DEC-003)
- **Decision:**
  - **Requests:**
    - honest User-Agent with a contact URL;
    - `limit=250` and `If-None-Match`;
    - at most 30 requests/min in total across all stores.
  - **Daily `.js` fetch:** `/products/<handle>.js` once a day for tracked products, stored in `variant_snapshots`, including the variant barcode (GTIN) when present.
  - **No collection-time velocity:** velocity is never computed at collection time.
  - **Feature names:** prefixed by source (`shopify_*`), so Shopify-derived features can be dropped from training.
  - **Enabled flag:** gated as described in DEC-003.
  - **Deferred:** Web Bot Auth signing and bot registration, until a Railway move shows they're needed (BACKLOG).
- **Alternatives:** Web Bot Auth signing in Phase 1.
- **Why:**
  - Shopify staff say a signature is "necessary but not sufficient" (SI §0.1).
  - The `.js` inventory is the only free per-product unit signal (SI §1, §4.1).

### DEC-034 · Google Trends access
**2026-10-22 · proposed — pending Phase 0 approval** · default #24, Review M2
- **Decision:**
  - No unofficial client.
  - SerpApi's free tier (250 searches/mo) covers a weekly US keyword set.
  - DataForSEO only after the owner approves it (paid).
  - Apply for Google's official Trends API alpha.
- **Alternatives:** pytrends; DataForSEO from day 1.
- **Why:**
  - pytrends was archived on 2025-04-17, and Google's terms ban scraping.
  - Trends history can be backfilled (5 years), so waiting costs nothing.

### DEC-035 · CJ adapter error handling
**2026-10-22 · proposed — pending Phase 0 approval** · default #25, Review M3
- **Decision:**
  - Each of these maps to its own Data Health error:
    - `1600014` (no transactions for 30 days);
    - "one ip limit";
    - points exhausted;
    - rate-limit 429s.
  - Token expiry is read from the auth response.
  - No webhooks and no dedicated-IP proxy.
- **Alternatives:** webhooks; a VPS proxy now.
- **Why:** The IP-limit risk is speculative for one user on a residential IP. Act if the error actually appears.

### DEC-036 · FX: Frankfurter daily job
**2026-10-22 · proposed — pending Phase 0 approval** · default #26
- **Decision:**
  - A daily Frankfurter v2 job fills `fx_rates(date, base, quote, rate, source)` from Phase 1.
  - Amounts convert at the rate for the observation's UTC date.
- **Alternatives:** a paid FX API.
- **Why:**
  - Free, no key, and based on official reference rates.
  - Even US-only, competitor stores can price in other currencies (from `/meta.json`), so conversion is still needed.

### DEC-037 · AliExpress: live lookup only
**2026-10-22 · proposed — pending Phase 0 approval** · default #27, Review M1
- **Decision:**
  - The AliExpress adapter (Phase 3) is live lookup only, cached in Redis for 24h.
  - Nothing goes to `raw_payloads`, snapshots or features until AliExpress approves storage in writing.
- **Alternatives:** store derived metrics flagged as unapproved.
- **Why:** The API agreement bans storage without approval (§7.6, §9.2) and allows termination without notice (SF §1).

### DEC-038 · Vendor and candidate sources listed as disabled
**2026-10-22 · proposed — pending Phase 0 approval** · default #28, Review M5
- **Decision:**
  - Vendor-scraped sources, Pinterest Trends and Merchant Best Sellers are listed in `docs/DATA_SOURCES.md` as disabled candidates, with cost and risk notes. No adapters until approved.
  - §4.3 #7 is to be corrected: TikTok Top Products is likely retired (probed 2026-10-22). This is a proposed spec amendment, not yet applied.
- **Alternatives:** build vendor adapters behind flags now.
- **Why:** Pending DEC-010.

### DEC-039 · Demand signal families and the label-source choice
**2026-10-22 · proposed — pending Phase 0 approval** · default #29, Review H3
- **Decision:**
  - **Candidate families:**
    - `.js` inventory deltas (Grade A, fragile);
    - counts of `updated_at` bumps (Grade B, a lower bound);
    - CJ stock and listing-count deltas (unproven);
    - search-interest slope.
  - **Handling:**
    - each family is its own feature column with its own velocity, never summed;
    - store-count is excluded, because it already feeds Saturation;
    - a product with no qualifying family shows "insufficient signal".
  - **Phase 1 exit metric:** the number of products with a daily count series on at least 12 of 14 days, measured on the collector host. The label source is chosen then.
  - **Risk logged:** Phase 6 is at risk if no family carries signal.
- **Alternatives:** fix a label priority order now.
- **Why:** It's too early to choose before measuring coverage.

### DEC-040 · Scores with missing inputs; append-only scores
**2026-10-22 · proposed — pending Phase 0 approval** · default #30, Review M4, M15
- **Decision:**
  - **Missing inputs:** a missing component gets weight 0 and the rest are renormalized. The explanation records `missing:[…]` and coverage, and the UI says "no source yet", never 0. This applies to ads in v1.
  - **Normalization:** robust per-category z-scores (median/MAD, capped at ±3), falling back to the parent category and then global when n < 30.
  - **Growth:** `log((U7+5)/(U7_prev+5))`, computed over a stable panel of stores tracked since t−28.
  - **Versioning:** `model_version` is a hash of the weights config.
  - **History:** `scores` is append-only per (product, date, model_version), which gives Phase 6 a free live baseline.
- **Alternatives:** a plain z-score; dropping ads from the formula.
- **Why:** Prevents undefined or exploding scores, and fake growth from Pulso's own coverage growth.

### DEC-041 · Margin and Opportunity computed per workspace at query time
**2026-10-22 · proposed — pending Phase 0 approval** · default #31
- **Decision:**
  - Margin, best margin and Opportunity are computed at query time through a SQL view, from the workspace's `default_country` (US) and fee settings.
  - Freight quotes are fetched only for `settings.default_country`.
  - The view is materialized only if it proves slow.
- **Alternatives:** a nightly table per workspace; a global margin.
- **Why:** Thousands of products are trivial for Postgres, and this keeps per-tenant logic correct.

### DEC-042 · Matching persistence
**2026-10-22 · proposed — pending Phase 0 approval** · default #32, Review M8
- **Decision:**
  - Phase 2 adds `match_candidates` (score components and status) and an append-only `match_decisions` log, which the matcher treats as hard constraints.
  - Merges set `products.merged_into_id` and redirect. Products are never deleted.
  - Forecasts keep their original `product_id`.
- **Alternatives:** a full as-of link table with valid_from/valid_to.
- **Why:** Preserves link history cheaply. Phase 6 decides whether features read membership as of *t*.

### DEC-043 · Categories: Google Product Taxonomy
**2026-10-22 · proposed — pending Phase 0 approval** · default #33
- **Decision:** `products.category_id` plus `category_source` (`rule`, `ai` or `manual`), with mapping tables per source.
- **Alternatives:** our own taxonomy.
- **Why:** Free and standard, and it matches Merchant data.

### DEC-044 · Forecasting rigor and cold-start gate
**2026-10-22 · proposed — pending Phase 0 approval** · default #34, Review M12–M16 (adjusted for DEC-001)
- **Decision:**
  - **Gate:** `D ≥ 14 + 7(a−1) + h + 7(f+n−1) + h`, where D counts days of continuous collection on the collector host. Days with gaps in label-relevant sources count according to the label checklist's gap tolerance, set in Phase 6.
  - **Lean design:** about 12 weeks for the 14-day horizon and about 17 for the 30-day.
    - The review estimated that collection starting 2026-11-09 would mean about 2027-02-01 and 2027-03-05.
    - PC downtime pushes these dates out.
  - **Build order:** Phase 6 build work may start at 6–8 weeks. Ship the 14-day horizon first, and logistic regression before LightGBM.
  - **Validation:**
    - training origins are purged so that t_train + h ≤ t_test;
    - the holdout is enforced by the harness, with one promotion run per window logged with the git SHA.
  - **Forecast log:**
    - nightly batch forecasts for the whole eligible universe, with `label_version` and `baseline_value`, not logged on page view;
    - outcomes are hit, miss or unresolvable;
    - a database trigger enforces immutability.
  - **First promotion:** needs the holdout base rate within about 15 points of training, or owner sign-off. The first windows straddle Black Friday (2026-11-27) and Chinese New Year (2027-02-06).
- **Alternatives:** the spec's 6–8 weeks; logging forecasts on page view.
- **Why:** Without these, backtests are inflated and Track Record is biased.

### DEC-045 · Track Record: public aggregates only
**2026-10-22 · proposed — pending Phase 0 approval** · default #35
- **Decision:**
  - `/track-record` shows aggregates only, with sample sizes and unresolvable counts.
  - Per-forecast detail stays behind login.
  - The page is truly public only after go-live (DEC-001).
- **Alternatives:** fully public; fully private.
- **Why:** Publishing individual picks would give away the product's value.

### DEC-046 · Alerts fire once per crossing
**2026-10-22 · proposed — pending Phase 0 approval** · default #36
- **Decision:**
  - A unique `dedupe_key` per threshold crossing.
  - In-app read state is a `read_at` column.
  - Discord webhook URLs are stored encrypted.
  - The email provider is chosen in Phase 7.
- **Alternatives:** fire on every run.
- **Why:** Without dedupe, a threshold alert fires every night.

### DEC-047 · AI budgets and AI-derived facts
**2026-10-22 · proposed — pending Phase 0 approval** · default #37
- **Decision:**
  - **System jobs:** a null `workspace_id` means a system job, with its own `AI_SYSTEM_MONTHLY_BUDGET_USD`.
  - **Over budget:** raises `BudgetExceeded`, which pauses bulk jobs.
  - **Caps:** asked at Phase 5 entry. The defaults are $20 for the workspace and $20 for system jobs, with a hard stop.
  - **AI-derived facts:** may feed deterministic scores only when flagged `ai_derived`, with the prompt version and a UI badge. Free text never does.
- **Alternatives:** charge system jobs to the owner's workspace.
- **Why:** Global review summaries have no workspace to charge, and §9 requires AI content to be labelled.

### DEC-048 · Unplaced §6 items and phase-end listing
**2026-10-22 · proposed — pending Phase 0 approval** · default #38 (with DEC-008)
- **Decision:**
  - A §6 item not named in a §11 phase is built in the last phase of its tag range unless reassigned at a phase review. Notes and tags land in Phase 2, and the PWA manifest in Phase 4.
  - PROGRESS.md lists §6 items done and pending at every phase end, including any approved "[Added — pending approval]" items.
- **Alternatives:** a detailed placement table now.
- **Why:** Stops tagged features from silently never being built, without guessing a full plan.

### DEC-049 · Continuous build with an hourly lead automation
**2026-10-22 · approved by owner 2026-10-22** · supersedes part of DEC-008; amends SPEC §0 and §11 (A-11)
- **Decision:**
  - The build runs continuously. Phases still go in order, but a phase gate no longer stops work: when exit checks pass, the lead writes the phase summary (PROGRESS.md, the phase note, Owner To-Dos) and starts the next phase. The owner reviews asynchronously and can stop the build by disabling the Orca automation "Pulso lead".
  - Exit criteria only the owner can satisfy (Docker install, Clerk keys and sign-in, accounts) are logged as pending owner and do not block the next phase.
  - "[Added — pending approval]" items are built with their target phase unless the owner vetoes them. Proposed defaults are binding working defaults until vetoed.
  - An Orca automation runs a Claude "lead" every hour in the main checkout. It follows the vault note Agents/Lead Playbook: process the orchestration inbox, merge finished lanes into main after checks pass, push, keep Claude and Codex workers busy on the next tasks, run cross-reviews and brainstorms, and record state in Agents/Lead State.
  - Hard stops stay with the owner: paid services and plan changes, accounts and secrets, ToS/compliance changes, Railway deploys, destructive data operations, collector-host operations, force-pushes.
- **Alternatives:** stop at every phase gate (SPEC §0 as written) — the owner asked for the build to keep going; one long-lived coordinator session — it stops when that session hits a usage limit.
- **Why:** The owner wants Pulso built and improved continuously. A scheduled lead survives usage limits and session restarts: a failed run is simply retried the next hour.

### DEC-050 · Phase 0 worker, image and CI boundaries
**2026-10-22 · proposed (task_0ad44e416db2 / P0-INFRA)**
- **Decision:** Celery 5.6 uses the shared Redis settings, no result backend, and a fresh SQLAlchemy engine on `worker_process_init` (also emitted by the Windows solo pool). The guarded Beat entry point rejects scheduler-off and linked-worktree starts. It has no schedules; DEC-002 advisory-lock enforcement is required in Phase 1 before scheduling is enabled.
- **Images:** three multi-stage, non-root Dockerfiles under `infra/docker`, built from the repo root. Python uses uv 0.11.23 and package-specific non-editable installs; the API excludes torch and LightGBM. The worker stays lean until the Phase 2/6 ML dependencies arrive. Web copies Next standalone output plus static/public assets and uses the pinned pnpm 11.9.0.
- **CI:** one workflow with `python`, `web`, `contracts`, `images` and `tokens-only` jobs; full-SHA action pins, uv/pnpm caches, and cancellation of superseded runs. Absent lane targets skip explicitly; existing targets must pass. The Python job runs all tests against isolated pgvector/Redis services, and contracts exercise a single migration head, migration round trip, model drift and generated API/client drift. CI-4 and reduced-motion browser checks join later.
- **Integration:** migrations use the backend lane's root `alembic.ini`; API export is `python -m pulso_api.openapi` to `apps/api/openapi.json`; client types are `apps/web/src/lib/api/schema.d.ts`. The root mypy source path includes core so a worker-only check analyzes settings before core has a packaged typing marker.
- **Alternatives:** editable installs in runtime images; a separate image workflow; failing missing lanes before the join; enabling Beat without a lock. These either carry extra source/runtime state, duplicate workflow setup, block parallel landing, or break the single-scheduler rule.
- **Why:** this is the smallest runnable Phase 0 lane while retaining the future collector-host boundary. Docker/Redis/Postgres execution is unverified locally (no Docker); CI must supply that evidence before deployment.
- **Railway verification:** [Config as Code](https://docs.railway.com/config-as-code/reference) still states deprecation and the 2026-12-01 legacy cutoff, checked 2026-10-22. DEC-014's dashboard default remains; no Railway configuration file or deployment was created.

### DEC-051 · Phase 0 backend schema and API defaults
**2026-10-22 · proposed (task_95f0f99136cb)** · P0-BACKEND (DB-1..DB-5, API-1..API-5)
- **Decision:**
  - Migration `0001` freezes 21 Core, Catalog, Vendors and workspace tables, plus currencies and FX. Use the refined Data Model names (`raw_payloads.run_id/request`, `stores.currency/last_crawled_at`, explicit variant options); no user email is stored, following Auth. Search trends, embedding columns and similarity indexes remain in their shipping phases per DEC-028 and the Phase 0 plan.
  - Observation provenance includes UTC `captured_at`, `observed_for` and `raw_payload_id`. Shipping quote identity includes listing, optional variant, destination and method; `UNIQUE NULLS NOT DISTINCT` makes repeat quotes idempotent even without a variant. FX keeps the specified date/base/quote/source primary key and adds observation provenance. History is never corrected in place.
  - Install `vector` and `pg_trgm`; seed eight currency exponents and the four Phase 1 source identities, all disabled with empty config. No store/keyword seeds or live collection are enabled.
  - `to_minor` accepts exact Decimal/string/integer amounts, rejects fractional minor units, nonfinite values, floats and BIGINT overflow, and never silently rounds. The shared exponent dict matches migration currency seeds.
  - Settings are restricted to US/USD in v1. Fee, CPA and target-margin assumptions initialize to zero until configured; these are user assumptions, not measured costs. PATCH rejects nulls, unknown fields, noninteger money and out-of-range values, and resolves workspace identity exclusively from the authenticated membership.
  - First login inserts the unique Clerk subject before creating workspace, membership and settings in one transaction. PostgreSQL's conflicting insert wait serializes concurrent first logins without an extra lock. JWKS sets expire after 300 seconds; individual keys are not cached indefinitely, so key removal can take effect. JWTs require iss/exp/nbf/iat/sub/azp, RS256, five-second leeway and the admin allowlist.
  - Export OpenAPI to `apps/api/openapi.json`, following the dispatch contract; the web lane consumes it. Support `python -m pulso_api`, `packages/core/alembic.ini` and a root Alembic config. No shared Settings/S3 fields or modules were changed.
  - DB tests require an explicit `TEST_DATABASE_URL` naming `pulso_ci` (the existing CI service) or a dedicated `pulso_test*` database and migrate isolated temporary schemas. They skip clearly when absent/unreachable; no fallback to the collector database. Root changes are limited to test dependency/marker/fixture, Alembic config, the documented test URL and the regenerated lockfile. The API uses Redis client 6.4 to satisfy Celery/Kombu's shared workspace constraint (<6.5); Redis server versions are independent.
- **Alternatives:** freeze all planned tables; inline mutable model metadata in migrations; silently round money; preselect-then-insert first login; indefinite signing-key cache; reuse the development database for tests.
- **Why:** Follow Phase 0's minimum complete scope, preserve provenance and exact money, prevent duplicate first-login workspaces and cross-workspace writes, and keep test execution isolated from the collector host.
- **Validation:** `ruff check .` passed; strict `mypy packages/core apps/api` passed (29 files); pytest 59 passed, 4 skipped after rebasing onto the infrastructure lane. Both Alembic configurations export SQL and report one head (`0001`); OpenAPI export is byte-identical across two runs. Connected autogeneration/roundtrip, concurrency and isolation execution remain unverified locally (no Docker); a frozen revision was rendered with Alembic operations from metadata and reviewed offline. The DB tests cover those checks in CI. Starlette emits a non-failing httpx deprecation warning.
- **References checked:** [Clerk manual verification](https://clerk.com/docs/guides/sessions/manual-jwt-verification), [PyJWT API and JWKS caching](https://pyjwt.readthedocs.io/en/latest/api.html), [Alembic offline SQL](https://alembic.sqlalchemy.org/en/latest/offline.html).

### DEC-052 · Standalone Shopify spike boundaries
**2026-10-22 · proposed (P0-11)** · task_a79030ee06ef
- **Decision:** The diagnostic script uses the existing httpx dependency and Python 3.14's robots parser. The seed draft uses JSON-compatible YAML with full-line comments, read with stdlib JSON; all 90 entries remain disabled pending DEC-011 approval.
- **Request accounting:** No automatic redirects, retries or environment proxies. A redirect is recorded without following it; unavailable robots (except a 404) stop that store. All attempted requests, including transport failures, count toward 50. Three-second spacing is global; stricter robots delays and Retry-After extend it. Blocked stores are not retried, including duplicate input domains.
- **Execution:** The CLI rejects linked worktrees. Tests inject MockTransport and a clock. The owner explicitly chooses domains or a seed file for this one-shot diagnostic; it never enables a source, writes observations, or approves seeds. Missing ETags/handles produce skipped rows; a 404 is labelled possible headless/unavailable, not a definitive diagnosis.
- **Alternatives:** Follow redirects and account for every hop; add a YAML dependency; treat a 404 as proven headless. These add requests/dependencies or overstate the evidence for a bounded spike.
- **Why:** Keep the probe small, auditable and fixture-testable without altering the adapter or compliance policy. Live results and the SPK-3 go/no-go remain owner/lead work on the collector host.

### DEC-053 · Web foundation: pinned stack, Cache Components off, worktree-aware dev script
**2026-10-22 · proposed (P0-WEB)** · WEB-1, WEB-3; details DEC-018, DEC-024, DEC-025
- **Decision:**
  - **Versions (exact pins):** Next 16.4.2 with React 19.3.1, Tailwind 4.3.3 through the `@tailwindcss/turbopack` loader (create-next-app's default, no PostCSS), `@clerk/nextjs` 7.9.18, `motion` 14.4.0, `cmdk` 1.1.1, `radix-ui` 1.8.1, `next-themes` 0.4.6, `lucide-react` 1.61.0, TypeScript 5.9.3, ESLint 10.13.0, Vitest 5.0.5, Playwright 1.64.1.
  - **Release age:** pnpm 11 refuses packages younger than its minimum release age. Where the newest release was too new (Clerk 7.9.19, motion 14.6.0), the previous release is pinned instead of adding `minimumReleaseAgeExclude` entries. `unrs-resolver` is set to `false` in `allowBuilds` (its optional postinstall isn't needed).
  - **Cache Components and Partial Prefetching off** (create-next-app 16.4 turns both on). Every route reads the Clerk session, so a static shell gains little; Clerk 7 documents no Cache Components support; and the hidden `<Activity>` routes it keeps around would break the route-enter animation, focus-to-h1 and one h1 per page. Revisit in Phase 2 when there is cacheable data.
  - **Build:** `output: "standalone"`, `outputFileTracingRoot` and `turbopack.root` at the repo root, `devIndicators` off. `/api/*` rewrites to `API_URL`, which Next evaluates when the config loads (at `next dev` start and at `next build`), so the production image must be built with `API_URL` set.
  - **Class merging:** `clsx` + `tailwind-merge`, extended so the type-scale names (`text-label`, `text-title-1`, …) count as font sizes. shadcn's new `cn` package was removed: it doesn't know the custom scale and would drop one class of `text-label text-muted-foreground`.
  - **shadcn:** `components.json` (radix-nova) stays for `shadcn add`. Generated primitives are rewritten onto the tokens (no `transition-all`, ring focus or `bg-black/10`); only button, tooltip, sheet, kbd and skeleton are kept.
  - **`pnpm dev:web`** runs `apps/web/scripts/dev.mjs`, which starts `next dev` on `WEB_PORT` and passes `API_URL` and `PLATFORM_ADMIN_USER_IDS` from the repo-root `.env` / `.env.local` that `worktree_env.py` writes (real env vars win). Next only reads env files from `apps/web`, and reads the port before any of them.
  - **`typecheck`** is `next typegen && tsc --noEmit`, so the generated route types (`PageProps`, `LayoutProps`) exist in a clean clone.
- **Alternatives:** keep Cache Components and wrap every session read in `<Suspense>`; a runtime route-handler proxy instead of rewrites; a per-worktree `apps/web/.env.local` written by the worktree script (infra lane's file).
- **Why:** Boring, documented defaults; exact pins against front-end churn (Phase 0 risk table); one env source per worktree.

### DEC-054 · Web auth gate: proxy + layout check, shared allowlist, dev-only E2E bypass
**2026-10-22 · proposed (P0-WEB)** · WEB-2; details DEC-020
- **Decision:**
  - **Gate:** `src/proxy.ts` (Next 16 renamed `middleware` to `proxy`) runs `clerkMiddleware` on every page request: signed out → `/sign-in`; signed in but not on `PLATFORM_ADMIN_USER_IDS` → `/not-authorized`. The `(app)` layout runs the same check, because Clerk 7 recommends resource-based checks and deprecates `createRouteMatcher`. The proxy copy also covers client-side navigations, which don't re-run the layout. Public: `/sign-in/*`, `/not-authorized`, static files, the manifest and icons.
  - **`/api/*` is not matched by the proxy:** it is rewritten to FastAPI, which verifies the Clerk JWT itself (DEC-020).
  - **Allowlist:** the same `PLATFORM_ADMIN_USER_IDS` variable as the API. `/not-authorized` shows the signed-in Clerk user id with a copy button, so the owner can copy it into the allowlist on first sign-in.
  - **Fails closed:** without Clerk keys, `clerkMiddleware` throws, so every page errors instead of opening; an empty allowlist admits nobody. `next build` succeeds without keys.
  - **E2E bypass:** `NEXT_PUBLIC_PULSO_E2E_AUTH_BYPASS=1` runs `next dev` without Clerk, so Playwright can drive the shell before keys exist. It is honoured only when `NODE_ENV !== "production"`. Both values are inlined at build time, so a production build compiles the check to `false`; a unit test pins this. Agents never use Clerk keyless mode (it provisions temporary Clerk keys); the owner can turn it off with `NEXT_PUBLIC_CLERK_KEYLESS_DISABLED=1`.
- **Alternatives:** a middleware-only gate with `createRouteMatcher` (deprecated); a layout-only gate (misses client navigations); Clerk testing tokens now (they need real keys: CI-4); keyless mode for tests (creates a Clerk app).
- **Why:** Defense in depth, with no switch that can disable auth in production.

### DEC-055 · App shell defaults: visible unbuilt routes, cookie-remembered rail, palette and motion details
**2026-10-22 · proposed (P0-WEB)** · WEB-4, WEB-5, WEB-6; vault Design/App Shell & Navigation, Motion System
- **Decision:**
  - **Unbuilt routes are visible:** every SPEC §10 route (plus `/methodology`) is in the sidebar with a muted phase chip (`P2`) and opens a "{Page} arrives in Phase N" state. This follows the P0-WEB brief and the Phase 0 note, and supersedes the App Shell note's "hidden behind feature flags". One nav config (`src/lib/nav.ts`), with `CURRENT_PHASE` as the flag, feeds the sidebar, sheet, tab bar, breadcrumbs, palette and placeholder pages. A phase that builds a route adds its own folder, which wins over the catch-all.
  - **Sidebar collapse** is remembered in a `pulso_sidebar` cookie (not `localStorage`), so the server renders the right width and nothing shifts or animates on load. Collapsing reflows once with no width or FLIP animation: Motion System pattern 11 wins over the Phase 0 note's "FLIP collapse", because scaling the content panel distorts text. `[` toggles it.
  - **Breakpoints:** bottom tab bar below 768px, sheet below 1024px, 56px rail at 1024–1279px, 240px sidebar from 1280px.
  - **Palette:** cmdk + Radix Dialog with Motion, used directly (the generated shadcn Command/Dialog pulled in input-group and ring styles). Radix restores focus only to a `Dialog.Trigger`, so the shell records the focused element on open and restores it on close, except after a navigation, where the new page's h1 takes focus. Esc clears the query, then closes. Full-screen below 768px.
  - **Copy:** the top-bar trigger reads "Search or run a command…" until Phase 2 search exists; the palette shows a disabled "Search products, stores, suppliers · Phase 2" row.
  - **Enter animations run only on client navigations** (route enter, Daily Pulse stagger), never on the server-rendered first paint, so content is never hidden behind an animation and hydration stays stable.
- **Alternatives:** hidden unbuilt routes; `localStorage` for the collapsed state; shadcn's Sidebar block (it animates width).
- **Why:** The owner can review the whole product map from Phase 0, with no layout shift and the motion rules intact.

### DEC-056 · Phase 0 spine pins, build-script allowlist and environment names
**2026-10-22 · proposed (P0-13)** · task_3cd7ff937c62; implementation details of DEC-012 and DEC-018
- **Decision:**
  - Record the images already used by `infra/docker-compose.yml`: `pgvector/pgvector:0.8.7-pg18-trixie`, `redis:8.8.3-alpine` and `rustfs/rustfs:1.0.3`, with named volumes `pgdata`, `redisdata` and `s3data`. This records the checked-in pins, not a new image or registry verification.
  - Keep `packageManager: pnpm@11.9.0` in root `package.json`. pnpm 11's `allowBuilds` mapping in `pnpm-workspace.yaml` explicitly permits `sharp` and `esbuild`; it replaces the older `onlyBuiltDependencies` spelling.
  - The raw-payload bucket is `pulso-raw`, configured by `S3_BUCKET_RAW` in `.env.example` and `packages/core/src/pulso_core/settings.py`. Local creation is explicit: `uv run python -m pulso_core.s3 init`. The earlier vault name `pulso-data` / `S3_BUCKET_DATA` is superseded; no bucket or data is renamed by this documentation change.
  - Compose host-port variables are `PG_PORT`, `REDIS_PORT`, `S3_PORT` and `S3_CONSOLE_PORT`, bound to loopback. They are distinct from native app ports `API_PORT` / `WEB_PORT` and the full connection settings `DATABASE_URL`, `REDIS_URL` and `S3_ENDPOINT_URL`; changing a host port requires matching connection settings. `infra/scripts/worktree_env.py` assigns app ports, database names and Redis DB numbers while keeping both scheduler/live flags off; it does not provision databases.
- **Alternatives:** floating image tags; the old pnpm allowlist key; the planning-only bucket name and `PULSO_PG_PORT`-style aliases.
- **Why:** Match the existing code and avoid a second set of names in the setup notes. DEC-049 governs continuous build, not these spine implementation details. Railway configuration remains in its dashboard under DEC-014; no runtime configuration or collector-host operation changes here.

### DEC-057 · Backend cross-review safety defaults
**2026-10-22 · proposed (task_712636763b04 / P0-14)** · refines DEC-050 and DEC-051
- **Decision:**
  - Test connections use only their generated temporary schema in `search_path`, excluding `public` and its Alembic version table. Migration `0001` needs no extension types; its existing extension installation works in the temporary schema when absent, or reuses an already installed extension without adding its schema to the path. No migration is changed. The CI Python job leaves migration setup to the fixture; the contracts job retains its separate roundtrip.
  - `TEST_DATABASE_URL` accepts no query parameters, preventing libpq destination/service/options overrides. Check both the parsed database name and `current_database()` on each fixture engine before any schema creation or migration; only `pulso_ci` or `pulso_test*` names qualify. The guard fails closed without echoing connection details.
  - The shared engine factory keeps UTC, pre-ping and hidden SQL parameters. Its default has no statement-timeout override; API sessions and readiness explicitly request 10,000 ms. The process cache separates timeout policies. Workers use the shared per-PID engine and its pool defaults instead of the previous private 3-connection/no-overflow pool; inherited engine pools are still disposed with `close=False`.
  - Beat checks the working directory and installed module path for linked worktrees. The same guard runs at `beat_init`, including raw and embedded Beat. Scheduler-off remains the default; the Phase 1 advisory lock is still required before scheduling.
  - Keep only the root `alembic.ini`; tests resolve it from the repository path. This supersedes DEC-051's duplicate-config support without rewriting that historical entry.
  - The API binds `::` with a stdlib dual-stack socket passed to Uvicorn, preserving IPv4 callers. The installed Uvicorn host-only startup delegates to asyncio, which sets `IPV6_V6ONLY`; changing only the host string would lose IPv4. Keep `PORT` / `API_PORT` precedence. Re-check Railway private-network documentation and connectivity at go-live.
- **Alternatives:** allow-list selected test-URL query parameters; keep a universal 10-second timeout; retain a separate worker engine; expose both Alembic configs; use Uvicorn's IPv6-only host path. These leave override maintenance, inappropriate query limits, divergent defaults, config drift or an IPv4 regression.
- **Why:** Resolve cross-review findings 1–9 with existing dependencies and no schema, source, collector-host or deployment changes. Finding 10 remains the owner decision on spike scope.

### DEC-058 · Typed client wiring, root dev scripts and the e2e job
**2026-10-22 · proposed (P0-07)** · WEB-7, CI-4; details DEC-019, DEC-020, DEC-054. Renumbered from DEC-057 at merge (P0-14 took DEC-057).
- **Decision:**
  - **Versions (exact pins):** `openapi-typescript` 7.13.0, `openapi-fetch` 0.17.0, `openapi-react-query` 0.5.4 on `@tanstack/react-query` 5.104.5; `@clerk/testing` 2.2.48, the newest release whose `@clerk/backend` range matches the pinned `@clerk/nextjs` 7.9.18 tree (2.2.49 wants 3.26.1).
  - **Client:** `apps/web/src/lib/api/client.ts` calls `/api` (the Next rewrite) and adds `Authorization: Bearer` from `window.Clerk.session.getToken()`. The API also accepts the `__session` cookie, but `getToken()` refreshes the short-lived token first. `schema.d.ts` is generated by the same command as the CI contracts job and committed.
  - **Error states:** a problem+json body (it carries `request_id`) means the API answered with an error. Anything else means "API not reachable": the fetch failed, or the rewrite couldn't connect and Next answered with its own plain-text 500 (checked locally).
  - **Query defaults:** `staleTime` 5 min (the API & Typed Client note), `retry: 1`, so a stopped API shows its state within seconds.
  - **Workspace chip:** `/v1/me` returns ids only, so the top bar shows the first 8 characters of `workspace_id` (full id, admin flag and check time in the tooltip) and links to `/settings`. It hides below 768px like the freshness chip. Under the E2E bypass it is static and makes no request.
  - **`pnpm dev:api`:** uvicorn with reload on `127.0.0.1`, port from `get_settings().api_port`, so the worktree's `.env.local` `API_PORT` applies. Reload watches only `apps/api/src` and `packages/core/src` (StatReload: `watchfiles` isn't installed). `python -m pulso_api` stays the container-style entry (`0.0.0.0`, `PORT`). `db:migrate` = `uv run alembic -c alembic.ini upgrade head`; `gen:api` = OpenAPI export, then the CI codegen command.
  - **e2e:** two Playwright runs, because Next 16 allows one `next dev` per app directory: `pnpm --filter web e2e` (E2E bypass: palette keyboard flow, reduced motion) and `pnpm --filter web e2e:clerk` (`playwright.clerk.config.ts`: real Clerk dev instance with testing tokens; a signed-out visit lands on `/sign-in` with `redirect_url`). The CI job sets a `HAS_CLERK` flag from the two secrets. Without both, one step prints a "skipped: no Clerk secrets" notice and the job succeeds. Only the Clerk step receives the keys; no `pull_request_target`.
  - **Deferred:** signed-in flows (sign in → Daily Pulse → Ctrl+K) need a Clerk test user and its id on the CI allowlist. Add them when the owner creates that user.
- **Alternatives:** cookie-only auth through the rewrite; a fixed uvicorn CLI port; one Playwright run with a production build for the Clerk test; a job-level `if:` (GitHub shows it as skipped, not succeeded).
- **Why:** The smallest pieces that prove the pipeline end to end, with every command working from PowerShell 5.1 and Git Bash.
