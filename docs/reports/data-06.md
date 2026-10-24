# data-06: FX first-run check — each check names its error_code; next-day rows are skipped

Orca task `task_88bf69c1fa92`, dispatch `ctx_95bee58a03bc`, done by a Claude worker. The branch is `CodySpooner/data-06-fx-first-run` on `origin/main` `54be445`. Nothing was pushed or merged. No request went to `api.frankfurter.dev` or any other data source. Only the public docs pages `frankfurter.dev/` and `frankfurter.dev/javascript/` were read.

## What changed

| Commit | What |
|---|---|
| `b48d202` | Adapter: one `ValueError` subclass per check; `upsert` skips rows dated after the capture's UTC date; tests |
| `d30dd33` | DEC-230 (proposed), `docs/DATA_SOURCES.md` Frankfurter section, fixtures README |
| (tip) | this report |

- **`packages/sources/src/pulso_sources/fx_frankfurter/__init__.py`** (+32/−9). It adds `FxNotRateArray`, `FxDuplicateRow`, `FxCaptureMetadata`, `FxUnsupportedRequest` and `FxBackfillRange`, each a plain `ValueError` subclass, so every existing `except ValueError` and `pytest.raises(ValueError)` still holds. The future-date check in `upsert` changes from a raise to a filter (DEC-230 b). `UpsertStats.unchanged` now counts only the rows kept.
- **`packages/sources/tests/fx_frankfurter/test_fx_run.py`** (new). This replays the first run through `execute_run`, as `enqueue_run(trigger="catchup", slot_key="fx:2026-10-24")` with `plan(session, 2026-10-24)`. The clock is frozen at 2026-10-24 18:50Z. The fake `FrankfurterAdapter.fetch` serves a synthetic backfill body to the `from`/`to` request and the test's body to latest. S3 is in memory. `HTTPSConnection` is replaced by a mock that raises, so a real connection attempt would show up as `error_code` `AssertionError`.
- **`test_fx.py`**: two assertions changed. `backfill(start > end)` now expects `FxBackfillRange`, which is stricter. The live adapter's upsert of rows dated after the capture now returns `UpsertStats(unchanged=1)` instead of raising, which is the behaviour DEC-230 changes.
- No migration, dependency, CI, schedule, rate-limit, block-rule or framework change. The framework still stores `type(exc).__name__` as both `error_code` and `error_message`.

## Hypotheses: what the code could produce, and what each yields now

The framework catches per target, records `type(exc).__name__`, and marks the target `partial` once any request in it has a raw payload. FX's first run is one target: backfill 2025-01-01..2026-10-23, then latest.

