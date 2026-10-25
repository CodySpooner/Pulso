# Pulso — Progress

**Last updated:** 2026-10-25 (p2-39 Phase 2 end, on `origin/main` `16abd9a`)

## Current status

**Phase 3 (signals expansion) is being built. Phase 2's build is done; its data checks wait on real data and the owner. Phase 1's data checks run in the background.**

- On 2026-10-24 at 22:23Z the owner moved the build on: "we are not gonna wait until oct 31st if we need to skip this and build the rest of the site" (vault `Agents/Lead State`, `current_phase`). Phase 1's open exit criteria never block (DEC-049).
- **Phase 0:** built. Left: CI-4 (the Clerk secrets in GitHub Actions, optional) and the DOC-4 fresh-agent walkthrough.
- **Phase 1:** every build task is merged except P1-10 (coverage memo CLI) and P1-15 (exit checks). Five data- or owner-gated exit criteria are pending ([Phase 1 exit criteria](#phase-1-exit-criteria)).
- **Phase 2:** build done. Every Phase 2 task is merged on `origin/main`, the last as `16abd9a` (P2-37). The phase-end UI checklist and design review ran in p2-39 (`docs/reports/p2-39.md`). Six of eight exit criteria are met or met on fixtures; the other two wait on real data and the owner ([Phase 2 exit criteria](#phase-2-exit-criteria)). None blocks Phase 3 (DEC-049).
- **Phase 3:** in progress since 2026-10-25, overlapping Phase 2's end. p3-01 (AMZ-1 Amazon CSV import, DEC-279), p3-02 (KW-1 product keywords, DEC-281) and p3-03 (AE-1 + AE-2 AliExpress client and 24 h cache, DEC-283) are running. The web app's `CURRENT_PHASE` is 3 (DEC-284).
- **Data:** only Frankfurter FX collects. It has been enabled on the collector host since 2026-10-24T18:47Z (`docs/DATA_SOURCES.md`). `seed_v1` was loaded there on 2026-10-24 at 21:18Z (30 stores, 10 CJ categories, 50 keywords). The host runs `88ce93b` (migration 0004). Its update to the current head waits for the open DEC-072 review batch.
- **Shopify is off for good** (DEC-261, `3abfd73`). No `enable shopify_stores` and no new crawler work. Store-based views show "no source yet" until a replacement source fills them. The owner chose Google Merchant Center Popular products as the replacement (P2-29, running).
- **CI** runs on GitHub (the repo went public on 2026-10-22). **Docker** runs on the PC (engine 29.9.2) since 2026-10-23, so the database tests run locally.
- **Workers:** Codex has been off since 2026-10-23 (usage used up). The lead runs up to 4 Claude workers (owner, 2026-10-25). While Codex is off, a fresh Claude session does the DEC-072 cross-reviews (DEC-202).

## Phase status

| Phase | Name | Status | Notes |
|---|---|---|---|
| 0 | Foundation | built | Left: CI-4 Clerk secrets in GitHub Actions (optional), DOC-4 walkthrough |
| 1 | Data engine | build done (owner, 2026-10-24); data checks pending | FX collects since 2026-10-24. CJ is next (DEC-136). Shopify off for good (DEC-261). Trends waits on OPEN-1/2 evidence |
| 2 | Core product experience | build done; data checks pending | p2-01..p2-39 merged or delivered. Exit criteria wait on `enable cj`, `listing_images`, the owner's labels and Settings values |
| 3 | Signals expansion | in progress | p3-01 AMZ-1, p3-02 KW-1, p3-03 AE-1/AE-2 running. The AliExpress app review has a lead time; the application is the owner's |
| 4 | Scores and workflow | not started | |
| 5 | AI layer | not started | Needs an Anthropic API key and AI caps at entry |
| 6 | Forecasting v1 | not started | Build work may start after 6–8 weeks of collection. First 14-day forecasts need about 12 weeks of continuous collection, 30-day about 17 (DEC-044) |
| 7 | Store operations | not started | Review the Shopify API Terms before building the app (DEC-003) |
| 8 | Expansion and launch prep | not started | Railway go-live can happen earlier, at the owner's call (DEC-001). SaaS-only work waits for a new owner decision (DEC-136) |

## Phase 0 (built)

- **Done (2026-10-22):** spine (S-1, S-2; `66b997c`, DEC-056); data model and API (DB-1..5, API-1..5; `4e16884`, DEC-051) with review fixes (P0-14, `93539d5`, DEC-057); workers, images and CI (WRK-1, IMG-1/2, CI-1/2/3/5; `1ea56fb`, DEC-050); web shell (WEB-1, 3, 4, 5, 8; `f03e4e0`, DEC-053..055); typed client, root scripts, e2e job (WEB-7, CI-4 built; `dcaaf27`, DEC-058); UI gate and `/admin/ui` (WEB-9; `f012f7f`, DEC-059); docs (DOC-2 `c5bdce5`, DOC-3 `970b78f`); spike script and seed draft (SPK-1; `5a9dd45`, DEC-052).
- **Closed since:** WSL2 + Docker (2026-10-23; S-4, S-5 and the compose and migrate checks passed in the owner's setup session). GitHub Actions billing (repo public, 2026-10-22). WEB-6 screenshots and RustFS (DEC-128, SPEC A-13). Sign-in: the owner signed in on the Railway deploy on 2026-10-23 (vault `Phases/Phase 0 - Foundation` Log; DEC-102). Spike: SPK-2 ran once on 2026-10-22 (DEC-073); its SPK-3 proposal DEC-090 was declined by DEC-261.
- **Pending:** CI-4, which needs the two Clerk secrets in GitHub Actions (owner, optional). DOC-4, the fresh-agent walkthrough (an agent task).

## Phase 1 (build done; data checks pending)

### Merged tasks

Each commit is the task's own merge (or direct commit) on `main`'s first-parent history.

| Task | What | Merge | DEC |
|---|---|---|---|
| P1-01 | Phase 1 schema, migration 0002 (FW-5) | `4283e80` | DEC-060 |
| P1-02 | Raw capture storage (FW-2) | `ccac16f` | DEC-061 |
| P1-03 | Collector framework (FW-1, FW-3, SCH-3) | `a37e181` | DEC-063 |
| P1-03b | Block rule and durable Retry-After (FW-4) | `05f7366` | DEC-069 |
| P1-03c + P1-23 | Observation order, CSV quoting, capture-date bounds | `12431ec` | DEC-071, DEC-074 |
| P1-04 | Scheduling core: Beat, advisory lock, consumers (SCH-1; SCH-2 code) | `bd77343` | DEC-089 |
| P1-04b | SCH-4 recovery: heartbeat, gaps, catch-up; FX registration | `cb301f2` | DEC-098 |
| P1-04c | Shopify plan factory and registration | `1552f37` | DEC-110 |
| P1-05 | Import service (CSV-1, CSV-2) | `6c54ae4` | DEC-064 |
| P1-06 | Seed loader and approval guard | `1aed0e0` | DEC-065 |
| P1-07 | Shopify catalog adapter (SHP-1, SHP-2) | `6a61853` | DEC-087 |
| P1-07b | Shopify `.js` variant snapshots (SHP-3) | `db5f961` | DEC-113 |
| P1-07c | Shopify CSV and browser-JSON import mapping (carried by P1-51) | `b803124` | DEC-152 |
| P1-08 | CJ adapter, fixture slice (CJ-1) | `62d930e` | DEC-095 |
| P1-08b | CJ guarded transport, auth cache, category resolution | `25833f0` | DEC-105 |
| P1-08c | CJ tracked detail and stock, bounded US freight | `5c546e6` | DEC-112 |
| P1-08d | CJ provider points guard, CSV registration (carried by P1-52) | `59e0a67` | DEC-116 |
| P1-08e | CJ account-activity countdown | `40bac86` | DEC-211 |
| P1-09 | Frankfurter FX adapter (FX-1) | `b7763ef` | DEC-088 |
| P1-09b | Trends parser and monthly quota | `dcb703a` | DEC-099 |
| P1-09c | Trends live integration, fixtures only (TRD-1) | `953ea3b` | DEC-111 |
| P1-11 | Data Health admin API (DH-1) | `9e2d4b7` | DEC-068 |
| P1-11b | Data Health import API | `1aea91a` | DEC-117 |
| P1-11c | Data Health CSV import panel | `81c2bed` | DEC-117b |
| P1-12 | Data Health UI and nav badge (DH-2, DH-3) | `415f197` | DEC-096 |
| P1-13 | Collector compose profile, host commands, Railway runbook, backup and restore tooling (P1-14 folded in) | `374ebb2` | DEC-104, DEC-100, DEC-129 |
| P1-17 | Schema fixes from P1-16, API `check_s3` | `2f9396e` | DEC-062 |
| P1-18 | DeltaBadge missing state, P1-02 review | `cdaab61` | — |
| P1-20 + P1-24 | Raw storage and replay safeguards | `a3a209c` | DEC-070, DEC-075 |
| P1-21 | Release worker worktrees Windows refuses to delete | `ef80cd2` | DEC-066 |
| P1-25 | Seed revision order, stored-target validation | `f69f2cc` | DEC-076 |
| P1-27 | Admin toggle row lock, publish-failure redaction | `6b0c753` | — |
| P1-29 | Import retry after a failed or partial import | `1e8434c` | DEC-092 |
| P1-30 | Change-only bound, hook-error block stop | `0aee328` | DEC-093 |
| P1-33 | Worker concurrency 1, Shopify clocks, 24 h robots cache | `78a9a3b` | DEC-103 |
| P1-34 | Job-scoped slot suppression | `dc62bec` | DEC-108 |
| P1-36 | SCH-4 catch-up fixes | `e4ae6ea` | DEC-115 |
| P1-38 | Shopify `.js` failures stay product-scoped | `bc9a77e` | DEC-119 |
| P1-39 | Variant snapshot writer isolation | `955f1cd` | DEC-120 |
| P1-41 | Windows detach flags pass Linux mypy (protected) | `abab38c` | — |
| P1-42 + P1-45 | Guarded collector seeds, enable and disable (protected) | `2656704` | DEC-131, DEC-143 |
| P1-44 | Compose env-file test for Linux CI | `3b90235` | DEC-141 |
| P1-46 | Shopify Grade A label exclusion | `aa48a0f` | DEC-144 |
| P1-48 | CJ review fixes (carried by P1-52) | `59e0a67` | DEC-156 |
| P1-49 | Trends outage stop | `202d849` | DEC-157 |
| P1-51 | Shopify import review fixes | `b803124` | DEC-162 |
| P1-52 | Omitted CJ import fields keep stored values | `59e0a67` | DEC-186 |
| P1-53 | CI fix: Data Health on Linux font metrics | `70a1e1d` | DEC-203 |
| P1-54 | Cross-review of imp-108 and imp-109 | `ea6bf07` | — |
| P1-55 | Cross-review of imp-161 | `16e6726` | — |
| P1-56 | Cross-review of imp-151 and data-06 | `3b2d43f` | — |
| data-01 + data-03 | Bounded Shopify probe, public bot page, `PulsoBot/0.1` identity | `3a75f21` | DEC-077 |
| data-04 | SPK-2 results, SPK-3 proposal | `71a8b7b` | DEC-090 (declined by DEC-261) |
| data-05 | Collector `status` reports read-only Data Health (protected) | `2bf5fe3` | DEC-210 |
| data-06 | FX checks name their error code; next-day rows skipped; FX status enabled | `a0f7595`, `88ce93b` | DEC-230 |

Also merged in Phase 1: the Railway site-only deploy (`5ea0bb4`, DEC-102), the non-stop safety rails (`e1a58db`, DEC-072, DEC-073) and the owner's decisions DEC-136 (`c017923`, use CJ now) and DEC-202 (`24b0e4f`, Claude cross-reviews while Codex is off).

**Review-only tasks, no code merged:** P1-16, P1-19, P1-22, P1-26, P1-28, P1-31, P1-32, P1-35, P1-37, P1-40, P1-43, P1-47, P1-50, and the first DEC-202 batch. Their findings went to the fix tasks above. The notes are in the vault `Agents/Reviews`. data-02 (seed homepage checks) changed the vault only.

**Not merged:**
- **P1-10** coverage measurement and memo CLI (MSR-1): one commit, `ddac1f8`, on `CodySpooner/p1-10-coverage-memo` (Codex, 2026-10-23). Codex is off.
- **P1-14** was folded into P1-13 and not merged on its own (DEC-129).
- **P1-15** join and exit checks: not started. This summary covers its PROGRESS part.

### Phase 1 exit criteria

Pending items are non-blocking (DEC-049).

| Criterion | State | Waits on |
|---|---|---|
| 7 straight days of healthy collection (R-13) | **Pending.** The clock started with FX on 2026-10-24T18:47Z. FX is the only enabled source. Gap days are not counted here; the collector database is read only through the lead's `status` | Time and a running PC. The earliest pass is 2026-10-31 if nothing is missed |
| Nightly backups on 3 straight nights | **Pending.** The restore drill passed (DEC-244, `db2411b`), but raw objects were not covered | The owner: the nightly backup task is not registered yet (vault `Platform/Backups & Restore` recipe; Owner To-Dos log 2026-10-24 22:23Z). Then 3 nights |
| CJ shows suppliers, offers and US shipping for at least 100 products (CJ-3) | **Pending.** CJ is built and disabled | The lead: the FX first-run check after 2026-10-25T17:00Z, the collector update once the open review batch clears, then `enable cj` (DEC-136, Lead Playbook §6) |
| Label-source coverage memo after at least 14 collection days (R-13) | **Pending.** It never blocked Phase 2. Shopify's two families will have no data (DEC-261) | P1-10 merging (Codex off), 14 days of CJ and Trends data, then the owner reads the memo |
| Google Trends enabled | **Pending owner.** TRD-1 is built on fixtures (`953ea3b`) | The owner's test evidence for OPEN-1 (the partial-flag key) and OPEN-2 (the no-results shape), vault `Data/Sources/Source - Google Trends` |
| Shopify source runs or is disabled with the reason shown | **Off for good** (DEC-261, `3abfd73`) | Nothing. No enable, no new crawler work |
| Re-runs idempotent | Replay tests pass on fixtures (P1-03, P1-03c, P1-05) | A manual re-run on the collector host |
| Data Health shows real runs, errors, block state, overdue, heartbeat, gap heatmap | Built (P1-11, P1-12). FX gives the first real runs | The lead's check on the collector host |
| Single scheduler; worktrees can't run live collectors | Built (P1-03 SCH-3, P1-04 SCH-2 code) | The SCH-2 PostgreSQL check |
| Railway runbook (not live) | Written in P1-13 (`374ebb2`) | The lead's walkthrough (RW-1) |
| Lint, typecheck, tests; docs updated | Green at every merge (lead checks). This file is now current | — |

## Phase 2 (build done; data checks pending)

### Merged tasks

| Task | Item | What | Merge | DEC |
|---|---|---|---|---|
| p2-01 | M-1 | Phase 2 migration 0005: embeddings + HNSW, match candidates and decisions, notes and tags, features, settings | `3ed58ed` | DEC-237 |
| p2-02 | UX-3 | Product page shell, `GET /v1/products/{id}` with per-stat provenance, `<Metric>` | `fe4342e` | DEC-238 |
| p2-03 | UX-2 | Discover: keyset feed, grid and virtualized table, URL state; migration 0007 | `3bc3a01` | DEC-239 |
| p2-04 | M-2 part a | Disabled `listing_images` source (migration 0006), 64-bit DCT pHash | `db3b1be` | DEC-240 |
| p2-05 | P2-05 | Cross-review of p2-01 + p2-04: 0 high, 1 medium, 4 low | `d6bba9b` | — |
| p2-06 | P2-06 | XR-11: robots.txt keeps the block count; imp-185 lows | `3807d03` | DEC-242 |
| p2-07 | UX-4 | Overview tab: key stats, where it appears, notes, tags, context rail | `8bde264` | DEC-243 |
| p2-08 | P2-08 | Restore drill of the newest collector dump; 0004 → 0007 rehearsal on a scratch copy | `db2411b` | DEC-244 |
| p2-09 | UX-5 | Trends tab: series endpoint, coverage gap bands, ECharts 6.1.0 | `dec9661` | DEC-245 |
| p2-10 | UX-8 part a | `landed_cost()` with `complete` + `missing[]`, loader, `POST /v1/profit/calc` | `b560704` | DEC-246 |
| p2-11 | UX-7 | Sellers tab: complete-crawl delisting, price spread, 90-day series | `53ae1ef` | DEC-247 |
| p2-12 | P2-12 | Cross-review of p2-03 + p2-06 + p2-10: 0 high, 1 medium, 6 low | `94684c2` | — |
| p2-13 | M-3 | Matcher: hashed scorer config, USD markup gate, HNSW top-20, auto-links | `9f09e74` | DEC-249 |
| p2-14 | P2-14 | XR-16, XR-20, XR-21 landed-cost freight fixes | `f8614df` | DEC-250 |
| p2-15 | UX-10 | Settings page: duty, returns and import fee on `/v1/settings` | `26335b6` | DEC-251 |
| p2-16 | UX-9 | Ctrl+K global search, `/v1/search`; pg_trgm migration 0008 | `600ae0f` | DEC-252 |
| p2-17 | M-6 | Google Product Taxonomy vendored, rule-based category mapper | `53bc9a2` | DEC-253 |
| p2-18 | P2-18 | Cross-review of p2-13 + p2-14: 0 high, 1 medium, 5 low | `069f743` | — |
| p2-19 | M-4 | GTIN shortcut at score 1.0 | `b076203` | DEC-255 |
| p2-20 | UX-8 part b | Profit tab with scenario sliders, ad cost and net profit | `786fce6` | DEC-256 |
| p2-21 | M-5 | Merge and split service, membership(t) by replay | `a8ded78` | DEC-257 |
| p2-22 | P2-22 | XR-23 landed-cost freight fix | `ecf2f39` | DEC-258 |
| p2-23 | Q-1 | Provenance contract: every product-facing resource carries `as_of` | `74b1d6d` | DEC-259 |
| p2-24 | P2-24 | Cross-review of p2-16 + p2-19 + p2-21 + p2-22: 0 high, 1 medium, 6 low | `70f32cc` | — |
| p2-25 | UX-1 | Matching Queue `/admin/matching`, undo as compensating decisions | `8855082` | DEC-263 |
| p2-28 | P2-28 | XR-29: replay `match_decisions` in lock order | `3a0b02c` | DEC-266 |
| p2-26 | UX-6 | Suppliers tab: per-supplier Profit calc, Best margin and Fastest shipping picks, `?supplier=` | `672d46d` | DEC-264 |
| p2-29 | P2-29 part a | Merchant Center Popular products CSV import: `merchant_bestsellers` source (disabled), append-only `popular_products` (migration 0009), GTIN links on read | `ce50c4c` | DEC-267 |
| p2-32 | P2-32 | PROGRESS refresh and the Phase 1 summary (docs only) | `fb7e39c` | — (DEC-270 unused) |
| p2-30 | Q-2 | Loading, empty, error, stale and no-source states across the Phase 2 views | `5d35ef4` | — (DEC-268 unused) |
| p2-27 | UX-8 part c | `workspace_product_economics` view (migration 0010), golden landed-cost vectors, Discover best margin | `98d0bc5` | DEC-265 |
| p2-31 | M-2 part b | `ml.embed` OpenCLIP image + title embeddings, flag off, optional `clip` extra | `4381db8` | DEC-269 |
| p2-33 | P2-29 part b | Google popular page `/google-popular`, `GET /v1/popular-products`, major brands hidden by default | `d48d935` | DEC-272 |
| p2-35 | P2-35 part a | Feature store: as-of repository, `daily_units`, V7/G7, `cj_stock` + `shp_inv`, truncation leakage test | `c0b48c2` | DEC-275 |
| p2-34 | P2-34 | Cross-review of p2-20 + p2-29, riders p2-25, p2-26, p2-28: 0 high, 1 medium, 5 low (rode in p2-36) | `19dc46e` | — (DEC-273 unused) |
| p2-36 | P2-36 | XR-36: an undone accept frees its listings for the matcher | `19dc46e` | DEC-276 |
| p2-38 | P2-35 part b | `ml.features` task behind a flag, Discover momentum end-to-end test | `fd6ca2d` | DEC-278 |
| p2-37 | P2-37 | Workspace brand hide list for Google popular (migration 0011) | `16abd9a` | DEC-277 |
| p2-39 | Phase end | UI checklist and design review of every Phase 2 screen, small fixes, `CURRENT_PHASE` 3, this refresh | this branch | DEC-284 |

Also merged during Phase 2: imp-136 + imp-179 (`2f7fa02`, DEC-236), imp-154 + imp-186 + imp-187 (`aef2ef7`, DEC-235), imp-183 + imp-182 (`933cc24`, DEC-233), imp-224 (`7f9054d`, DEC-260), imp-273 (`4b8334d`, DEC-271), imp-278 (`504441b`), imp-301 (`1d84f67`) and the owner's DEC-261 (`3abfd73`).

Every Phase 2 data path ships off: the matcher (`MATCHER_ENABLED`), embeddings (`EMBEDDINGS_ENABLED`), the feature job (`FEATURES_ENABLED`), and the `listing_images` and `merchant_bestsellers` sources stay disabled until the owner decides and real data arrives. The M-2 verify (95% of listings embedded in one nightly run) waits on `listing_images`, the ml worker image and an ml consumer (imp-284).

### Phase 2 exit criteria

Pending items are non-blocking (DEC-049). Phase 3 runs alongside them.

| Criterion | State | Waits on |
|---|---|---|
| The owner finds a product (Discover or Ctrl+K), sees its suppliers and sellers, and calculates landed margin from real data | **Pending.** Built and tested on fixtures: Discover (`3bc3a01`), Ctrl+K (`600ae0f`), Suppliers (`672d46d`), Sellers (`53ae1ef`), Profit (`786fce6`, `98d0bc5`). The collector has only FX data | `enable cj` for suppliers (the lead, DEC-136, after the collector update). A seller source: Shopify is off (DEC-261), so the owner's weekly Merchant Center CSV fills Google popular, and Phase 3's Amazon CSV (p3-01) adds a marketplace. The owner's fee and duty defaults in Settings |
| Auto-merge precision ≥ 95% on the owner-labelled set; queue precision reported | **Pending.** Matcher, GTIN pass, queue and undo are built (`9f09e74`, `b076203`, `8855082`) | The owner's `listing_images` decision (DEC-240), the ml worker image and consumer (imp-284), real CJ plus a second source with images, then the owner labelling about 200 pairs (about 30 minutes, keyboard only) |
| Manual merge/split overrides hold across matcher re-runs | **Met on fixtures** (p2-21 `a8ded78`, p2-28 `3a0b02c`, p2-36 `19dc46e`) | A real-data check once the matcher runs |
| Every product-page number traces to source + as-of | **Met on fixtures** (Q-1 `74b1d6d`, Q-2 `5d35ef4`, the p2-39 hovers). Two backlog rows remain: the Sellers summary tile and the Suppliers pick cards name their source in the tile, not per number | Real data, and those two p2-39 backlog rows |
| Tests: matching thresholds, profit math, landed cost, endpoints; lint/typecheck green | **Met** at every merge; p2-39 re-ran the web checks | — |
| PROGRESS, DECISIONS (CLIP checkpoint, thresholds, ECharts theming) and vault notes updated | **Met** for PROGRESS (this file) and DECISIONS (CLIP checkpoint DEC-269 a, thresholds DEC-249, ECharts DEC-245) | The lead applies the vault lines in `docs/reports/p2-39.md` |
| Polish checklist passes for Discover, the product page tabs, the Matching Queue and Settings | **Passes, with backlog rows** (p2-39): design-review scores of 87–98 per screen. Every checklist line passes except three contrast items (one appears only while Profit recalculates), now backlog rows | The p2-39 backlog rows |
| Summary to the owner | **Written** (`docs/reports/p2-39.md`, Phase summary) | The lead pastes it into the Phase 2 note and Owner To-Dos |

## §6 items done and pending (DEC-048)

Phases 0–2 only. Everything else is pending in its phase (vault `00 Home`).

| §6 item | Phase | State |
|---|---|---|
| 6.1 Daily Pulse | 4 | Empty shell since Phase 0 (`f03e4e0`) |
| 6.2 Discover feed, filters, sort | 2 | Built (p2-03 `3bc3a01`); best margin from complete rows (p2-27 `98d0bc5`); momentum from the feature store (p2-38 `fd6ca2d`). Score columns wait for Phase 4; margin sort and filter are imp-279. Quick actions are Phase 4 |
| 6.4 Overview: key stats, notes, tags | 2 | Built (p2-07 `8bde264`). The watchlist toggle is Phase 4; the forecast card is v2 |
| 6.4 Trends tab | 2 | Built (p2-09 `dec9661`). Search and ads rows show "no source yet"; search fills once Trends is enabled |
| 6.4 Suppliers tab | 2 | Built (p2-26 `672d46d`). Supplier rows fill once `enable cj` runs |
| 6.4 Sellers tab | 2 | Built (p2-11 `53ae1ef`). It shows "no source yet" while Shopify is off (DEC-261) |
| 6.4 Profit tab: calculator, scenario sliders | 2 | Built (p2-10 `b560704`, p2-20 `786fce6`, economics view p2-27 `98d0bc5`) |
| 6.4 Risk tab: saturation | 4 | Not started |
| 6.17 Data Health | 1 | Built (P1-11 `9e2d4b7`, P1-11b `1aea91a`, P1-11c `81c2bed`, P1-12 `415f197`). Real runs: FX only so far |
| 6.17 Matching queue | 2 | Built (p2-25 `8855082`) |
| 6.18 Ctrl+K palette and global search | 0, 2 | Palette since Phase 0 (`f03e4e0`); search built (p2-16 `600ae0f`) |
| 6.18 Settings | 2 | Built (p2-15 `26335b6`). The owner enters real fees and duty |
| 6.18 CSV export on every table | 4 | Not started. CSV import is built (P1-05 `6c54ae4`) |
| 6.18 Responsive layout and PWA install | 0, 4 | Manifest since Phase 0 (`f03e4e0`); install in Phase 4 |
| Added: `/admin/ui` gallery (WEB-9) | 0 | Built (`f012f7f`) |
| Added: Google popular (Merchant Center weekly report) | 2 | Built (p2-29 `ce50c4c`, p2-33 `d48d935`, p2-37 `16abd9a`). Fills once the owner imports the weekly CSV |
| Added: feature store and leakage test | 2 | Built (p2-35 `c0b48c2`, p2-38 `fd6ca2d`), flag off. The nightly Beat entry waits on imp-284 |

## Improvement and audit work

80 improvement merges and 7 audit merges landed between `a93540d` (imp-002) and `7f9054d` (imp-224): aud-007, aud-009..aud-014 and imp rows from the vault `Agents/Improvement Backlog`. Each has its report in `docs/reports/` and its row in the backlog. Most polish Data Health and the shell.

## Done (pre-Phase 0)

- **Market research, verified 2026-10-22.** Six notes in the vault's `Research/` folder.
- **Spec review, 2026-10-22:** six lenses, about 90 findings merged into 47 items. It lives in the vault at `Research/Spec Review 2026-10-22`.
- **Owner decisions** recorded in `docs/DECISIONS.md` (DEC-001 to DEC-011), plus the proposed defaults DEC-012 to DEC-048.
- **`docs/SPEC.md`** amended for owner-approved decisions only (Amendment log).
- **Repo** at `C:\dev\pulso`, outside OneDrive. **Agent guides** `AGENTS.md` and `CLAUDE.md`. **Docs** `DECISIONS.md`, `PROGRESS.md`, `BACKLOG.md`, `DATA_SOURCES.md`. **Vault** planning notes.

## Next

1. The lead merges p2-39, pastes its Phase summary, Owner To-Dos and 00 Home lines into the vault, and sets Lead State `current_phase` to 3.
2. The open DEC-072 review batch of the risky merges since P2-34 (Lead State), then the collector `update` to the current head, `status`, and p2-17's `map` run.
3. The FX first-run check after 2026-10-25T17:00Z, then `enable cj` (DEC-136).
4. Phase 3: p3-01 AMZ-1, p3-02 KW-1, p3-03 AE-1/AE-2, then the rest of the Phase 3 note's task table.

## Owner to-dos (summary)

The canonical list is the vault note `Phases/Owner To-Dos`. Open items that affect Phases 1 and 2:

| To-do | Unblocks | Status |
|---|---|---|
| Register the nightly backup task (vault `Platform/Backups & Restore`) | The 3-night backup criterion | open |
| Turn on Docker Desktop autostart and the never-sleep power plan (vault `Platform/Collector Host`) | Collection after every restart; the 7-day criterion | open |
| Run the Trends test for OPEN-1 and OPEN-2 | Enabling Google Trends | open |
| Download the weekly US Popular products CSV from Merchant Center and import it in Data Health | Google popular (P2-29), the Shopify replacement | open (steps in the Owner To-Dos log, 2026-10-25 06:04Z) |
| Decide whether to enable `listing_images` (DEC-240) | M-2 part b on real data, matching | open |
| Label about 200 match pairs in `/admin/matching` | Matching thresholds | after real data from two sources |
| Enter real fees and duty defaults in Settings | Landed margin from real data | open |
| Read the coverage memo; pick a label source or "no defensible label yet" | Phase 6 labels | after 14 collection days |
| Vendor-data policy (DEC-010) | Whether forecasting may use a vendor series | pending owner |
| Clerk secrets in GitHub Actions | CI-4 (optional) | open |
| Google Trends API alpha; AliExpress applications | Phase 3 sources | open (lead time) |

## Open questions for the owner

- **Primary buttons:** neutral, as the design default proposes so green keeps meaning "up", or brand green? (DEC-024)
- **Raw payloads off the PC:** write them to R2 once a bucket exists? Today they stay in the local RustFS volume, which the nightly `pg_dump` doesn't cover (DEC-013, DEC-015, DEC-244).

## Phase-end checklist (every phase)

- [ ] Lint, typecheck and tests pass (Python: ruff, mypy, pytest; web: eslint, tsc, vitest; plus the Playwright smoke tests).
- [ ] End-of-phase UI checklist passes (AGENTS.md).
- [ ] §6 items done and pending are listed here (DEC-048).
- [ ] DECISIONS, BACKLOG and DATA_SOURCES are current. Vault feature notes have their status and Log updated.
- [ ] Summary to the owner (async review, DEC-049); the build moves on to the next phase.
