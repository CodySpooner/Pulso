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
| DEC-009 | CJ account must transact every 30 days | approved by owner 2026-10-23 (DEC-136: use CJ now until it lapses) |
| DEC-010 | Vendor-scraped demand data policy | pending owner |
| DEC-011 | Starter seed lists | approved by owner 2026-10-22 (DEC-073) |
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
| DEC-059 | `/admin/ui` gallery, specimen values, DeltaBadge and skeleton timing tokens | proposed (P0-09) |
| DEC-060 | Phase 1 collection evidence, parser/import identity and queued runs | proposed (P1-01) |
| DEC-061 | Raw capture objects, bodyless evidence and sanitized request metadata | proposed (P1-02) |
| DEC-062 | 0002 amended in place before first apply | proposed (P1-17) |
| DEC-063 | Collector execution, target evidence and effective observations | proposed (P1-03) |
| DEC-064 | Offline import templates, identity, preview and original-capture parser correction | proposed (P1-05) |
| DEC-065 | Versioned seed loading and approval guard | proposed (P1-06) |
| DEC-066 | Releasing worker worktrees on Windows: stop processes standing in the folder first | proposed (P1-21) |
| DEC-067 | Non-stop build: leads every 15 minutes (Claude/Codex), 5 workers, improvement backlog | approved by owner 2026-10-22 |
| DEC-072 | Non-stop safety: atomic lead lock, a lead worktree per provider, protected paths, batched reviews, always-on e2e smoke; repo public | proposed (own-001) |
| DEC-073 | Data collection approvals: seed_v1, crawler ID, Shopify test, collector host via scripts | approved by owner 2026-10-22 |
| DEC-069 | Collector block accounting, durable Retry-After deadlines and request hook | proposed (P1-03b) |
| DEC-068 | Data Health admin API: shapes, live-run guard, target freshness and the import split | proposed (P1-11) |
| DEC-070 | Raw request sanitization and portable capture reads | proposed (P1-20) |
| DEC-075 | Reject import mappings changed by metadata sanitization | proposed (P1-24) |
| DEC-076 | Seed revision ordering and stored-target validation | proposed (P1-25) |
| DEC-077 | Bounded Shopify probe: whole-run request budget, first-block run stop, public bot page | proposed (data-01) |
| DEC-090 | SPK-3: Shopify crawler go/no-go after SPK-2 (conditional go; enables nothing) | proposed (data-04) |
| DEC-087 | Shopify catalog evidence, conservative cache and store exclusions | proposed (P1-07) |
| DEC-088 | Frankfurter gap recovery, first-rate evidence and explicit FX rounding | proposed (P1-09) |
| DEC-089 | Queued publishing and guarded Beat | proposed (P1-04) |
| DEC-092 | Import retry: a capture with no successful run is re-run on upload, not skipped | proposed (P1-29) |
| DEC-096 | Data Health UI: derived source states, nav badge rule, inline heatmap and contract gaps | proposed (P1-12) |
| DEC-100 | Database-only backup and scratch restore tooling | proposed (P1-14) |
| DEC-102 | Railway site-only deploy: Hobby, Railway Bucket, no Docker cache mounts | proposed (railway-site) |
| DEC-103 | Shopify pacing across restarts and a 24-hour robots cache | proposed (P1-33) |
| DEC-104 | Collector profile, guarded operations and Railway handoff | proposed (P1-13); merge approved by owner 2026-10-23 (DEC-129) |
| DEC-128 | RustFS replaces MinIO as the local S3 emulator (R-05); Phase 0 screens approved (WEB-6) | approved by owner 2026-10-23 |
| DEC-129 | Owner merges the protected collector scripts (P1-13 + P1-14) and sets up the collector host | approved by owner 2026-10-23 |
| DEC-136 | Use CJ now until the 30-day rule lapses it; Pulso is for the owner's own stores, not a paid app | approved by owner 2026-10-23 |

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
**2026-10-22 · approved by owner 2026-10-23 (DEC-136)** · Review M3, D4 · originally pending owner
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
**2026-10-22 · approved by owner 2026-10-22 (DEC-073)** · Review M6, D7 · originally pending owner
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
- **Decision:** A repo-local git identity of `CodySpooner` with the GitHub noreply email. The repo stays private. *(Superseded in part by DEC-072: the owner made the repo public on 2026-10-22.)*
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
  - **`pnpm dev:api`:** uvicorn with reload on `127.0.0.1`, port from `get_settings().api_port`, so the worktree's `.env.local` `API_PORT` applies. Reload watches only `apps/api/src` and `packages/core/src` (StatReload: `watchfiles` isn't installed). `python -m pulso_api` stays the container-style entry (dual-stack `::` listener per DEC-057, `PORT` overriding `API_PORT`; wording corrected after the P0-15 review, which found `0.0.0.0` here). `db:migrate` = `uv run alembic -c alembic.ini upgrade head`; `gen:api` = OpenAPI export, then the CI codegen command.
  - **e2e:** two Playwright runs, because Next 16 allows one `next dev` per app directory: `pnpm --filter web e2e` (E2E bypass: palette keyboard flow, reduced motion) and `pnpm --filter web e2e:clerk` (`playwright.clerk.config.ts`: real Clerk dev instance with testing tokens; a signed-out visit lands on `/sign-in` with `redirect_url`). The CI job sets a `HAS_CLERK` flag from the two secrets. Without both, one step prints a "skipped: no Clerk secrets" notice and the job succeeds. Only the Clerk step receives the keys; no `pull_request_target`.
  - **Deferred:** signed-in flows (sign in → Daily Pulse → Ctrl+K) need a Clerk test user and its id on the CI allowlist. Add them when the owner creates that user.
- **Alternatives:** cookie-only auth through the rewrite; a fixed uvicorn CLI port; one Playwright run with a production build for the Clerk test; a job-level `if:` (GitHub shows it as skipped, not succeeded).
- **Why:** The smallest pieces that prove the pipeline end to end, with every command working from PowerShell 5.1 and Git Bash.

### DEC-059 · `/admin/ui` gallery, specimen values, DeltaBadge and skeleton timing tokens
**2026-10-22 · proposed (P0-09)** · WEB-9 (Added — pending approval, in scope per DEC-049); AGENTS.md §8.
- **Decision:**
  - **Route:** `/admin/ui` is a real page in the `(app)` group, so it sits behind the same allowlist gate (proxy + layout, DEC-054) and ships in production builds. It is in the nav config under Admin with `phase: 0` (built), so the sidebar, the palette and the breadcrumbs pick it up.
  - **Specimen values:** the table sample uses rows from `src/app/(app)/admin/ui/specimens.ts`, named "Specimen 01…08". The page says they are specimens, not data, and they are never fetched or stored (AGENTS.md §2, no fake data).
  - **Delta rule in code:** `formatDelta` in `src/lib/format.ts` (glyph, signed text with U+2212, tone from `goodDirection`, `±0.0` when it rounds to zero) and a `DeltaBadge` text component that renders it. `formatDelta` is Vitest-covered. Phase 2 tables reuse them instead of rebuilding the rule.
  - **Skeleton timing tokens:** `--skeleton-delay` (150ms) and `--duration-shimmer` (1.6s) in `tokens.css` replace the raw values in `skeleton.tsx` (the phase-end checklist found them).
  - **Motion samples:** nothing animates on first paint. "Replay motion" remounts the samples. Reduced motion is verified by the existing recorder journey, which now replays them.
