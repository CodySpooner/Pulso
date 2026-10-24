# data-05: collector `status` reports Data Health

Orca task `task_d484fd9171ce`, dispatch `ctx_3ff07c5ff534`, done by a Claude worker. The branch is `CodySpooner/data-05-collector-health` on `origin/main` `ed76039`. Nothing was pushed or merged.

> [!warning] Protected path: owner merge
> This branch changes `infra/scripts/collector/` (AGENTS.md §6, Lead Playbook §6), so the lead must not auto-merge it. After the owner merges, `update` must rebuild the worker image before `status` can report `data_health` (see "After the merge").

## What changed

| Commit | What |
|---|---|
| `bf94d99` | `status` gains `data_health`; the container module gains a `health` op; tests |
| `29be169` | DEC-210 (proposed) |
| (tip) | this report |

- **`infra/scripts/collector/__main__.py`** (+18 lines, `status` branch only). When collector Postgres is running and `alembic_revision` is non-empty, `status` runs `docker compose -p pulso-collector … run --rm --no-deps -T worker python -m infra.scripts.collector.sources health` through the existing `checked` runner, which rechecks `.collector-hold` first. It parses the last output line, as `seeds`/`enable`/`disable` already do. Otherwise `data_health` is `null`. Every guard is unchanged: clean checkout, hold file, op lock and journal. No other op changed.
- **`infra/scripts/collector/sources.py`** (+76 lines). `health(session)` runs a few plain SELECTs, because the API's Data Health helpers are not in the worker image (`uv sync --package pulso-workers`). `main` runs `SET TRANSACTION READ ONLY` as the first statement of the `health` transaction. The worker Dockerfile already copies this module, so it needs no change.
- No migration, schema change, new dependency or new op name. The source still contains none of the strings `down`, `-v`, `volume rm`, `downgrade` or `prune` (`test_forbidden_package_source` passes).

## `data_health` shape

Only the listed columns are selected, so `config` (seed entries and private domains), run `params`, `error_message`, `disabled_reason`, payloads and settings never leave the database. Times are UTC ISO 8601. Illustrative values:

```json
{
  "as_of": "2026-10-24T02:10:00+00:00",
  "heartbeats": [{"host": "3f2a9c1d7b4e", "at": "2026-10-24T02:08:31+00:00", "age_seconds": 89}],
  "sources": [
    {
      "key": "fx_frankfurter",
      "enabled": false,
      "status": "disabled",
      "retry_not_before": null,
      "latest_run": null,
      "runs_24h": {},
      "open_gaps": 0,
      "newest_open_gap": null
    }
  ]
}
```

- `heartbeats`: the newest 5 hosts, newest first, each with its latest `at` and `age_seconds` at `as_of`. The ops heartbeat uses the container hostname, so every rebuilt `worker-ops` container adds a host; the cap keeps the list short (DEC-210 a).
- `sources`: every `sources` row ordered by key, including the `backup` pseudo-source. `latest_run` is the highest run id (`status`, `started_at`, `finished_at`, `error_code`). `runs_24h` counts runs by status whose `queued_at` falls in the last 24 h (DEC-210 b). `open_gaps` counts unfilled `collection_gaps` rows, and `newest_open_gap` gives the latest-starting one's `slot_key`, `slot_start`, `slot_end` and `reason`.
- `data_health` is `null` while Postgres is stopped, and also while Postgres runs with no Alembic revision (a first boot that failed before `migrate`), where the tables don't exist yet.
- **Fail closed (DEC-210 c).** If the container step fails, `status` fails (exit 1, journaled as `Operation failed: RuntimeError`); it never prints a report without `data_health`.

## Tests

| Test | Proves |
|---|---|
| `test_sources.py::test_health_reports_heartbeats_runs_and_open_gaps` (SQLite) | Seeded fixture DB: two hosts (newest first, age ≈ 90 s), a `blocked` FX with `retry_not_before`, its latest run `failed`/`http_429`, 24 h counts `{failed: 1, success: 1}` (a 48 h-old run excluded), 2 open gaps with the newest open one (the newest gap is filled and excluded), every other source empty. The exact key set is asserted, and the seeded URL with a token, the private domain, `error_message`, `params` and `disabled_reason` never appear |
| `test_sources.py::test_health_main_runs_in_read_only_transaction` (`db`, Postgres) | `main(["health"])` on the migrated schema prints the same report; a write inside the `health` transaction fails with "read-only transaction" and leaves no row. Red check: with the `SET TRANSACTION READ ONLY` line removed, it fails (`DID NOT RAISE DBAPIError`) |
| `test_collector.py::test_status_reports_health_revision_and_previous_operation` (updated) | Postgres running and migrated: `data_health` is the container's JSON; the only `run` is the health container (no stdin); nothing is built or started |
| `test_collector.py::test_status_data_health_null_without_running_migrated_postgres` (2 cases) | Postgres stopped → `data_health` and `alembic_revision` `null`; Postgres running but unmigrated → `data_health` `null`. No container call in either |

