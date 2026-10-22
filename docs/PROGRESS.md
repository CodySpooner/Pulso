# Pulso — Progress

**Last updated:** 2026-10-22

## Current status

**Phase 0 built; owner-gated items pending. Phase 1 in progress (continuous build since 2026-10-22, DEC-049).** The hourly lead automation merges lanes and keeps Claude and Codex workers busy (vault `Agents/Lead Playbook`, `Agents/Lead State`).

- Phase 0: every build task is merged and the UI gate passed (P0-09, DEC-059). What's left needs the owner (see "Phase 0 summary" below; full summary in the vault `Phases/Phase 0 - Foundation`).
- Phase 1: P1-01 schema migration 0002 merged (`4283e80`, DEC-060). Running: P1-02 raw storage (Codex), P0-16 Codex review of P0-09, P1-16 Claude review of P1-01 plus the P0-14 fix check. Critical path P1-01 → P1-03 → P1-05 → P1-11 → P1-12 (15 tasks in the vault Phase 1 note).
- Local checks on `4283e80`: ruff + format, mypy (45 files), pytest 127 passed / 17 DB skips, eslint, tsc, Vitest 255, web build, one Alembic head (0002), `gen:api` clean.
- CI on GitHub is refused before it starts (account billing), so merges run on local checks until the owner fixes billing.
- Docker is not installed on the PC yet, so compose, migration and image checks are unverified locally.
- Data collection has not started. Every week before collection starts pushes the first forecast date back by a week (DEC-044).

## Phase status

| Phase | Name | Status | Notes |
|---|---|---|---|
| 0 | Foundation | built; owner items pending | All build tasks merged; UI gate passed. Pending owner: WSL2 + Docker Desktop, Clerk dev keys, GitHub billing + Clerk CI secrets, the spike run, the WEB-6 screenshot review, DOC-1 amendment approvals |
| 1 | Data engine | in progress | P1-01 schema merged (DEC-060); P1-02 and reviews running. Collection runs on the home-PC collector host (DEC-001). Needs: the CJ answer (DEC-009), approved seed lists (DEC-011), a SerpApi account |
| 2 | Core product experience | not started | |
| 3 | Signals expansion | not started | The AliExpress app review has a lead time; start the application now |
| 4 | Scores and workflow | not started | |
| 5 | AI layer | not started | Needs an Anthropic API key and AI caps at entry |
| 6 | Forecasting v1 | not started | Build work may start after 6–8 weeks of collection. First 14-day forecasts need about 12 weeks of continuous collection, 30-day about 17 (DEC-044) |
| 7 | Store operations | not started | Review the Shopify API Terms before building the app (DEC-003) |
| 8 | Expansion and launch prep | not started | Railway go-live can happen earlier, at the owner's call (DEC-001) |

## Phase 0 summary (2026-10-22, lead run 4)

- **Done:** spine (S-1, S-2; DEC-056); data model and API (DB-1..5, API-1..5, `4e16884`, DEC-051) with review fixes (P0-14, `93539d5`, DEC-057); workers, images and CI (WRK-1, IMG-1/2, CI-1/2/3/5, `1ea56fb`, DEC-050); web shell (WEB-1, 3, 4, 5, 8, `f03e4e0`, DEC-053..055); typed client, root scripts, e2e job (WEB-7, CI-4 built, `dcaaf27`, DEC-058); UI gate and `/admin/ui` (WEB-9, `f012f7f`, DEC-059); docs (DOC-2, DOC-3, DOC-4 paths); spike script and seed draft (SPK-1, `5a9dd45`, DEC-052); three cross-reviews (P0-08a, P0-08b, P0-15) with every finding fixed except the spike size (owner).
- **Built, check pending owner:** S-4, S-5, DOC-4 setup and the 17 DB tests (Docker); WEB-2 sign-in (Clerk keys); CI-4 and CI green (billing + Clerk secrets); WEB-6 (screenshot review).
- **Not started, owner-gated:** SPK-2/SPK-3 spike run (`PULSO_BOT_CONTACT`, spike size); DOC-1 SPEC amendments (approvals, R-05 first).
- **Lead, in flight:** P0-16 review of P0-09; P0-14 fix check (P1-16). S-3 done (Codex quoted the scheduler rule in P0-15).
- **§6 items (DEC-048):** none complete yet. Phase 0 ships foundations only: the empty Daily Pulse (§6.1, Phase 4), the Ctrl+K stub (§6.18, search in Phase 2), the PWA manifest (§6.18, Phase 4) and the added `/admin/ui` gallery (WEB-9). Every other §6 item is pending in its phase (vault `00 Home`).