- **Alternatives:** a dev-only route excluded from production (then the owner can't review it on Railway); a static HTML preview in the vault only (it drifts from the real tokens); invented product names in the table (they read as data).
- **Why:** One reference page built from the real tokens and components, reviewed by the owner and copied by agents, with no number on it that could be mistaken for data.

### DEC-060 · Phase 1 collection evidence, parser/import identity and queued runs
**2026-10-22 · proposed (P1-01)** · FW-5; R-06/R-08/R-09/R-10; agreed P1-00 D3, Slots and Imports
- **Decision:** one revision `0002` on frozen `0001`, with matching SQLAlchemy models; all additions are global market/ops data.
  - **Replay:** `Observation.parser_version VARCHAR(80) NOT NULL DEFAULT '1'` joins every observation unique key. Existing snapshots retain their values and provenance; corrected listing/variant/freight/search parses append under a different version. `parser_version` is an opaque label and is never ordered; the effective row for a (natural key, raw_payload_id) is the one with the greatest `id` (shared read helper owned by P1-03). FX retains its date/base/quote/source primary key and first-rate behavior (DEC-051 and the agreed P1-09 exception); later conflicting FX captures remain raw evidence plus a source event, not a replacement rate.
  - **Freight:** `shipping_options.quantity INTEGER NOT NULL DEFAULT 1`; the natural key is listing, nullable variant, nullable origin, destination, quantity and method, followed by raw payload and parser version. Keep `NULLS NOT DISTINCT`, so unknown variant/origin cannot defeat replay idempotency.
  - **Imports:** nullable `raw_payloads.template_version VARCHAR(80)`, with `uq_raw_payloads_import(source_id, sha256, template_version) WHERE template_version IS NOT NULL`. Live captures leave it null and remain distinct even with identical bytes. Parser replay reuses the original capture; an ordinary repeat import is handled as a skipped run by P1-05.
  - **Queue/retry:** default new runs to `queued`; `queued_at` is non-null with `now()` default, while `started_at` is nullable with no default until execution. Legacy runs use their recorded start as the earliest available queue timestamp. Persist `sources.retry_not_before TIMESTAMPTZ`. Job-qualified strings such as `catalog:2026-10-22` and `freight:2026-W43` fit the existing 30-character `slot_key`; its successful-slot index is unchanged. Publish-failure and abandoned-run handling belong to P1-03/04; no outbox.
  - **Target evidence:** `collector_run_targets(run_id, scope, target_id, status, raw_payload_id, captured_at)`, primary key `(run_id, scope, target_id)`, lookup index `(scope, target_id, captured_at)`. Target ids are text within a source and scope, allowing store, variant and keyword identities. The framework records every planned target, defaults to `pending`, and stamps `captured_at` when recording terminal evidence. `success` means the entire target scope completed (including unchanged/304) and requires a raw payload; failed/partial targets may have none. Catalog coverage never proves inventory coverage; only complete store-catalog success permits delisting.
  - **Search series:** `search_trends` uses the observation mixin plus source, keyword, geo, window, granularity, metric, numeric value and partial flag. Natural identity includes every series dimension and `observed_for`; indexes cover `(source_id, captured_at)` and `(keyword, geo, captured_at)`. Every capture can append its entire returned series without overwriting another capture.
  - **Operations:** append `host_heartbeats(id, host, at)` with `(host, at)` index; `collection_gaps(id, source_id, slot_key, slot_start, slot_end, reason, detected_at, filled_by_run_id)` with unique source/slot, positive half-open interval and `(source_id, slot_start)` index. `source_events(id, source_id, actor, action, reason, at)` uses actor `system` or the user id string, an open action string for toggles/block/FX-conflict events, `(source_id, at)` index, and triggers rejecting UPDATE/DELETE/TRUNCATE. Seed source id 5, key `backup`, type `internal`, phase 1, disabled; it uses existing run records.
  - **Coverage view:** `source_daily_coverage(source_id, day, status, runs, rows, targets, successful_targets)` groups distinct `(source, UTC capture day, scope, target)` evidence, counting any success for that target/day, separately from run counts and inserted-row sums. Gaps span all UTC dates intersecting their half-open slot interval. Status is `success` only with all recorded targets covered and no unfilled gap, `partial` with some coverage, then `gap`, `running`, `queued`, `failed`, `filled` for healed gaps, or `unknown` without evidence. A run's success flag alone never grants coverage; source summaries never prove a specific target was observed. This is a current operational view, not the as-of feature query: later `filled_by_run_id` changes do not authorize historical feature coverage (D4). The heatmap excludes `sources.type = 'internal'` (the backup pseudo-source; P1-11 filters it); the backup card and its 26 h alert read `collector_runs`. DH-1 always passes a day bound; view optimization is deferred in BACKLOG until target volume warrants EXPLAIN.
- **Alternatives:** a job column/new slot index; separate imports table; deduplicating live captures by hash; source-wide success or snapshot spacing as coverage; rewriting corrected observations or FX rates. These add state or lose capture, scope or historical truth. Unspecified status values stay strings, matching the existing run model; lifecycle validation belongs to the framework.
- **Why:** freeze exactly the shared Phase 1 contract before the framework/adapters land, preserving history and supporting unchanged observations, durable retry deadlines and safe import replay without extra services or dependencies.
- **Downgrade:** refuses any Phase 1 evidence before changing the schema: rows in `search_trends`, `collector_run_targets`, `collection_gaps` or `source_events`; non-default freight quantity; import template identity; a retry deadline; or a non-`1` parser version in listing/variant snapshots, shipping options or FX. `host_heartbeats` remains prunable. Old uniqueness and non-null-start constraints still reject incompatible history and queued runs without deduplication or invented start times. Use an isolated empty/compatible database or restore a backup; non-test destructive operations remain owner-only.
- **Validation:** single `0002` head and offline SQL render; model/UTC/money/index checks pass. PostgreSQL-marked tests cover upgrade/downgrade/upgrade, legacy-row preservation, metadata/default drift, replay/correction, freight/import identity, the FX exception, job slots, audit immutability and target/UTC coverage; execution remains unverified locally (no Docker). No API contract, dependency, collector-host, scheduler or adapter change.

### DEC-061 · Raw capture objects, bodyless evidence and sanitized request metadata
**2026-10-22 · proposed (P1-02)** · FW-2; task_503174e041ff
- **Decision:** `pulso_sources.storage` exposes `store_capture`, `read_capture` and `presign_capture`, using existing `make_client` and `S3_BUCKET_RAW`; no schema, settings or dependency changes.
  - **Objects:** SHA-256 and `raw_payloads.bytes` describe the uncompressed bytes; gzip uses `mtime=0`. Keys are `raw/<source>/<yyyy>/<mm>/<dd>/<sha256>.<ext>.gz`, with an aware `captured_at` normalized to UTC. `text/csv` and `application/csv` use `csv`; `application/json` and `+json` types use `json`; all others (including absent content type and HTML error bodies) use `bin`. Media-type matching ignores case and parameters, while the received content type stays on the row and object (`application/octet-stream` on the object when absent); objects have `ContentEncoding=gzip`.
  - **Capture identity:** conditional `PutObject(IfNoneMatch="*")` reuses an existing key on `PreconditionFailed`/412; every successful call adds and flushes a fresh `RawPayload` with `template_version=None`, even for identical bytes. Other upload failures propagate before adding/flushing any row. The caller commits/rolls back; a later database failure can leave an unreferenced object, which this module never deletes. Import deduplication/template stamping remain P1-05's responsibility (DEC-060).
  - **No body:** `body=None` creates evidence with `storage_key=None`, size 0 and the SHA-256 of empty bytes (the existing hash column is non-null). A 304 normalizes empty bytes to None and rejects a nonempty body. An empty 200 body is still stored. `read_capture` rejects bodyless rows, decompresses stored bytes and verifies their SHA-256; `presign_capture` returns None for bodyless rows or a 900-second GET URL. `make_client` explicitly uses SigV4, since boto3 otherwise presigns with SigV2 in `us-east-1`; clients and response streams are closed explicitly.
  - **Sanitizer:** recursively copy JSON metadata maps/lists and strip credential keys after case folding and removal of non-alphanumeric separators. Known names: `auth`, `authorization`, `proxy-authorization`, `cookie`, `cookies`, `set-cookie`; `token`, `access_token`, `refresh_token`, `id_token`, `CJ-Access-Token`, `X-Auth-Token`, `auth_token`, `X-Shopify-Access-Token`; `api_key`, `X-API-Key`, `key`, `app_key`, `app_secret`, `client_secret`, `password`, `passwd`, `secret`, `credentials`, `credential`, `signature`, `sig`; `AWSAccessKeyId`, `access_key`, `access_key_id`, `secret_access_key`; `csrf_token`, `X-CSRF-Token`, `xsrf_token`, `X-XSRF-Token`; `X-Amz-Credential`, `X-Amz-Signature`, `X-Amz-Security-Token`, `X-Goog-Credential`, `X-Goog-Signature`. URL query names are decoded before checking; URL userinfo and fragments are removed. Raw `query`/`query_string` strings receive the same query filter. Safe repeated/blank query parameters survive. Adapters supply structured metadata, never serialized auth blobs; new auth field names must extend this list. AliExpress writes are rejected (DEC-037).
- **Alternatives:** hash-deduplicated rows lose repeated observation evidence; unconditional PUT can overwrite a shared object; linking 304 to an old object obscures its bodyless response; committing inside storage splits caller transactions. A new storage abstraction or dependency is unnecessary.
- **Why:** keep capture evidence distinct, preserve retrievable original response bytes, and remove known request credentials before persistence while leaving framework lifecycle/import rules with their owners.
- **Validation:** offline fake S3 and botocore Stubber tests cover duplicate captures/one object, JSON/CSV/empty-body round trips, UTC/day/source scopes, hash/gzip corruption, failed uploads with no row, 304 evidence, fixture credential stripping and SigV4 presigning. PostgreSQL persistence/snapshot-to-object test uses `TEST_DATABASE_URL` and remains unverified locally (no Docker), as does a real RustFS/R2 round trip; FW-2's end-to-end checkbox stays open.

### DEC-062 · 0002 amended in place before first apply (P1-17)
**2026-10-22 · proposed (P1-17)** · schema review P1-16; task_866283a2b159
- **Decision:** amend migration `0002` in place, retaining a single `0002` head and frozen `0001`. The lead verified on 2026-10-22 that no database anywhere has applied `0002`: Docker is not installed on the PC, so neither the dev stack nor the collector host `C:\dev\pulso` has a Postgres, and GitHub Actions has refused every job since before `0002` merged because of billing, so CI never ran migrations.
- **Changes:** guard downgrade against Phase 1 evidence, reject source-event TRUNCATE, and display healed gaps as `filled`; DEC-060 now states the backup and parser selection contracts. The API S3 readiness check uses `contextlib.closing`, matching the existing storage pattern; real boto3/Stubber tests cover bucket success/failure and client closure without network access.
- **Alternatives:** a new `0003` repair revision; leave a destructive downgrade with a warning; infer parser order from version strings. These add migration churn before any apply, lose evidence or choose corrections incorrectly.
- **Why:** fix the reviewed contract before its first use without adding tables, columns, dependencies or history rewrites. P1-03 owns the shared greatest-id read helper; P1-11 owns the internal-source heatmap filter. DEC-063+ remain reserved for P1-03.
- **Validation:** lint/typecheck/tests pass (155 Python passed, 45 DB skips; 255 Vitest passed), with one `0002` head. Both S3 regression cases failed on the old code and passed with `closing`. New DB-marked cases cover all 11 guard predicates plus queued runs and parser pairs, all coverage branches/precedence, UTC queue attribution and TRUNCATE; they remain unverified locally (no Docker). Additional offline SQL probes passed on disposable PGlite 0.5.11 / PostgreSQL 18.6 WASM: 13 isolated downgrade rejections, 14 coverage cases, audit immutability, UTC/healed gaps and upgrade/downgrade/re-upgrade with prunable heartbeats. Only `CREATE EXTENSION vector` was omitted in the scratchpad (no schema object uses it); this does not verify the real Postgres fixture, pgvector or CI.

### DEC-063 · Collector execution, target evidence and effective observations
**2026-10-22 · proposed (P1-03)** · FW-1, FW-3, SCH-3; D2/D3, Slots, R-06/R-10
- **Decision:** `pulso_sources.framework` exports a typed `Adapter[R]` protocol, request/response/target values, lifecycle functions and observation helpers; no new dependency, storage changes or schema changes.
  - `enqueue_run` owns a dedicated session's commits: persist queued/queued_at before calling the broker callback with the run id. A publish exception conditionally fails the still-queued row with `publish_failed`, then propagates; it never overwrites a concurrently started delivery. `execute_run` atomically claims only queued rows, stamps started_at, and returns an already-running/terminal row without executing it. P1-04 owns per-source advisory locking, scheduling and abandoned-run recovery; no outbox or worker process is added here.
  - Plan all target identities before fetching; each target may yield page requests lazily. Store/commit each raw capture through DEC-061 before parsing, then commit parsed changes and counts per payload. Parse/upsert failure rolls back that payload's changes while retaining its raw evidence and earlier committed pages. Only a nonempty, wholly completed target is success; 304 succeeds without parsing or inserting snapshots, and `Response.complete=False` prevents target success. Every target is re-stamped at terminal status. Never infer another target's coverage from run success.
  - Offline request modes (`csv`, `json`, `fixture`) return supplied bytes without calling adapter HTTP; live `fetch` enforces D2 and passes the required contact-based `PulsoBot/1.0` User-Agent. The core helper preserves Beat's cwd + installed-module worktree checks. Adapters must use the shared fetch/runner boundary, supply request timeouts, translate transport failures to `TimeoutError`/`ConnectionError`, and never commit. HTTP 500/502/503/504 and transport failures receive three additional retries at 2/8/30 seconds by default; no jitter is needed on the single sequential consumer. A monotonic plan budget stops unfinished work as partial. Arbitrary exception text is not persisted because it can contain credentials.
  - Observation inserts use PostgreSQL `ON CONFLICT DO NOTHING` on the model's natural key plus raw payload and parser version. Listing/variant snapshots compare values_hash with the shared effective-row helper for new captures; existing captures with a different parser append. `parser_version` is an opaque label, never ordered: within `(natural key, raw_payload_id)` the greatest id wins. Without a capture argument, the helper orders captured_at, raw_payload_id, id descending; historical readers must first select an eligible capture under DEC-031. FX retains its adapter-owned first-rate exception.
  - Slots contain the job and UTC date/ISO week, validated against the existing 30-character column. Settings and `.env.example` define block threshold 5, request/task retry caps, 45-minute default plan budget, 60/75-minute collect limits, source budgets (Shopify/CJ 30 minutes, Trends 10, FX 5; working defaults), HTTP timeout 30 seconds, Shopify at most 30/min with a 10-product .js panel (maximum 20), CJ at most 1/sec and 20k points/day, and Trends at most 250 searches/month. Source-specific pacing/quota reservation belongs to P1-07–09; Celery limits belong to P1-04. Secrets remain empty env placeholders with SecretStr settings; a real bot contact is required only for live fetch.
- **Size split:** the permitted core exceeds the task's approximately 400-line threshold, so FW-4 moves to P1-03b before live enablement: consecutive block accounting, exactly one disable source_event, Retry-After parsing/persistence and bounded in-process waiting are not implemented. Existing persisted retry_not_before deadlines already stop a live run without fetching; that alone does not complete R-08. No source is enabled here.
- **Alternatives:** a base adapter class, an HTTP dependency, an outbox, lexically ordered parser versions, transactions spanning network calls, or source-wide coverage. These add machinery or lose replay/evidence correctness; the protocol, existing storage API and DB constraints suffice.
- **Validation:** fake lifecycle tests, existing Beat tests, SQL-shape checks and an actual SQLite replay/correction test run offline. PostgreSQL replay/constraint and committed lifecycle/raw/snapshot integration tests are DB-marked and unverified locally (no Docker). No live calls, scheduler start, collector-host operation or deployment.

### DEC-065 · Versioned seed loading and approval guard
**2026-10-22 · proposed (P1-06)** · implements DEC-011; seed approval remains pending owner
- **Decision:** JSON-compatible YAML retains the existing lists and gains only an `approval` block: `version` (`seed_v1`, increment for subsequent revisions), `status` (`draft` or `approved`), `approved_on` (null for draft, valid `YYYY-MM-DD` for approved), and `decision` (`DEC-011`). Only the owner grants approval and records it in DECISIONS; this task leaves the shipped file draft and all entries disabled.
- **Loader:** `uv run python -m infra.scripts.seeds [--seed-file <path>]` previews the seed-only diff against the configured database; `--apply` commits all three source changes in one transaction. Known sections map to fixed migration identities: `stores` → `shopify_stores`, `cj_categories` → `cj`, `keywords` → `google_trends`. Missing source rows fail with a migration hint; FX is untouched. Validation requires the section/entry fields, normalizes bare domains to lowercase, rejects duplicate domains and case/whitespace-equivalent keywords/category names, and enforces US/UTC keywords without new dependencies.
- **Storage:** each source's `config.seed` contains `version`, `status`, `approved_on`, `decision`, and `entries`; the loader preserves every other config key and every source enablement/status field. Draft entries are forced disabled regardless of their file flags. Applying locks the source rows; an identical payload/version writes nothing, while changed content under the installed version fails and requires a new version (including a later approval). A new version replaces only the seed block. The diff omits unrelated config to avoid exposing credentials.
- **Guard:** adapters and scheduling import `approved_targets(session, source_key)` from `pulso_sources.seed_approval`, with no dependency on `infra`. It returns enabled entry dictionaries only from valid, dated approved seed metadata; draft/missing/malformed metadata or unknown source keys return `[]`. This target check is additional to `sources.enabled`, live-fetch/worktree guards, source-specific gates and Shopify workspace tracking; it does not enable sources or populate workspace tracking rows.
- **Alternatives:** PyYAML, a new seed table/migration, writing top-level config lists, or silently changing a loaded version. These add dependencies/schema, collide with source settings, or obscure the approved revision. A single versioned JSON block keeps the initial contract small and reviewable.
- **Validation:** offline SQLite execution covers the shipped 30/10/50 dry run, draft-true suppression, approved target filtering, actual committed re-apply with zero writes, config/source-flag preservation, missing sources, version conflicts and invalid input. PostgreSQL locking and connected production-database execution remain unverified locally (no Docker); no live collection or collector-host operation was run.

### DEC-066 · Releasing worker worktrees on Windows
**2026-10-22 · proposed (P1-21)** · DEC-064 and DEC-065 stay reserved for P1-05 and P1-06
- **Decision:** the lead releases a merged worker worktree with `uv run --with psutil python infra/scripts/release_worktree.py <path>` instead of a bare `orca worktree rm`. The script refuses dirty or unmerged worktrees, the lead workspace and anything outside the Orca workspaces folder; then it closes the workspace terminals, stops every process whose working directory is inside the folder, removes the worktree and deletes the leftover folder.
- **Alternatives:** `orca worktree rm --force` alone — on 2026-10-22 it failed for 13 worktrees with `EBUSY` ("Delete failed"): git unregistered them but Windows kept the folders because idle Orca shells and Codex-daemon helpers (MCP servers, `node_repl`) still used them as their working directory; adding `psutil` to the project — the script runs it through `uv run --with`, so the project dependencies stay unchanged.
- **Why:** Windows cannot delete a directory that is any process's current directory, and those helpers outlive the agent session that started them.

### DEC-064 · Offline import templates, identity, preview and original-capture parser correction
**2026-10-22 · proposed (P1-05)** · CSV-1, CSV-2; R-10; DEC-060/061/063
- **Decision:** `pulso_sources.imports` provides synchronous Python functions for the later P1-11 API/worker integration, without routes, dependencies, migrations or real source parsers.
  - **Templates/validation:** `TEMPLATES` contains the vault's Phase 1 columns for seeded keys `shopify_stores`, `cj`, `google_trends`, version `csv-v1`; `template_csv(source_key)` returns headers and an explicitly illustrative example. Missing money currency defaults to USD; supported currencies/exact minor-unit validation reuse `pulso_core.money`, with no rounding. CJ requires either product id or SKU. UTF-8 BOM and comma/semicolon are accepted; header case/spaces/hyphens auto-map, with optional uploaded-header → canonical-column mappings. Unknown/duplicate mapped headers, bad encoding/CSV syntax and cap breaches reject the file; invalid values/row widths report `(row, column, message)` and skip the whole row. Blank rows count as skipped. Working caps: 20 MiB (20 × 1024² bytes), 100,000 CSV data records, first 20 valid rows in preview. Larger CSV fields are allowed up to the upload cap, rather than Python's incidental 128 KiB default.
  - **Preview:** `parse_csv(source_key, body, *, mapping=None)` returns validated typed rows, errors and blank-row count. `preview_csv(source_key, body, *, classify, mapping=None)` adds insert/update/skip/invalid counts without creating a run, uploading or calling upsert. The source-owned `classify(rows) -> UpsertStats` callback must be read-only and account for every valid row; the service cannot guess existing entity state before source adapters exist. Pass `sources.config.csv_mapping` explicitly for preview; commit uses it when no mapping argument is supplied.
  - **Identity/commit:** `commit_import(session, source_key, body, *, settings, mode='csv', mapping=None, observed_for=None) -> CollectorRun` owns a dedicated session's commits and runs synchronously (P1-11 owns transport/Celery wiring). It creates a queued run with `trigger='csv'`, locks the source row until the capture commit, and checks `(source_id, sha256(original bytes), template_version)` **before** raw storage, adapter lookup or parsing. A repeat, including a multi-date file or a changed mapping/parser, finishes `skipped` with the original run/capture ids and no new raw object/row or observations. New files use DEC-061 storage, stamp template_version before commit, then enter `execute_run` with offline `csv`/`json` requests and import-scoped target evidence. Disabled/live-off sources remain importable. Failures are durable and sanitized; framework parse/upsert failures retain the original raw evidence. Row errors remain in run params; no imported entity data is copied into error messages.
  - **Time/JSON:** `captured_at` is UTC upload/import time, never a historical CSV date. Adapters use each row's `date`/`observed_for`, falling back to the capture's UTC date. Browser-saved Shopify JSON uses `shopify-json-v1`, validates UTF-8/JSON syntax and the size cap, and requires the owner's `observed_for: date`; source schema parsing remains P1-07's responsibility. Thus historical imports cannot satisfy a pre-import feature cutoff under DEC-031. Explicit `replay_import(session, raw_payload_id, *, settings) -> CollectorRun` requires a different parser_version from the original import, reuses the original capture/bytes/time/mapping/owner date, and appends through FW-3. Repeating a correction with the same new version remains idempotent through the observation key. Ordinary uploads always skip, even after a parser change.
  - **Adapter hook:** source modules register `ADAPTERS[source_key] = factory`, where `factory(ImportData) -> framework.Adapter[R]`. `ImportData.csv` holds validated CSV rows/errors; source-specific `parse()` consumes those rows, while JSON `parse(body)` consumes original bytes. Upsert alone maps records to observations and copies payload provenance/parser_version. No Shopify/CJ/Trends mapping is implemented here. `Row` values remain typed major-unit Decimal/date/bool/int/text; adapters use `to_minor` for DB money.
  - **Framework ownership exception:** the coordinator authorized the additive `Request.raw_payload_id: int | None` hook in P1-05 while P1-03b was unstarted. Offline reuse verifies source identity and a stored body, respects the wall-time budget, reads through `storage.read_capture`, and never stores another capture; live reuse is rejected before network. No other framework or storage behavior changes.
- **Alternatives:** deduping after S3 writes violates the repeat rule; including observed date/mapping/parser in identity duplicates evidence; a second upsert path loses framework transactions; inferred preview counts misstate updates; rewriting corrected observations loses history. Source factories and the additive request field reuse the existing pipeline with about 430 production lines including templates/validation and the hook.
- **Validation:** offline CSV fixtures and the real SQLAlchemy lifecycle/storage with SQLite plus fake S3 cover templates, BOM/mapping, exact money, invalid rows, caps, previews, versioned identity, duplicates, original timestamps and correction idempotency. Framework tests cover reuse, source mismatch, missing body and live rejection. The same import integration cases are PostgreSQL-marked; real PostgreSQL constraints/locking/UTC and real S3 remain unverified locally (no Docker).

### DEC-067 · Non-stop build
**2026-10-22 · approved by owner 2026-10-22** · extends DEC-049
- **Owner instruction (2026-10-22):** both agents should build the full website all the way through without stopping, keep refining it (features, tools, UI) and work non-stop. Capacity chosen by the owner: 5 workers, 3 Codex + 2 Claude.
- **Decision:**
  - Two Orca lead automations alternate every 15 minutes: "Pulso lead" (Claude, :00 and :30 UTC) and "Pulso lead · Codex" (:15 and :45). Both follow the vault note Agents/Lead Playbook; a lock in Agents/Lead State keeps one lead active at a time.
  - Up to 5 workers run at once (3 Codex + 2 Claude). When no phase task is ready, leads take next-phase tasks whose dependencies are met, then the vault Agents/Improvement Backlog, refilled by rotating audits (UX flow, visual polish, accessibility and performance, data connections, competitor feature gaps, code health, data quality). After Phase 8 the build stays in improvement mode.
  - This decision changes cadence and capacity only. It grants no new data or collector-host permissions: seed approval (DEC-011), the crawler contact and collector-host operations stay with the owner.
- **Alternatives:** hourly leads with 3 workers (DEC-049) — workers sat idle up to an hour between runs; a single lead provider — one usage limit would stop the build.
- **Why:** keeps both agents busy continuously and survives a usage limit on either plan.

### DEC-072 · Non-stop safety rails
**2026-10-22 · proposed (own-001)** · hardens DEC-067; amends DEC-023 and DEC-049
- **Decision:**
  - **Atomic lead lock.** `infra/scripts/lead_lock.py` (stdlib, tested): a directory created with one atomic `mkdir` at `C:\Users\Xody2\orca\workspaces\pulso\.lead-lock`, outside OneDrive and every worktree, with a heartbeat; a holder that stops beating for 20 minutes is stale. Each lead acquires it first, beats before every side effect and releases it at the end. The `lock:` line in the vault Lead State is a display copy only.
  - **A lead worktree per provider.** Claude leads run in `pulso-lead`, Codex leads in `pulso-lead-codex`; every git command uses `git -C <own lead worktree>` after checking `rev-parse --show-toplevel` (the automation's run context names `C:/dev/pulso`). `release_worktree.py` protects both lead worktrees and the lock directory.
  - **Protected paths.** The lead never auto-merges a branch touching AGENTS.md, CLAUDE.md, apps/web/AGENTS.md, `.github/`, `.gitignore`, `infra/seeds/`, the collector-host scripts or the SPEC amendment log, or adding "approved by owner", or relaxing AGENTS.md §3/§4 or a compliance decision (AGENTS.md §6).
  - **Batched cross-reviews.** One review by the other agent covers all risky merges (migrations, money math, auth, live-collector paths, CI) since the last one; dispatched at 3 risky merges or 2 hours.
  - **CI e2e smoke always runs** under the E2E auth bypass; only the real-Clerk sign-in check waits for secrets. Until now every e2e step was skipped without Clerk secrets.
  - **Repo is public** (owner, 2026-10-22). GitHub secret scanning, push protection and a "Protect main" ruleset (no deletion, no force-push) are on, per the owner.
  - DEC-049's "in the main checkout" for the lead now reads "in the lead worktrees".
- **Alternatives:** the lock as a line in a OneDrive-synced note — sync delay and conflict copies allow two leads at once; one shared lead worktree — one lead could reset the other's tree mid-merge; reviewing every merge — took 8 of 14 Phase 1 worker slots.
- **Why:** an adversarial review of the non-stop design (2026-10-22) found these as the ways two alternating leads and five workers could collide, widen their own permissions or ship untested UI.

### DEC-073 · Data collection approvals
**2026-10-22 · approved by owner 2026-10-22** · resolves DEC-011; authorizes Lead Playbook §6 steps 2–5; SPEC A-12
- **Owner's answers (2026-10-22, ticked explicitly in the owner's session):** "Seed list as drafted", "Crawler ID = repo URL", "Shopify test: 4 stores", "Lead runs collector host".
- **Decision:**
  - **Seeds:** the drafted list in the vault note Data/Seed Lists (30 competitor stores, 10 CJ categories, 50 US keywords) is approved as `seed_v1`. The owner's own store domains go in a gitignored `infra/seeds/private*` file, never in the public repo. The owner may edit or veto entries at any time; a changed list is a new seed version. A follow-up task re-verifies each store (live, US-shipping, actually selling) and proposes `seed_v2`.
  - **Crawler identity:** User-Agent `PulsoBot/0.1 (+https://github.com/CodySpooner/Pulso/blob/main/docs/BOT.md)`; `PULSO_BOT_CONTACT` is that URL. No email.
  - **Shopify test (SPK-2):** one run from the owner's home connection against sageandsill.com, meowingtons.com, thecloudies.com and bleame.com, at most 20 requests in total (DEC-003), stopping the whole run on the first 429/430/403.
  - **Collector host:** once Docker works, the lead may operate `C:\dev\pulso` only through the repo's collector scripts: `git pull --ff-only` on a clean checkout, start the collector project, back up then migrate, load approved seeds, enable approved sources one at a time after their fixture tests and the block-rule tests pass, and check Data Health. Never destructive (`down -v`, deleting volumes, databases, snapshots or raw payloads, downgrade migrations on the collector database). A file `C:\dev\pulso\.collector-hold` pauses all collector-host operations.
  - Accuracy first: official sources before anything else; no vendor-scraped data (DEC-010 stays pending owner).
- **Why:** the owner asked to start populating accurate, organic data, and approved each of the four steps needed for real collection.

### DEC-069 · Collector block accounting, durable Retry-After deadlines and request hook
**2026-10-22 · proposed (P1-03b)** · FW-4, R-08; P1-19 findings 1 and 5; task_c91c02fd57cf
- **Transactions:** the dedicated runner session uses `expire_on_commit=False`. Guard reads, before-request writes and attempt counts commit before fetch; source/run ids and the source key are bound before commit. S3 upload precedes response writes; committed payload attributes stay loaded for S3 download. No fetch, upload, download or retry sleep holds a database transaction. Storage and adapters still never commit.
- **Blocks:** live 403/429/430 responses increment the persisted consecutive count across runs; any other live response resets it, while imports and transport failures leave it unchanged. At the configured threshold (default 5), disable the enabled source, set blocked/reason/time, and append one `source_events(action='disable', actor='system')` in the capture transaction. Later disabled runs make no request or duplicate event. Every block response stops the entire plan as `RunDeferred`, ending partial under the existing status rules; it never proceeds to another target or retries the block within that run. This implements the P1-03b task's explicit stop rule over the older vault retry-once sketch. Source-specific fatal/quota exceptions remain adapter work; P1-04 supplies the existing per-source execution lock.
- **Deadlines:** `Response.headers` defaults to an empty mapping. For 403/429/430 and retryable 500/502/503/504, parse case-insensitive Retry-After as nonnegative integer seconds from receipt time or an HTTP-date in UTC; ignore malformed values. Persist the full deadline with that raw capture, never shortening an existing deadline. Every live attempt, including a later run, rechecks the deadline. Wait outside a transaction only when the remaining delay is within `collector_retry_wait_cap_seconds` (default/max 600) and the plan budget; otherwise stop partial. Valid server deadlines replace the 2/8/30 backoff for 5xx; absent/invalid headers retain that schedule. Expired deadlines remain historical evidence, not a request barrier.
- **Hook:** optional `execute_run(..., request_hook=...)` receives `(session, source, run, request, response)`: `response=None` before each live attempt, then the Response after its capture/deadline commit. Before-hook writes commit with the attempt count before fetch; after-hook writes commit separately, preserving raw/deadline evidence if the hook fails. No hook for offline capture/reuse or after a transport exception with no response. Hooks do database work, never commit or perform network calls; they may raise exported `RunDeferred` for quota exhaustion. P1-08/P1-09 can reserve quota here; no adapter uses it yet.
- **Alternatives / why:** holding transactions across I/O, clamping a server deadline, moving to another target after a block, or committing quota inside adapters violate the transaction, rate-limit or ownership contract. Existing columns/settings plus one callback suffice; no migration, dependency or live configuration change.
- **Validation:** 22 new offline cases use real SQLAlchemy/SQLite with fake HTTP/S3 and a fake clock; engine begin/commit/rollback listeners reproduce and prevent all three network transaction leaks (including recovery after rollback), and commit observers verify capture/deadline atomicity. Five-block/one-event, reset, HTTP-date/seconds, 503, cross-session later runs, configured caps/budgets and quota-before-fetch checks pass. Full lint/typecheck/tests pass (306 Python, 269 web; 60 DB skips). PostgreSQL and real S3 checks remain unverified locally (no Docker).

### DEC-068 · Data Health admin API: shapes, live-run guard, target freshness and the import split
**2026-10-22 · proposed (P1-11)** · DH-1; R-06; D2/D3; DEC-060/063/064/065; task_6f72c6eb5bcd
- **Decision:** `pulso_api.routers.admin` serves `/v1/admin/*` behind the existing `current_principal` allowlist dependency (non-allowlisted → 403 `not_allowlisted`); response models live in `pulso_api.schemas.admin`, and operation ids are the function names. `pulso-api` now declares the workspace package `pulso-sources` (no external dependency), so the API image ships the framework and seed guard.
  - **Sources:** `GET /sources` returns every `sources` row (a bounded registry, so no pagination) without `config`, plus the latest run by id with target counts, `freshness` = the latest `captured_at` of a `success` target in any run or scope (R-06: unchanged/304 counts; a later failed target never clears it; imports count at upload time), and seed state read only through `pulso_sources.seed_approval` (`seed_approved`, `approved_targets`; null without a seed list). No other config key is read, returned or logged. `quota_used`/`quota_limit` stay null until quota usage is persisted.
  - **Runs:** `GET /runs?source=&cursor=&limit=` is keyset-paginated by id, newest first (`limit` 1–200, default 50, `next_cursor`). `GET /runs/{id}` adds its targets with `raw_payload_id` only: no presigned URLs, and unpaginated while seed lists keep targets per run in the tens.
  - **Run now (D2/D3):** `POST /sources/{key}/run` answers 409 `collectors_live_off` unless `COLLECTORS_LIVE=on` outside a linked worktree (the same `is_linked_worktree` check as `fetch`), and 409 `source_disabled` for a disabled source. Otherwise `enqueue_run(trigger="manual")` commits the queued row, then calls the injectable `get_publisher` dependency, a no-op until P1-04 overrides it with Celery (until then the row stays queued). A publish exception becomes a 500 after the framework records `publish_failed`. `GET /host` exposes the same check as `live_runs_allowed` so the UI can disable the button.
  - **Toggle:** `PATCH /sources/{key}` accepts only `{enabled, reason?}` and appends one `source_events` row (actor = Pulso user id, action `enable`/`disable`). Enabling sets status `active` and clears the disabled fields; disabling sets `disabled` with the reason and time, but keeps a `blocked` status, and re-enabling a blocked source needs a non-blank reason (422 `reason_required`, §4.2). Block counters and Retry-After stay with P1-03b.
  - **Coverage/host:** `GET /coverage?days=90` (1–366) reads `source_daily_coverage` from UTC today − (days − 1) and excludes `sources.type = 'internal'` (the backup pseudo-source; its card reads `GET /runs?source=backup`). `GET /host` returns the latest heartbeat by `at` and unfilled gaps that start in the last 90 days, with null/empty when nothing exists.
  - **Imports → P1-11b:** the task's ~400-line rule splits the import endpoints to P1-11b (ready on local branch `CodySpooner/p1-11b-admin-imports`, one commit on this branch). Its contract: `GET /sources/{key}/import/template` (text/csv from `template_csv`), `POST /sources/{key}/import/preview` (CSV; validation-only through `parse_csv`, because no source has registered the read-only classifier `preview_csv` needs) and `POST /sources/{key}/import?mode=csv|json&observed_for=` (`commit_import`; a repeat returns its skipped run with `original_run_id`). Uploads are the raw file bytes as `application/octet-stream`, since FastAPI multipart needs the extra `python-multipart` dependency; the saved `config.csv_mapping` and P1-05 header auto-mapping apply. Responses carry the first 100 row errors with complete counts (P1-22 finding 4), and a non-UTF-8 file answers "Save the file as CSV UTF-8."
- **Alternatives:** the vault sketch's id-based paths and extra `data-health`/`gaps`/`backups` endpoints (the DH-1 task list supersedes it); a new admin dependency; returning sanitized config; run success or snapshot spacing as freshness; multipart through a new dependency; importing Celery in the router.
- **Why:** the smallest surface that lets P1-12 render the cockpit from real evidence while keeping D2, R-06 and the config/secrets boundary in one place.
- **Validation:** endpoint tests cover the 403 on every route, both D2 409s (live off; live on inside a worktree), the disabled 409, a queued manual run with its publish call, freshness surviving an unrelated target failure, pagination and run detail, toggle events and the blocked-reason rule, internal-source coverage exclusion, and host nulls/gaps. They run offline on SQLite (a plain table stands in for the view) and again under the `db` marker on Postgres, which is unverified locally (no Docker).

### DEC-070 · Raw request sanitization and portable capture reads
**2026-10-22 · proposed (P1-20)** · P1-18 findings 1–6, 8; P1-19 finding 9; amends DEC-061
- **Decision:** replace DEC-061's exact credential-name list with a conservative pattern after case folding and separator removal: names containing `token`, `secret`, `password`, `passwd`, `auth`, `signature`, `credential`, `cookie` or `session`; names ending in `key` or `keyid`; and exact `bearer`, `sid` or `sig`. Apply it to nested maps, list-of-pairs headers, decoded query names and form-encoded strings under `body`/`data`/`form` (plus `query`/`query_string`). Prefer dropping harmless metadata to retaining a credential. Adapters still supply structured metadata, never opaque credential blobs or authentication responses as raw captures.
- **Fidelity:** sanitize absolute URLs with a scheme and host, or strings under URL-named keys (including relative URLs). Strip userinfo and secret query/fragment segments, preserving the original encoding of safe segments. Ordinary strings and secret-free URLs, including safe fragments and empty delimiters, stay byte-identical; this replaces DEC-061's unconditional fragment removal.
- **Storage:** retain the public capture signature, but validate `source_id` against `Source.key` without autoflush before upload; missing or mismatched identities fail, so a caller cannot evade DEC-037 by changing the supplied key. Reject Content-Type longer than 200 characters before upload rather than truncate evidence. Retry `ConditionalRequestConflict` once; a successful PUT or `PreconditionFailed`/412 permits the new capture row, while another failure propagates without one. Read gzip only when the returned bytes have its magic prefix, then verify SHA-256 in either case. Original response bodies that themselves contain gzip still fail loudly if a provider decodes the outer gzip and the remaining layer is mistaken for it; connected provider checks remain required.
- **Readiness:** `make_client(settings, *, config=None)` merges an optional botocore config into path-style SigV4 defaults. Only `/readyz` requests `connect_timeout=2`, `read_timeout=2`, `retries={"max_attempts": 1}` (one retry after the initial request); ordinary storage clients keep their existing timeouts.
- **Alternatives:** extending the exact-name list leaves new credential names exposed; re-encoding safe URLs changes evidence; trusting a caller's source key bypasses the AliExpress guard; treating 409 alone as success can create a row before an object exists. No schema change, dependency or new storage abstraction is needed.
- **Validation:** regression cases reproduce the review failures before the fixes; real botocore Stubber covers both gzip/decoded GETs, both 412 error names and 409 followed by 412 or successful PUT. `pnpm lint`, `pnpm typecheck`, `pnpm test` pass (315 Python passed, 60 DB skips; 269 web passed). PostgreSQL and real RustFS/R2 round trips remain unverified locally (no Docker); no live network or real S3 calls were made.

### DEC-075 · Reject import mappings changed by metadata sanitization
**2026-10-22 · proposed (P1-24)** · P1-22 finding 3 and alert A2; supplements DEC-064/070
- **Decision:** treat a top-level request `mapping` as replay-critical metadata. Apply the existing recursive credential sanitizer to the entire request; if the resulting mapping differs from the supplied mapping, `store_capture` raises a value-free `ValueError` before S3 upload or capture insertion/flush. The import service's existing failure handler records the failed run, with no durable raw capture or observation. The owner must rename credential-like CSV headers before uploading again. No mapping subtree bypasses sanitization, and this guard does not validate or grant trust to mapping content.
- **Boundary:** the existing import parser still validates used header-to-template-column destinations before calling storage. Safe mappings such as `Query -> keyword` survive exactly and replay from the original capture after source configuration changes. `Key`, `Token`, `Signature`, `Author` and `Search Key` mapped to `keyword` now fail during upload, for both explicit mappings and saved source mappings, instead of silently committing an unreplayable capture. Other request/response metadata retains DEC-070 redaction. Existing capture history is untouched.
- **Alternatives:** a narrowly validated metadata interface could preserve credential-shaped header labels, but requires another trust boundary and coordinated import-service changes; a blanket `mapping` exemption would store arbitrary untrusted credentials. Early rejection satisfies the replay contract with three storage lines and no service patch or new dependency.
- **Validation:** a new isolated import test module uses the existing real SQLAlchemy commit/replay path on offline SQLite and fake S3. It reproduces 11 failures before the guard, checks all six requested labels, both mapping inputs, unchanged successful replay, invalid destinations, no S3/capture/observation writes on rejection and arbitrary nested credential redaction. PostgreSQL variants remain unverified locally (no Docker).

### DEC-076 · Seed revision ordering and stored-target validation
**2026-10-22 · proposed (P1-25)** · P1-22 findings 6–9 and 15 (seeds); extends DEC-065 validation
- **Decision:** compare the integer suffix of `seed_vN` before staging any changes; an older revision fails in preview and apply, equal-version mutations still fail, and identical repeats remain no-ops. Reject duplicate JSON object keys at every depth before opening a database session.
- **Stored targets:** the loader and `approved_targets` share the existing per-section field, domain, duplicate and US/UTC validation. If any stored entry is invalid, the source returns no targets; normalized copies leave stored config unchanged. Approval dates must be strict `YYYY-MM-DD` and no later than the current UTC date.
- **Evidence:** a test checks any approved shipped seed against the existing DEC-011 index/entry and DEC-073 status, date and version evidence. This task changes no approval metadata, seed files, source flags or unrelated config; runtime eligibility remains additional to all existing source/live/workspace guards.
- **Alternatives:** silently accept older files, keep separate validators, or skip only malformed rows. Rejecting the whole section avoids silently collecting a partial list, and sharing the validator keeps file and stored-config checks consistent without a dependency or migration.
- **Why:** stale revisions must not restore removed targets, ambiguous JSON must not override a visible flag, and config written outside the loader must pass the same validation before use.

### DEC-071 · Observation ordering and one entity per import file
**2026-10-22 · proposed (P1-03c)** · task_61ae52bf8c8a; P1-19 findings 2, 3a, 3b and lead decision 3c; DEC-031/060/063/064
- **Decision:** `observed_for` does **not** join listing/variant/freight observation identity; `0002` stays unchanged. Multi-date history for the same entity in one file is deferred in BACKLOG. FX keeps its adapter-owned first-rate exception.
- **Ordering:** `effective_observation(..., before=(captured_at, raw_payload_id))` accepts an exclusive capture bound. Listing/variant change-only comparisons use this bound, so a later capture cannot suppress an earlier replay or out-of-order append. Among eligible captures, effective rows order by `observed_for DESC`, then `captured_at`, `raw_payload_id` and `id` descending; a September import received after an October live row stays historical and cannot replace the live baseline. An explicit raw id still selects greatest row id, never parser-label order. Historical feature readers must still enforce DEC-031's capture-time cutoff; observed date never authorizes pre-import features.
- **Import validation:** the existing Shopify and CJ templates can emit listing/variant/freight observations, so more than one valid row for a Shopify `(store_domain, product_url)`, or sharing either CJ `cj_product_id` or `sku`, rejects the entire file even when dates agree or are absent. Identifier strings retain existing exact-value semantics; no new URL/entity resolver is introduced. `parse_csv` raises `DuplicateEntityRows(ValueError)` with row-level `.errors`; every conflicting row names another row, without copying entity values. `preview_csv` returns no candidate rows, zero write counts and the errors without calling the classifier. Commit/replay record a failed run with durable `params.errors`; new rejected files never reach adapter lookup or raw storage. Ordinary repeat uploads retain their pre-parse identity skip. Nonduplicate files keep existing row-validation behavior; multi-date Search Trends remains valid because its observation key includes the date.
- **Alternatives:** adding observed date to database keys requires a separate history-import contract; accepting the first duplicate silently loses later rows; comparing with the newest capture overall loses corrected historical changes; capture-time-only current ordering promotes old imports over live facts.
- **Validation:** review probes 1–3 failed on the original code and pass offline on SQLite/fake S3, alongside equal-time capture bounds, out-of-order insertion, same-parser idempotency, parser correction, CJ alternate identifiers and distinct entities. `pnpm lint`, `pnpm typecheck`, `pnpm test` pass (294 Python, 269 Vitest; 62 database skips). DB-marked PostgreSQL constraints/locking tests remain unverified locally (no Docker); no live network, migration, dependency, scheduler, collector-host or deployment changes.

### DEC-074 · CSV quoting, entity consistency and capture-date validation
**2026-10-22 · proposed (P1-23)** · task_f716b31522a7; P1-22 alert A1 and findings 1, 4, 5, 12, 15 (covered cases), 16 (CSV note)
- **Decision:** supersede DEC-071's overly broad import-file rule without changing observation identities or its capture/observed-date ordering. Shopify rows share `(store_domain, product_url)` with consistent `title`, `currency` and effective observed date, but distinct `sku` (fallback `variant_title`) values are allowed with their own prices, compare-at prices and availability. Repeated variant identities reject the file. Adapters aggregate listing snapshots across variants once per capture, as in the source contract.
- **CJ:** group listings by `cj_product_id`, falling back to SKU; a supplied product id elsewhere in the file resolves a SKU-only row. Shared `name`, `currency`, `moq` (default 1) and effective observed date must agree; each product/SKU has one `unit_cost`, while `(product, sku, warehouse_country)` freight rows can differ in shipping price/days. Repeated freight identities, inconsistent listing/variant fields or a SKU assigned to different product ids reject the file before adapter lookup/storage, naming conflicting row numbers. Different product ids and SKU-only identifiers remain separate namespaces. This is file-local consistency, not database entity matching or URL normalization; history imports for multiple dates of the same entity remain deferred.
- **CSV:** sniff only the delimiter; the reader keeps Excel's double-quote semantics for comma/semicolon, including quoted headers and multiline fields. Missing required non-defaulted headers, including CJ's product-id-or-SKU requirement, fail before row parsing. No template-version bump or new dependency.
- **Dates:** `parse_csv` and `preview_csv` add optional `as_of: date`, defaulting to today's UTC date for existing callers. New imports bind one UTC capture time before validation and store that same timestamp; replay validates against the original capture's UTC date. Future CSV dates are row errors, future Shopify JSON owner dates raise `ValueError`. Missing CSV dates retain the capture-date fallback. Zero-valid-row CSV runs fail with `no_valid_rows` and retain the committed raw evidence; mixed files still import valid rows. No new date floor or historical rewrite.
- **Errors:** keep `DuplicateEntityRows(ValueError)`, full in-memory row errors and the `(row, column, message)` shape. Persist only the first 100 in `params.errors`, with full `error_count`, `invalid_rows` and `errors_by_column`; P1-11b's existing errors reader remains compatible. Reconstructing an invalid-row download must pass the raw capture date to `parse_csv`. Retry, source-lock duration, file-level CSV default dates, old-template replay and richer header-inspection work remain deferred; P1-24 owns sanitizer/mapping safety.
- **Alternatives:** rejecting every repeated product blocks ordinary variants/warehouses; accepting inconsistent shared fields lets database uniqueness silently discard facts; sniffed quote semantics corrupt inch marks; today's replay date legalizes formerly future data; unbounded persisted errors inflate run queries and backups.
- **Validation:** original-code regressions reproduced quoted-field corruption, rejected valid variants/warehouses, absent date bounds and unbounded error samples. Writer round trips (both delimiters/quoting modes), entity consistency, capture-date/replay checks and 100,000-row invalid/duplicate files pass offline; stored error params stay below 64 KiB. SQL execution retains one listing, two variants and two warehouse quotes once per capture. After rebasing onto `a3a209c` (P1-03b/11/20/24), `pnpm lint`, `pnpm typecheck`, `pnpm test` pass (411 Python, 269 Vitest, 92 DB skips); DB-marked checks remain unverified locally (no Docker).

### DEC-077 · Bounded Shopify probe and public bot page
**2026-10-22 · proposed (data-01)** · task_58e55e18a090; applies DEC-003 and DEC-073 to the DEC-052 probe
- **Decision:**
  - **Budget:** `infra/scripts/spikes/shopify_probe.py` takes `--max-requests` (default 20, allowed 1–50). It is one budget for the whole run. Every request sent counts: robots.txt, the catalog, its conditional repeat, `/meta.json`, product `.js` and transport failures. Redirects are never followed, so each redirect response is one counted request and its target is never fetched. 50 is DEC-052's old fixed cap; the flag can only lower it.
  - **Blocks:** the first 429, 430 or 403 on any request stops the whole run, not just that store, with no retry. Password pages and transport errors still stop only that store, as before.
  - **Report:** the header records requests used out of the budget, stores reached, the stop reason (finished, budget spent before the next request, or the blocking status and URL) and stores not reached. Rows already observed are kept. A missing `--out` directory is refused before any request. A `304` row is no longer labelled "redirect not followed"; only a 3xx with a `Location` header is.
  - **Bot page:** `docs/BOT.md` is the public page behind DEC-073's User-Agent link. It says what Pulso is, what it fetches, the ≤ 30/min global limit, the robots.txt handling, the block behaviour and opt-out by GitHub issue or robots.txt.
  - **SPK-2 command:** documented once in the Shopify section of `docs/DATA_SOURCES.md` for the four DEC-073 stores with `--max-requests 20`, writing to `C:/Users/Xody2/orca/workspaces/pulso/spike-SPK-2.md`. This task does not run it; the lead runs it under Lead Playbook §6 step 2.
- **Alternatives:** an unbounded `--max-requests`, which would relax DEC-052's fixed cap; stopping only the blocked store (DEC-052), which keeps sending requests after the first sign of rate limiting and breaks DEC-073; following redirects and counting each hop, which spends budget on other hosts.
- **Why:** DEC-073 allows one test of at most 20 requests that stops entirely at the first block. The cap and the stop have to live in the script, not in the operator's care, and the report has to say why a partial run ended.

### DEC-090 · SPK-3 — Shopify crawler go/no-go after SPK-2
**2026-10-22 · proposed (data-04)** · task_48353588040b; SPK-3; evidence: the SPK-2 report `C:\Users\Xody2\orca\workspaces\pulso\spike-SPK-2.md`, summarized in `docs/DATA_SOURCES.md` (Shopify, "SPK-2 results (2026-10-22)"); builds on DEC-003, DEC-033, DEC-069, DEC-073 and DEC-077
- **Decision:** a **conditional go**. Work on the `shopify_stores` adapter continues toward enabling, but enabling stays gated on all five conditions below. Each one is built into the adapter and covered by a fixture test before the flag can turn on.
  - **(a) Per-store spacing.** Requests to the same store are spaced well above 3 s. A store's `Retry-After`, and any robots.txt crawl delay, set a minimum that is never shortened. The global cap of ≤ 30 requests/min (DEC-033) still applies on top. The adapter task sets and tests the exact interval.
  - **(b) No repeated URL in a run.** A run never requests the same URL twice. Conditional requests use the ETag stored by an earlier run (`If-None-Match`, DEC-033), so 304s come from repeats across runs, never within one run.
  - **(c) robots.txt redirects.** A robots.txt response that redirects to another host is not followed. That store is skipped for the run and logged to Data Health.
  - **(d) Stop on the first block, unchanged.** DEC-069 applies as written: the first 429, 430 or 403 stops the whole run with no retry and no further stores. Consecutive blocks count across runs toward auto-disable, and a 430 disables the source at once.
  - **(e) No inventory-based labels.** The Grade A demand-label family (`.js` `inventory_quantity` deltas) counts as unavailable for these stores. The adapter still stores the fields if a store exposes them. MSR-1's coverage memo decides the label source later.
  - **This enables nothing.** `shopify_stores` stays off. To enable it, every Lead Playbook §6 step 4 condition must hold: P1-03b block tests, `parse()` fixture tests and the 30/min limiter test, `approved_targets()` entries, SPK-2 results in `docs/DATA_SOURCES.md` and this entry on `main`. Conditions (a)–(e) must be met as well, and the owner must give the go. SPK-2 stays a single run and is not repeated. This entry does not relax DEC-003, DEC-033, DEC-069, DEC-073 or AGENTS.md §3/§4.
- **Alternatives:**
  - **No-go:** keep the source off and rely on CSV/URL paste only. Rejected: three of the four stores served public `/products.json`, conditional requests returned 304 on both stores where the repeat got a normal answer, and `/meta.json` returned USD. The only 429 came on a repeat of the same URL sent at the probe's minimum 3 s spacing, a pattern conditions (a) and (b) remove. A no-go would give up the best free store signal on evidence that points at the request pattern, not at a blanket block. The CSV fallback stays either way.
  - **Go without conditions:** enable once the fixture gates pass, keeping the probe's request pattern. Rejected: one of the three catalog repeats drew a 429 at the probe's 3 s minimum spacing, and in a scheduled run that would trip the DEC-069 stop and move the source toward auto-disable. The robots.txt 301 needs a defined handling. `inventory_quantity` was absent on every public-JSON row, so a design that assumes Grade A labels would be built on a field these stores don't expose.
- **Why:** the evidence comes from one run of 14 requests to four stores, small but direct:
  - public JSON and working ETags on the stores that were reached;
  - one 429 with `Retry-After: 60` on bleame's same-URL repeat (probe spacing ≥ 3 s), at which the run stopped as DEC-069/DEC-077 require;
  - one robots.txt 301 (meowingtons), not followed;
  - no `inventory_quantity` anywhere.

  The conditions are cheap, change none of the compliance rules and only make the adapter politer than the probe. The owner can veto them or make them stricter.

### DEC-088 · Frankfurter gap recovery, first-rate evidence and explicit FX rounding
**2026-10-22 · proposed (P1-09)** · FX-1, DOC-1 FX; DEC-031/051/060/063/069/071/074; D4
- **Decision:** preserve the existing first-rate primary key without migration, as clarified by the coordinator. Fresh fetches keep separate raw captures; existing rates are never updated/deleted. Conflicts emit one `fx_conflict` source event per raw capture/parser, pointing to the retained raw evidence; replay adds neither rates nor duplicate events. Manual CSV rates use `source=manual` through the existing import service, with positive NUMERIC(18,8) validation.
- **Plan:** USD base and the seven non-USD currencies already supported by the currency table. Daily requests backfill from the slowest pair's latest stored date plus one through yesterday, then fetch latest. They share one target so failed backfills stop latest from hiding a gap. Initial history starts 2025-01-01 (working default from the source note); explicit range backfills remain available. No dates are fabricated for weekends/holidays or missing provider data.
- **Read/conversion:** `rate_as_of(session, quote, day, source=...)` selects the latest observed date on/before day among captures strictly before day+1 UTC. The returned row retains provenance; absent history returns None. `convert_minor` takes a Decimal quote/base rate and requires an explicit rounding mode, checks BIGINT boundaries, and rounds only the destination amount; exact `to_minor` stays unchanged.
- **Alternatives:** a per-capture FX migration contradicts the existing exception; newest-capture-only ordering promotes old backfills; latest-first requests hide failed backfills; implicit rounding or floats lose money precision. Reuse the standard-library HTTPS transport and existing settings, framework retries/blocks and import service; no new dependency, environment variable, enablement or compliance policy.
- **Scope:** FX ships first; TRD-1 and DOC-1 Trends are left for P1-09b under the dispatch size rule. Public Frankfurter docs/terms were checked 2026-10-22 (DATA_SOURCES); all payload execution uses synthetic fixtures only. Scheduler wiring belongs to P1-04 and must pass `FX_WALL_TIME_SECONDS` into `execute_run`.

### DEC-092 · Import retry: a capture with no successful run is re-run on upload
**2026-10-22 · proposed (P1-29)** · P1-22 finding 2; amends DEC-064 "Identity/commit"; D3; DEC-060/063/074/075
- **Decision:** the `(source_id, sha256, template_version)` identity check stays first, under the source row lock. When it matches a capture, `commit_import` decides in this order:
  - **Imported:** if any `collector_run_targets` row for that `raw_payload_id` is `success` (the first upload, a retry or a replay), the run is `skipped` with `params = {raw_payload_id, original_run_id}`, where `original_run_id` is the lowest run id with that success target. No parsing, adapter lookup or S3, as before.
  - **In progress:** otherwise, if a `queued`/`running` run is linked to the capture (the run that stored it, or a run whose `params.raw_payload_id` is that capture), the run is `skipped` with the same keys plus `reason: "in_progress"`. Nothing is duplicated. This is D3's rule applied per capture: runs are claimed only from `queued`, and a finished run is never re-executed.
  - **Retry:** otherwise the new run commits `params.raw_payload_id` (so concurrent uploads see it as in progress once the lock drops), then rebuilds the import from the capture's own bytes, capture date and stored `mode`/`mapping`/`observed_for` (the replay path), and executes through `Request(raw_payload_id=…)` with the current adapter. No second capture or S3 PUT. Rows already written dedupe on `(key, raw_payload_id, parser_version)`, so a retry after a partial write is idempotent.
- **Unchanged:** `replay_import` still requires a different `parser_version` (DEC-064). A changed mapping, parser or owner date on a re-upload still does not change identity; the retry uses the capture's stored mapping and date, so provenance and later replays stay consistent. An all-invalid capture (`no_valid_rows`, DEC-074) is re-run too and fails again with the same errors.
- **Limit:** a worker killed while its run is `queued`/`running` blocks retries of that capture until abandoned-run recovery (P1-04, DEC-063) ends the run; the re-upload says `in_progress` meanwhile, not "already imported".
- **Alternatives:** keep skipping and require a parser bump (the reported dead end); let `replay_import` accept the same version when nothing succeeded (the wizard re-upload path still skips); return the in-flight run instead of a skipped one (the caller's new queued run would then be orphaned); a `retry_of` column (needs a migration).
- **Validation:** offline SQLite + fake S3: a parse that fails once, then a re-upload → `success` with rows and one capture, then a third upload → `skipped` pointing at the retry; replay with the same parser_version → `failed`; a capture whose run never left `queued` → `skipped`/`in_progress`, and after that run ends a retry queues, then the next upload is `in_progress` against the retry. The PostgreSQL `params ->> 'raw_payload_id'` cast and the DB-marked concurrency test are unverified locally (no Docker).

### DEC-089 · Queued publishing and guarded Beat
**2026-10-22 · proposed (P1-04)** · task_62006dc470bb; SCH-1/SCH-2, D1/D3, P1-19 findings 7/10, P1-26 I1
- **Decision:** six UTC crontabs call the existing queued-before-publish lifecycle, with job/date or ISO-week slots, source-enabled gating and queued/running/successful-slot suppression. `collect.run(run_id)` uses the per-source advisory lock and `execute_run`; source lanes register plan factories with their adapter, targets, cooperative budget and optional request hook. Missing registrations fail closed. Collect concurrency defaults to one, with the existing in-process limiter owned by each source adapter; `ops` routes and a separate consumer command are ready, but its tasks remain SCH-4 work.
- **Beat lock:** on `beat_init`, acquire a dedicated, detached PostgreSQL session with the two-int key `(0x50554C53, 0)` in the configured application database; source execution uses the same namespace and the source id. Every tick checks ownership in `pg_locks` on that same session, before scheduling, with at most five seconds between ticks. Loss stops Beat; a second Beat exits non-zero. This follows DEC-002's database-scoped detail; the vault's maintenance-database sketch is superseded. Source and worktree flags remain off. No source row `FOR UPDATE` is added.
- **Publishing:** bypass Celery Beat's eagerly connected producer because its error handler includes broker exception text. The scheduler's `enqueue_run` boundary logs only the exception class. With coordinator permission, the API declares the already-locked `celery[redis]` dependency and overrides `get_publisher` at application construction, keeping P1-27's redaction wrapper. It sends only the run id, explicitly to `collect`, with broker retry disabled; the generated lockfile adds no package/version. Worker/ML packages stay out of the API image.
- **Limits:** `execute_run(stop_exceptions=...)` stops remaining targets on the Celery soft limit without importing Celery into sources. Settings enforce all five wall-time budgets < soft limit < hard limit and backoff base ? cap. Schedule/catch-up enqueue without a slot now raises before any write or publish.
- **Size split:** core code, integration and regression coverage already exceed the roughly 400-line target. As allowed by the task, SCH-4 remains a follow-up: heartbeat, overdue/gap audit, exactly one catch-up, stale queued/running reconciliation only while the source lock is free, and retry/recovery of contended queued delivery. These are required before live rollout; no catch-up or ops task is claimed complete here.
- **Alternatives / why:** an outbox, RedBeat, a second API entry point, importing worker/ML code in the API, or duplicating collection lifecycle logic adds dependencies or competing contracts. Existing Celery, SQLAlchemy and framework primitives suffice; no schema, service, host or compliance change.

### DEC-087 · Shopify catalog evidence, conservative cache and store exclusions
**2026-10-22 · proposed (P1-07)** · SHP-1/2, P1-19 finding 8, data-03 item 2; supplements DEC-033/063/069
- **Plan and identity:** `pulso_sources.shopify_stores.collect(session, run_id, settings=...)` runs under the worker's existing per-source lock. It intersects `approved_targets` with workspace-tracked stores and records one `shopify_catalog` target per active domain. Qualification (`/meta.json`) precedes every catalog; pages use `limit=250` and end only at a validated page with fewer than 250 products. Only that store's successful target permits delisting; a failed store never invalidates another successful catalog. Mutable listing metadata records sightings; snapshots use the framework's append-only, change-only helper with currency included in the value hash. Feature names remain `shopify_*`; no velocity is calculated.
- **ETags (P1-19 finding 8):** never cache or send a page ETag before its parse/upsert commits and its target ends `success`. Reuse the existing raw captures joined to successful catalog targets, partitioned by exact URL, instead of a second Redis cache. This deliberately withholds all of a store's new page ETags when any later page fails. A 304 requires such a cached body and the sent ETag; its validated product IDs count as seen, advance target/listing freshness and add no snapshots. Currency changes suppress conditional requests. Unsolicited 304s cannot make a catalog complete.
- **Pacing and robots:** obey `shopify_requests_per_minute` (maximum 30 globally), additionally space requests to one store by at least 10 seconds, and honor a larger robots delay/request interval. Process-local clocks survive adapter instances on the single consumer; DEC-069 owns the persisted Retry-After floor across runs. Each exact URL is requested at most once per run, including transport failures: Shopify runs disable the framework's same-run retries, with a duplicate-URL guard as a second check. Cache successful robots bodies for seven days; use Python 3.14's robots parser, including wildcards, and never follow redirects (same-host or cross-host). Unavailable robots fail that store's target. The shared live/worktree guard, configured timeout and settings User-Agent remain in force; no proxy environment is used.
- **Known blocks and untrackable stores (data-03 item 2):** a newly observed 403 still stops the entire current run under DEC-069, and also persists `stores.status='blocked'`. Later plans omit HTTP for all non-active stores and retain `shopify_excluded` targets labelled with domain/status for Data Health. The recorded pre-check 403 for `inspireuplift.com` initializes that exclusion if it ever enters the approved tracked set; no probe is repeated. Password/HTML storefronts and 402/404 catalog/qualification responses persist `untrackable`; robots redirects exclude only this run. No automatic reactivation. A single 430 disables the source with one source event; five consecutive 429s retain the framework threshold. These exclusions do not weaken stop-on-first-block behavior.
- **Alternatives and why:** response-time ETag caching can turn failed ingestion into false coverage; run-wide delisting loses store isolation; automatically retrying a known 403 repeatedly stops every run; 3-second same-URL repeats already produced a 429 in SPK-2. Existing tables, settings, storage and stdlib HTTP/robots suffice without a migration or dependency.
- **Split:** SHP-3 `.js` panel collection is deferred under the task's size allowance (default remains 10 approved tracked products/store). Catalog variant inventory stays null, never zero. The source stays disabled; worker registration, source import mapping/registration and connected-service validation remain integration work before enablement. No seed, environment, collector-host, terms-policy or protected-file changes.

### DEC-093 · History-import change-only ordering and block stop on hook errors
**2026-10-22 · proposed (P1-30)** · P1-28 review findings 1–2; task_25eef67f7358
- **Ordering (amends DEC-071):** `effective_observation(..., before=(observed_for, captured_at, raw_payload_id))` uses an exclusive three-column row comparison matching the effective ordering. Listing/variant change-only comparisons pass the new row's three values, so a later observed fact cannot suppress an earlier historical import or mis-date its change. Current rows still order by observed date, capture time, raw id and row id descending; explicit raw-id reads still select greatest row id. Observation identity, parser replay and DEC-031's separate capture-time cutoff are unchanged.
- **Hook (adds to DEC-069's Hook bullet):** if the after-response hook or its commit raises on a 403/429/430, roll back its transaction and raise `RunDeferred(f"http_{code}")` chained from that exception, preserving committed raw/block/deadline evidence and stopping the remaining plan.
- **Alternatives / why:** capture-only bounds can compare imported history with its future; propagating an ordinary hook error lets the next target fetch after a block. Aligning the bound and retaining the existing stop signal fixes both without a migration, unique-key change or dependency. Non-block hook errors still propagate unchanged.
- **Validation:** O1/O2 and L1 (also 403/430) fail against `origin/main` `71a8b7b` and pass with these changes. Tests retain skipped-capture correction, historical-current ordering and a non-block hook-error control, and verify hook rollback with committed capture/block evidence. PostgreSQL and real S3 checks remain unverified locally (no Docker). Merge before any import adapter registers in `ADAPTERS` or P1-08/P1-09 passes `request_hook`.

### DEC-095 · CJ fixture slice, point reservations and remaining live integration
**2026-10-22 · proposed (task_023bec3662b4)** · P1-08; DEC-009/035/063/069/071
- **Decision:** ship a disabled fixture slice under `pulso_sources.cj`: response-expiry authentication/refresh state, `listV2` panels (10 listing-count, 2 newest, 3 US-inventory pages per resolved category, size 100), pure parsing and append-only listing observations through the existing framework. Preserve missing listing count as null; it is adoption/listing activity, never orders. Each panel has its own target scope; no complete-catalog or delisting claim. Auth tokens remain SecretStr values in memory and never enter raw captures. Production HTTP refuses calls until the follow-up; no source or import registration is added.
- **Budget:** reserve 50 points per catalog attempt using the existing source JSON config (`cj_points.day/reserved`) under its row lock, and add run-local `cj_points_reserved`; the before-request hook lets the framework commit before HTTP. No refunds on uncertain attempts. UTC rollover resets the local counter. The dry run includes proposed later detail/stock/freight costs: ten categories plus 300 tracked products (two calls each) plus 300 total freight quotes = 16,500 points. This is an upper-bound plan, not measured CJ usage; it corrects the earlier double-endpoint undercount.
- **Errors / dependency:** this slice passes `request_hook`, requiring P1-30 (`0aee328`) before integration. The after-hook stores no DB state; it stops via `RunDeferred`, then the CJ entry point records the safe specific Data Health code/message and disables once for inactivity/IP-limit failures. Raw evidence and generic HTTP block accounting remain the framework's responsibility. The coordinator directed retention of generic points-429 block accounting for this slice. This is an implementation limitation against the intended quota exemption, not a compliance-policy change: the local cap does not prevent all provider quota errors, because refill timing/other account use are unknown. An explicit quota exemption needs separate framework work and review.
- **Split / alternatives:** full HTTP pacing, Redis auth cache, reactive token rejection retry, category-tree resolution of name-only seeds, tracked product/stock and US freight, provider-refill pacing, account countdown and CSV registration remain P1-08b. The existing CJ CSV template fits cost/freight but lacks stock; no second template or migration is introduced. Prefer this testable slice over speculative account behavior, fake category IDs or a framework fork. Public terms evidence is in DATA_SOURCES; owner review remains required before enablement.
- **Verification:** handwritten auth/refresh/catalog/error fixtures, fake-clock refresh, exact USD ranges, null counts, raw/target/snapshot replay and parser correction, persisted cross-session quota/reset, mocked live-hook reservations and distinct Data Health errors. PostgreSQL locks/constraints and connected services remain unverified locally (no Docker); no CJ API, collector-host, scheduler, account, secret, deployment or migration operation was performed.

### DEC-102 · Railway site-only deploy: Hobby, Railway Bucket, no Docker cache mounts
**2026-10-22 · proposed (railway-site; the owner chose scope, plan and storage in chat on 2026-10-22, sign-off pending)** · DEC-001, DEC-002, DEC-014, DEC-015
- **Decision:**
  - **Scope:** Railway project `pulso` runs web, api, Postgres (the pinned pgvector image, `dynamic_shared_memory_type=mmap` start command, volume at `/var/lib/postgresql`), Redis (Railway template) and one Railway Bucket. Worker, Beat and pg-backup are not deployed. `PULSO_SCHEDULER=off` and `COLLECTORS_LIVE=off` on Railway; the home PC stays the collector host, and the DEC-002 cutover has not started.
  - **Plan:** Hobby. Pro is chosen at full go-live, when snapshot tables outgrow Hobby's 5 GB volume cap.
  - **Object storage:** the Railway Bucket `raw` (region sjc) replaces R2 for this deploy, amending DEC-014's alternatives. The R2 backup target with 35-day lifecycle (DEC-015) is unchanged for go-live.
  - **Dockerfiles:** no BuildKit cache mounts. Railway's builder rejects a cache mount unless its id is `s/<service id>-<path>`, which would bind the images to one Railway project and break compose and CI.
  - **Wait for CI:** on for web and api, as DEC-014 says (GitHub Actions runs again since the repo went public).
  - **Config:** service settings are dashboard state, applied through `railway environment edit` (no `railway.json` or `railway.toml`). Connection values are Railway variable references, the Postgres password comes from a Railway `secret()` generator, and the owner enters the Clerk keys.
  - **Postgres start command:** `docker-entrypoint.sh postgres -c dynamic_shared_memory_type=mmap`. A Railway start command replaces the image entrypoint, so a bare `postgres` runs as root and refuses to start.
- **Alternatives:** service-id cache mounts per Railway service; R2 now; Pro now; full go-live.
- **Why:** the owner wants the site viewable before the collector cutover, with one vendor and no new account for storage. Removing the cache mounts is the only builder fix that keeps one Dockerfile per image across Railway, compose and CI.
- **Consequences:** slower image rebuilds without the uv and pnpm caches. The bucket has no lifecycle rules. Hobby's included usage is shared with the owner's other Railway projects.

### DEC-098 · Ops recovery and worker adapter registration
**2026-10-23 · proposed (task_c2e2b3a6384b)** · P1-04b; SCH-4, D1/D3; DEC-063/069/087/088/089/093
- **Recovery:** the separate `ops` consumer persists a hostname/UTC heartbeat every five minutes and audits every fifteen minutes. Its startup requests a heartbeat; Beat startup requests an audit. Heartbeat processing audits before advancing the watermark, so an outage is not lost when heartbeat and audit deliveries arrive in either order. A dedicated advisory key `-1` serializes ops window processing, separate from Beat `0` and positive source IDs. No external healthcheck ping is added.
- **Evidence:** a heartbeat gap longer than fifteen minutes records one `host_offline` gap per missed scheduled slot without a complete successful run. Each gap spans that slot's UTC day, including weekly jobs; repeated audit is idempotent through the existing source/slot key. Source status becomes `overdue` while its most recent due job slots lack success; blocked/disabled sources are not re-enabled. Matching successful slots may link `filled_by_run_id`; this is display evidence and does not rewrite captures, observations or historical feature coverage. The latest heartbeat is global because the single host's ops container hostname can change on recreation.
- **Catch-up:** one earliest missing current-period job per enabled source, at most one catch-up per source per UTC day and at most one per slot, including failed attempts. Daily jobs catch up only today's due slot; weekly jobs may catch up later in the same ISO week. Queued/running rows suppress catch-up. Reconciliation and the catch-up decision hold the same source execution lock as collection; the scheduler also takes that lock before checking/enqueueing. Stale queued/running rows become `failed/abandoned`, `complete=false`, only with that lock free, after the greater of two hours or twice the source budget. Disabled sources can be reconciled but never caught up. A live lock prevents reconciliation and publication, while gap evidence can still be persisted.
- **Busy delivery:** persist `params.lock_retries` before republishing the same run ID with the existing task retry delay/cap (defaults: two retries fifteen minutes apart). Exhaustion conditionally ends only a queued row as `failed/source_lock_busy`; a delivery that has already started or finished is untouched. Retry publish failure records `failed/publish_failed`. Every schedule, catch-up, retry and ops publish boundary logs the exception class only, without exception text or traceback. A crash between commit and publish is covered by the stale-run audit, without an outbox.
- **Registration:** a worker startup import registers the existing Frankfurter adapter and `plan(session, utc_day)` with `fx_wall_time_seconds`; unsupported jobs and missing adapters fail closed. Registration changes no source row, live flag, network guard or seed approval.
- **Permitted size split:** SCH-4 plus FX already exceeds the approximately 400-line target. Per coordinator response to `msg_0a9e131d4435`, Shopify registration moves to P1-04c: extract its existing approved/tracked-store planning, successful-target cache, retry suppression and finalization, make `collect()` a thin wrapper, then register the identical worker path with its request hook. Existing Shopify tests must pass unchanged, with fixture equivalence between the registered path and `collect()`. No Shopify source code is duplicated or changed in P1-04b, and the missing registration still fails closed.
- **Alternatives / why:** a migration, outbox, external heartbeat service, repeated catch-up storms or replaying historical daily slots add scope or misrepresent missing history. Existing evidence tables, JSON run metadata, task retry settings and PostgreSQL locks suffice. Fixtures/SQLite/fakes verify the behavior; PostgreSQL lock execution remains unverified locally (no Docker), as do Redis transport and separate Linux consumers. No Beat or live collector is started.

### DEC-096 · Data Health UI: derived source states, nav badge rule, inline heatmap and contract gaps
**2026-10-22 · proposed (P1-12)** · task_39d407d94458; DH-2, DH-3, imp-001; builds on DEC-060 and DEC-068 and changes no API
- **Decision:**
  - **One display state per source**, derived in the web from `SourceHealth` and `HostHealth.open_gaps` by one pure function (`apps/web/src/components/data-health/model.ts`). First match wins: **Blocked** (`status = blocked`), **Disabled** (`enabled = false`), **Running** (last run queued or running), **Failing** (last run failed or blocked), **Overdue** (an unfilled gap for the source whose slot ended less than 24 h ago), **Partial** (last run partial, or success with `complete = false`), **Never run**, **Healthy**. The vault's Stale and Degraded need each source's expected interval, which DH-1 doesn't serve; Overdue (from the gap audit), Partial and Failing stand in until it does.
  - **DH-3 nav badge:** a red count of sources that are Blocked, Failing or Overdue, the internal backup source included. Nothing shows at zero, while loading or on error. Every admin query refetches every 5 minutes.
  - **Host and backup states:** the host is online up to 15 min after its last heartbeat, late up to 2 h, then offline (vault Data Health, States); the sidebar footer reads the same rule. The backup card shows Failed when the latest backup run failed and Overdue when no backup succeeded in 26 h (DEC-060).
  - **Coverage heatmap:** an inline CSS grid, not ECharts: 90 days × 4 sources needs no chart library. Collected days are neutral; colour marks only partial, failed and running days, and gaps are hatched. Phones show the last 30 days. Each row has a text summary for screen readers.
  - **Fields DH-1 doesn't serve show "—" with a "no source yet" reason, never 0:** next due, uptime and offline windows, backup size, quota while null, and raw-payload download links (the drawer shows payload ids). The CSV upload is a designed disabled state until P1-11b merges. Follow-ups are in `docs/BACKLOG.md`.
  - **Controls:** Run now stays focusable (`aria-disabled`) with its reason in a tooltip when `live_runs_allowed` is false or the source is disabled. Disabling asks for an optional reason; re-enabling a blocked source requires one (§4.2), matching the API's 422.
  - **`CURRENT_PHASE = 1`** in `apps/web/src/lib/nav.ts` (imp-001), pinned by a unit test, so the coming-soon pages, palette hints and phase progress bar agree.
- **Alternatives:** hard-coding each source's interval in the web to compute Stale (it would drift from the Beat config); an ECharts heatmap (a large client library for one grid); badging partial runs too (noisy: one store timing out would light the badge).
- **Why:** the badge has to mean "act now", so it counts only states the owner must act on. Every state comes from the shipped contract, so the UI never shows a status the API can't back. The missing fields are visible as gaps rather than invented.

### DEC-099 · Trends capture parsing and conservative monthly reservations
**2026-10-22 · proposed (task_b029c09b094e)** · P1-09b, TRD-1, DOC-1 Trends
- **Capture:** one approved keyword per US/UTC `TIMESERIES` search with `today 3-m`; append every returned daily point per raw capture/parser using `append_observation`. Values are relative 0–100, never volumes. Copy `is_partial` exactly; absent means false. No velocity, smoothing or guessed partial point. Empty timelines create no rows. Manual template rows share validation/upsert but use `window=manual` because no request window is supplied.
- **Quota:** `request_hook` locks and refreshes the source row, reserves in `sources.config.trends_quota={month: YYYY-MM, used: N}`, and lets the framework commit before each live attempt. UTC calendar month, configured limit 0–250, no refund after errors/retries/cache hits. The live/worktree guard and missing-key check precede reservation. Exhaustion raises `TrendsError`/`trends_monthly_budget_exhausted`, stopping the plan partial. Fifty keywords on each weekly run require 200–250 attempts/month before retries; outside account usage remains unknown.
- **Alternatives / why:** a new quota table needs a migration; in-memory counting loses reservations on restart; counting successful responses undercounts crashes and retries. The existing config column and source row lock fit without a migration or dependency. Manual rows must not pretend to belong to a SerpApi normalization window.
- **Size split:** P1-09b delivers parser, fixtures, error classification, approved plan and persisted reservation hook. P1-09c must add guarded HTTP, response-side 401 disable/provider-quota handling, distinct Data Health error-code integration, live block/Retry-After adapter tests, import/worker registration and capture-cutoff reader acceptance before TRD-1 is complete. No transport or live registration ships here; all sources remain disabled. Existing 2026-10-22 terms evidence is reused, with no policy changes.

### DEC-103 · Shopify pacing across restarts and a 24-hour robots cache
**2026-10-23 · proposed (P1-33)** · P1-32 M1/M3; tightens DEC-087 and preserves DEC-003/033/069/089/090
- **Decision:** remove the worker image's concurrency override so DEC-089's single consumer setting applies. At Shopify `collect()` start, under the existing source lock, group this source's raw captures by request domain and take `max(captured_at)`. Seed each store's monotonic deadline from that UTC capture time plus 10 seconds and the global deadline from the newest Shopify capture plus `60 / shopify_requests_per_minute`. Include failed responses and domains outside the current tracked set; pacing evidence does not depend on successful catalog/cache eligibility. Never shorten an existing in-process deadline; those clocks remain the per-request fast path. Reads finish and commit before any HTTP or pacing sleep.
- **Robots:** successful robots bodies expire at 24 hours, replacing DEC-087's seven-day cache (RFC 9309 §2.4). Expired rules require a fresh robots response; existing unavailable/disallowed handling remains. Robots delays, durable Retry-After, stop-on-first-block, no repeated URL, source/worktree guards and the disabled source remain unchanged. This relaxes no compliance or collector-host rule.
- **Alternatives / why:** process-only clocks lose spacing on restart; an additional Redis limiter or persisted deadline table adds another state store or migration. Existing raw captures provide conservative response-time evidence, with no history edits. The existing `(source_id, captured_at)` index scopes the query; no domain-expression index exists, so grouping still scans that source's capture history. No index or migration is added in this task.
- **Validation:** offline regressions cover the worker command, reset clocks with recent/expired/failed captures, global and store spacing, preservation of an existing deadline, and robots opt-out at 24/25 hours with a 23-hour cache control. No live source request or enablement.

### DEC-107 · Web: the Problem guard checks the full API contract; CopyButton reports a failed copy
**2026-10-22 · proposed (imp-033)** · audit aud-003 F-01, F-02; DEC-019, DEC-025
- **Decision:**
  - **Problem guard:** `isProblem` (`apps/web/src/lib/api/client.ts`) accepts a body only when `type`, `title`, `code`, `detail` and `request_id` are strings, `status` is an integer, and `errors`, if present, is an array of plain objects. That is everything the generated `Problem` type promises. RFC 9457 lets a server omit `type`, but `apps/api` errors.py always sends it, so a body without it did not come from our API.
  - **CopyButton:** a denied write or a missing clipboard API (an insecure origin) resolves to a "Couldn’t copy" label with a `--negative` warning icon and neutral text, announced through the button's existing polite live region. It shows for 4 s (Copied stays 1.2 s); the timer is cleared on unmount, and every click starts fresh, so a retry is possible and a repeated failure is announced again.
- **Alternatives:** narrow the predicate's type to the fields the one caller reads (a weaker contract for future callers); accept a missing `type` as `about:blank` (a predicate that lies about `type: string`); a toast for the failure (Sonner isn't installed, and the label already sits where the user is looking).
- **Why:** a type guard that says more than it checks lets a malformed body reach the UI typed as trusted. A clipboard write can be denied by the browser or by permissions policy, and the old button raised an unhandled rejection and showed no feedback.

### DEC-105 · CJ guarded transport and category resolution
**2026-10-23 · proposed (P1-08b)** · DEC-009/032/035/095; P1-32 L9/L10
- **Runtime:** fixed-host standard-library HTTPS with no redirects and sequential `CJ_REQUESTS_PER_SECOND` pacing across auth/data/retries in the collector process. Existing worker source locking remains required. Cache response-expiry tokens in Redis under a configured-key digest with TTL ending five minutes before refresh expiry; refresh access tokens five minutes early and reactively retry once on documented token-rejection codes. Auth bodies remain outside raw storage; only safe error/status/deadline metadata reaches Data Health.
- **Accounting:** the CJ collector owns send-boundary callbacks: commit daily catalog reservations immediately before HTTP, including a paid retry; preserve the rejected product response as raw evidence; count actual auth and product attempts. The existing before-hook now validates flags/worktree/contact/endpoint before the framework records an attempt. Cache failures and refused worktrees reserve nothing; uncertain sent attempts retain their reservations. No framework fork or migration.
- **Source codes:** HTTP 200 with rate `1600200` or points `16900500`/insufficient-points text defensively counts toward DEC-032 blocking while preserving actual captured status. The public docs explicitly specify HTTP 429 for point exhaustion but leave the global codes' HTTP status unspecified (DATA_SOURCES). Preserve generic quota blocking; imp-039 is separate work.
- **Categories / alternatives:** resolve exact normalized hierarchy paths only against returned category IDs, expand parents and deduplicate before checking the plan budget. Prefer an explicit unresolved seed over fuzzy aliases or invented IDs. The public sample proves one Office ID, not the ten draft seeds; all ten mappings remain unresolved. Per the lead clarification (2026-10-23 01:57Z), synthetic trees are test-only, and the lazy category target stops before HTTP with `cj_category_unresolved` in Data Health if any name is unresolved. Real getCategory evidence and the ten mappings remain P1-08c after the existing owner terms/key gates; no guessed or fuzzy IDs.
- **Split:** items 1–2 and L9/L10 ship here; P1-08c carries detail/stock/freight, refill/balance/countdown and CSV registration. No source enablement, scheduler registration or terms decision. Fixture-only tests cover Redis reuse/expiry, reactive refresh/budget, pacing, real documented category ID resolution, raw retry evidence and HTTP/body-code errors; real service and account behavior remain unverified.

### DEC-108 · Job-scoped slot suppression with durable evidence
**2026-10-23 · proposed (P1-34)** · task_37801dc82ecf; P1-32 M2 / W2 / W2b; DEC-089/098
- **Suppression:** a scheduled slot is blocked only by a recent queued/running row for its source and job, or an existing successful row for the exact slot. Slotless runs use the same default job as execution (catalog, except Trends and FX). Age uses started time, falling back to queued time; rows at or beyond DEC-098's max(two hours, twice the source budget) threshold never block scheduling. The threshold is shared with recovery, which alone may abandon stale rows under the free execution lock.
- **Evidence:** same-job active suppression commits a `skipped` schedule run for the requested slot, `complete=false`, `params.blocked_by=<run id>`, and `error_code=slot_suppressed`. Data Health's existing run list/detail can display it; the gap audit still treats the slot as missing rather than collected. A `slot_suppressed` log includes only source, job, slot key, blocker id and age in seconds; safe fields are in the message because the shared JSON formatter omits arbitrary extras. No exception text or run params are logged. Successful-slot deduplication keeps its existing successful evidence.
- **Coordination:** amends DEC-089's no-source-row-lock choice and DEC-098's scheduler execution-lock gate: schedule and catch-up enqueue decisions now hold the source row `FOR UPDATE` through their queued/skipped commit. Scheduling never takes the long-lived source execution lock, so `cj.catalog` cannot drop `cj.freight`; freight delivery waits through DEC-098's existing bounded retry. Collection and stale reconciliation retain their source execution locks; catch-up retains its source-wide active-run gate, current-period limit, and per-source/day/slot caps.
- **Alternatives / why:** narrowing the run query while retaining the scheduler's execution-lock early return still loses freight; dropping coordination entirely can race catch-up against scheduling. Existing source-row locking and run evidence solve both without a migration, dependency, new table, schedule change or adapter change. PostgreSQL row-lock concurrency and Redis/Linux process behavior remain unverified locally; all new regressions use SQLite/fakes.

### DEC-106 · Coarse-pointer touch targets: an invisible ::after hit area, not bigger controls
**2026-10-22 · proposed (imp-026)** · A11Y-02 (aud-002); DEC-007, DEC-024; vault Design/Accessibility
- **Decision:** under `@media (pointer: coarse)` the `hit-area` utility (globals.css) adds an absolutely positioned, invisible `::after` with `inset: min(0px, (100% - var(--hit-target)) / 2)`, so every control owns at least a `--hit-target` (44px) square around its centre. The dense visual box and the layout don't change, and fine pointers get no pseudo-element at all. The control must be positioned: `Button` and `Switch` now carry `relative hit-area` in their base classes; other shell, sheet and page controls add the pair. Already-positioned controls (the fixed skip link, the absolute sheet close) add only `hit-area`.
- **Visual growth only where neighbours leave no room:** command palette rows (40 → 44px) and its input (36 → 44px, in a 52 → 56px bar so the 4px focus ring still fits), Data Health run-drawer items (34 → 44px), the gallery section chips' row gap (8 → 12px) and the sidebar footer gap (2 → 6px), all on coarse pointers only. The Data Health source-name button moves `truncate` to an inner span, so the button doesn't clip its own hit area. `--input-h` under coarse rises from 40px to 44px (unused so far), because an `<input>` can't render `::after`. This supersedes the 40px in vault Color & Tokens.
- **Test:** `e2e/touch-targets.spec.ts` uses a `hasTouch` context and probes a 44×44px square around each visible control with `elementFromPoint`. That measures the real hit area, pseudo-elements included, and it fails when a neighbour or a clipping ancestor takes part of the square. It probes 1px inside the edge because Chrome rounds hit-test points to whole pixels, so two areas that only touch would otherwise read as overlapping. Covered: Daily Pulse, the gallery and Data Health (DH-1 fixtures) at 375/1024/1440px, and at 375px the More sheet, the palette, the run drawer and the disable-reason dialog, with no page scroll. On fine pointers, screenshots compared with `origin/main` show no layout change. The only pixel differences are sub-perceptual: Switch thumb shadows (at most 6/255) and two antialiased pixels behind the palette overlay.
- **Alternatives:** raise `--button-h-*` and the chip heights under coarse (changes every touch layout, crowds the 375px top bar, and the brief asks to keep the visual dense); padding plus negative margin (the padding paints the background, so the visual grows); a `position: relative` built into the utility (it would silently override `fixed`, `absolute` or `sticky` on touch).
- **Consequences:** a control that clips its overflow (for example `truncate` or `overflow-hidden` on the control itself) clips its own hit area; the test catches it. Adjacent dense controls need about 12px between them, or a 44px visual, on touch. Clerk's `UserButton` trigger gets `relative hit-area` through `appearance`, which can't be checked under the E2E auth bypass (needs Clerk dev keys).

### DEC-110 · Shared Shopify catalog plan and worker finalization
**2026-10-23 · proposed (task_bbaf4d1ad0a2)** · P1-04c; P1-32 L2; DEC-087/098/103
- **Decision:** extract `shopify_stores.plan(session, source, settings=...)` from `collect()`, returning the adapter, targets and a `finalize(session, run)` callable. Planning retains approved/tracked-store selection, successful-target ETag/robots preload, persisted pacing and the request hook. Both entry paths use the same successful-store delisting and `last_crawled_at` finalizer; `collect()` retains its queued-run guard and lifecycle behavior.
- **Worker contract:** add only optional `collector_max_retries` and `finalize` fields to `Plan`. The Shopify startup factory preloads its adapter and sets retries to zero, so a 5xx/transport failure fails that store without another attempt at the URL or deferring later stores. The source lock covers planning, execution and finalization. Unset fields retain existing plan behavior; no general settings override or separate cache hook is needed.
- **Alternatives / why:** a worker runner calling `collect()` would duplicate worker lifecycle/time-limit handling; moving the worker plan type into the source framework would broaden the dependency boundary. A source-local factory and finalization closure reuse the existing code without either change.
- **Scope / verification:** register only Shopify `catalog`, leaving `variants_js` for P1-07b. Fixture parity checks cover requests, observations and store-local finalization; registered-path regressions cover cache preload, 503/transport isolation, block hooks and disabled/live/worktree guards. Existing Shopify tests remain unchanged. No source, seed or flag is enabled; no request, robots, block, compliance or collector-host policy changes.

### DEC-114 · Palette input ring drawn inset at the row geometry; a failed copy names the next step
**2026-10-23 · proposed (imp-040, imp-041)** · A11Y-01 (imp-025), DEC-106, DEC-107; vault Design/Accessibility, UI States
- **Palette ring (imp-040):** the palette input keeps the global token focus ring (2px solid `--ring`) but draws it inset (`-outline-offset-2`), and the input itself takes the row-highlight box: 40px tall (44px on coarse pointers, DEC-106), 6px gutters, `rounded-lg`. The search icon, the `Esc` hint and the phone `Close` sit over the input's padding, at the row icon (14px) and hint (14px from the right) columns, so they sit inside the ring. The bar is now 6px padding around the field (53px, 57px on touch) instead of a fixed 52/56px with room for an outset ring. The input still fills a 44px square on touch, because an `<input>` can't take the `hit-area` `::after`.
- **Copy failure hint (imp-041):** while the "Couldn’t copy" state shows (4s), a tooltip below the button opens by itself with "Select the ID to copy it.", and the same sentence follows the label as sr-only text in the existing live region. Esc dismisses both early. It sits below the button so it never covers the ID above it in ErrorState and PanelError.
- **Alternatives:** put the ring on a wrapper through `:has(:focus-visible)` (it moves the ring off the focused element and restates the global rule); keep the outset ring on a 32px input (on touch the input must be 44px tall, so the ring would be 52px against 44px rows); label-only copy such as "Couldn’t copy: select the ID" (too long for a small button at 375px); a hover-only tooltip (keyboard and touch users would never see it).
- **Consequences:** Playwright asserts the ring's height, insets and radius against the selected row and the icon inside it, in both themes, in forced colors and on touch. The hint names "the ID" because every consumer copies an ID shown beside the button; a CopyButton for anything else needs its own hint.

### DEC-112 · CJ tracked detail, stock and bounded US freight
**2026-10-23 · proposed (task_651b1cefcfd7)** · P1-08c; DEC-009/032/035/095/105
- **Decision:** reuse the existing CJ collector with a source-local `TrackedAdapter`, existing observation models and `append_observation`. Detail creates listing prices and variant prices; product-ID stock writes each known variant's sum of country `totalInventory`, without double-counting CJ/factory/warehouse subtotals. Empty/null inventory remains unknown. Each endpoint has its own raw capture and sparse observations: do not copy price into stock captures or claim inventory from detail pricing. Replay is idempotent under the existing entity/raw/parser-version uniqueness; history is never rewritten.
- **Bound:** accept up to 300 caller-selected tracked products (two requests each) plus up to 150 tracked variants quoted from both CN and US, to US only, quantity one. Thus freight is at most 300 requests and the ten-category projection stays 16,500 points. Reject oversized plans, duplicate IDs and unsupported freight inputs before HTTP. Reserve 10 points for detail, stock and freight at the existing paid-send boundary; retain reservations for uncertain sends and retries. Freight uses POST JSON, exact USD minor units and append-only shipping options; unavailable delivery time remains null.
- **Alternatives / why:** unit quantity and two origins provide bounded v1 freight without multiplying quantity/origin combinations; reject oversized inputs rather than silently sampling them. Reuse the existing lifecycle and schema instead of adding a scheduler, migration, separate persistence layer or fabricated tracking/seed data. Callers pass `TrackedAdapter()` explicitly to `collect`; scheduler selection/registration remains absent.
- **Remaining:** provider balance/minute-refill, account-activity countdown and `TEMPLATES['cj']` import mapping/registration are proposed as P1-08d under the task's size-split allowance. No stock column is added. Account transaction evidence remains unknown and token issuance never establishes activity; the ten seed mappings remain unresolved and fail closed, pending real evidence after the existing owner gates. No source, seed, flag or compliance policy changes.
- **Verification:** handwritten detail/stock/freight fixtures, replay and changed-capture history, exact money failures with no observation writes, US/quantity/origin caps, reservations before fake sends, POST wire format and live/worktree refusal. All network calls in CJ tests remain blocked except mocked transport; real provider and PostgreSQL/service behavior are unverified locally.

### DEC-113 · Shopify bounded .js panel and variant observations
**2026-10-23 · proposed (task_cc615336e1c6)** · P1-07b; SHP-3; DEC-033/087/103/110
- **Panel:** extend the shared plan with `job="variants_js"`, registered through the existing worker factory with zero retries. Use only active stores in the approved/workspace-tracked intersection. Before watchlists exist, select non-delisted catalog listings by their latest listing snapshot's `source_updated_at` descending (nulls last), then listing ID; cap by the existing `shopify_js_panel_size` (default 10, maximum 20). An empty panel makes no requests. This replaces the source note's earlier top-20/600-per-day sketch, without changing settings, seeds or flags.
- **Evidence:** parser `shopify-2` distinguishes bare product `.js` from catalog/meta JSON. Strict integer inventory, including zero or negative quantities, is retained; absent inventory remains null. Append variant observations with capture/date/raw/parser provenance and existing replay/change-only semantics. Preserve exposed barcode as text. Catalog owns identity: unknown products/variants fail the target until a catalog discovers them; no synthetic IDs or identity inference. Match the response to its requested listing/handle. Prices use the captured qualified-store currency; zero-subunit prices remove Shopify's two appended places exactly. Public default currency equivalence remains unverified live; no forbidden endpoint is consulted.
- **Shared controls:** use the same fetch path, restored/global/store clocks, robots cache and checks, honest UA, Retry-After/block hook, and successful-target-only exact-URL ETags. Successful `.js` targets can supply cache bodies; failed targets cannot. A proven 304 adds no observations and its target carries freshness. Only catalogs finalize delisting and `last_crawled_at`; a panel is never a complete store crawl. No velocity is computed and no source is enabled.
- **Alternatives / split:** reusing catalog decimal-string parsing would misread `.js` prices; duplicating HTTP/planning would split request accounting. The small endpoint-specific parser plus shared plan avoids both. To keep the snapshot/registration/tests change near the task's size target, CSV/browser-JSON mapping and import registry wiring move to **P1-07c**, including explicit store/currency context (bare browser JSON has no domain), CSV variant grouping, provenance, idempotency and same-table tests. Import support is not claimed by P1-07b.

### DEC-115 · SCH-4 catch-up eligibility and publication order
**2026-10-23 · proposed (P1-36)** · task_9e07a2c8ef9a; P1-35 M1/M2/M3/L1; DEC-063/098/108
- **Grace:** a slot enters missing/overdue calculation only at `due <= now - OFFLINE_AFTER` (the existing fifteen minutes), leaving Beat its on-time enqueue. Existing heartbeat-gap evidence and successful-gap linking remain unchanged.
- **Eligibility:** under the source execution and row locks, discard every current-period slot with any catch-up attempt or any success before selecting the earliest remaining slot. Only no-run slots or slots whose latest run (greatest id) is `failed`/`skipped` are eligible; stale queued/running rows first become `failed/abandoned` under the existing threshold. A latest `partial` is not automatically replayed, and its run/target evidence remains visible as Partial in Data Health. The per-source UTC-day cap, per-slot cap, active-run gate and DEC-108 scheduling suppression stay intact.
- **Publication:** commit the queued catch-up under the source lock using the existing enqueue helper, return its id, then release the execution lock before publishing. A publish exception still conditionally fails only the queued row with fixed `publish_failed` text and logs only the exception class; it cannot overwrite a delivery that has started. Lost delivery remains subject to stale reconciliation.
- **Alternatives / why:** passing successful target ids into each plan factory could retry only failed targets, but changes the planner contract and source adapters. Excluding latest partial slots is the smallest bounded fix: it avoids repeating successful Trends searches or full Shopify crawls while retaining partial evidence. Immediate catch-up races Beat; gating only the first missing slot lets a spent weekly attempt starve daily recovery; publishing under the execution lock needlessly consumes a busy retry.
- **Scope:** SQLite/fake regressions port P1-35 R1/R2/R3/R5 into the worker suite. No migration, schema, dependency, source/flag enablement, compliance-limit or collector-host change. PostgreSQL/Redis/Linux and host sleep/restart verification remain separate operational checks.

### DEC-117 · Data Health CSV import endpoints and the import-readiness flag
**2026-10-23 · proposed (P1-11b)** · DH-1; DEC-064, DEC-068, DEC-074, DEC-092; vault Features/Data Health, Features/CSV Export & Import
- **Endpoints (DEC-068 contract, rebased on current imports):** `GET /v1/admin/sources/{key}/import/template` [`get_import_template`], `POST …/import/preview` [`preview_import`] and `POST …/import?mode=csv|json&observed_for=` [`commit_source_import`], behind the router's `PLATFORM_ADMIN_USER_IDS` dependency (non-admin 403 test). Market sources are global, so no workspace scope applies. Uploads stay raw bytes (`application/octet-stream`; no `python-multipart`). Preview is validation-only through `parse_csv` and writes nothing; a `DuplicateEntityRows` file (DEC-074) previews as zero valid rows with its row-numbered errors instead of a 422. Both responses carry at most 100 row errors plus the complete `error_count`. A repeat of an imported file returns P1-05's skipped run with `original_run_id`, and `in_progress` when DEC-092 skipped it because that run is still going.
- **Readiness flag (a):** `SourceHealth.csv_import` is `ready` (template and a registered `ADAPTERS` factory), `preview_only` (template, no factory yet) or null (no template). Commit answers 409 `import_unavailable` for `preview_only` sources instead of letting `commit_import` record a `KeyError` failed run. Today only Frankfurter FX is `ready`; Shopify, CJ and Trends turn `ready` when P1-07–09 register their factories, with no API change.
- **Split:** the task's ~400-line rule moves the Data Health upload flow to P1-11c (stacked branch `CodySpooner/p1-11c-import-panel`). Until it merges, the disabled area says the flow comes with P1-11c.
- **Alternatives:** multipart upload (a new dependency); letting commit fail on a missing adapter (a misleading failed run per attempt); hiding the template for sources without an adapter (hides the §4.2 fallback the owner can already check).
- **Deferred:** insert/update counts in preview (needs P1-07–09 read-only classifiers, BACKLOG), the invalid-row download, and rejecting oversized bodies before the API buffers them (the client can refuse files over 20 MB first).

### DEC-117b · Data Health CSV import panel
**2026-10-23 · proposed (P1-11b, shipped as P1-11c)** · DEC-117; DEC-096, DEC-106; vault Features/Data Health, Features/CSV Export & Import, Design/UI States
- **Decision:** the P1-12 disabled area becomes an inline flow, not the planned 5-step wizard. Pick a source (preselected: the first `ready` one), download its template, then choose or drop a file. The file is checked at once, showing counts and row errors with row numbers, and one button imports it. The outcome names the run (imported, "already imported as run #N", "still importing as run #N", or the failure code) and opens that source's runs. Import takes 2 actions with the source preselected: choose (or drop) the file, then Import. Another source adds 1.
- **States:** a `preview_only` source shows "No import adapter yet" and keeps Import aria-disabled with that reason ("no source yet"). Changing the source re-checks the chosen file, so a preview never outlives its source (stale). Files over 20 MB are refused before upload. A 422 file error offers no Retry, since the same bytes would fail again. The source select uses `--input-h`, so it reaches 44px under a coarse pointer (DEC-106).
- **Alternatives:** a dialog wizard with a column-mapping step (more clicks; mapping is already server-side through `config.csv_mapping` and header aliases); hiding sources without an adapter (hides the §4.2 fallback the owner can already check).
- **Deferred:** the first-20-rows table, the invalid-row download, Shopify JSON from the panel (the API accepts it), and a per-row "Import CSV" action in the sources table.

### DEC-100 · Database-only backup and scratch restore tooling
**2026-10-22 · proposed (P1-14)** · task_de6c8a4714ef; BAK-1/2 tooling, Lead Playbook §6 step 1
- **Guard:** both scripts require a primary checkout, clean tracked files, branch `main`, zero commits ahead of `origin/main`, no `.collector-hold`, and an exclusive mkdir operation lock. Git inspection is the only subprocess activity before those checks pass. The checkout is parameterized for temporary-repository tests; no collector-host operation is performed by this task. Status is `.git/pulso-collector-op.json` with `{op, started, finished, exit, log}` and value-safe JSON log lines. `--detach` launches a hidden child which repeats the guards and acquires the lock; callers must confirm a new status timestamp before treating the launch as started. Abrupt termination leaves the lock for owner inspection, never automatic takeover.
- **Artifact:** `docker compose -p pulso-collector` uses the existing compose file and both collector env files. Container `psql` holds a read-only repeatable-read transaction while a separate `compose exec -T postgres pg_dump -U pulso -d pulso -Fc -f /tmp/pulso.dump --snapshot …` imports its snapshot, so exact counts for every public table and the migration revision describe the dump even during collection. Both process failures abort publication; `pg_restore --list` must pass before `compose cp` writes a unique UTC `.dump.partial`. A SHA-256 manifest is published before the final same-directory rename. Coverage is explicitly `database only`, raw-object coverage `none`.
- **Data Health:** when the process receives `DATABASE_URL`, append one terminal `collector_runs` record under the existing `backup` source, without creating or enabling sources. Recording errors are redacted and never remove a saved dump. No URL means no database recording; the scripts do not load secret files themselves.
- **Retention:** pure selection keeps the newest dump on each of 14 UTC dates, the newest dump on each of 8 Sundays (overlap is retained once), and the newest 3 dumps regardless of date. Only recognized timestamped, direct, regular `pulso-*.dump` children are eligible; manifests, partials, unknown names and symlinks are untouched. Default is a logged preview. Enabling `--delete-expired` awaits the owner; no deletion is enabled by this task.
- **Restore:** `--latest --db pulso_restore_check` requires a matching checksum, creates a previously absent scratch database, compares all manifest table counts and the Alembic revision, and removes only that created database even on a restore/check failure. Names must start with `pulso_restore_check`, contain only lowercase ASCII letters/digits/underscores, fit PostgreSQL's identifier limit, and differ from the collector `DATABASE_URL` database. Existing databases are never replaced or removed. Raw-object sampling/re-parsing (BAK-2 R-11) is explicitly later work; this is not a production recovery command.
- **Scheduling and scope:** the vault has an exact `schtasks.exe /Create /TN "Pulso nightly backup" /XML "$env:TEMP\pulso-nightly-backup.xml"` recipe encoding 03:30 local and `StartWhenAvailable`, running `uv run --frozen` as the interactive Docker owner. It is documentation only. R2 upload/raw sync/lifecycle verification is deferred: there are no dedicated backup R2 settings, and safely separating credentials/destination from raw storage plus verification exceeds this task's optional ~40-line allowance. No new dependency, secret setting, service, scheduler registration, network source request or live database operation.
- **Alternatives / why:** counts queried after an independent dump can disagree during collection; PowerShell binary redirection can corrupt archives; unconditional retention or replacement restores can destroy the last recoverable copy. The shared guard and existing PostgreSQL, Pydantic and SQLAlchemy tools suffice. Docker-dependent end-to-end checks are unverified locally (no Docker); nightly streaks and the real restore drill remain pending.

### DEC-104 · Collector profile, guarded operations and Railway handoff
**2026-10-22 · proposed (P1-13)** · SCH-5, SCH-6 commands, RW-1; DEC-002/013/089/098/100/102
- **Profile:** the default Compose project remains dev infrastructure. Collector commands select `pulso-collector` and profile `collector`, adding worker, a separate ops consumer (DEC-098), and Beat to Postgres/Redis/RustFS. All persistent services restart unless stopped. Worker/ops/Beat share the Railway worker Dockerfile; the collect command is inherited, so P1-33 owns its concurrency correction. Beat persists its schedule in the image user's home volume. The tools-only `migrate` service uses the existing API Dockerfile and Alembic command; the coordinator selected it because it already packages migration files, avoiding worker-image changes.
- **Environment:** container settings come only from `.env.collector`, using Compose's literal `raw` env-file format (Compose 2.30+); no shell interpolation supplies live/scheduler flags. The file is optional for static config validation but mandatory in the guarded commands. The owner supplies literal, unquoted values and separate host ports. Shared `.env` plus `.env.collector` still configure Compose infrastructure through P1-14's existing command prefix. No settings, secrets or services are enabled by this change.
- **Operations:** `uv run --frozen python -m infra.scripts.collector start|update|migrate|status --checkout <repo>` reuses P1-14's primary-checkout/clean-main/not-ahead/hold guards, atomic mkdir lock, UTC status file and hidden detached launcher. Start/update/migrate detach by default and repeat guards in the child; launch success is not completion. Status runs synchronously under the same guards/lock, reports container state/health, current Alembic revision and the preceding operation, and journals its own result. Missing PostgreSQL reports a null revision, not a fabricated head. Hold is checked again before each external operation. Abrupt termination leaves the lock for owner inspection.
- **Ordering:** start is a no-op if every persistent service is running. Otherwise start builds images, stops consumers, starts healthy infrastructure, takes the verified backup, applies migrations, initializes the raw bucket with the existing helper, then starts consumers. Update first pulls with `--ff-only`, then follows that sequence. Migrate follows it but resumes only consumers that were running at entry. A failed backup or migration never resumes consumers; it writes failure status. No source enablement, seed loading or history edits occur here. A populated collector database still requires the Lead Playbook's recorded restore drill before migration.
- **Backup reuse:** P1-14's dump body is extracted as `create_dump` for use inside an already-held operation lock; its standalone backup and restore interfaces are preserved. Snapshot metadata now handles an absent or empty Alembic table, so first boot can back up the empty database before creating schema. Custom-format dump, readability check, manifest, atomic publication and retention preview remain unchanged; deletion stays off.
- **Railway:** the runbook preserves DEC-102's already-live site-only Hobby deployment and Railway raw bucket. Worker/ops/Beat deployment, collector data transfer, plan changes, backup provisioning and cutover remain owner work. It documents API pre-deploy migration, single-scheduler handoff and rollback that preserves both histories; it does not change dashboard state or write Railway config files.
- **Alternatives / evidence:** duplicate guards or a nested backup operation would create competing locks/status; starting consumers before schema is ready can dispatch invalid jobs. Reusing P1-14 and the API image avoids both. [Compose profiles](https://docs.docker.com/compose/how-tos/profiles/), [env-file format](https://docs.docker.com/reference/compose-file/services/#env_file), [Railway Dockerfiles](https://docs.railway.com/builds/dockerfiles) and [pre-deploy commands](https://docs.railway.com/deployments/pre-deploy-command) were checked for this task. Validation is offline unit tests and Compose config only; real image builds, migrations, restarts and host/OneDrive/Railway checks remain unverified here.

### DEC-128 · RustFS for local S3; Phase 0 screens approved
**2026-10-23 · approved by owner 2026-10-23** · R-05; WEB-6; SPEC A-13 (DOC-1)
- **Owner's answers (2026-10-23, in the owner's session):** "Keep RustFS (Recommended)" for local file storage, and "Approve the screens (Recommended)" for the Phase 0 shell, Daily Pulse empty state, Ctrl+K palette and UI gallery.
- **Decision:** local dev and the collector host use RustFS (`rustfs/rustfs:1.0.3`) as the S3-compatible emulator instead of MinIO, whose community edition was archived; production stays Cloudflare R2. SPEC §2 and §11 Phase 0 are amended (A-13). WEB-6 is closed.
- **Why:** RustFS is already running and tested on the owner's PC; the choice affects local development only.

### DEC-129 · Collector scripts merged by the owner; collector host set up
**2026-10-23 · approved by owner 2026-10-23** · DEC-073, DEC-100, DEC-104; protected paths (DEC-072)
- **Owner's answer (2026-10-23, in the owner's session), after a review of P1-13 (including the P1-14 backup tooling):** "Merge + set up collector (Recommended)".
- **Decision:** merge `CodySpooner/p1-13-collector-compose` (collector compose profile, guarded `infra.scripts.collector` start/update/migrate/status, verified pre-migration backups to `OneDrive/Pulso Backups/db`, scratch-only restore); it supersedes `CodySpooner/p1-14-backup-tooling`, which is not merged. The owner's session creates `C:\dev\pulso\.env.collector` (random local credentials, collector ports 55432/56379/59000/59001, `PULSO_BOT_CONTACT` per DEC-073, `PULSO_SCHEDULER=on`, `COLLECTORS_LIVE=on`) — individual sources stay disabled until the lead enables them one at a time under Lead Playbook §6 step 4.
- **Review notes:** preflight refuses dirty/linked/held checkouts; atomic operation lock and status file; no `down`, `-v`, `prune`, volume deletes or downgrades; restore only into new `pulso_restore_check*` databases; old backups are deleted only with an explicit `--delete-expired`. Low: the in-container `/tmp/pulso.dump` is left behind (overwritten each run) → backlog.

### DEC-136 · Use CJ now; Pulso is for the owner's own stores
**2026-10-23 · approved by owner 2026-10-23** · resolves DEC-009; the P1-08 CJ user-agreement escalation; DEC-073; affects Phase 8 scope (DEC-048)
- **Owner's answers (2026-10-23, in the owner's session):** asked whether the CJ account orders every 30 days: "not yet because we havent started selling yet"; offered "use CJ now until it switches off" or "keep CJ off": "use it now"; asked about CJ's user agreement (Usage Rules 3: no commercial use or off-platform display without written permission): "yea i think im leaning towards just using this product for myself and keeping it to use for my stores only so it will not be a paid app".
- **Decision:**
  - **CJ:** the owner's key is in `.env.collector`. Enable `cj_dropshipping` on the collector host as early as Lead Playbook §6 step 4 allows, **right after Frankfurter FX** (its 30-day window is time-limited), then Shopify stores, then Google Trends. When CJ returns `1600014` (30 days without orders), the adapter's existing rule disables the source with the Data Health alert "CJ API disabled: 30 days without orders"; nobody retries around it. The owner requests reactivation in My CJ once he starts selling.
  - **CJ terms:** CJ data is used only inside Pulso for the owner's own product research, which the owner accepts under CJ's agreement. If Pulso were ever offered to others, CJ's written permission comes first.
  - **Product scope:** the owner currently intends Pulso for his own stores only, not as a paid app. SaaS-only work (Stripe billing, plans, team seats, public API, marketing site in SPEC §6.18/§11 Phase 8) is deprioritised to the end of the queue and not started without a new owner decision. The multi-tenant `workspace_id` model stays (already built, cheap to keep).
