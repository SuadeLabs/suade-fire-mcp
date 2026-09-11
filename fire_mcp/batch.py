"""Batch validation: per-record validate_record plus within-batch referential
integrity checks (does a *_id / *_ids field on one record point at an id
actually present in the same batch)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import validation

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


def _index_present_ids(records: list[dict[str, Any]]) -> dict[str, set[str]]:
    present: dict[str, set[str]] = {}
    for item in records:
        entity = item["entity"]
        record = item["record"]
        if record.get("id") is not None:
            present.setdefault(entity, set()).add(str(record["id"]))
    return present


def _referential_issues_for(
    index: int, item: dict[str, Any], present: dict[str, set[str]]
) -> list[ReferentialIssue]:
    entity = item["entity"]
    record = item["record"]
    issues = []
    for field_name, expected_entity in SINGLE_ID_FIELD_ENTITY_MAP.items():
        value = record.get(field_name)
        if value is None:
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
        values = record.get(field_name) or []
        for value in values:
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
    """records: list of {"entity": str, "record": dict}."""
    present = _index_present_ids(records)
    record_results = []
    referential_issues = []
    for index, item in enumerate(records):
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
