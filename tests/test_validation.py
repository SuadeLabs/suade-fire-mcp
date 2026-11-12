from __future__ import annotations

import copy

import pytest

from fire_mcp import loader, validation

CASES = [
    ("bond_future", "derivative"),
    ("current_account_with_guarantee", "account"),
]


def _records(example_name: str, entity: str) -> list[dict]:
    example = loader.load_example(example_name)
    return example["data"][entity]


def test_examples_validate_cleanly():
    for example_name, entity in CASES:
        for record in _records(example_name, entity):
            issues = validation.validate_record(entity, record)
            assert issues == [], f"{example_name}/{entity}: {issues}"


def test_missing_required_field_detected():
    example_name, entity = CASES[0]
    record = copy.deepcopy(_records(example_name, entity)[0])
    del record["id"]
    issues = validation.validate_record(entity, record)
    assert any(issue.kind == "missing_required" for issue in issues)


def test_wrong_type_detected():
    example_name, entity = CASES[0]
    record = copy.deepcopy(_records(example_name, entity)[0])
    record["notional_amount"] = "not-a-number"
    issues = validation.validate_record(entity, record)
    assert any(issue.kind == "type_mismatch" for issue in issues)


def test_bad_enum_detected():
    example_name, entity = CASES[0]
    record = copy.deepcopy(_records(example_name, entity)[0])
    record["asset_class"] = "not_a_real_asset_class"
    issues = validation.validate_record(entity, record)
    assert any(issue.kind == "enum_mismatch" for issue in issues)


def test_strict_mode_flags_unknown_field():
    example_name, entity = CASES[0]
    record = copy.deepcopy(_records(example_name, entity)[0])
    record["bogus_field_xyz"] = "y"
    issues = validation.validate_record(entity, record, strict=True)
    assert any(
        i.kind == "unknown_field" and i.path == "bogus_field_xyz" for i in issues
    )


def test_strict_mode_does_not_flag_known_fields():
    example_name, entity = CASES[0]
    record = copy.deepcopy(_records(example_name, entity)[0])
    issues = validation.validate_record(entity, record, strict=True)
    assert not any(i.kind == "unknown_field" for i in issues)


def test_strict_mode_does_not_flag_allof_inherited_fields_on_customer():
    issues = validation.validate_record(
        "customer", {"id": "c1", "date": "2020-01-01T00:00:00Z"}, strict=True
    )
    assert not any(i.kind == "unknown_field" for i in issues)


def test_non_strict_mode_still_accepts_unknown_field():
    example_name, entity = CASES[0]
    record = copy.deepcopy(_records(example_name, entity)[0])
    record["bogus_field_xyz"] = "y"
    issues = validation.validate_record(entity, record)
    assert issues == []


def test_missing_required_does_not_echo_the_whole_record():
    issues = validation.validate_record("loan", {"note": "x" * 5000})
    missing = [i for i in issues if i.kind == "missing_required"]
    assert missing
    assert all(i.got is None for i in missing)


def test_long_values_are_truncated_in_issues():
    issues = validation.validate_record(
        "loan", {"id": "L1", "date": "2020-01-01T00:00:00Z", "balance": "9" * 5000}
    )
    (issue,) = issues
    assert issue.kind == "type_mismatch"
    assert len(issue.got) < 300
    assert len(issue.message) < 300


def test_unknown_jurisdiction_is_rejected():
    with pytest.raises(
        validation.UnknownJurisdictionError, match="Known jurisdictions"
    ):
        validation.validate_record("loan", {}, jurisdiction="NOT_A_JURISDICTION")


def test_jurisdiction_is_case_insensitive():
    record = {"id": "L1", "date": "2020-01-01T00:00:00Z"}
    assert validation.validate_record("loan", record, jurisdiction="us") == []
