# data-07: CJ first run fails before any request — the worker had no CJ plan

Orca task `task_55dec610dbe1`, dispatch `ctx_a0eae5148f31`, done by a Claude worker. The branch is `CodySpooner/data-07-cj-prerun-fix` on `origin/main` `2b87388f`. Nothing was pushed or merged. No request went to CJ or any other data source. No `.env` file was read or edited, nothing under `C:\dev\pulso` or the collector compose project was touched, and no file under `infra/collector/` or `infra/scripts/collector*` changed. **Risky merge (live-collector path): it joins the next cross-review batch.**

## Root cause

**Path (a), the `source.key not in PLANS` half.** No `tasks.PLANS["cj"]` existed on `d341e64`, on `main` or on any branch (`git log --all -S'PLANS["cj"]'` and `-S cj_plan` find nothing). `registration.py` registered only FX, Shopify, Trends and listing images. DEC-112 had left CJ "scheduler selection/registration absent", and the vault note said "no scheduler", but DEC-136 enabled the source on the host anyway. So every CJ run would fail this way: catch-up, the 04:00Z catalog and manual runs alike.

Evidence, replayed as on `d341e64` in `apps/workers/tests/test_cj_prerun.py::test_catchup_after_enable_reaches_execute_run`:

1. `enable cj` (infra/scripts/collector/sources.py `enable`) only flips `enabled` and `status=active`, and it needs at least one approved `cj_categories` target.
2. `ops.heartbeat` runs every 5 minutes, so the first one after 17:09:42Z ran at 17:10:00Z. It calls `audit` → `audit_slots` → `recover_source`. On Sunday 2026-10-25 the current-period missing slots were `freight:2026-W43` (due Monday 19 Oct 04:30, still in its ISO week) and `catalog:2026-10-25` (04:00 today). `slots()` walks day by day, so the catch-up took **`freight:2026-W43`**.
3. `collect_run`: the source was enabled, but `"cj" not in PLANS`, so it raised `ValueError("Source disabled or adapter unavailable")`. The handler stored `type(exc).__name__` in both columns.

The red test printed `freight:2026-W43 failed None ValueError ValueError` (slot, status, `started_at`, `error_code`, `error_message`). That matches the host row exactly, with no request sent.

