import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from pulso_core.models import Listing, ListingVariant, Source, VariantSnapshot
from pulso_core.settings import Settings
from pulso_ml.label_eligibility import label_eligibility

from .test_variants import catalog, js_run  # noqa: F401


@pytest.mark.usefixtures("catalog")
def test_grade_a_unavailable_with_stored_inventory(session: Session, settings: Settings) -> None:
    result = js_run(session, settings)
    assert result.error_code is None, (result.error_code, result.error_message)
    session.expire_all()
    observations = session.execute(
        select(VariantSnapshot, Source.key)
        .join(ListingVariant)
        .join(Listing)
        .join(Source)
        .where(VariantSnapshot.inventory_quantity.is_not(None))
    ).all()
    assert len(observations) == 2
    for snapshot, source_key in observations:
        assert snapshot.inventory_quantity == 7
        assert (snapshot.inventory_management, snapshot.inventory_policy) == ("shopify", "deny")
        eligibility = label_eligibility(source_key=source_key, family="shp_inv")
        assert not eligibility.available
        assert eligibility.reason == "dec_090_e"
        session.refresh(snapshot)
        assert snapshot.inventory_quantity == 7
        assert (snapshot.inventory_management, snapshot.inventory_policy) == ("shopify", "deny")


def test_other_sources_and_families_are_unaffected() -> None:
    for source_key, family in (
        ("cj", "shp_inv"),
        ("shopify_stores", "shp_bump"),
        ("cj", "cj_stock"),
        ("google_trends", "gt_slope"),
    ):
        eligibility = label_eligibility(source_key=source_key, family=family)
        assert eligibility.available
        assert eligibility.reason is None
