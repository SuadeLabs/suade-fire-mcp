"""Fuzzy search over FIRE fields, for `search_fields` and `suggest_mapping`.

FIRE field names are abbreviated snake_case (`cust_id`, `mtm_dirty`,
`acc_fv_change_before_taxes`), so token-based fuzzy scoring (rapidfuzz) does
much better here than a plain character-diff ratio. Both sides are normalised
into lowercase space-separated words first, so a source system's `CustomerID`,
`customer-id` or `CUSTOMER_ID` all compare equally against FIRE's `customer_id`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from rapidfuzz import fuzz, process

from . import catalog, refs

# (entity, field name, field spec, [(channel, normalised text), ...])
_IndexEntry = tuple[str, str, dict, list[tuple[str, str]]]
_INDEX_CACHE: list[_IndexEntry] | None = None

_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_NON_ALNUM_RE = re.compile(r"[^0-9a-zA-Z]+")


def normalise(text: str) -> str:
    """'OutstandingBalance' / 'outstanding_balance' -> 'outstanding balance'."""
    text = _CAMEL_BOUNDARY_RE.sub(" ", text)
    return " ".join(_NON_ALNUM_RE.sub(" ", text).lower().split())


def _mapping_score(source: str, target: str, **kwargs: Any) -> float:
    # token_set_ratio alone scores 100 whenever one name's words are a subset of
    # the other's, so every "x id" source tied with the bare `id` field. WRatio
    # handles abbreviations (cust -> customer); token_sort_ratio penalises the
    # words that don't match.
    return 0.5 * fuzz.WRatio(source, target, **kwargs) + 0.5 * fuzz.token_sort_ratio(
        source, target, **kwargs
    )


def _build_index() -> list[_IndexEntry]:
    entries = []
    for entity in catalog.known_entity_names():
        resolved = refs.resolve_entity_schema(entity, with_extension=True)
        for field_name, spec in resolved.get("properties", {}).items():
            texts = [
                (kind, normalise(text))
                for kind, text in _candidate_texts(field_name, spec)
            ]
            entries.append((entity, field_name, spec, texts))
    return entries


def _get_index() -> list[_IndexEntry]:
    global _INDEX_CACHE
    if _INDEX_CACHE is None:
        _INDEX_CACHE = _build_index()
    return _INDEX_CACHE


@dataclass
class SearchResult:
    entity: str
    field: str
    score: float
    matched_on: str
    type: str | None
    enum: list[str] | None
    description: str | None


def _candidate_texts(field_name: str, spec: dict) -> list[tuple[str, str]]:
    texts = [("name", field_name)]
    description = spec.get("description")
    if description:
        texts.append(("description", description))
    for value in spec.get("enum") or []:
        texts.append(("enum", value))
    return texts


# A single short enum value can score deceptively high against a longer
# query under plain WRatio (e.g. the enum value "customer" scores higher
# against "customer id" than the field "customer_id" does). Down-weight
# enum/description matches slightly so a genuine field-name match wins ties.
# An exact match (after normalising) is never down-weighted, whatever its channel.
_CHANNEL_WEIGHT = {"name": 1.0, "description": 0.92, "enum": 0.85}


def search_fields(query: str, limit: int = 10) -> list[SearchResult]:
    normalised_query = normalise(query)
    scored = []
    for entity, field_name, spec, texts in _get_index():
        best_score = 0.0
        best_on = "name"
        for kind, text in texts:
            if text == normalised_query:
                score = 100.0
            else:
                score = fuzz.WRatio(normalised_query, text) * _CHANNEL_WEIGHT[kind]
            if score > best_score:
                best_score, best_on = score, kind
        scored.append((best_score, entity, field_name, spec, best_on))
    scored.sort(key=lambda row: row[0], reverse=True)

    results = []
    for score, entity, field_name, spec, matched_on in scored[:limit]:
        results.append(
            SearchResult(
                entity=entity,
                field=field_name,
                score=round(score, 1),
                matched_on=matched_on,
                type=spec.get("type"),
                enum=spec.get("enum"),
                description=spec.get("description"),
            )
        )
    return results


@dataclass
class MappingCandidate:
    source_field: str
    entity_field: str
    score: float
    reason: str


def suggest_mapping(
    entity: str,
    source_fields: list[str],
    sample_values: dict[str, Any] | None = None,
    limit_per_field: int = 3,
) -> list[MappingCandidate]:
    catalog.ensure_known_entity(entity)
    resolved = refs.resolve_entity_schema(entity, with_extension=True)
    properties = resolved.get("properties", {})
    field_names = list(properties.keys())
    sample_values = sample_values or {}

    results = []
    for source in source_fields:
        matches = process.extract(
            source,
            field_names,
            scorer=_mapping_score,
            processor=normalise,
            limit=limit_per_field,
        )
        sample = sample_values.get(source)
        sample_text = normalise(str(sample)) if sample is not None else None
        for candidate_name, score, _ in matches:
            enum = properties[candidate_name].get("enum") or []
            is_enum_match = sample_text is not None and sample_text in {
                normalise(value) for value in enum
            }
            adjusted = min(100.0, score + 15) if is_enum_match else score
            results.append(
                MappingCandidate(
                    source_field=source,
                    entity_field=candidate_name,
                    score=round(adjusted, 1),
                    reason="enum value match" if is_enum_match else "name similarity",
                )
            )
    return results