- **Why:** free, real supplier data now beats waiting for the first sale; the auto-disable makes the lapse safe and visible.

### DEC-141 · Compose env-file contract asserted on the un-interpolated model
**2026-10-23 · proposed (P1-44)** · DEC-104; CI python job
- **Cause:** CI (`ubuntu-24.04` image 20261012.334, Docker Compose 2.38.2) renders `docker compose config --format json --no-env-resolution` with every service `env_file` inlined into `environment` and the `env_file` key dropped. This happens whether or not `.env.collector` exists. Compose 5.6.1 on the owner's PC keeps the declaration, so `infra/tests/collector/test_compose.py` passed locally and failed in CI (run 39905831046) with `KeyError: 'env_file'`.
- **Decision:** a separate test reads `config --format json --no-interpolate`. Both 2.38.2 and 5.6.1 return the same un-normalized model there: anchors, merge keys and paths are resolved, and no env file is read or needed. The test asserts that worker, worker-ops, beat and migrate each declare exactly one `.env.collector`, `format: raw`, `required: false`, with no live or scheduler flags in `environment`. The rendered-config test keeps its other assertions and no longer reads `env_file`. `infra/docker-compose.yml` is unchanged because its declaration is correct.
- **Alternatives:** parsing the YAML with PyYAML would add a new dev dependency and a `uv.lock` change. Pinning Compose in CI would touch the protected `.github/` and leave older local Compose versions failing. Accepting a missing `env_file` would remove the check on CI.