| Candidate | On `d341e64` | Verdict |
|---|---|---|
| (a) `not source.enabled` | the source was enabled | no |
| (a) `source.key not in PLANS` | no CJ factory registered | **fired** |
| (b) plan budget ≥ soft limit | `Settings._collector_limits` (settings.py) refuses to load unless every source budget < `collect_soft_time_limit_seconds` < hard. CJ's plan uses `cj_wall_time_seconds` (default 1800 < 3600) | can't fire with valid settings; reachable only through an unvalidated `model_copy` (tested) |
| (c) job prefix unsupported | needs a factory | would have fired next for `freight` (no plan exists for it) |
| (d) error inside `PLANS["cj"]` | no factory | n/a |
| Key naming (`cj` vs DEC-136's `cj_dropshipping`) | `cj` everywhere: `SEED_SOURCES`, `COLLECTION_SLOTS`, `stale_after`, collector `SOURCES` | not a cause |

## What changed

| Commit | What |
|---|---|
| `6797dca0` | Worker: named pre-run codes, `Plan.collect`, `PLANS["cj"]` (catalog), freight slot removed; CJ `CatalogAdapter`; tests |
| `8e0882c4` | DEC-321 (proposed (data-07)) with parts a and b |
| (tip) | this report |

- **`apps/workers/src/pulso_workers/tasks.py`** (+44/−17). `PreRunFailed(code, message)` is raised for every refusal before `execute_run`, and the handler stores its code and fixed message. The codes are `source_unavailable`, `unknown_job` (the factory raised the new `UnknownJob(ValueError)`), `plan_failed` (any other factory exception; the message is `Plan failed: <ExceptionClass>`) and `plan_budget_invalid`. Exceptions after the pre-run checks keep storing their class name, as before. The `collection_failed` log's `error_type` is now that code. `Plan` gains an optional `collect(session, run_id, settings, stop_exceptions)`; when set, it replaces the direct `execute_run` call.
- **`apps/workers/src/pulso_workers/registration.py`** (+24/−4). The four existing factories raise `UnknownJob` instead of `ValueError` (a subclass, so every `pytest.raises(ValueError)` still holds). The new `cj_plan` accepts `catalog` only and reads the enabled names from `approved_targets(session, "cj")`; when there are none it raises `ValueError` (→ `plan_failed`). It builds `cj.CatalogAdapter(names)`, uses `cj_wall_time_seconds`, and sets `collect=` to call `cj.collect(..., adapter=adapter, stop_exceptions=stop)`.
- **`packages/sources/src/pulso_sources/cj/__init__.py`** (+25). `CatalogAdapter(CJAdapter)` has one `cj_category_resolution`/`catalog` target. Its lazy request stream yields `/product/getCategory` first, then `category_plan(self.tree, names)`'s panels (`resolve`, then `dry_run` < 20,000 points, then `listV2`). `parse` keeps a body whose `data` is a list (the tree) and returns no records; any other body goes to the existing `parse`. `cj.collect` gains `stop_exceptions=()`, passed through to `execute_run`.
- **`apps/workers/src/pulso_workers/schedules.py`**: `("cj", "freight", 30, 4, "1")` is replaced by a comment (DEC-321b, below).
- **`apps/workers/README.md`**: the Plan signature, the job list, the pre-run codes and the CJ wiring.
- **Existing tests:** three assertions change from `ValueError` to `source_unavailable` (`apps/workers/tests/test_registration.py`, `packages/sources/tests/shopify_stores/test_registered_plan.py`, `test_variants.py`). `test_recovery.py::test_spent_weekly_catchup_does_not_block_daily_slot` monkeypatches the freight row back into `ops.COLLECTION_SLOTS`, so it still covers weekly + daily slots.
- No migration, dependency, settings, rate-limit, budget, retry, block-rule, framework, API or UI change. The collector CLI's `status` already prints `error_code`, so the new codes show there without a change to the protected scripts.

### Why the tree is a framework request

`category_plan` needs a `getCategory` body, and no production code fetched one. Fetching it inside `CatalogAdapter.targets()` as the target's first request sends it through `_capture` and CJ's hook. That gives it the COLLECTORS_LIVE/worktree guard, an honest UA, raw capture, `BLOCK_STATUSES` accounting, body error codes, and the 1600014 disable (tested). The alternative was a side fetch through the transport, the way the DEC-156 renewal does it; that would skip raw evidence and HTTP block accounting for the tree. `getCategory` is not in `POINTS`, so it reserves nothing.

### DEC-321b: CJ freight is unscheduled (coordinator's choice A)

`freight` cannot get a real plan: DEC-112's tracked product and variant IDs are caller-selected, and nothing selects them. At 18:16Z I asked the coordinator (A: drop the slot, B: keep it failing as `unknown_job`, C: define a selection now), with A as the stated default. The first 10-minute wait timed out. On resuming, the coordinator chose **A** and asked for the BACKLOG row; C (a selection policy that spends CJ points) is logged for the owner. Under B, every Monday 04:30 run fails, the audit keeps CJ `overdue` all week (`latest[freight]` never succeeds), and the week's first catch-up is spent on freight. To restore the slot, add the line back together with a freight plan. A freight run already queued now fails as `unknown_job`.

## Acceptance

| # | Criterion | Evidence |
|---|---|---|
| 1 | Failing test first reproducing 17:10Z, then green | `test_catchup_after_enable_reaches_execute_run`: red before the fix (`started_at` None; printed `freight:2026-W43 failed None ValueError ValueError`). Green after: the catch-up is `catalog:2026-10-25`, `started_at` is set, and COLLECTORS_LIVE=off stops it as `CollectorsLiveDisabled` with 0 requests |
| 2 | One test per pre-run path asserting its code | `test_source_unavailable[cj]` (disabled), `[no_plan]` (key without a factory), `test_unknown_job` (`freight:2026-W43`), `test_plan_failed` (seed not approved), `test_plan_budget_invalid` (unvalidated 10⁶ s budget). Each asserts the exact code and message, so no setting value can appear in the message |
| 3 | Catch-up and scheduled catalog runs reach `execute_run`, fake adapter, no network | `packages/sources/tests/cj/test_registered_plan.py::test_catchup_and_scheduled_catalog_reach_execute_run[catchup/schedule]`, through `tasks.collect_run` and `PLANS["cj"]` with the CJ harness (`HTTPSConnection` raises; fake `Transport.http`). Sent: `getCategory`, then 15 × `listV2`; `success`, `complete`; `http_requests` 16; 750 points reserved; 16 raw captures; 2 change-only snapshots. Also: an unresolved seed stops after the tree with nothing paid (`partial`/`cj_category_unresolved`), and 1600014 on the tree disables CJ (`blocked`, `cj_api_disabled_inactivity`) |
| 4 | ruff, format, mypy ×2, full workers + sources pytest | see Checks |
| 5 | Report: root cause, host actions, vault lines | this file |

**Mutations** (each reverted after use). Removing `PLANS["cj"]` → 8 of the 10 new tests fail. Removing the `UnknownJob` branch → 1 fails. Removing the tree request → 5 fail. Restoring the bare `ValueError` for `source_unavailable` → 2 fail. Parsing the tree as a page → 3 fail.

## Checks

All on Windows, Python 3.14 via `uv`, after the rebase on `2b87388f` (DECISIONS append conflicts only, both sides kept).

| Check | Result |
|---|---|
| `uv sync --locked --all-packages` | clean |
| `uv run ruff check .` / `uv run ruff format --check .` | all passed / 430 files formatted |
| `uv run mypy` / `uv run mypy --platform linux` | no issues in 258 files / no issues in 258 files |
| `pytest apps/workers packages/sources` on a throwaway `pgvector/pgvector:0.8.7-pg18-trixie` (127.0.0.1:55977, removed after) | **840 passed, 0 skipped** |
| `pytest apps/api packages/core packages/ml infra` on the same database | **not completed**: Claude Code stopped the run because the PC was low on memory; it was not restarted. Nothing in those packages imports `pulso_workers`, `COLLECTION_SLOTS` or the CJ package (grep), so CI's full run is the check there |

On SQLite only (no `TEST_DATABASE_URL`), workers + sources give 752 passed and 88 skipped. A first PostgreSQL attempt hit `type "vector" does not exist` because my own earlier background run was still holding the extension in its schema on the same database. The suites above ran one at a time on a fresh container. No web or UI change, so the UI checklist doesn't apply.

## What the lead must do on the host

1. Merge, and add this to the next cross-review batch (live-collector path: fetch order, the tree request, the pre-run codes).
2. **Collector update to the merged commit** before 04:00Z, through the repo's collector scripts per DEC-073 and Lead Playbook §6, only while `C:\dev\pulso\.collector-hold` is absent. There is no migration (head unchanged). Worker and beat must both restart on the new image: the worker for `PLANS["cj"]`, beat for the schedule without `cj.freight`. CJ stays enabled; no re-enable or seeds change is needed.
3. **Next CJ slot:** `cj.catalog` at 2026-10-26 04:00Z (Monday; no freight run at 04:30 any more). Today's catch-up is already spent (one per source per UTC day), so nothing runs earlier unless someone starts a manual run from Data Health. That costs real points (750 per resolved category) and is the lead's call.
4. **Check Data Health / `status` after 04:00Z.** Expected outcomes, from best to worst:
   - `success`: the tree, then the panels, with listings and snapshots appended.
   - `partial`/`cj_category_unresolved`: an approved seed name is not an exact path in CJ's real tree (the vault notes the ten draft names were never resolved against real data). Only the free tree request is sent and stored as raw evidence. Fix the seed names, not the code.
   - `partial`/`cj_points_unknown`: CJ's `getCategory` reply carries no `pointsInfo` (unverified live, DEC-156), so the first `listV2` is refused after the one free renewal. This is an existing gate, unchanged.
   - `CollectorsLiveDisabled`: the host's live flag is off.
   - A body or HTTP block code (`cj_api_disabled_inactivity`, `cj_rate_limited`, `http_429` and so on) follows the existing DEC-035/105/136 rules.
   - A pre-run code (`source_unavailable`, `plan_failed`, and so on) now names the gate.
5. The failed 17:10Z `freight:2026-W43` row stays as history. After the update, freight slots are no longer expected, so W43 stops counting as missing.

## Proposed vault changes (for the lead, after merge)

I edited only the body of `Data/Sources/Source - CJ Dropshipping` (a dated `[!warning]` finding under Schedule) and appended one Session Log entry. Everything else is for the lead:

- **`Data/Sources/Source - CJ Dropshipping` Log:** `- 2026-10-25 — data-07 merged (claude) <hash>, DEC-321: first host run failed pre-run because no worker plan existed; PLANS["cj"] now runs catalog (captured getCategory, then approved panels through cj.collect); freight unscheduled until a tracked selection exists (DEC-321b); pre-run codes source_unavailable / unknown_job / plan_failed / plan_budget_invalid.` The note's `status: planned` should probably become `in-progress`, since the source is enabled and now has a worker plan.
- **`Data/Sources/Source - CJ Dropshipping` Schedule table:** mark `cj_freight_us` "unscheduled (DEC-321b)".
- **`Platform/Workers & Scheduling`:** in the canonical table, mark row `cj.freight` (`30 4 * * 1`) "unscheduled until a tracked-product selection exists (DEC-321b)". In the Plan paragraph, add `collect=None`, the four pre-run codes, and the job list without `freight`. Log: `- 2026-10-25 — data-07 merged (claude) <hash>: CJ catalog registered via Plan.collect; named pre-run codes; cj.freight unscheduled (DEC-321).`
- **`Platform/Collector Host` Log:** `- 2026-10-25 — data-07: CJ's first run (17:10Z catch-up) failed pre-run because no worker plan existed; fixed in <hash>; host update needed before the 04:00Z catalog.`
- **`Features/Data Health` Log:** `- 2026-10-25 — data-07 merged (claude) <hash>: pre-run refusals show source_unavailable / unknown_job / plan_failed / plan_budget_invalid instead of ValueError (DEC-321). No UI change.`
- **Phase note** (Phase 1 or current): `- 2026-10-25 — data-07 merged (claude) <hash>: CJ worker plan registered (catalog); first live CJ run is the 04:00Z slot after the host update.`

### Backlog rows (added to `docs/BACKLOG.md` at the coordinator's request)

| Deferred work | Evidence | When | Notes |
|---|---|---|---|
| CJ tracked-product selection and the freight / details-stock jobs | DEC-112, DEC-321b | With watchlists × CJ matching, or an owner selection rule | Then restore `("cj", "freight", 30, 4, "1")` and register `freight` (and the vault's daily `cj_details_stock`) in `cj_plan`. Points: 2 × 10 per tracked product, 10 per freight quote |
| Weekly `cj_categories` tree job (vault Schedule: Sun 00:30) | DEC-321a | When daily tree requests matter | Each catalog run now sends one free `getCategory`. A stored weekly tree would save it, but needs a reader for the stored raw payload |
| PostgreSQL-backed CJ registered-plan test | `test_registered_plan.py` runs on SQLite | Next CJ worker change | Covers the same flow under real locks and JSON types |
