# Workers

From the repo root, after filling the settings in `.env` / `.env.local`:

```powershell
uv sync --all-packages
uv run celery -A pulso_workers.celery_app:app worker --pool=solo --loglevel=INFO
```

Windows uses the solo pool. Linux containers use prefork with concurrency 2.
`worker_process_init` creates a fresh SQLAlchemy engine in either pool; imports
create no engine or connection. The Redis broker comes from shared settings.
`pulso.ping` returns `pong`; results are not persisted (the CLI `call` prints a task ID).
The eager test checks its return value without Redis.

The collector-host-only entry point is `python -m pulso_workers.beat`. It rejects
scheduler-off and linked-worktree starts, checking both the working directory and
installed package path. The same guard runs on `beat_init` for raw `celery beat`
and embedded `worker -B` starts. Never run Beat in an Orca worktree.
Phase 0 has no schedules. **Phase 1 must implement DEC-002's advisory lock before
adding schedules or enabling Beat on a collector host.**

```powershell
uv run ruff check apps/workers
uv run mypy apps/workers
uv run pytest apps/workers
```