| Cause | Before (verified through the lifecycle) | Now |
|---|---|---|
| **(1)** Latest row dated after the capture's UTC date (18:50Z is already 10-25 east of UTC+5:10; the docs say blended latest can lead a single provider by a day) | `partial` / `ValueError` | **`success` / null.** The row is skipped and every other row is stored (test: 4 of 5 stored, 1 skipped, both raw payloads kept) |
| **(2a)** Body is a JSON object, not an array | `partial` / `ValueError` | `partial` / `FxNotRateArray`; backfill rows kept |
| **(2b)** NDJSON body | `JSONDecodeError`, **not `ValueError`, so ruled out** | unchanged |
| **(3)** Duplicate pair/date in one capture | `partial` / `ValueError` | `partial` / `FxDuplicateRow`; backfill rows kept |
| Bad row (unsupported currency, bad date or rate) | `ValidationError`, **ruled out** | unchanged |
| Naive capture time or bad parser version | `ValueError` (not reachable live: the lifecycle always passes an aware UTC time and `parser_version="1"`) | `FxCaptureMetadata` |
| Non-blended request param | `failed` / `ValueError` (not reachable from `plan`) | `failed` / `FxUnsupportedRequest`, before any connection |
| `backfill(start > end)` | `ValueError` (not reachable from `plan`, which only calls it when start ≤ end, and never inside a run) | `FxBackfillRange` (unit test; it can't enter a run) |

Causes (1), (2a) and (3) all reproduce the live result exactly. The docs (re-checked 2026-10-24) say `/v2/rates` "returns a flat array, one row per quote" and blends providers by default. NDJSON comes only when `Accept` asks for it, and the adapter sends `application/json`. No range-response schema is published. So (2a) and (3) are undocumented shapes: they keep failing the capture under their own codes rather than being guessed at. (1) is consistent with the docs and with the time of the run, so it is the most likely cause, but no evidence here proves it.

## What the next live run will show

These hold once this branch is merged and the collector host is updated to include it.

- **Cause was (1):** `latest_run` is `success` with `error_code` null. In the run drawer, `fetched − inserted − unchanged` is the number of next-day rows skipped. If the first run's backfill committed (it does when latest is the request that fails), the next plan starts from the stored watermark, not 2025-01-01.
- **Cause was (2a) or (3):** `partial` with `FxNotRateArray` or `FxDuplicateRow`. Then someone needs one example of the real shape (an owner-run request or the raw payload read on the collector host) before the adapter parses it.
- **Cause is something else:** if it is still a bare `ValueError`, it didn't come from an FX check. The remaining sources after a capture are raw storage: `read_capture` ("Capture has no stored body", "Raw capture SHA-256 mismatch"), or `store_capture`'s checks on the second request, since the target is already `partial` from the first. Any other code is the exception's own class name.
- **Before this branch reaches the host:** the old code still runs. The 2026-10-25T17:00Z slot can succeed or fail on its own, depending on whether a provider is ahead of UTC at that time and whether the shape repeats.

## Checks

All run on Windows with Python 3.14 via `uv`, after the rebase on `54be445`, which needed no changes.

| Check | Result |
|---|---|
| `uv run ruff check .` / `uv run ruff format --check .` | pass / 223 files formatted |
| `uv run mypy` / `uv run mypy --platform linux` | no issues in 143 files / no issues in 143 files |
| `uv run pytest` (all Python) | 1322 passed, 205 skipped, 1 warning (from outside `packages/sources` and `apps/workers`) |
| FX + framework + imports | 244 passed, 58 skipped (baseline before the change: 237 passed, 58 skipped; +7 new) |

- **Red before green:** before the adapter change, 5 of the 7 new lifecycle tests failed with `ValueError`, and the 2 rule-out cases passed.
- **Unverified locally (no Docker):** PostgreSQL-marked tests are skipped. The FX tests run `ON CONFLICT DO NOTHING` on SQLite, as before. CI covers PostgreSQL.
- No web or UI change, so no UI checklist items apply.

## Proposed vault changes (for the lead, after merge)

I edited only note bodies: `Data/Sources/Source - Frankfurter FX` (an error-code table and a "First live run" section) and `Features/Data Health` (an "FX error codes name the check" section). Statuses, ticks and Log lines are left to the lead:

- **`Phases/Phase 1 - Data Engine` Log:** `- 2026-10-24 — data-06 merged (claude) <hash>: FX first-run check — each Frankfurter check has its own error_code (FxNotRateArray, FxDuplicateRow, FxCaptureMetadata, FxUnsupportedRequest, FxBackfillRange); a rate dated after its capture's UTC date is skipped from that capture, the rest stored (DEC-230). Next live FX run after update: success/null if the cause was a next-day row, otherwise the code names the check.`
- **`Features/Data Health` Log:** `- 2026-10-24 — data-06 merged (claude) <hash>: FX error codes name the failing check; bare ValueError on FX now means storage/framework (DEC-230). No UI change.`
- **`Data/Sources/Source - Frankfurter FX` Log:** `- 2026-10-24 — data-06 merged (claude) <hash>: error code per check; next-day rows skipped from a capture, not stored early (DEC-230). First-run check re-runs at the next live run after update.`
- **`docs/DATA_SOURCES.md`:** the Frankfurter row's status (summary table and section `Status:`) still says `planned` although the source is enabled on the collector host. I left the status for the lead.
- **Improvement Backlog row (proposed):** "FX same-day early blends: the 17:00Z latest stores same-day blended rates before providers that publish later that UTC day; first-rate-wins (DEC-088) keeps that early blend. Options: move the FX slot later in the UTC day, or take latest only for dates before the capture day and leave the capture day to the next day's backfill. Needs a DEC; no live evidence yet."
