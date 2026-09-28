from __future__ import annotations

import pytest

from fire_mcp import catalog, examples, loader


def test_find_examples_matches_product_names():
    names = [m.name for m in examples.find_examples("overdraft", limit=3)]
    assert names[0] == "overdraft_account"


def _first_loan_example() -> tuple[str, dict]:
    # Derived from whatever examples the FIRE checkout has, so this passes both
    # before and after the SME example set (SuadeLabs/fire#690) lands.
    for name in loader.list_example_names():
        loans = loader.load_example(name)["data"].get("loan")
        if loans:
            return name, loans[0]
    pytest.skip("FIRE checkout has no loan examples")


def test_find_examples_returns_classification_values():
    name, loan = _first_loan_example()
    match = examples.find_examples(name.replace("_", " "), entity="loan", limit=20)
    by_name = {m.name: m for m in match}
    assert name in by_name
    classification = by_name[name].classification["loan"]
    # type is an enum on loan, so the example's own value must be reported.
    assert loan["type"] in classification["type"]
    # Non-enum fields (ids, amounts, dates) are never reported as classification.
    assert "id" not in classification and "balance" not in classification


def test_find_examples_entity_filter_only_returns_examples_with_that_entity():
    for match in examples.find_examples("swap", entity="derivative", limit=10):
        assert "derivative" in match.entities


def test_find_examples_rejects_unknown_entity():
    with pytest.raises(catalog.UnknownEntityError):
        examples.find_examples("swap", entity="not_an_entity")


def test_evidence_for_counts_examples_using_a_field():
    name, loan = _first_loan_example()
    evidence = examples.evidence_for("loan", "type")
    assert evidence["used_in_examples"] > 0
    assert loan["type"] in evidence["example_values"]


def test_evidence_for_unused_field_is_zero():
    assert examples.evidence_for("loan", "not_a_field") == {"used_in_examples": 0}