## Done (pre-Phase 0)

- **Market research, verified 2026-10-22.** Six notes in the vault's `Research/` folder: 00 Research Synthesis, Competitor Landscape, Supplier & Fulfillment Data Sources, Trend & Ad Intelligence Sources, Store Intelligence, Voice of the Customer.
- **Spec review, 2026-10-22.**
  - Six lenses (builder, data, ML, infra, product, consistency), adversarially verified.
  - About 90 findings merged into 47 items: 1 blocker, 5 high, 22 medium, plus the low items.
  - Lives in the vault at `Research/Spec Review 2026-10-22`.
- **Owner decisions recorded** in `docs/DECISIONS.md`:
  - 8 approved (DEC-001 to DEC-008);
  - 3 pending (DEC-009 to DEC-011);
  - 37 proposed defaults (DEC-012 to DEC-048).
- **`docs/SPEC.md` amended** for owner-approved decisions only (Amendment log A-1 to A-10).
- **Repo moved** to `C:\dev\pulso`, outside OneDrive, with `.gitignore` in place.
- **Agent guides:** `AGENTS.md` (canonical, for Codex and Claude) and `CLAUDE.md` (imports AGENTS.md).
- **Docs:** `DECISIONS.md`, `PROGRESS.md`, `BACKLOG.md` and `DATA_SOURCES.md` written. `DATA_SOURCES.md` was seeded from the vault `Data/Sources/` notes, with a seed-list availability pre-check (one `/meta.json` per candidate store, 2026-10-22). Before each adapter is built, re-check that source's terms and add to it (§4.2). The DEC-003 `/products.json` spike (Phase 0) is logged there when it runs.
- **Obsidian vault planning notes**, created in parallel on 2026-10-22:
  - one note per feature (`Features/`);
  - data and sources (`Data/`);
  - scores and forecasting (`Intelligence/`);
  - platform (`Platform/`);
  - design (`Design/`);
  - phases and owner to-dos (`Phases/`);
  - agent collaboration (`Agents/`), templates (`Templates/`) and the `00 Home` index.

## Next

1. **Owner reviews asynchronously** (DEC-049): the build continues; the owner can veto any proposed decision (DEC-012 onward) and any "[Added — pending approval]" enhancement at any time.
2. **Owner clears the Phase 0 leftovers:** WSL2 + Docker Desktop, the Clerk dev app and CI secrets, GitHub billing, the spike run, the commit identity (see the to-dos below).
3. **Phase 1 build** (vault `Phases/Phase 1 - Data Engine`): P1-02 raw storage now, then P1-03 framework once P1-01 + P1-02 are in, then the adapters. Live collection waits for the seed approval (DEC-011) and the owner's go-ahead for the collector host.

## Owner to-dos (summary)

The canonical, maintained list is the vault note `Phases/Owner To-Dos`.

