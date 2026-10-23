"""Guarded SerpApi transport and response handling; all HTTP goes through the framework."""

from contextlib import closing
from datetime import UTC, datetime, timedelta
from http.client import HTTPException, HTTPSConnection
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from pulso_core.models import CollectorRun, Source, SourceEvent
from pulso_core.settings import get_settings
from pulso_sources.framework import Request, Response
from pulso_sources.google_trends import (
    ACCOUNT_ERRORS,
    PARAMS,
    GoogleTrendsParser,
    TrendsError,
    error_code,
    request_hook,
)


class GoogleTrendsAdapter(GoogleTrendsParser):
    error: str | None = None
    exhausted_until: datetime | None = None
    failures = 0

    def outage(self) -> TrendsError | None:
        """The second consecutive attempt with no response or a 5xx stops the run (DEC-157)."""
        self.failures += 1
        if self.failures < 2:
            return None
        self.error = "serpapi_unavailable"
        return TrendsError(self.error)

    def fetch(self, request: Request, *, user_agent: str) -> Response:
        settings = get_settings()
        keyword = request.params.get("q")
        if (
            set(request.params) != {*PARAMS, "q"}
            or any(request.params[k] != v for k, v in PARAMS.items())
            or not isinstance(keyword, str)
            or not keyword.strip()
            or "," in keyword
        ):
            raise ValueError("Unexpected Trends request parameters")
        if not settings.serpapi_api_key:
            raise TrendsError("serpapi_missing_key")
        try:
            with closing(
                HTTPSConnection("serpapi.com", timeout=settings.collector_request_timeout_seconds)
            ) as connection:
                connection.request(
                    "GET",
                    "/search.json?"
                    + urlencode(
                        {**request.params, "api_key": settings.serpapi_api_key.get_secret_value()}
                    ),
                    headers={"User-Agent": user_agent, "Accept": "application/json"},
                )
                with closing(connection.getresponse()) as response:
                    return Response(
                        response.read(),
                        response.status,
                        response.getheader("Content-Type"),
                        headers=dict(response.getheaders()),
                    )
        except OSError, HTTPException:
            raise self.outage() or ConnectionError("SerpApi transport failed") from None

    def request_hook(
        self,
        session: Session,
        source: Source,
        run: CollectorRun,
        request: Request,
        response: Response | None,
    ) -> None:
        try:
            if response is None:
                request_hook(session, source, run, request, None)
            else:
                code = error_code(response.body or b"", response.status_code)
                if response.status_code in range(500, 600) and code in {None, "serpapi_error"}:
                    if stop := self.outage():
                        raise stop
                    return
                self.failures = 0
                if code is None:
                    return
                self.error = code
                if code == "serpapi_searches_exhausted":
                    self.exhausted_until = (
                        datetime.now(UTC).replace(day=28) + timedelta(days=4)
                    ).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                if code in ACCOUNT_ERRORS:
                    raise TrendsError(code)
        except TrendsError as exc:
            self.error = str(exc)
            raise

    def finalize(self, session: Session, run: CollectorRun) -> None:
        """Own the finalization commit after the runner has preserved raw/block evidence."""
        if self.error is None:
            return
        run.error_code = run.error_message = self.error
        source = session.get_one(Source, run.source_id)
        if self.error == "serpapi_invalid_key" and source.enabled:
            source.enabled, source.status = False, "blocked"
            source.disabled_at, source.disabled_reason = datetime.now(UTC), self.error
            session.add(
                SourceEvent(
                    source_id=source.id,
                    actor="system",
                    action="disable",
                    reason=self.error,
                    at=source.disabled_at,
                )
            )
        if self.exhausted_until is not None:
            source.retry_not_before = max(
                source.retry_not_before or self.exhausted_until, self.exhausted_until
            )
        session.commit()
