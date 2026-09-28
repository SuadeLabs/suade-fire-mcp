"""An index over FIRE's worked examples, for `find_examples` and mapping evidence.

The examples are SME-reviewed FIRE records for common products (a buy-to-let
mortgage, an FX swap, ...). They record what a correct FIRE representation looks
like, not which client field it came from, so they can't inform name matching
directly. What they do give us:

- product-level lookup: "how do I represent a bridging loan" -> the example, plus
  the classification (enum) values the SMEs chose for it
- field-level evidence: how many examples actually populate a given field on an
  entity, and which values they use
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from rapidfuzz import fuzz

from . import catalog, loader, refs


@dataclass
class ExampleMatch:
    name: str
    comment: str | None
    score: float
    entities: list[str]
    # Enum-typed fields set on the example's records, e.g. {"loan": {"type":
    # ["mortgage"], "purpose": ["buy_to_let"]}} -- the part of a mapping that is
    # hardest to get right and most worth copying from a reviewed example.
    classification: dict[str, dict[str, list[str]]]


@dataclass
class FieldUsage:
    examples: list[str] = field(default_factory=list)
    values: set[str] = field(default_factory=set)


@lru_cache(maxsize=None)
def _enum_fields(entity: str) -> frozenset[str]:
    resolved = refs.resolve_entity_schema(entity, with_extension=True)
    return frozenset(
        name for name, spec in resolved.get("properties", {}).items() if "enum" in spec
    )


def _records(example: dict) -> list[tuple[str, dict]]:
    return [
        (entity, record)
        for entity, records in example.get("data", {}).items()
        if catalog.is_known_entity(entity)
        for record in records
    ]


@lru_cache(maxsize=None)
def _classification(name: str) -> dict[str, dict[str, list[str]]]:
    out: dict[str, dict[str, set[str]]] = {}
    for entity, record in _records(loader.load_example(name)):
        enum_fields = _enum_fields(entity)
        for key, value in record.items():
            if key in enum_fields and isinstance(value, str):
                out.setdefault(entity, {}).setdefault(key, set()).add(value)
    return {
        entity: {key: sorted(values) for key, values in fields.items()}
        for entity, fields in out.items()
    }


@lru_cache(maxsize=None)
def field_usage() -> dict[tuple[str, str], FieldUsage]:
    """(entity, field) -> which examples populate it and with which scalar values."""
    usage: dict[tuple[str, str], FieldUsage] = {}
    for name in loader.list_example_names():
        for entity, record in _records(loader.load_example(name)):
            for key, value in record.items():
                entry = usage.setdefault((entity, key), FieldUsage())
                if name not in entry.examples:
                    entry.examples.append(name)
                if isinstance(value, str):
                    entry.values.add(value)
    return usage


def find_examples(
    query: str, entity: str | None = None, limit: int = 5
) -> list[ExampleMatch]:
    if entity is not None:
        catalog.ensure_known_entity(entity)
    scored = []
    for name in loader.list_example_names():
        example = loader.load_example(name)
        entities = sorted(example.get("data", {}))
        if entity is not None and entity not in entities:
            continue
        readable_name = name.replace("_", " ")
        score = max(
            fuzz.token_set_ratio(query, readable_name),
            fuzz.token_set_ratio(query, example.get("comment") or "") * 0.9,
        )
        scored.append((score, name, example, entities))
    scored.sort(key=lambda row: row[0], reverse=True)
    return [
        ExampleMatch(
            name=name,
            comment=example.get("comment"),
            score=round(score, 1),
            entities=entities,
            classification=_classification(name),
        )
        for score, name, example, entities in scored[:limit]
    ]


def evidence_for(entity: str, field_name: str, max_examples: int = 3) -> dict[str, Any]:
    """Compact example evidence for one candidate field, for suggest_mapping."""
    usage = field_usage().get((entity, field_name))
    if usage is None:
        return {"used_in_examples": 0}
    evidence: dict[str, Any] = {
        "used_in_examples": len(usage.examples),
        "example_names": usage.examples[:max_examples],
    }
    if field_name in _enum_fields(entity):
        evidence["example_values"] = sorted(usage.values)
    return evidence
