# Pulso — Backlog

This file holds deferred ideas and research extras that are **not** in the §11 phases and **not** folded into a vault feature note as "[Added — pending approval]" (DEC-008). Any item can be promoted at a phase gate.

**Rules**
- To promote an item, move it into the relevant vault feature note as "[Added — pending approval]" with a target phase. Delete the row here and record it in that note's Log.
- If a vault note already carries an item as pending approval, the vault note wins; remove the duplicate row here.
- The evidence column names vault notes under `Research/` (section numbers in §).
- Phase suggestions are estimates.

## Data sources

| Idea | Evidence | Suggested phase | Notes |
|---|---|---|---|
| TikTok Shop sold counts from a vendor feed (Apify or similar, about $70–180/mo) as a demand series | Trend & Ad Intelligence Sources §2.4, §2.15; 00 Research Synthesis §2a, §5.5 | Decide at Phase 1 exit | Blocked on DEC-010. TikTok's US ToS §3.4 bans automated extraction. Paid, so ask first |
| Meta Ad Library EU/UK collector moved to Phase 3 | Trend & Ad Intelligence Sources §2.5; Spec Review M4 | Only if markets expand | Not applicable under US-only (DEC-004). Meta stays in Phase 8 |
| TikTok Commercial Content API (EU ad library) | Trend & Ad Intelligence Sources §2.3 | Phase 8+, if EU is added | US-only makes it moot for now |
| YouTube Data API v3 as a demand/attention signal | Trend & Ad Intelligence Sources §2.9 | Phase 3+ candidate | The review sent this to BACKLOG |
| Reddit API mentions as a signal | Trend & Ad Intelligence Sources §2.10 | Phase 8+ candidate | Check the current API terms and pricing first |
| Google Ads Transparency Center (Search, Shopping and YouTube ads) | Trend & Ad Intelligence Sources §2.6 | Phase 8 | Complements the Ads pages |
| 17TRACK delivery-time measurement for supplier scorecards | Supplier & Fulfillment Data Sources §12; 00 Research Synthesis §3.2 gap 10 | Phase 7 (needs real orders) | About $119 per 5,000 tracking numbers. Paid, so ask first |
| Further supplier sources: Zendrop, Spocket, DSers, Alibaba/1688, Temu, eBay, Etsy, Walmart | Supplier & Fulfillment Data Sources §3–§11 | Phase 8+ | Re-check each one's terms before building (§4.2) |
| Search by screenshot across suppliers (CJ image search) | Supplier & Fulfillment Data Sources §2 | Phase 8+ | 1,000 CJ points per call and needs Level 3+. Show the quota cost in the UI |

## Intelligence and forecasting

| Idea | Evidence | Suggested phase | Notes |
|---|---|---|---|
| "Discovery winner" forecast label v2: reached N units/day within 30 days of first detection | Trend & Ad Intelligence Sources §5.3; 00 Research Synthesis §5.5; Voice of the Customer P1 | After at least 12 weeks of first-detection cohorts (Phase 6+) | The spec's momentum label stays as label v1 |
| Calendar and holiday features in the model | Spec Review M16 | After one full year of history | No calendar features before that |
| Research Winning Product Score (WPS) formula and A/B/C data grades as an alternative to §7 | Trend & Ad Intelligence Sources §5; Store Intelligence §10 | Revisit at Phase 6 | §7 definitions stand (Review M20). Grades may already appear in the provenance work |
| Decoy-resistant store data: detect anti-spy apps (StopSpy, Spy Protect) and add `stores.exclude_from_labels` | Store Intelligence §4.4, §10; 00 Research Synthesis §3.2 gap 2 | Phase 6 | Drop store-wide simultaneous bumps from Grade B counts |
| TikTok-to-Meta transfer check | Voice of the Customer §10 #7; 00 Research Synthesis §3.2 gap 15 | Phase 8+ | Needs 60–90 days of cross-channel history |

## Product features (mostly SaaS-stage)

| Idea | Evidence | Suggested phase | Notes |
|---|---|---|---|
| Search by screenshot over Pulso's own CLIP index (paste or drop into Ctrl+K) | Competitor Landscape §1 (Minea); 00 Research Synthesis §3.3 | Revisit at Phase 4 | Reuses the Phase 2 embeddings. Needs a round trip through the worker |
| Research agent that delivers a weekly evidence-cited shortlist | Voice of the Customer §9, §10 #16; 00 Research Synthesis §4 #16 | Phase 7+ | Builds on Ask Pulso. Show a cost preview |
| MCP server and public API | 00 Research Synthesis §3.2 gap 13, §3.3; Competitor Landscape (2) | Phase 8+ | §6.18 already has the public API as v3 |
| Crowding indicator (how many Pulso users saved a product) and personalised picks | 00 Research Synthesis §3.2 gap 8 | Phase 8+ (needs many users) | Meaningless with a single user |
| Honest-billing package: one-click cancel/pause, pre-renewal reminder, monthly default, usage meters, cost previews | Voice of the Customer P3, P5, §10 #3; 00 Research Synthesis §3.2 gaps 3–4 | Phase 8 (with billing) | Fold into Billing & Plans when billing is scoped |
| Beginner guided mode and budget planner ($1.5–3K realistic plan, sample first) | Voice of the Customer §7, §10 #17 | Phase 8+ | SaaS onboarding |
| TikTok Shop creator and affiliate intelligence | Voice of the Customer §10 #15; Competitor Landscape §2 | Phase 8+ | Needs TikTok Shop data (DEC-010) |
| Account-health monitor (chargebacks, payout holds, policy violations) | Voice of the Customer P9, §10 #19 | Phase 8+ | Needs store connections beyond Shopify |
| Feed optimiser for agentic storefronts and Merchant Center | Voice of the Customer §2, §10 #21 | Phase 8+ | |
| Creative diversity score and product-faithful image generation | 00 Research Synthesis §3.2 gap 12; Voice of the Customer P8 | Phase 5+ | May be folded into Creative Studio as a pending enhancement |
| Community trust layer: verified ratings of suppliers and tools | Voice of the Customer §10 #22 | Phase 8+ | SaaS only |
| Multi-channel destinations: TikTok Shop seller, WooCommerce, Amazon/eBay | Supplier & Fulfillment Data Sources §14–§15; Voice of the Customer §8 | Phase 8+ | v2 is Shopify only |
| Regional coverage and purchasing-power pricing | Voice of the Customer §6, §10 #23 | Phase 8+ | Not applicable under US-only (DEC-004) |

