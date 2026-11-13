"""Fuzzy search over FIRE fields, for `search_fields` and `suggest_mapping`.

FIRE field names are abbreviated snake_case (`cust_id`, `mtm_dirty`,
`acc_fv_change_before_taxes`), so token-based fuzzy scoring (rapidfuzz) does
much better here than a plain character-diff ratio. Both sides are normalised
into lowercase space-separated words first, so a source system's `CustomerID`,
`customer-id` or `CUSTOMER_ID` all compare equally against FIRE's `customer_id`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from rapidfuzz import fuzz, process

from . import catalog, examples, refs
from .text import normalise


@dataclass
class _IndexEntry:
    """One searchable field, shared by every entity that defines it identically.

    FIRE repeats most field names across entities (`balance` is on five), so
    indexing per (entity, field) would let one field fill half of a result page
    with identical rows. Entries are grouped by name, type and enum instead;
    only fields whose enum genuinely differs by entity (loan.repayment_type vs
    security.repayment_type) stay as separate entries. Descriptions do vary by
    entity, so each variant keeps its own.
    """

    field: str
    type: Any
    enum: list[str] | None
    # (entity, description, [(channel, normalised text), ...]) per entity.
    variants: list[tuple[str, str | None, list[tuple[str, str]]]] = field(
        default_factory=list
    )

    @property
    def entities(self) -> list[str]:
        return sorted(entity for entity, _, _ in self.variants)


_INDEX_CACHE: list[_IndexEntry] | None = None


def _mapping_score(source: str, target: str, **kwargs: Any) -> float:
    # token_set_ratio alone scores 100 whenever one name's words are a subset of
    # the other's, so every "x id" source tied with the bare `id` field. WRatio
    # handles abbreviations (cust -> customer); token_sort_ratio penalises the
    # words that don't match.
    return 0.5 * fuzz.WRatio(source, target, **kwargs) + 0.5 * fuzz.token_sort_ratio(
        source, target, **kwargs
    )


def _build_index() -> list[_IndexEntry]:
    entries: dict[str, _IndexEntry] = {}
    for entity in catalog.known_entity_names():
        resolved = refs.resolve_entity_schema(entity, with_extension=True)
        for field_name, spec in resolved.get("properties", {}).items():
            key = json.dumps([field_name, spec.get("type"), spec.get("enum")])
            entry = entries.get(key)
            if entry is None:
                entry = entries[key] = _IndexEntry(
                    field=field_name, type=spec.get("type"), enum=spec.get("enum")
                )
            texts = [
                (kind, normalise(text))
                for kind, text in _candidate_texts(field_name, spec)
            ]
            entry.variants.append((entity, spec.get("description"), texts))
    return list(entries.values())


def _get_index() -> list[_IndexEntry]:
    global _INDEX_CACHE
    if _INDEX_CACHE is None:
        _INDEX_CACHE = _build_index()
    return _INDEX_CACHE


@dataclass
class SearchResult:
    field: str
    # Every entity on which this field has this type and enum.
    entities: list[str]
    score: float
    matched_on: str
    type: str | None
    enum: list[str] | None
    # From the entity whose text matched best (descriptions differ by entity).
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
    for entry in _get_index():
        best_score = 0.0
        best_on = "name"
        best_description = entry.variants[0][1]
        for _, description, texts in entry.variants:
            for kind, text in texts:
                if text == normalised_query:
                    score = 100.0
                else:
                    score = fuzz.WRatio(normalised_query, text) * _CHANNEL_WEIGHT[kind]
                if score > best_score:
                    best_score, best_on, best_description = score, kind, description
        scored.append((best_score, entry, best_on, best_description))
    scored.sort(key=lambda row: row[0], reverse=True)

    return [
        SearchResult(
            field=entry.field,
            entities=entry.entities,
            score=round(score, 1),
            matched_on=matched_on,
            type=entry.type,
            enum=entry.enum,
            description=description,
        )
        for score, entry, matched_on, description in scored[:limit]
    ]


@dataclass
class MappingCandidate:
    source_field: str
    entity_field: str
    score: float
    reason: str
    # Points added to score because FIRE's worked examples populate this field
    # (already included in score; reported so the boost is never hidden).
    example_boost: float = 0.0


# Evidence re-ranking. Name similarity can't tell `provision_type` from `type` for
# a source field called "prod_type"; the worked examples can (`type` is set on 26
# of 27 loan examples, `provision_type` on 6). A field gets up to
# EXAMPLE_BOOST_MAX points, scaled by the share of the entity's examples that
# populate it. Tuned on a 41-case benchmark (loan, derivative, security,
# account): 8 fixed two mappings and broke none; the first correct mapping broke
# at 12.5 (issue_dt -> issuer_id, as issue_date is in only 6 security examples).
EXAMPLE_BOOST_MAX = 8.0
# Below this many examples, a usage share is noise (1 of 1 is 100%), so no boost.
MIN_EXAMPLES_FOR_BOOST = 5
# Candidates considered per source field before re-ranking, so a well-used field
# just outside the top 3 by name can still move up.
_CANDIDATE_POOL = 10
_ENUM_MATCH_BONUS = 15.0


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

    entity_examples = examples.entity_example_count(entity)

    def example_boost(field_name: str) -> float:
        if entity_examples < MIN_EXAMPLES_FOR_BOOST:
            return 0.0
        used = examples.evidence_for(entity, field_name)["used_in_examples"]
        return EXAMPLE_BOOST_MAX * used / entity_examples

    results = []
    for source in source_fields:
        matches = process.extract(
            source,
            field_names,
            scorer=_mapping_score,
            processor=normalise,
            limit=max(limit_per_field, _CANDIDATE_POOL),
        )
        sample = sample_values.get(source)
        sample_text = normalise(str(sample)) if sample is not None else None
        candidates = []
        for candidate_name, score, _ in matches:
            enum = properties[candidate_name].get("enum") or []
            is_enum_match = sample_text is not None and sample_text in {
                normalise(value) for value in enum
            }
            boost = example_boost(candidate_name)
            adjusted = score + boost + (_ENUM_MATCH_BONUS if is_enum_match else 0.0)
            candidates.append(
                MappingCandidate(
                    source_field=source,
                    entity_field=candidate_name,
                    score=round(min(100.0, adjusted), 1),
                    reason="enum value match" if is_enum_match else "name similarity",
                    example_boost=round(boost, 1),
                )
            )
        # Stable sort: equal scores keep rapidfuzz's name-similarity order.
        candidates.sort(key=lambda c: c.score, reverse=True)
        results.extend(candidates[:limit_per_field])
    return results
