"""Google Product Taxonomy categories and the rule-based category mapper (M-6, DEC-253).

`python -m pulso_core.taxonomy load` upserts the vendored taxonomy into `categories`;
`python -m pulso_core.taxonomy map` loads it, then sets `products.category_id` from the rules in
`data/category_rules.toml` wherever no manual or AI category exists. Both are idempotent.
"""

import argparse
import json
import re
import tomllib
from collections import Counter
from dataclasses import asdict, dataclass
from functools import cache
from itertools import groupby
from pathlib import Path
from typing import Any

from sqlalchemy import bindparam, or_, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from pulso_core.db import get_session
from pulso_core.models import Category, CategoryMapping, Listing, Product, Source

DATA = Path(__file__).parent / "data"
TAXONOMY = DATA / "google_product_taxonomy.txt"
RULES = DATA / "category_rules.toml"
RULE = "rule"  # category_source and mapping_source of everything this module writes
SEPARATOR = re.compile(r"\s*[›>]\s*")


@dataclass(frozen=True)
class Row:
    id: int
    parent_id: int | None
    name: str
    path: str


def parse(text: str) -> list[Row]:
    """Google's `id - A > B > C` lines, each after its parent; raises on an orphan or duplicate."""
    ids: dict[str, int] = {}
    seen: set[int] = set()
    rows = []
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        number, path = line.split(" - ", 1)
        parent, _, name = path.rpartition(" > ")
        if path in ids or int(number) in seen:
            raise ValueError(f"Taxonomy has a duplicate: {line}")
        seen.add(int(number))
        if parent and parent not in ids:
            raise ValueError(f"Taxonomy line precedes its parent: {line}")
        ids[path] = int(number)
        rows.append(Row(int(number), ids[parent] if parent else None, name, path))
    return rows


def load(session: Session, text: str | None = None) -> int:
    """Upsert every category (Google's id as `categories.id`); returns the rows added or changed.

    ponytail: never deletes; a category Google drops stays for the products that reference it.
    """
    rows = [asdict(row) for row in parse(text or TAXONOMY.read_text("utf-8"))]
    stmt = insert(Category).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Category.id],
        set_={column: stmt.excluded[column] for column in ("parent_id", "name", "path")},
        where=tuple_(Category.parent_id, Category.name, Category.path).is_distinct_from(
            tuple_(stmt.excluded.parent_id, stmt.excluded.name, stmt.excluded.path)
        ),
    )
    return len(session.scalars(stmt.returning(Category.id)).all())


def norm(text: str) -> str:
    """Casefolded, spacing collapsed, and CJ's "›" read as Google's " > "."""
    return " > ".join(SEPARATOR.split(" ".join(text.casefold().split())))


def fold(word: str) -> str:
    # ponytail: crude English plural folding, applied to titles and keys alike; a stemmer if
    # the collector-host coverage report shows misses.
    if word.endswith(("sses", "shes", "ches", "xes")):
        return word[:-2]
    return word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word


def words(text: str) -> tuple[str, ...]:
    return tuple(fold(word) for word in re.findall(r"[a-z0-9]+", text.casefold()))


@dataclass(frozen=True)
class Rules:
    sources: dict[str, dict[str, int]]  # source key -> normalised source category -> id
    names: dict[str, int]  # normalised Google path, or a Google name used once -> id
    keywords: list[tuple[tuple[str, ...], int]]  # title words -> id
    paths: dict[int, str]


@cache
def rules() -> Rules:
    """The rules file resolved against the vendored taxonomy; raises on an unknown path."""
    taxonomy = parse(TAXONOMY.read_text("utf-8"))
    ids = {row.path: row.id for row in taxonomy}
    counts = Counter(norm(row.name) for row in taxonomy)

    def find(path: str) -> int:
        if path not in ids:
            raise ValueError(f"{RULES.name}: not a Google Product Taxonomy path: {path}")
        return ids[path]

    config = tomllib.loads(RULES.read_text("utf-8"))
    return Rules(
        sources={
            source: {norm(key): find(path) for key, path in table.items()}
            for source, table in config["sources"].items()
        },
        names={norm(row.name): row.id for row in taxonomy if counts[norm(row.name)] == 1}
        | {norm(row.path): row.id for row in taxonomy},
        keywords=[(words(key), find(path)) for key, path in config["keywords"].items()],
        paths={row.id: row.path for row in taxonomy},
    )


def resolve(rules: Rules, source: str, source_category: str | None) -> int | None:
    """The source's rule, else a Google path or unique name; the whole value, then its leaf."""
    if not source_category or not (value := norm(source_category)):
        return None
    table = rules.sources.get(source, {})
    for key in (value, value.rpartition(" > ")[2]):
        if (found := table.get(key) or rules.names.get(key)) is not None:
            return found
    return None


