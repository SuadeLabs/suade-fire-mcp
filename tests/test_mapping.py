from __future__ import annotations

from fire_mcp import search


def test_suggest_mapping_finds_plausible_candidates():
    results = search.suggest_mapping("loan", ["cust_id", "loan_bal", "orig_date"])
    by_source: dict[str, list] = {}
    for result in results:
        by_source.setdefault(result.source_field, []).append(result)

    assert set(by_source) == {"cust_id", "loan_bal", "orig_date"}
    for source, candidates in by_source.items():
        assert candidates, source
        assert candidates[0].score > 0


def test_suggest_mapping_boosts_enum_value_match():
    results = search.suggest_mapping(
        "loan",
        ["accounting_basis"],
        sample_values={"accounting_basis": "held_for_trading"},
    )
    matches = [r for r in results if r.entity_field == "accounting_treatment"]
    assert matches
    assert any(r.reason == "enum value match" for r in matches)


def _top(source: str) -> str:
    return search.suggest_mapping("loan", [source])[0].entity_field


def test_suggest_mapping_ignores_case_and_separator_style():
    for source in ["CustomerID", "customer-id", "CUSTOMER_ID", "customer id"]:
        assert _top(source) == "customer_id", source


def test_suggest_mapping_does_not_rank_bare_id_first_for_any_x_id():
    assert _top("cust_id") == "customer_id"


def test_suggest_mapping_enum_boost_ignores_case():
    results = search.suggest_mapping(
        "loan",
        ["accounting_basis"],
        sample_values={"accounting_basis": "Held_For_Trading"},
    )
    assert any(r.reason == "enum value match" for r in results)


def test_normalise_splits_camel_case_and_separators():
    assert search.normalise("OutstandingBalanceGBP") == "outstanding balance gbp"
    assert search.normalise("acc_fv-change.YTD") == "acc fv change ytd"


def test_example_usage_breaks_name_similarity_ties():
    # By name alone, prod_type ranks provision_type first; the worked examples
    # set loan.type far more often, so type should win.
    top, *_ = search.suggest_mapping("loan", ["prod_type"])
    assert top.entity_field == "type"
    assert top.example_boost > 0


def test_example_boost_does_not_override_a_clear_name_match():
    # issue_date is rare in the examples, issuer_id common; the closer name wins.
    assert _top_on("security", "issue_dt") == "issue_date"


def test_example_boost_is_bounded_and_included_in_score():
    for candidate in search.suggest_mapping("loan", ["balance", "cust_id", "x"]):
        assert 0 <= candidate.example_boost <= search.EXAMPLE_BOOST_MAX
        assert candidate.score <= 100


def test_no_example_boost_for_entities_with_few_examples(monkeypatch):
    monkeypatch.setattr(search.examples, "entity_example_count", lambda entity: 1)
    candidates = search.suggest_mapping("loan", ["prod_type"])
    assert all(c.example_boost == 0 for c in candidates)


def test_candidates_are_ranked_by_final_score():
    candidates = search.suggest_mapping("loan", ["prod_type", "int_rate"])
    for source in ("prod_type", "int_rate"):
        scores = [c.score for c in candidates if c.source_field == source]
        assert scores == sorted(scores, reverse=True)


def _top_on(entity: str, source: str) -> str:
    return search.suggest_mapping(entity, [source])[0].entity_field
