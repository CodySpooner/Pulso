from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, aliased

from pulso_core import taxonomy
from pulso_core.models import Category, CategoryMapping, Listing, Product

TRIMMED = (Path(__file__).parent / "fixtures" / "google_product_taxonomy_trimmed.txt").read_text()
SHOPIFY, CJ = 1, 2  # sources rows from migration 0001
HOME, KITCHEN, LAMPS, PET_SUPPLIES, DOG_BEDS = 536, 638, 4636, 2, 4434


def test_parse_links_each_row_to_its_parent() -> None:
    rows = taxonomy.parse(TRIMMED)
    assert len(rows) == 9
    by_id = {row.id: row for row in rows}
    lamps = by_id[LAMPS]
    assert (lamps.name, lamps.path, lamps.parent_id) == (
        "Lamps",
        "Home & Garden > Lighting > Lamps",
        594,
    )
    assert by_id[HOME].parent_id is None
    for row in rows:
        if row.parent_id is not None:
            assert by_id[row.parent_id].path == row.path.rpartition(" > ")[0]


def test_parse_rejects_an_orphan_or_a_duplicate() -> None:
    with pytest.raises(ValueError, match="parent"):
        taxonomy.parse("4636 - Home & Garden > Lighting > Lamps\n")
    with pytest.raises(ValueError, match="duplicate"):
        taxonomy.parse("536 - Home & Garden\n536 - Garden\n")


def test_vendored_taxonomy_is_google_2021_09_21_with_every_parent() -> None:
    text = taxonomy.TAXONOMY.read_text("utf-8")
    assert text.splitlines()[0] == "# Google_Product_Taxonomy_Version: 2021-09-21"
    rows = taxonomy.parse(text)  # raises on an orphan or a duplicate
    assert len(rows) == 5595
    assert max(row.id for row in rows) < 2**31  # categories.id is INTEGER


def categorise(source: str, source_category: str | None, title: str) -> int | None:
    return taxonomy.categorise(taxonomy.rules(), source, source_category, title)


def test_every_rule_path_is_in_the_vendored_taxonomy() -> None:
    rules = taxonomy.rules()  # raises on an unknown path
    assert rules.sources["shopify_stores"] and rules.sources["cj"] and rules.keywords


@pytest.mark.parametrize(
    ("product_type", "expected"),
    [
        ("Home", HOME),  # a rule
        ("  home ", HOME),  # case and spacing don't matter
        ("Dog Beds", DOG_BEDS),  # a unique Google category name
        ("Home & Garden > Lighting > Lamps", LAMPS),  # a full Google path
        ("Decor > Lamps", LAMPS),  # else the last segment
    ],
)
def test_shopify_product_type(product_type: str, expected: int) -> None:
    assert categorise("shopify_stores", product_type, "Fixture product") == expected


@pytest.mark.parametrize(
    ("cj_category", "expected"),
    [
        ("Pet Supplies", PET_SUPPLIES),
        ("Home & Garden › Kitchen & Dining", KITCHEN),  # CJ's › path, by its last segment
        ("Sports & Outdoors › Fitness", 990),
    ],
)
def test_cj_category(cj_category: str, expected: int) -> None:
    assert categorise("cj", cj_category, "Fixture product") == expected


def test_source_rules_are_per_source() -> None:
    assert categorise("cj", "Toys, Kids & Babies", "Fixture product") is not None
    assert categorise("shopify_stores", "Toys, Kids & Babies", "Fixture product") is None


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Galaxy Projector Star Night Light", 505826),  # ambient lighting, not a video projector
        ("Mini Projector 1080P Portable", 396),
        ("Resistance Bands Set (5 pcs)", 5869),  # plural folds to the keyword
        ("Dog Harness and Leash Combo", 6250),  # the longest keyword wins over "leash"
    ],
)
def test_title_fallback(title: str, expected: int) -> None:
    assert categorise("cj", None, title) == expected


def test_title_refines_a_broader_source_category_but_never_contradicts_it() -> None:
    assert categorise("shopify_stores", "Home", "Sunset lamp") == LAMPS
    assert categorise("shopify_stores", "Pet Supplies", "Sunset lamp") == PET_SUPPLIES


@pytest.mark.parametrize(
    ("source_category", "title"),
    [("Fixture", "Synthetic CJ product"), (None, "Fixture bowl"), ("", "")],
)
def test_no_match_is_none(source_category: str | None, title: str) -> None:
    assert categorise("shopify_stores", source_category, title) is None


SEED_NICHES = (  # infra/seeds/seed_v1.yaml keywords, as product titles
    "cat tree;dog harness;pet hair remover;cat water fountain;dog car seat cover;lick mat;"
    "self cleaning litter box;sunset lamp;galaxy projector;led strip lights;cordless table lamp;"
    "sofa cover;blackout curtains;portable blender;milk frother;vegetable chopper;"
    "countertop ice maker;oil sprayer;ice roller;gua sha;led face mask;crystal hair eraser;"
    "scalp massager;heatless curls;teeth whitening kit;pilates bar;massage gun;posture corrector;"
    "neck massager;resistance bands;walking pad;magnetic power bank;wireless charging station;"
    "phone tripod;car phone mount;mini projector;smart ring;car vacuum;dash cam;"
    "car seat gap filler;trunk organizer;white noise machine;baby carrier;montessori toys;"
    "camping pad;neck fan;cloud slides;flat cap;name necklace;custom pet portrait"
).split(";")