def guess(rules: Rules, title: str) -> int | None:
    """The longest keyword in the title as whole words, then the earliest one."""
    found = words(title)
    best: tuple[tuple[int, int], int] | None = None
    for keyword, category in rules.keywords:
        size = len(keyword)
        start = next(
            (i for i in range(len(found) - size + 1) if found[i : i + size] == keyword), None
        )
        if start is not None and (best is None or (-size, start) < best[0]):
            best = ((-size, start), category)
    return best[1] if best else None


def refine(rules: Rules, source: int | None, title: int | None) -> int | None:
    """A title category under the source category refines it; one elsewhere never overrides it."""
    if source is None or title is None:
        return source or title
    return title if rules.paths[title].startswith(rules.paths[source] + " > ") else source


def categorise(rules: Rules, source: str, source_category: str | None, title: str) -> int | None:
    """One listing's category: (source key, source category, title) -> Google id, or None."""
    return refine(rules, resolve(rules, source, source_category), guess(rules, title))


def apply(session: Session) -> dict[str, int]:
    """Re-derive rule categories for products with no manual or AI one; returns the counts.

    A product takes its listings' first resolved source category, refined by the first title
    (listings by id, then the product name) that a keyword matches. Mapping rows another
    method wrote (`manual`, `ai`) win over the rules and are never overwritten.
    ponytail: one pass in memory; page by product id if the catalogue outgrows it.
    """
    current = rules()
    keys = dict(session.execute(select(Source.id, Source.key)).tuples().all())
    fixed = {
        (row.source_id, row.source_category): row.category_id
        for row in session.scalars(
            select(CategoryMapping).where(CategoryMapping.mapping_source != RULE)
        )
    }
    resolved: dict[tuple[int, str], int | None] = {}
    rows = session.execute(
        select(
            Product.id,
            Product.name,
            Product.category_id,
            Product.category_source,
            Listing.source_id,
            Listing.product_type,
            Listing.title,
        )
        .outerjoin(Listing, Listing.product_id == Product.id)
        .where(
            Product.merged_into_id.is_(None),
            or_(Product.category_source.is_(None), Product.category_source == RULE),
        )
        .order_by(Product.id, Listing.id)
    ).all()
    counts = {"categorised": 0, "uncategorised": 0}
    changes: list[dict[str, Any]] = []
    for product_id, group in groupby(rows, key=lambda row: row.id):
        listings = list(group)
        source: int | None = None
        for row in listings:
            if row.product_type:
                key = (row.source_id, norm(row.product_type))
                if key not in resolved:
                    resolved[key] = fixed.get(key) or resolve(
                        current, keys[row.source_id], row.product_type
                    )
                source = source or resolved[key]
        titles = [row.title for row in listings if row.title] + [listings[0].name]
        title = next((found for text in titles if (found := guess(current, text))), None)
        category = refine(current, source, title)
        counts["categorised" if category else "uncategorised"] += 1
        new = (category, RULE if category else None)
        if (listings[0].category_id, listings[0].category_source) != new:
            changes.append({"b_id": product_id, "b_category": new[0], "b_source": new[1]})
    if changes:  # the WHERE re-checks, so a manual category set meanwhile still wins
        session.connection().execute(  # a plain executemany, not the ORM's bulk-by-key path
            update(Product)
            .where(
                Product.id == bindparam("b_id"),
                or_(Product.category_source.is_(None), Product.category_source == RULE),
            )
            .values(category_id=bindparam("b_category"), category_source=bindparam("b_source")),
            changes,
        )
    mappings = [
        {"source_id": source_id, "source_category": text, "category_id": category}
        for (source_id, text), category in resolved.items()
        if category is not None and (source_id, text) not in fixed
    ]
    if mappings:
        stmt = insert(CategoryMapping).values([row | {"mapping_source": RULE} for row in mappings])
        session.execute(
            stmt.on_conflict_do_update(
                index_elements=[CategoryMapping.source_id, CategoryMapping.source_category],
                set_={"category_id": stmt.excluded.category_id},
                where=CategoryMapping.mapping_source == RULE,
            )
        )
    return counts | {"changed": len(changes), "mappings": len(mappings)}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m pulso_core.taxonomy", description="Google Product Taxonomy categories."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("load", help="upsert the vendored taxonomy into categories")
    commands.add_parser("map", help="load, then set rule categories on products")
    command = parser.parse_args(argv).command
    with get_session() as session, session.begin():
        result: dict[str, int] = {"categories_changed": load(session)}
        if command == "map":
            result |= apply(session)
    print(json.dumps({"event": f"taxonomy_{command}", **result}))


if __name__ == "__main__":
    main()