## Platform and process

| Idea | Evidence | Suggested phase | Notes |
|---|---|---|---|
| Orca worktree-create script that writes each worktree's `.env.local` (ports, `pulso_<slug>` database, Redis `/N`, schedulers off) | Spec Review M18; DEC-022 | When parallel Orca work starts (Phase 1+) | Until then, set `.env.local` by hand |
| Web Bot Auth signing and Shopify bot registration | Store Intelligence §2; DEC-033 | At Railway go-live, only if the crawler moves there | Needs a public bot page and a domain |
| GitHub Pro ($4/mo) for branch protection on the private repo | Spec Review (Low: git) | Only if agents merge without the owner | Paid, so ask first |
| `railway.ts` snapshot via `railway config pull` | DEC-014 | At go-live, optional | The dashboard stays the source of truth |
| RedBeat or a Redis lock for Beat | DEC-016 | Only if duplicate runs actually appear | The advisory lock plus idempotency cover v1 |
| Expand/contract migrations for zero-downtime deploys | Spec Review (agents-md finding) | SaaS stage | Not needed for single-user v1 |
| Light-mode polish | DEC-024 | Phase 8 | Light mode works but is unpolished until then |

## DOC-3 source follow-ups (2026-10-22)

| Deferred work | Evidence | When | Notes |
|---|---|---|---|
| Resolve Pinterest storage/research/ML permission before adopting the daily-snapshot proposal | DATA_SOURCES; [Developer guidelines](https://policy.pinterest.com/en/developer-guidelines), Basics / What not to do (checked 2026-10-22); vault Candidate Sources | Before adoption | Owner review / written permission; candidate and enablement unchanged. Lead records owner to-do; source note left unchanged |
| Resolve Store Leads competitive-use, republication and deletion obligations before adoption | DATA_SOURCES; [Terms](https://storeleads.app/terms) §2.1.5–9 / §2.12 (checked 2026-10-22); Store Intelligence §5 | Before adoption | Owner review / written permission; paid approval still required; vault low-risk label needs reconciliation by its owner |
| Confirm unresolved source evidence at the existing adapter/approval gates | DATA_SOURCES; Source - Keepa; Candidate Sources; Trend & Ad Intelligence Sources §2.5/8/9/11; Supplier & Fulfillment Data Sources §12 | Before the relevant adapter or vendor purchase | Keepa official entry price/redistribution; 17TRACK first paid tier/service-specific terms; Meta vendor permission clause (public terms check reached login/block); Pinterest/Meta/vendor numeric quotas; YouTube derived-history retention permission. Unverified fields are not clearance to collect |

## Phase 1 brainstorm deferrals (P1-00, 2026-10-22)

| Deferred work | Evidence | When | Notes |
|---|---|---|---|
| Redis token-bucket limiter and one Celery queue per source | Phase 1 brainstorm D1 | Only if a second collector process becomes necessary | v1: one `collect` consumer at concurrency 1 with an in-process limiter |
| Enqueue outbox for collector runs | Phase 1 brainstorm D3 | Only if P1-04's recovery tests show lost publishes | v1: run row written `queued` before publish; publish failure marks it failed |
| Coverage-memo API endpoint and Data Health card; product-level coverage | Phase 1 brainstorm (P1-10) | After Phase 2 matching exists | Phase 1 memo is a dated CLI report |
| External heartbeat monitor | Phase 1 brainstorm | With the Phase 7 alerts | Needs an account, so ask the owner first |
| Count immutable facts (FX, Keepa-style series) as of their own date in features | Phase 1 brainstorm D4; DEC-031 | Phase 6, only via an owner SPEC amendment | Until then features use only `captured_at < d+1 00:00Z` |
| Automatic five-year Trends backfill | Phase 1 note; Phase 1 brainstorm | After the Trends alpha or an approved paid tier | Paid tier needs owner approval |

## Phase 1 schema review deferral (P1-17, 2026-10-22)

| Deferred work | Evidence | When | Notes |
|---|---|---|---|
| Coverage view: mark `coverage`/`runs`/`gaps` `AS NOT MATERIALIZED` (or replace it with a `from_day` SQL function that filters `captured_at` ranges) | P1-16 schema review finding 5; DEC-060 | Once `collector_run_targets` passes ~1M rows | Verify with EXPLAIN; DH-1 always passes a day bound. Current materialized CTEs aggregate all history before the outer day filter |
