from __future__ import annotations

import pytest

from fire_mcp import catalog, loader


def test_list_entities_excludes_meta_schemas():
    entities = catalog.list_entities()
    names = {entity.name for entity in entities}
    assert names == set(loader.list_schema_names()) - {"example"}
    assert "example" not in names
    assert all(entity.description for entity in entities)


def test_get_field_returns_expected_detail():
    field = catalog.get_field("loan", "accrued_interest_balance")
    assert field.type == "integer"
    assert field.monetary is True
    assert field.doc_excerpt
    assert "accrued interest" in field.doc_excerpt.lower()


def test_get_field_unknown_entity_raises():
    with pytest.raises(catalog.UnknownEntityError):
        catalog.get_field("not_a_real_entity", "id")


def test_get_field_unknown_field_raises():
    with pytest.raises(catalog.UnknownFieldError):
        catalog.get_field("loan", "not_a_real_field")


def test_get_field_extension_field_carries_jurisdictions():
    field = catalog.get_field("loan", "anchor_tenant")
    assert field.jurisdictions == ["US"]


def test_get_field_resolves_allof_inherited_field():
    field = catalog.get_field("customer", "id")
    assert field.type == "string"
    assert field.required is True
    field = catalog.get_field("issuer", "date")
    assert field.type is not None


def test_get_field_unknown_field_reports_other_entities():
    with pytest.raises(catalog.UnknownFieldError) as excinfo:
        catalog.get_field("account", "joint_customer_structure")
    assert excinfo.value.exists_on == ["loan"]


def test_get_field_unknown_field_reports_empty_exists_on_when_truly_absent():
    with pytest.raises(catalog.UnknownFieldError) as excinfo:
        catalog.get_field("loan", "not_a_real_field_anywhere_xyz")
    assert excinfo.value.exists_on == []


def test_list_fields_flags_required():
    fields = {f.name: f for f in catalog.list_fields("loan")}
    assert fields["id"].required is True
    assert fields["date"].required is True
    assert fields["accrued_interest_balance"].required is False


def test_list_fields_includes_allof_inherited_fields_for_customer():
    fields = {f.name for f in catalog.list_fields("customer")}
    assert "id" in fields
    assert "name" in fields
    assert "annual_debit_turnover" in fields


def test_list_examples_returns_title_and_comment():
    summaries = {s.name: s for s in catalog.list_examples()}
    assert "bond_future" in summaries
    assert summaries["bond_future"].title


def test_get_enum_definitions_reports_undocumented_values():
    result = catalog.get_enum_definitions("loan", "repayment_type")
    assert result.definitions
    assert isinstance(result.undocumented_values, list)


def test_get_enum_definitions_rejects_non_enum_field():
    with pytest.raises(catalog.FieldNotEnumError):
        catalog.get_enum_definitions("loan", "id")