### DEC-119 · Shopify product .js failures stay product-scoped; one panel listing per handle
**2026-10-23 · proposed (P1-38)** · P1-37 M1, L4, L5; DEC-087/090/113
- **Decision:** the store-level `untrackable` rule (402/404, password redirect, HTML 200) applies only to `/meta.json` and `/products.json?…` responses, exactly as DEC-087 scoped it. A failed `/products/<handle>.js` response fails that store's `shopify_variants_js` target (partial) and nothing else: the store stays `active`, other stores' panels continue, and later catalogs still crawl it. The 403 → `blocked`, 430 → disable, 429 streak, Retry-After floor and stop-on-first-block rules are unchanged for every path, `.js` included. Stores already marked `untrackable` stay excluded; nothing reactivates them.
- **Panel:** select at most one live listing per handle, the one with the newest `last_seen_at` (then highest id), before the existing order and cap. A handle reused before a catalog delists the stale twin is one `.js` URL, so it no longer trips DEC-090's duplicate-URL guard and stops every later store's panel. The guard itself is unchanged.
- **Alternatives / why:** per-product targets would let one 404 skip only that listing, but change target identities and the per-store ETag eligibility join; skipping inside the store's request generator is impossible because the framework raises `ResponseFailed` before the generator resumes. Both need framework work outside this task. A password-protected store still fails `/meta.json`, which every panel run requests before any `.js`, so the store rule still sees it. Deduplicating in Python after the SQL cap would let twins consume panel slots.
- **Verification:** `test_product_scope.py` ports P1-37 probes S1 (as four `.js` replies) and S3; both fail on `origin/main` (`db5f961`, and `1aea91a` after rebase) and pass here. It pins the meta/catalog rule (eight cases), the panel's `delisted_at IS NULL` filter and the `.js` unproven-304 check; six revert-the-fix mutations are all caught. PostgreSQL probe PG_S1 is not ported (no DB-marked Shopify harness yet, P1-35 L6). No source, seed, flag, migration or compliance change.