@pytest.mark.parametrize("niche", SEED_NICHES)
def test_every_seed_niche_has_a_title_rule(niche: str) -> None:
    assert categorise("cj", None, f"2026 New {niche.title()} for Gift") is not None


def all_categories(session: Session) -> list[tuple[int, int | None, str, str]]:
    rows = session.execute(
        select(Category.id, Category.parent_id, Category.name, Category.path).order_by(Category.id)
    )
    return [tuple(row) for row in rows]


def test_load_is_idempotent(db_engine: Engine) -> None:
    with Session(db_engine) as session, session.begin():
        assert taxonomy.load(session, TRIMMED) == 9
    with Session(db_engine) as session, session.begin():
        before = all_categories(session)
        assert taxonomy.load(session, TRIMMED) == 0
        assert all_categories(session) == before
        assert taxonomy.load(session, TRIMMED.replace("> Lamps", "> Table Lamps")) == 1


def test_load_keeps_parent_integrity(db_engine: Engine) -> None:
    with Session(db_engine) as session, session.begin():
        taxonomy.load(session)
        parent = aliased(Category)
        rows = session.execute(
            select(Category.path, parent.path).outerjoin(parent, parent.id == Category.parent_id)
        ).all()
    assert len(rows) == 5595
    for path, parent_path in rows:
        assert (parent_path or "") == path.rpartition(" > ")[0]


def product(
    session: Session,
    *listings: tuple[int, str | None, str],
    category: tuple[int | None, str | None] = (None, None),
) -> Product:
    row = Product(
        name=listings[0][2] if listings else "Unlisted",
        category_id=category[0],
        category_source=category[1],
    )
    session.add(row)
    session.flush()
    for source_id, product_type, title in listings:
        session.add(
            Listing(
                source_id=source_id,
                external_id=uuid4().hex,
                url="https://example.test/",
                title=title,
                product_type=product_type,
                product_id=row.id,
            )
        )
    session.flush()
    return row


def test_apply_sets_rule_categories_and_writes_mappings(db_engine: Engine) -> None:
    with Session(db_engine) as session, session.begin():
        taxonomy.load(session)
        lamp = product(session, (SHOPIFY, "Home", "Sunset lamp"))
        bowl = product(session, (CJ, None, "Fixture bowl"))
        stale = product(session, (CJ, None, "Synthetic CJ product"), category=(KITCHEN, "rule"))
        named = product(session, category=(None, None))
        named.name = "Mini projector"
        counts = taxonomy.apply(session)
        session.flush()
        session.expire_all()
        assert (lamp.category_id, lamp.category_source) == (LAMPS, "rule")
        assert (bowl.category_id, bowl.category_source) == (None, None)
        assert (stale.category_id, stale.category_source) == (None, None)  # rules re-derive theirs
        assert (named.category_id, named.category_source) == (396, "rule")
        mappings = session.execute(
            select(
                CategoryMapping.source_id,
                CategoryMapping.source_category,
                CategoryMapping.category_id,
                CategoryMapping.mapping_source,
            )
        ).all()
        assert [tuple(row) for row in mappings] == [(SHOPIFY, "home", HOME, "rule")]
        assert counts == {"categorised": 2, "uncategorised": 2, "changed": 3, "mappings": 1}
    with Session(db_engine) as session, session.begin():
        assert taxonomy.apply(session)["changed"] == 0


def test_apply_never_overwrites_a_manual_or_ai_category(db_engine: Engine) -> None:
    with Session(db_engine) as session, session.begin():
        taxonomy.load(session)
        manual = product(session, (SHOPIFY, "Home", "Sunset lamp"), category=(DOG_BEDS, "manual"))
        ai = product(session, (SHOPIFY, "Home", "Sunset lamp"), category=(KITCHEN, "ai"))
        taxonomy.apply(session)
        session.flush()
        session.expire_all()
        assert (manual.category_id, manual.category_source) == (DOG_BEDS, "manual")
        assert (ai.category_id, ai.category_source) == (KITCHEN, "ai")


def test_a_manual_mapping_wins_over_the_rules_and_is_kept(db_engine: Engine) -> None:
    with Session(db_engine) as session, session.begin():
        taxonomy.load(session)
        session.add(
            CategoryMapping(
                source_id=SHOPIFY,
                source_category="home",
                category_id=KITCHEN,
                mapping_source="manual",
            )
        )
        item = product(session, (SHOPIFY, "Home", "Fixture product"))
        taxonomy.apply(session)
        session.flush()
        session.expire_all()
        assert (item.category_id, item.category_source) == (KITCHEN, "rule")
        mapping = session.get(CategoryMapping, (SHOPIFY, "home"))
        assert mapping is not None
        assert (mapping.category_id, mapping.mapping_source) == (KITCHEN, "manual")
