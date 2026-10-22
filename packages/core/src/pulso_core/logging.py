"""JSON logging with request/job correlation, without request bodies or credentials."""

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime

request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
job_id: ContextVar[str | None] = ContextVar("job_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id.get(),
            "job_id": job_id.get(),
        }
        for key in ("method", "path", "status", "duration_ms", "error_type"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.getLogger("pulso").handlers = [handler]
    logging.getLogger("pulso").setLevel(level)
    logging.getLogger("pulso").propagate = False