### DEC-111 · Trends transport, response finalization and capture-cutoff reads
**2026-10-23 · proposed (task_d47374939c64)** · P1-09c; TRD-1; DEC-031/069/098/099
- **Transport:** fixed-host stdlib HTTPS with the existing timeout and Pulso contact User-Agent; no redirect following or proxy discovery. Only fixed US/UTC daily-series parameters and one keyword are accepted. The key comes only from Settings and is added to the outbound query, never Request metadata; transport failures suppress provider exception text and chaining. No dependency, migration, enablement, seed or policy change; reuse the recorded 2026-10-22 terms evidence without source requests.
- **Responses:** the hook stops on invalid key and provider exhaustion; generic HTTP-200 JSON errors fail only that keyword so later targets still run (P1-35 M4). The DEC-110 plan finalizer commits distinct safe Data Health codes after the framework's rollback. Invalid-key failures disable once with a source event. Exhaustion preserves the later of the next UTC month's start and any existing Retry-After deadline. HTTP 403/429, including quota-429, still count, stop and disable through the framework; generic 5xx keeps its retries. DEC-099 reservations remain committed before every attempt, with no refunds and a cap of 250.
- **Review evidence:** compare echoed fixed parameters as strings, accepting both `tz=0` and `tz="0"` (P1-35 L4). OPEN-1 (actual partial-flag key) and OPEN-2 (actual no-results shape) remain owner-run pre-enable checks; synthetic fixtures cannot establish either. Enablement also waits for the separate SCH-4 M3 partial-slot catch-up fix. No guessed no-results message or partial-flag alias is added.
- **Reader:** `series_as_of` selects one successful live keyword capture strictly before the next UTC midnight, then returns only its points. It uses raw/target evidence so a newer empty capture returns no points instead of older observations; manual CSV remains a separate normalization window. Three fixture capture clocks prove the boundary and prevent late captures from improving earlier features.
- **Alternatives / why:** redirect-capable clients add credential exposure; raising after-hook database changes loses them to rollback; selecting the newest observation hides empty captures and may mix normalization windows. Existing framework finalization and evidence tables fit without a new schema or shared framework policy change.

