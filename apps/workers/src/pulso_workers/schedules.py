"""Phase 1 UTC slots; only LockedScheduler publishes collection run ids."""

from celery.schedules import crontab  # type: ignore[import-untyped]

BEAT_SCHEDULE = {
    f"{source}.{job}": {
        "task": "collect.run",
        "schedule": crontab(minute=minute, hour=hour, day_of_week=day),
        "args": (source, job, "daily" if day == "*" else "weekly"),
        "options": {"queue": "collect"},
    }
    for source, job, minute, hour, day in (
        ("shopify_stores", "catalog", 0, 2, "*"),
        ("shopify_stores", "variants_js", 0, 3, "*"),
        ("cj", "catalog", 0, 4, "*"),
        ("cj", "freight", 30, 4, "1"),
        ("google_trends", "trends", 0, 5, "1"),
        ("fx_frankfurter", "fx", 0, 17, "*"),
    )
}