**One existing test changed.** `test_status_reports_health_revision_and_previous_operation` asserted the exact old status dict and that no `run` call happened. Both assertions now admit exactly the new field and the one health container. Every other existing collector test is unchanged and passes, including the guard matrix for `status`.

The SQLite fixture now also creates `host_heartbeats`, `collector_runs` and `collection_gaps`, with the same INTEGER-key and JSON substitutions it already made.

**Production engine check (not committed).** The container uses `make_engine` with `pool_pre_ping=True`, which the test fixture's engine doesn't use. A scratch script against the throwaway DB confirmed that `SET TRANSACTION READ ONLY` still refuses a write on both a fresh connection and a pooled, pre-pinged one ("cannot execute CREATE TABLE in a read-only transaction").

## Checks (base `ed76039`)

| Check | Result |
|---|---|
| `uv run ruff check .` | pass |
| `uv run ruff format --check .` | pass (200 files) |
| `uv run mypy` | pass (139 files) |
| `uv run mypy --platform linux` | pass (139 files) |
| `uv run pytest` with `TEST_DATABASE_URL` on a throwaway `pgvector/pgvector:0.8.7-pg18-trixie` container (`data05-pgtest`, loopback port 55517, database `pulso_test_data05`, local throwaway password; removed afterwards; not the collector or shared dev stack) | **1,394 passed, 0 skipped**, 1 existing starlette `TestClient` deprecation warning |
| `infra/tests/collector` alone | 220 passed |

No command touched `C:\dev\pulso` or the collector stack, and no data source was contacted. Web files are untouched, so `pnpm` web checks were not run.

## After the merge (owner, then lead)

1. The owner merges this branch onto `origin/main`. It touches only collector scripts, tests, DECISIONS, and this report, and has no migration.
2. The lead's next collector-host step runs `update` (Playbook §6, DEC-073). It rebuilds the worker image, which then contains `health`. **Until then, `status` fails while Postgres is up**, because the old image refuses the unknown op. Run `update` first, not `status`.
3. Run `status` and read its JSON line from the journal log.

## For the lead

**Lead State `data_track` line** (append after merge):
> data-05 merged `<sha>` (DEC-210, owner merge): collector `status` now prints `data_health` (ops heartbeat age per host; per source enabled/status/retry_not_before, latest run, 24 h runs by status, open gaps). The next `update` rebuilds the worker image; until then `status` fails while Postgres is up. FX enablement waits on one `status` after that `update` that passes the Data Health check below.

**Collector Host `## Log` line**:
> - 2026-10-24 — data-05 merged (claude, DEC-210): `status` prints read-only `data_health` from the worker image (heartbeat age, per-source state, latest run, 24 h runs, open gaps); `update` must rebuild the worker image before `status` reports it.

**Data Health fields to check before enabling FX** (one `status` after `update`, all must hold):

| Field | Must be |
|---|---|
| journal `exit` of the `status` op | `0` |
| `containers` | `postgres`, `redis`, `s3`, `worker`, `worker-ops`, `beat` all `running` |
| `alembic_revision` | the single Alembic head on `origin/main` |
| `data_health` | not `null` |
| `data_health.heartbeats[0].age_seconds` | ≤ 600 (`ops.heartbeat` runs every 5 min; 600 s allows one missed beat) |
| `sources[key="fx_frankfurter"].status` | `disabled`, not `blocked` (only the owner's typed-reason re-enable clears a block) |
| `sources[key="fx_frankfurter"].enabled` | `false` (else the enable is a no-op and the previous enable needs its first-run check) |
| `sources[key="fx_frankfurter"].retry_not_before` | `null` or earlier than `as_of` |
| every other source's `enabled` | `false` (FX goes first, one source at a time) |

**After enabling FX**, the first-run check (Playbook §6 step 4) is a later `status` once FX's scheduled slot has passed: `fx_frankfurter.latest_run.status = "success"` with `error_code = null` and a non-null `finished_at`; `runs_24h` has no `failed`; `status` is still `active` with `retry_not_before` `null`; `open_gaps` not higher than before. A `blocked` status or a block `error_code` means the source auto-disabled: log it and never retry around it (§6 step 6). Optionally, `sources[key="backup"].latest_run.status = "success"` confirms the nightly backup (only the nightly backup records `backup` runs; the dump inside `update` does not).

**Vault (lead applies after merge):** append the Collector Host Log line above. This branch edited only the `status` bullet in the body of the vault note `Platform/Collector Host`; its frontmatter `updated` and Log are left to the lead. No ticks, statuses or backlog rows change.

## Not done

- No new op; extending `status` worked.
- `status` reports no partial result when the container fails (DEC-210 c). If leads find that too strict during the window between merge and `update`, a follow-up could print the report with `data_health: {"error": "unavailable"}` once a container failure can be told apart from a hold refusal.