### DEC-120 · Variant snapshot writers: change-only per writer and a per-field current read
**2026-10-23 · proposed (P1-39)** · P1-37 M2; task_ccd52d8a81f7; DEC-031/060/071/093/112/113
- **Writers:** a `Writer` is one evidence kind sharing an observation model. It has a predicate over its capture's `raw_payloads.request` and the fields it owns for reads. Shopify catalog: `path` starts with `/products.json?`. Shopify `.js`: `path` like `/products/%.js`. CJ detail: `endpoint` is `/product/query`. CJ stock: `endpoint` is `/product/stock/getInventoryByPid`. Request metadata is written once per capture and parser replay reuses the capture, so a row's writer never changes. No migration, column or unique-key change.
- **Change-only:** `append_observation(..., writer=)` compares `values_hash` only with the latest earlier row (DEC-093 bound) whose capture matches the same writer. Each writer's hash fields are unchanged, so an unchanged capture appends nothing however catalog/`.js` or detail/stock alternate. Same-capture parser correction, replay idempotency and append-only history are unchanged. Single-writer models (listing snapshots, freight, trends) pass no writer and keep the existing comparison.
- **Current read:** `current_fields(session, model, key=, writers=, captured_before=)` returns, per owned field, the owning writer's effective row (DEC-071/093 ordering; greatest id within a capture) among rows with `captured_at < captured_before` (DEC-031: `d+1 00:00Z` for day *d*). The row is that field's own provenance: `captured_at`, `observed_for`, `raw_payload_id`, `parser_version` and `currency`. A field with no row before the cutoff is absent (missing, "no source yet"). An owned null is returned as a row (explicit unknown or none) and supersedes the writer's older non-null value. No carry-forward, no filling and no inferred values.
- **Ownership (disjoint, enforced):** Shopify catalog owns price, compare-at, availability and `source_updated_at`; `.js` owns `inventory_quantity`, `inventory_management` and `inventory_policy`; CJ detail owns `price_minor`; CJ stock owns `inventory_quantity`. `.js` prices and availability stay stored and change-only, readable only through an explicit writer read. Because no field has two owners, a writer's suppressed unchanged capture can never let another writer's older, contradicting value become current.
- **Freshness:** under change-only a row's `captured_at` is when its writer first saw those values, not its last confirmation. "Last seen" comes from target evidence (DEC-060) and stays with readers.
- **Alternatives:** separate per-writer tables or a writer column (migration for what request metadata already records); latest non-null per column (keeps old inventory after an explicit unknown); latest across writers for shared fields (stale cross-writer wins, above); comparing with any writer's latest row (the M2 defect).
- **Remaining:** import adapters (P1-07c, P1-08d) must join an owning writer's predicate with the same owned fields, or amend this decision, before they write variant snapshots. Until then their rows are never read as current, and any capture matching no writer is never current (fail-closed). A batch read waits for the first P2 reader.

