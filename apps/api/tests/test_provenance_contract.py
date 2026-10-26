"""Q-1 provenance contract (DEC-238, DEC-259): every number a product-facing resource returns
carries a required `as_of`, checked on the exported OpenAPI."""

import copy
from typing import Any

from pulso_api.main import create_app

# Product-facing prefixes: every 2xx response under them is walked, so a new endpoint joins on
# arrival. Settings, account, admin (Data Health) and health return no product data.
COVERED = (
    "/v1/products",
    "/v1/search",
    "/v1/profit",
    "/v1/categories",
    "/v1/popular-products",
    "/v1/amazon",
    "/v1/pulse",
    "/v1/screener",
)
# At least these operations; a test fails if a prefix stops reaching one of them.
COVERED_OPERATIONS = {
    "list_products",
    "get_product",
    "get_product_overview",
    "get_product_sellers",
    "get_product_scores",
    "get_product_series",
    "get_product_suppliers",
    "list_product_notes",
    "create_product_note",
    "list_product_tags",
    "put_product_tags",
    "list_product_keywords",
    "set_product_keyword",
    "search",
    "calc_profit",
    "list_categories",
    "list_popular_products",
    "list_amazon_ranks",
    "list_product_amazon_ranks",
    "get_pulse",
    "screen_products",
}
# Numbers that are not observations, so no capture time applies. Each needs a reason, and one
# the check no longer flags must be removed.
EXEMPT = {
    "CategoryOption.id": "a taxonomy id (Google's), not a measurement",
    "StoreHit.id": "the stores row the palette opens, not a measurement",
    "SupplierHit.id": "the suppliers row the palette opens, not a measurement",
    "Vendor.id": "the stores or suppliers row Discover's chip filters by, not a measurement",
    "AlertOut.id": "the alerts row Daily Pulse lists (fired_at dates it), not a measurement",
}
# A score's explanation (pulso_core.scores, DEC-331): the score carries as_of, and each input its
# own capture time in Component.as_of; weights, z, points, freshness and coverage are arithmetic
# on them.
EXEMPT |= {
    f"{schema}.{field}": "a term of a score explanation; the score and its inputs carry as_of"
    for schema, fields in {
        "Component": ("contribution", "freshness", "raw", "weight", "weight_eff", "z"),
        "Explanation": ("confidence", "coverage", "panel_size"),
        "Normalization": ("category_id", "n"),
        "Penalty": ("points", "raw"),
    }.items()
    for field in fields
}


def holds_number(prop: dict[str, Any]) -> bool:
    """A number itself, or inside a union, list or map (a `$ref` object is checked on its own)."""
    if prop.get("type") in ("integer", "number"):
        return True
    parts = [*prop.get("anyOf", []), *prop.get("oneOf", []), *prop.get("allOf", [])]
    parts += [prop.get("items"), prop.get("additionalProperties")]
    return any(isinstance(part, dict) and holds_number(part) for part in parts)


def objects(spec: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Every object schema a covered 2xx response reaches, with its component name (the
    operationId when inline), in a stable order."""
    schemas = spec["components"]["schemas"]
    found: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()

    def walk(node: Any, where: str) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item, where)
        if not isinstance(node, dict):
            return
        if "$ref" in node:
            name = node["$ref"].rsplit("/", 1)[1]
            if name not in seen:
                seen.add(name)
                walk(schemas[name], name)
            return
        if "properties" in node:
            found.append((where, node))
        for value in node.values():
            walk(value, where)

    for path, operations in spec["paths"].items():
        if path.startswith(COVERED):
            for operation in operations.values():
                for status, response in operation["responses"].items():
                    if status.startswith("2"):
                        walk(response, operation["operationId"])
    return found


def numbers_without_as_of(spec: dict[str, Any]) -> set[str]:
    return {
        f"{where}.{key}"
        for where, node in objects(spec)
        if "as_of" not in node.get("required", [])
        for key, prop in node["properties"].items()
        if holds_number(prop)
    }


def covered_operations(spec: dict[str, Any]) -> set[str]:
    return {
        operation["operationId"]
        for path, operations in spec["paths"].items()
        if path.startswith(COVERED)
        for operation in operations.values()
    }


def test_every_number_in_a_product_resource_carries_as_of() -> None:
    spec = create_app().openapi()
    assert covered_operations(spec) >= COVERED_OPERATIONS
    flagged = numbers_without_as_of(spec)
    assert sorted(flagged - EXEMPT.keys()) == []
    assert sorted(EXEMPT.keys() - flagged) == []
    assert all(EXEMPT.values())


def test_dropping_as_of_from_a_covered_resource_fails_the_contract() -> None:
    spec = create_app().openapi()
    baseline = numbers_without_as_of(spec)
    carriers = [
        (index, where)
        for index, (where, node) in enumerate(objects(spec))
        if "as_of" in node.get("required", [])
        and any(map(holds_number, node["properties"].values()))
    ]
    assert {"Sourced", "ProfitCalc", "SupplierRow", "Rating", "Orders", "BulkTier"} <= {
        where for _, where in carriers
    }
    for index, where in carriers:
        mutated = copy.deepcopy(spec)
        _, node = objects(mutated)[index]
        node["required"].remove("as_of")
        del node["properties"]["as_of"]
        assert numbers_without_as_of(mutated) > baseline, where


def test_a_number_inside_a_list_map_or_union_counts() -> None:
    integer = {"type": "integer"}
    assert holds_number({"type": "array", "items": integer})
    assert holds_number({"type": "object", "additionalProperties": integer})
    assert holds_number({"anyOf": [integer, {"type": "null"}]})
    assert not holds_number({"$ref": "#/components/schemas/Sourced"})
    assert not holds_number({"type": "array", "items": {"type": "string"}})
