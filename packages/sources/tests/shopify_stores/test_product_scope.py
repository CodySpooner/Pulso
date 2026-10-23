"""P1-37 review regressions: product-level .js failures stay product-scoped (M1, L4, L5)."""

import json
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pulso_core.models import CollectorRunTarget, Listing, Store, VariantSnapshot
from pulso_core.settings import Settings
from pulso_sources.framework import Response

from .conftest import fixture
from .test_catalog import CATALOG, run
from .test_variants import JS, catalog, js_run  # noqa: F401

META = "https://first.test/meta.json"
STORE_RULE_REPLIES = {
    "404": fixture("headless"),
    "402": Response(b"Payment required", 402, "text/html"),
    "html": fixture("password"),
    "password_redirect": Response(b"", 302, headers={"Location": "https://first.test/password"}),
}


def status(session: Session, run_id: int, scope: str, target_id: str) -> str | None:
    target = session.get(CollectorRunTarget, (run_id, scope, target_id))
    return None if target is None else target.status


@pytest.mark.parametrize("reply", sorted(STORE_RULE_REPLIES))
@pytest.mark.usefixtures("catalog")
def test_js_failure_fails_only_that_panel_and_store_stays_active(
    session: Session, settings: Settings, io_mock: Any, reply: str
) -> None:
    io_mock.replies[JS] = STORE_RULE_REPLIES[reply]
    result = js_run(session, settings)
    assert status(session, result.id, "shopify_variants_js", "first.test") in {"partial", "failed"}
    assert status(session, result.id, "shopify_variants_js", "second.test") == "success"
    assert session.get_one(Store, 1).status == "active"
    io_mock.calls.clear()
    later = run(session, settings)  # The next catalog still crawls the store.
    assert CATALOG in [url for url, _, _ in io_mock.calls]
    assert status(session, later.id, "shopify_excluded", "first.test:untrackable") is None
    assert status(session, later.id, "shopify_catalog", "first.test") == "success"


@pytest.mark.parametrize("reply", sorted(STORE_RULE_REPLIES))
@pytest.mark.parametrize("url", [META, CATALOG], ids=["meta", "catalog"])
def test_qualification_and_catalog_responses_still_mark_untrackable(
    session: Session, settings: Settings, io_mock: Any, url: str, reply: str
) -> None:
    io_mock.replies[url] = STORE_RULE_REPLIES[reply]
    run(session, settings)
    assert session.get_one(Store, 1).status == "untrackable"
    io_mock.calls.clear()
    later = run(session, settings)
    assert not any("first.test" in u for u, _, _ in io_mock.calls)
    assert status(session, later.id, "shopify_excluded", "first.test:untrackable") is not None


@pytest.mark.usefixtures("catalog")
def test_duplicate_handle_panel_requests_newest_listing_once(
    session: Session, settings: Settings, io_mock: Any
) -> None:
    first = session.scalars(select(Listing).where(Listing.store_id == 1)).one()
    session.add(  # A deleted product's stale twin, its handle reused before a catalog succeeded.
        Listing(
            source_id=1,
            store_id=1,
            external_id=first.external_id + "-old",
            url=first.url,
            handle=first.handle,
            title="stale twin",
            first_seen_at=first.first_seen_at - timedelta(days=30),
            last_seen_at=first.last_seen_at - timedelta(days=1),
        )
    )
    session.commit()
    result = js_run(session, settings)
    assert result.error_code is None, (result.error_code, result.error_message)
    assert [url for url, _, _ in io_mock.calls].count(JS) == 1
    assert any("second.test/products/" in url for url, _, _ in io_mock.calls)


@pytest.mark.usefixtures("catalog")
def test_delisted_listing_never_enters_panel(
    session: Session, settings: Settings, io_mock: Any
) -> None:
    listing = session.scalars(select(Listing).where(Listing.store_id == 1)).one()
    listing.delisted_at = listing.last_seen_at
    session.commit()
    result = js_run(session, settings)
    assert JS not in [url for url, _, _ in io_mock.calls]
    assert status(session, result.id, "shopify_variants_js", "first.test") is None
    assert any("second.test/products/" in url for url, _, _ in io_mock.calls)


@pytest.mark.usefixtures("catalog")
def test_js_unsolicited_304_never_counts_as_fresh(
    session: Session, settings: Settings, io_mock: Any
) -> None:
    assert js_run(session, settings).error_code is None  # Caches a successful .js body.
    meta = json.loads(fixture("meta").body or b"")
    meta["currency"] = "EUR"  # A currency change suppresses the conditional request.
    io_mock.replies[META] = Response(json.dumps(meta).encode(), 200)
    io_mock.replies[JS] = fixture("not_modified")
    count = session.scalar(select(func.count()).select_from(VariantSnapshot))
    io_mock.calls.clear()
    result = js_run(session, settings)
    assert "If-none-match" not in next(h for u, _, h in io_mock.calls if u == JS)
    assert status(session, result.id, "shopify_variants_js", "first.test") == "partial"
    assert session.scalar(select(func.count()).select_from(VariantSnapshot)) == count