### DEC-121 · Bound admin import bodies while receiving them
**2026-10-23 · proposed (imp-051)** · P1-22/P1-11b; DEC-064/068/074/092/117
- **Decision:** preview and commit share an async upload dependency that reads the request stream once, using `imports.csv.MAX_BYTES` (20 MiB). A declared length above the cap rejects without reading; every received chunk is counted before appending, so missing, malformed or understated lengths cannot bypass the cap. The crossing chunk is not appended and the remainder is not read. Exact-cap bodies still pass to the existing synchronous CSV/JSON import paths.
- **Contract:** the router's admin dependency stays first; non-admins retain 403. Oversized files return the existing preview problem, 422 `invalid_file` / `File exceeds 20 MiB`, on both routes before import parsing or DB/S3 writes. Empty bodies retain the required-body 422. Explicit OpenAPI metadata preserves the raw `application/octet-stream` body and operation IDs without FastAPI's eager `Body(bytes)` buffering; registry, mapping and repeat-import behavior are unchanged.
- **Alternatives:** checking only Content-Length misses chunked or dishonest uploads; checking `request.body()` is too late; a global middleware or proxy limit expands scope. No dependency, source adapter or deployment change.
- **Limit:** the API controls its accumulated buffer, not the size of a chunk already allocated by the ASGI server or upstream buffering. Accepted files remain in memory for the existing parsers; no disk-spooling or streaming parser is introduced.
- **Validation:** ASGI chunk tests cover the exact cap, cap plus one with an unread tail, declared/missing/chunked/understated/zero/malformed lengths, CSV preview/commit and JSON commit, original bytes and repeat imports, no import rows/S3 on rejection, admin 403 and required-body errors. PostgreSQL integration and real S3 remain separate from the offline boundary checks.

### DEC-127 · The phone palette sheet pads by the safe-area insets
**2026-10-23 · proposed (imp-047)** · DEC-106, DEC-114; vault Design/Layout & Spacing, Design/App Shell & Navigation, Features/Command Palette & Search
- **Decision:** below 768px the full-screen palette sheet takes `padding-top: env(safe-area-inset-top)` and `padding-bottom: env(safe-area-inset-bottom)`, the pattern the top bar and bottom tab bar already use. The input bar clears the notch, the list's last row clears the home indicator, and the strips show the sheet's own surface. The bottom inset is included because it is the same defect at the sheet's other edge. The centred desktop dialog takes no inset padding.
- **Test:** `e2e/palette-safe-area.spec.ts` emulates a notched phone (47px top, 34px bottom) with Chromium's CDP `Emulation.setSafeAreaInsetsOverride` and asserts the bar and list geometry at 375px, that the page doesn't scroll sideways, and that the 1440px dialog ignores the insets.
- **Alternatives:** padding only the input bar (the list would still end under the home indicator); asserting the class string (would pass even if `env()` resolved to 0).
