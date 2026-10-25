# Workers

Run commands from the repo root. Windows uses the solo pool; Linux uses prefork.
Both consumers stay at concurrency 1 (D1). Source adapters own their in-process
request limiter. Worker startup imports adapter registrations; registration enables nothing.

```powershell
uv run celery -A pulso_workers.celery_app:app worker --pool=solo -Q collect,default --concurrency=1 --loglevel=INFO
uv run celery -A pulso_workers.celery_app:app worker --pool=solo -Q ops --concurrency=1 --loglevel=INFO
```

The second consumer runs `ops.heartbeat` every five minutes and `audit.schedule`
every fifteen minutes. Its startup requests a heartbeat; Beat startup requests an audit. `worker_process_init` creates a process-local SQLAlchemy engine
and configures Pulso JSON logs. Imports open no database or broker connections.

Only the collector host may run `python -m pulso_workers.beat`. Never start Beat or
live collectors in a worktree. Scheduler-off and linked-worktree guards apply to
both the entry point and `beat_init`; raw Beat must use `LockedScheduler` too.
Beat takes a dedicated PostgreSQL advisory lock on `beat_init`, using the configured
application database (DEC-002). A second Beat exits non-zero. Each tick checks the
actual lock on that same session before scheduling; missing/disconnected sessions
stop Beat. Ticks sleep at most five seconds. Detached lock connections close their
physical session, so no session-level lock leaks back into a pool.

`schedules.py` defines six collection and two ops UTC crontabs. `LockedScheduler` checks `sources.enabled`,
skips recent queued/running work of the same job or a successful current slot, and calls `enqueue_run`
before publishing `collect.run(run_id)` to `collect`. Broker failures persist
`failed/publish_failed` and log only the exception class; Beat's eager producer
connection is bypassed so it cannot log broker exception text before that boundary.
Under DEC-108, schedule/catch-up enqueue decisions serialize on the source row;
scheduling does not take the source execution lock. A running catalog therefore
allows freight to queue and use DEC-098's bounded busy-delivery retry. Same-job
suppression persists a `skipped` run with `params.blocked_by`, `complete=false`,
and `error_code=slot_suppressed`, visible in Data Health and still missing to the audit.
The `slot_suppressed` log carries only source, job, slot, blocking run id and age
in its message (the shared JSON formatter drops arbitrary extras). Rows at least
max(two hours, twice the source budget) old never suppress scheduling; age uses
`started_at` or otherwise `queued_at`, exactly as recovery does. Only the audit,
with the source execution lock free, may mark them abandoned.
The API overrides `get_publisher` with its own lightweight Celery publisher, keeping
P1-27's fixed-text error wrapper and keeping worker/ML packages out of the API image.

Adapter lanes register `tasks.PLANS[source_key] = factory`. A factory receives
`(session, source, job)` and returns `Plan(adapter, targets, wall_time_seconds,
request_hook=None, collector_max_retries=None, finalize=None, collect=None)`. Jobs are `catalog`, `variants_js`, `trends`, `fx`, `images`;
manual runs default to catalog (Trends/FX use their own job). Registration must be
imported at worker startup. Missing adapters fail the queued run without fetching.
Pre-run refusals store a fixed code and message (DEC-321): `source_unavailable`,
`unknown_job` (the factory raised `UnknownJob`), `plan_failed` (any other factory error,
message names only its class) and `plan_budget_invalid`. CJ registers `catalog` only: `collect`
hands the run to `cj.collect`, so its guard, points, pacing and block rules wrap `execute_run`;
the run's first request is the captured `getCategory` tree. CJ `freight` is unscheduled until
a tracked-product selection exists (DEC-321b).
Frankfurter and Shopify catalog are registered. Shopify's factory preloads successful
captures and pacing evidence; both its `collect()` wrapper and worker plan use zero
request retries and the same successful-store delisting/freshness finalizer (DEC-110).
Shopify `variants_js` remains unsupported until P1-07b. Unset retry overrides preserve
the configured retries, and plans without a finalizer keep their existing lifecycle.
The consumer holds the source advisory lock across planning, `execute_run` and finalization, passes
`SoftTimeLimitExceeded` as a stop exception, and applies 60/75-minute soft/hard
limits from settings. Settings require every source budget below soft below hard,
and backoff base no greater than cap. Windows solo relies on cooperative budgets;
OS signal-based soft limits require Linux prefork.

**Recovery (DEC-098):** before persisting a heartbeat, ops audits the previous window.
A gap longer than fifteen minutes records `host_offline` evidence per missed slot;
source status is `overdue` until its latest due job slots succeed. Ops uses advisory
key -1, separate from Beat 0 and positive source IDs. Changing container hostnames
does not reset the single collector host's heartbeat history. No external ping.

Catch-up holds the source execution lock and skips queued/running rows. With that
lock free, rows older than max(two hours, twice the source budget) fail as `abandoned`.
Then at most one current-period catch-up per source per UTC day is enqueued; any prior
catch-up for that slot suppresses another, even if it failed. Daily slots before today
remain gaps; weekly slots can catch up within the same ISO week. A successful matching
slot links gap display evidence without changing historical observations or features.

Busy deliveries persist `params.lock_retries` and republish the same ID after the
configured delay (two retries, fifteen minutes apart by default), then fail only a
still-queued row with `source_lock_busy`. Failed publications record `publish_failed`
and log only the exception class. Lost publications are recovered by the stale audit.
No outbox or migration. Real Redis transport and independent Linux ops/collect
consumers remain unverified locally (no Docker).

```powershell
uv run ruff check apps/workers
uv run mypy
uv run pytest apps/workers
```

PostgreSQL lock tests use a random key above the source-id range and a dedicated test
database. They are unverified locally without Docker; no Beat process is started by tests.
