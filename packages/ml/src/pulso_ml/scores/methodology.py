"""The /methodology page's data, read from the scoring code (MT-1, DEC-313).

`uv run python -m pulso_ml.scores.methodology` writes OUT, a JSON file the web app imports at
build time. tests/test_methodology.py fails while that file differs from a fresh export, so a
threshold, weight or docstring change without regenerating fails CI.
"""

import annotationlib
import argparse
import inspect
import json
import re
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path
from types import ModuleType
from typing import Any, get_args

from pulso_core import scores as contract
from pulso_ml.scores import lifecycle, opportunity, saturation, trend, velocity

OUT = Path("apps/web/src/lib/methodology.json")

# (anchor, title, module, function, task) per built score, in reading order; the module has CONFIG.
BUILT: list[tuple[str, str, ModuleType, str, str]] = [
    ("velocity", "Velocity & Acceleration", velocity, "family_velocity", "SC-1"),
    ("lifecycle-stage", "Lifecycle Stage", lifecycle, "lifecycle_stage", "SC-4"),
    ("saturation", "Saturation", saturation, "saturation_scores", "SC-3"),
    ("trend-score", "Trend Score v0", trend, "trend_scores", "SC-2"),
    ("opportunity", "Opportunity", opportunity, "opportunity", "SC-5"),
]
# (anchor, title, phase, task) per score with no code yet (vault Score Definitions registry).
PLANNED: list[tuple[str, str, int, str | None]] = [
    ("risk", "Risk & Refund Risk", 5, None),
    ("supplier-reliability", "Supplier Reliability", 7, None),
]
LIMITATIONS = [
    "Collection runs on the owner's PC until Railway go-live (DEC-001), so days it is off are"
    " gaps: marked on every input they touch, never filled in.",
    "The Shopify store crawler stays off (DEC-261): no input reads Shopify stores' stock or"
    " seller counts.",
]


def _blocks(doc: str | None) -> list[dict[str, Any]]:
    """A docstring as paragraphs ({"text"}) and bullet lists ({"items"}), wrapped lines rejoined."""
    blocks: list[dict[str, Any]] = []
    open_ = False  # the last block continues on the next line
    for line in inspect.cleandoc(doc or "").splitlines():
        last = blocks[-1] if open_ else {}
        if not line.strip():
            open_ = False
        elif line.startswith("- "):
            if "items" in last:
                last["items"].append(line[2:])
            else:
                blocks.append({"items": [line[2:]]})
            open_ = True
        elif "items" in last and line.startswith(" "):
            last["items"][-1] += " " + line.strip()
        elif "text" in last:
            last["text"] += " " + line
        else:
            blocks.append({"text": line})
            open_ = True
    return blocks


def _fields(cls: type) -> list[dict[str, Any]]:
    """Each field of a dataclass or model: its name, its type as written and its line comment."""
    notes = dict(re.findall(r"^ +(\w+):.*?# *(.+)$", inspect.getsource(cls), re.M))
    types = annotationlib.get_annotations(cls, format=annotationlib.Format.STRING)
    return [{"name": n, "type": t, "note": notes.get(n)} for n, t in types.items()]


def _score(anchor: str, title: str, module: ModuleType, function: str, task: str) -> dict[str, Any]:
    fn = getattr(module, function)
    config = module.CONFIG
    values = asdict(config)
    model_version, digest = contract.version(config)
    params = inspect.signature(fn, annotation_format=annotationlib.Format.STRING).parameters
    return {
        "id": anchor,
        "title": title,
        "status": "built",
        "task": task,
        "code": f"{module.__name__}.{function}",
        "definition": _blocks(fn.__doc__),
        "inputs": [{"name": p.name, "type": p.annotation} for p in params.values()],
        "config": [{**f, "value": values[f["name"]]} for f in _fields(type(config))],
        "model_version": model_version,
        "config_digest": digest,
    }


def _confidence() -> dict[str, Any]:
    """Score Definitions §6 from pulso_core.scores: the formula, the freshness rule and cadences."""
    formula, *definition = _blocks(contract.confidence.__doc__)
    kinds = get_args(contract.Kind)
    return {
        "code": f"{contract.__name__}.confidence",
        "formula": formula["text"],
        "definition": definition,
        "freshness": _blocks(contract.fresh.__doc__),
        "fresh_within": contract.FRESH_WITHIN,
        "stale_after": contract.STALE_AFTER,
        "cadence": [
            {"source": source, "days": every / timedelta(days=1), "score": source in kinds}
            for source, every in contract.CADENCE.items()
        ],
    }


def build() -> dict[str, Any]:
    component = _blocks(contract.Component.__doc__)
    return {
        "scores": [_score(*s) for s in BUILT]
        + [
            {"id": a, "title": t, "status": "not built yet", "phase": p, "task": k}
            for a, t, p, k in PLANNED
        ],
        "contract": {
            "code": contract.__name__,
            "explanation": {
                "definition": _blocks(contract.Explanation.__doc__),
                "fields": _fields(contract.Explanation),
            },
            "component": {"definition": component, "fields": _fields(contract.Component)},
            "missing_inputs": next(b for b in component if "no source yet" in b.get("text", "")),
            "renormalisation": _blocks(contract.explain.__doc__),
            "versioning": _blocks(contract.version.__doc__),
            "confidence": _confidence(),
        },
        "limitations": LIMITATIONS,
    }


def dumps(doc: dict[str, Any]) -> str:
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    out = parser.parse_args().out
    out.write_text(dumps(build()), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