| # | To-do | When | Cost | Status |
|---|---|---|---|---|
| 1 | Install WSL2 and Docker Desktop: in an admin PowerShell run `wsl --install --no-distribution`, reboot, then `winget install Docker.DockerDesktop` | now (the only hard blocker) | free | open |
| 2 | Review the Phase 0 plan, the proposed decisions and the pending-approval enhancements asynchronously (veto what you don't want; the build continues, DEC-049) | any time | free | open |
| 3 | Answer DEC-009: does your CJ account place an order at least every 30 days? | before Phase 1 | free | open |
| 4 | Confirm the vendor-data default (official sources + CSV, revisit at Phase 1 exit) (DEC-010) | before Phase 1 | free | open |
| 5 | Approve the drafted seed lists, adding your own store domains (DEC-011) | before Phase 1 | free | open |
| 6 | Confirm the commit identity: `CodySpooner` + GitHub noreply email (DEC-023) | before Phase 0 | free | open |
| 7 | Create a Clerk application (development instance); put the keys in `.env` | before Phase 0 | free tier | open |
| 8 | Collector host setup: power plan sleep = Never while plugged in; Docker Desktop "start when you sign in"; Windows Update active hours. Decide on auto sign-in after reboots | before Phase 1 | free | open |
| 9 | Confirm the OneDrive backup folder and check your OneDrive quota (5 GB on the free plan) (DEC-015) | before Phase 1 | free | open |
| 10 | Create a SerpApi account (free tier, 250 searches/mo) | before Phase 1 | free | open |
| 11 | Provide the CJ API key, from a transacting account | before Phase 1 | free API | open |
| 12 | Apply for the Google Trends API alpha | now (lead time) | free | open |
| 13 | Start the AliExpress affiliate and Open Platform app reviews, and ask in writing whether storing daily derived metrics is allowed | now (lead time, Phase 3 source) | free | open |
| 14 | Optional: create a Cloudflare account, an R2 bucket and a scoped token (off-machine raw payloads and backup copies now; required at go-live) | before Phase 1 (optional) | free up to 10 GB | open |
| 15 | Optional: create a Railway account and the CLI (`npm i -g @railway/cli`, then `railway login`) to measure Shopify blocking from Railway in the spike | before Phase 0 spike (optional) | trial credit | open |
| 16 | Shopify ToS risk acceptance | — | — | done (DEC-003) |
| 17 | Move the repo out of OneDrive | — | — | done (DEC-005) |
| 18 | At go-live: approve the Railway plan and its usage limit; enable volume backups | at go-live | estimated ~$50–70/mo (guess) | deferred |
| 19 | Buy a pulso domain (needed for a Clerk production instance and a public Track Record) | at go-live | ~$10–15/yr | deferred |
| 20 | At Phase 5 entry: provide an Anthropic API key and set the AI caps (default $20 workspace + $20 system, hard stop) | Phase 5 | up to the caps | deferred |
| 21 | Optional: check whether your Merchant Center account can see Best Sellers reports | later | free | open |

## Open questions for the owner

- **Shopify after go-live:** keep the crawler on the home PC as its permanent egress, or move it to Railway and accept that it switches off if blocked? (DEC-003)
- **Primary buttons:** neutral, as the design default proposes so green keeps meaning "up", or brand green? (DEC-024)
- **Raw payloads on the collector host:** write them to R2 once the bucket exists, for an off-machine copy? Otherwise they stay in a local volume that the nightly `pg_dump` doesn't cover (DEC-013, DEC-015).
- **Merging PRs:** may agents merge task PRs after green CI and a peer-agent review, or must the owner merge each one? (vault `Agents/Agent Collaboration Protocol`)

## Phase-end checklist (every phase)

- [ ] Lint, typecheck and tests pass (Python: ruff, mypy, pytest; web: eslint, tsc, vitest; plus the Playwright smoke tests once they exist).
- [ ] End-of-phase UI checklist passes (AGENTS.md).
- [ ] §6 items done and pending are listed here (DEC-048).
- [ ] DECISIONS, BACKLOG and DATA_SOURCES are current. Vault feature notes have their status and Log updated.
- [ ] Summary to the owner (async review, DEC-049); the build moves on to the next phase.
