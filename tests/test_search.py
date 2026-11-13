from __future__ import annotations

from fire_mcp import search


def test_search_fields_typo_still_finds_target():
    results = search.search_fields("acc_fv_chnge_credit_risk")
    fields = {r.field for r in results}
    assert "acc_fv_change_credit_risk" in fields


def test_search_fields_matches_on_enum_value():
    results = search.search_fields("fv_thru_pnl")
    assert any(
        r.field == "accounting_treatment" and r.matched_on == "enum" for r in results
    )


def test_search_fields_short_id_query_ranks_id_fields_first():
    results = search.search_fields("customer id", limit=5)
    assert results
    assert results[0].field in {"id", "customer_id"}


def test_search_fields_excludes_example_meta_schema():
    results = search.search_fields("comment", limit=20)
    assert all("example" not in r.entities for r in results)


def test_search_index_includes_allof_inherited_fields():
    # A generous limit -- this asserts the allOf-inherited field is present
    # in the index at all, not that ranking surfaces it near the top (search
    # ranking/noise reduction is a separate, out-of-scope concern).
    results = search.search_fields("customer id", limit=20)
    assert any(r.field == "id" and "customer" in r.entities for r in results)


def test_search_fields_groups_a_shared_field_into_one_row():
    results = search.search_fields("balance", limit=10)
    balance_rows = [r for r in results if r.field == "balance"]
    assert len(balance_rows) == 1
    assert {"account", "loan", "security"} <= set(balance_rows[0].entities)
    assert balance_rows[0].description
    # The freed slots go to other fields rather than repeats.
    assert len({r.field for r in results}) == len(results)


def test_search_fields_keeps_fields_whose_enum_differs_by_entity_separate():
    rows = [
        r for r in search.search_fields("repayment_type") if r.field == "repayment_type"
    ]
    by_entity = {entity: set(r.enum) for r in rows for entity in r.entities}
    assert {"loan", "security"} <= set(by_entity)
    assert by_entity["loan"] != by_entity["security"]
    # Each variant is its own row: no row lists an entity under the wrong enum.
    assert len(rows) == len({frozenset(r.enum) for r in rows})
