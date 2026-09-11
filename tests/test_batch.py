from __future__ import annotations

from fire_mcp import batch, loader


def test_validate_batch_clean_batch_has_no_referential_issues():
    example = loader.load_example("encumbered_loan")
    records = [
        {"entity": entity, "record": r}
        for entity, recs in example["data"].items()
        for r in recs
    ]
    result = batch.validate_batch(records)
    assert result.referential_issues == []


def test_validate_batch_flags_missing_customer_id_reference():
    records = [
        {
            "entity": "loan",
            "record": {
                "id": "L1",
                "date": "2020-01-01T00:00:00Z",
                "customer_id": "C-missing",
            },
        },
    ]
    result = batch.validate_batch(records)
    assert any(
        i.field == "customer_id"
        and i.missing_id == "C-missing"
        and i.expected_entity == "customer"
        for i in result.referential_issues
    )


def test_validate_batch_resolves_reference_present_in_same_batch():
    records = [
        {"entity": "customer", "record": {"id": "C1", "date": "2020-01-01T00:00:00Z"}},
        {
            "entity": "loan",
            "record": {"id": "L1", "date": "2020-01-01T00:00:00Z", "customer_id": "C1"},
        },
    ]
    result = batch.validate_batch(records)
    assert result.referential_issues == []


def test_validate_batch_checks_plural_id_array_fields():
    records = [
        {"entity": "loan", "record": {"id": "L1", "date": "2020-01-01T00:00:00Z"}},
        {
            "entity": "collateral",
            "record": {
                "id": "COL1",
                "date": "2020-01-01T00:00:00Z",
                "value": 100,
                "loan_ids": ["L1", "L-missing"],
            },
        },
    ]
    result = batch.validate_batch(records)
    missing = [i for i in result.referential_issues if i.field == "loan_ids"]
    assert len(missing) == 1
    assert missing[0].missing_id == "L-missing"
