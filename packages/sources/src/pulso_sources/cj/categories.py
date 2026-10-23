"""Resolve exact category paths against CJ's returned tree, never guessed IDs."""

import json
from collections.abc import Sequence

from pydantic import BaseModel, Field

from pulso_sources.cj.errors import classify_error
from pulso_sources.framework import Response


class Category(BaseModel):
    categoryId: str = Field(min_length=1)
    categoryName: str = Field(min_length=1)


class Second(BaseModel):
    categorySecondName: str = Field(min_length=1)
    categorySecondList: list[Category]


class First(BaseModel):
    categoryFirstName: str = Field(min_length=1)
    categoryFirstList: list[Second]


def resolve(body: bytes, names: Sequence[str]) -> dict[str, list[str]]:
    if error := classify_error(Response(body, 200)):
        raise error
    paths = [
        (first.categoryFirstName, second.categorySecondName, leaf)
        for raw in json.loads(body)["data"]
        for first in [First.model_validate(raw)]
        for second in first.categoryFirstList
        for leaf in second.categorySecondList
    ]
    index: dict[tuple[str, ...], set[str]] = {}
    for first, second, leaf in paths:
        path = tuple(value.strip().casefold() for value in (first, second, leaf.categoryName))
        for depth in (1, 2, 3):
            index.setdefault(path[:depth], set()).add(leaf.categoryId)
    resolved = {}
    for name in names:
        parts = tuple(part.strip().casefold() for part in name.split("›"))
        if parts not in index:
            raise ValueError(f"Unresolved CJ category seed: {name}")
        resolved[name] = sorted(index[parts])
    return resolved
