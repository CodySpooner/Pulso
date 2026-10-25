"""Phase 1 UTC slots; only LockedScheduler publishes collection run ids."""

from celery.schedules import crontab  # type: ignore[import-untyped]

COLLECTION_SLOTS = (
    ("shopify_stores", "catalog", 0, 2, "*"),
    ("shopify_stores", "variants_js", 0, 3, "*"),
    ("cj", "catalog", 0, 4, "*"),
    ("cj", "freight", 30, 4, "1"),
    ("google_trends", "trends", 0, 5, "1"),
    ("listing_images", "images", 0, 6, "*"),  # after the day's new listings (DEC-240)
    ("fx_frankfurter", "fx", 0, 17, "*"),
)

BEAT_SCHEDULE = {
    f"{source}.{job}": {
        "task": "collect.run",
        "schedule": crontab(minute=minute, hour=hour, day_of_week=day),
        "args": (source, job, "daily" if day == "*" else "weekly"),
        "options": {"queue": "collect"},
    }
    for source, job, minute, hour, day in COLLECTION_SLOTS
}
BEAT_SCHEDULE.update(
    {
        name: {"task": name, "schedule": crontab(minute=minute), "options": {"queue": "ops"}}
        for name, minute in (("ops.heartbeat", "*/5"), ("audit.schedule", "*/15"))
    }
)
