"""Batch validation: per-record validate_record plus within-batch referential
integrity checks (does a *_id / *_ids field on one record point at an id
actually present in the same batch)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import catalog, validation

# Explicit, curated field-name -> target-entity table. Deliberately NOT
# suffix-stripping heuristics: most *_id fields in FIRE (national_id,
# version_id, parent_id, risk_group_id, deal_id, facility_id, mna_id, csa_id,
# frr_id, birr_id, behavioral_curve_id, hedge_id, owner_id,
# securitisation_id, ...) do not reference another FIRE entity's own
# top-level `id` at all, or reference systems/records outside this schema's
# entity list. Only add an entry here once it's confirmed the field's value
# is meant to equal another record's `id` within the same FIRE dataset.
SINGLE_ID_FIELD_ENTITY_MAP: dict[str, str] = {
    "customer_id": "customer",
    "loan_id": "loan",
    "guarantor_id": "guarantor",
    "issuer_id": "issuer",
    "security_id": "security",
    "derivative_id": "derivative",
    "underlying_issuer_id": "issuer",
    "underlying_security_id": "security",
    "underlying_derivative_id": "derivative",
}

# Fields whose value is a *list* of ids (e.g. collateral.account_ids), each
# checked individually against the same-entity id index.
PLURAL_ID_FIELD_ENTITY_MAP: dict[str, str] = {
    "account_ids": "account",
    "loan_ids": "loan",
}


@dataclass
class BatchRecordResult:
    index: int
    entity: str
    issues: list[validation.ValidationIssue] = field(default_factory=list)


@dataclass
class ReferentialIssue:
    index: int
    entity: str
    field: str
    missing_id: str
    expected_entity: str
    message: str


@dataclass
class BatchValidationResult:
    records: list[BatchRecordResult]
    referential_issues: list[ReferentialIssue]


# Id values that can sensibly be compared as strings. Anything else (an object,
# a nested list) is already reported as a type mismatch by schema validation.
_SCALAR_ID_TYPES = (str, int)


def _item_problem(item: Any) -> validation.ValidationIssue | None:
    """Why a batch item can't be validated at all, or None if it's well-formed."""
    if not isinstance(item, dict) or not isinstance(item.get("entity"), str):
        return validation.ValidationIssue(
            path="<item>",
            message='Each batch item must be {"entity": str, "record": object}.',
            kind="invalid_item",
        )
    if not isinstance(item.get("record"), dict):
        return validation.ValidationIssue(
            path="<item>/record",
            message='Each batch item must have a "record" object.',
            kind="invalid_item",
        )
    try:
        catalog.ensure_known_entity(item["entity"])
    except catalog.UnknownEntityError as exc:
        return validation.ValidationIssue(
            path="<item>/entity", message=str(exc), kind="unknown_entity"
        )
    return None


def _index_present_ids(records: list[dict[str, Any]]) -> dict[str, set[str]]:
    present: dict[str, set[str]] = {}
    for item in records:
        record_id = item["record"].get("id")
        if isinstance(record_id, _SCALAR_ID_TYPES):
            present.setdefault(item["entity"], set()).add(str(record_id))
    return present


def _referential_issues_for(
    index: int, item: dict[str, Any], present: dict[str, set[str]]
) -> list[ReferentialIssue]:
    entity = item["entity"]
    record = item["record"]
    issues = []
    for field_name, expected_entity in SINGLE_ID_FIELD_ENTITY_MAP.items():
        value = record.get(field_name)
        if not isinstance(value, _SCALAR_ID_TYPES):
            continue
        value = str(value)
        if value not in present.get(expected_entity, set()):
            issues.append(
                ReferentialIssue(
                    index=index,
                    entity=entity,
                    field=field_name,
                    missing_id=value,
                    expected_entity=expected_entity,
                    message=(
                        f"{entity}[{index}].{field_name} = {value!r} was not found "
                        f"among {expected_entity!r} records in this batch (it may "
                        "exist elsewhere in the full dataset -- this only checks "
                        "referential integrity within the given batch)."
                    ),
                )
            )
    for field_name, expected_entity in PLURAL_ID_FIELD_ENTITY_MAP.items():
        values = record.get(field_name)
        if not isinstance(values, list):
            continue
        for value in values:
            if not isinstance(value, _SCALAR_ID_TYPES):
                continue
            value = str(value)
            if value not in present.get(expected_entity, set()):
                issues.append(
                    ReferentialIssue(
                        index=index,
                        entity=entity,
                        field=field_name,
                        missing_id=value,
                        expected_entity=expected_entity,
                        message=(
                            f"{entity}[{index}].{field_name} contains {value!r}, "
                            f"not found among {expected_entity!r} records in this "
                            "batch."
                        ),
                    )
                )
    return issues


def validate_batch(
    records: list[dict[str, Any]],
    jurisdiction: str | None = None,
    strict: bool = False,
) -> BatchValidationResult:
    """records: list of {"entity": str, "record": dict}.

    A malformed item or unknown entity is reported against that item alone, so
    one bad item doesn't hide the results for the rest of the batch.
    """
    if jurisdiction is not None:
        jurisdiction = validation.canonical_jurisdiction(jurisdiction)
    problems = [_item_problem(item) for item in records]
    valid_items = [
        item for item, problem in zip(records, problems, strict=True) if not problem
    ]
    present = _index_present_ids(valid_items)
    record_results = []
    referential_issues = []
    for index, (item, problem) in enumerate(zip(records, problems, strict=True)):
        if problem is not None:
            entity = item.get("entity") if isinstance(item, dict) else None
            record_results.append(
                BatchRecordResult(index=index, entity=str(entity), issues=[problem])
            )
            continue
        entity = item["entity"]
        issues = validation.validate_record(
            entity, item["record"], jurisdiction=jurisdiction, strict=strict
        )
        record_results.append(
            BatchRecordResult(index=index, entity=entity, issues=issues)
        )
        referential_issues.extend(_referential_issues_for(index, item, present))
    return BatchValidationResult(
        records=record_results, referential_issues=referential_issues
    )
