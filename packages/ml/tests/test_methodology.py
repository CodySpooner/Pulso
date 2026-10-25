import math
from dataclasses import fields, replace
from pathlib import Path
from typing import Any

import pytest

from pulso_core.scores import version
from pulso_ml.scores import lifecycle, methodology

COMMITTED = Path(__file__).resolve().parents[3] / methodology.OUT


def score(doc: dict[str, Any], anchor: str) -> dict[str, Any]:
    return next(s for s in doc["scores"] if s["id"] == anchor)


def test_the_committed_export_is_the_code() -> None:
    fresh = methodology.dumps(methodology.build())
    assert COMMITTED.read_text(encoding="utf-8") == fresh, (
        "apps/web/src/lib/methodology.json is stale: run `uv run python -m pulso_ml.scores.methodology`"
    )


def test_a_threshold_change_changes_the_export_and_the_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = score(methodology.build(), "lifecycle-stage")
    monkeypatch.setattr(lifecycle, "CONFIG", replace(lifecycle.CONFIG, up=math.log(1.3)))
    after = methodology.build()
    entry = score(after, "lifecycle-stage")
    assert next(c["value"] for c in entry["config"] if c["name"] == "up") == math.log(1.3)
    assert entry["model_version"] != before["model_version"]
    assert entry["model_version"] == version(lifecycle.CONFIG)[0]
    assert methodology.dumps(after) != COMMITTED.read_text(encoding="utf-8")


def test_lifecycle_reads_its_docstring_signature_and_config() -> None:
    entry = score(methodology.build(), "lifecycle-stage")
    assert entry["code"] == "pulso_ml.scores.lifecycle.lifecycle_stage"
    assert entry["definition"][0] == {
        "text": "One product's stage on day t from its primary demand family's feature rows "
        "(DEC-275)."
    }
    lists = [b["items"] for b in entry["definition"] if "items" in b]
    assert "no source: no demand family, delisted or not." in lists[0]
    assert lists[1][5] == (  # a wrapped item rejoins its indented line
        "peaking · plateau: growth under +20%: flat, a stall after a run, or one week down "
        "that isn't a decline yet."
    )
    assert [i["name"] for i in entry["inputs"]][:2] == ["v7", "v7_prev"]
    assert entry["inputs"][0]["type"] == "int | None"
    assert [c["name"] for c in entry["config"]] == [f.name for f in fields(lifecycle.Config)]
    up = next(c for c in entry["config"] if c["name"] == "up")
    assert up == {"name": "up", "type": "float", "note": "+20% week on week", "value": math.log(1.2)}
    assert (entry["model_version"], entry["config_digest"]) == version(lifecycle.CONFIG)


def test_unbuilt_scores_name_their_phase_and_carry_no_numbers() -> None:
    planned = [s for s in methodology.build()["scores"] if s["status"] == "not built yet"]
    assert [s["id"] for s in planned] == [
        "trend-score",
        "saturation",
        "opportunity",
        "risk",
        "supplier-reliability",
    ]
    for entry in planned:
        assert set(entry) == {"id", "title", "status", "phase", "task"}


def test_every_section_has_a_unique_anchor() -> None:
    ids = [s["id"] for s in methodology.build()["scores"]]
    assert len(set(ids)) == len(ids)
    assert all(i.replace("-", "").isalpha() and i.islower() for i in ids)


def test_the_contract_names_its_fields_and_the_missing_rule() -> None:
    contract = methodology.build()["contract"]
    assert [f["name"] for f in contract["explanation"]["fields"]] == [
        "model_version",
        "config_digest",
        "components",
        "missing",
        "coverage",
    ]
    coverage = contract["explanation"]["fields"][-1]
    assert coverage["note"] == "present configured weight / all configured weight"
    assert "no source yet" in contract["missing_inputs"]["text"]
    assert contract["confidence"]["status"] == "not built yet"
