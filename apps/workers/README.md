# Workers

Run commands from the repo root. Windows uses the solo pool; Linux uses prefork.
Both consumers stay at concurrency 1 (D1). Source adapters own their in-process
request limiter; no live adapter is registered by this scheduling task.

```powershell
uv run celery -A pulso_workers.celery_app:app worker --pool=solo -Q collect,default --concurrency=1 --loglevel=INFO
uv run celery -A pulso_workers.celery_app:app worker --pool=solo -Q ops --concurrency=1 --loglevel=INFO
```

The second consumer is reserved for SCH-4 heartbeat/audit, which is not implemented
in this size split. `worker_process_init` creates a process-local SQLAlchemy engine
and configures Pulso JSON logs. Imports open no database or broker connections.

Only the collector host may run `python -m pulso_workers.beat`. Never start Beat or
live collectors in a worktree. Scheduler-off and linked-worktree guards apply to
both the entry point and `beat_init`; raw Beat must use `LockedScheduler` too.
Beat takes a dedicated PostgreSQL advisory lock on `beat_init`, using the configured
application database (DEC-002). A second Beat exits non-zero. Each tick checks the
actual lock on that same session before scheduling; missing/disconnected sessions
stop Beat. Ticks sleep at most five seconds. Detached lock connections close their
physical session, so no session-level lock leaks back into a pool.

`schedules.py` defines six UTC crontabs. `LockedScheduler` checks `sources.enabled`,
skips queued/running work or a successful current slot, and calls `enqueue_run`
before publishing `collect.run(run_id)` to `collect`. Broker failures persist
`failed/publish_failed` and log only the exception class; Beat's eager producer
connection is bypassed so it cannot log broker exception text before that boundary.
The API overrides `get_publisher` with its own lightweight Celery publisher, keeping
P1-27's fixed-text error wrapper and keeping worker/ML packages out of the API image.

Adapter lanes register `tasks.PLANS[source_key] = factory`. A factory receives
`(session, source, job)` and returns `Plan(adapter, targets, wall_time_seconds,
request_hook=None)`. Jobs are `catalog`, `variants_js`, `freight`, `trends`, `fx`;
manual runs default to catalog (Trends/FX use their own job). Registration must be
imported at worker startup. Missing adapters fail the queued run without fetching.
The consumer holds the source advisory lock across `execute_run`, passes
`SoftTimeLimitExceeded` as a stop exception, and applies 60/75-minute soft/hard
limits from settings. Settings require every source budget below soft below hard,
and backoff base no greater than cap. Windows solo relies on cooperative budgets;
OS signal-based soft limits require Linux prefork.

**Remaining SCH-4:** heartbeat, overdue/gap audit, catch-up, abandoned-run reconciliation
and bounded redelivery after source-lock contention. A busy source leaves the row
queued; the recovery lane must handle it before live rollout. No outbox or migration.

```powershell
uv run ruff check apps/workers
uv run mypy
uv run pytest apps/workers
```

PostgreSQL lock tests use a random key above the source-id range and a dedicated test
database. They are unverified locally without Docker; no Beat process is started by tests.
