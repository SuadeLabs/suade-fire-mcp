from __future__ import annotations

import anyio
import pytest
from mcp.server.mcpserver.exceptions import (
    ResourceError,
    ToolError,
    UnexpectedToolError,
)

from fire_mcp import catalog, refs, server, tools
from fire_mcp.validation import known_jurisdictions

MCP = server.create_server()


def _call(name, args):
    return anyio.run(MCP.call_tool, name, args)


def _properties():
    for tool in anyio.run(MCP.list_tools):
        for param, schema in tool.input_schema.get("properties", {}).items():
            yield tool.name, param, schema


def test_every_tool_has_a_title_and_read_only_annotations():
    listed = anyio.run(MCP.list_tools)
    assert len(listed) == 10
    for tool in listed:
        assert tool.title, tool.name
        assert len(tool.name) <= 64
        assert tool.annotations.read_only_hint is True, tool.name
        assert tool.annotations.destructive_hint is False, tool.name


def test_every_parameter_has_a_description():
    # Some clients show the model only the per-parameter schema, not the
    # tool's docstring, so each parameter has to explain itself.
    for tool, param, schema in _properties():
        assert schema.get("description"), f"{tool}.{param}"


def _enum(schema):
    if "enum" in schema:
        return schema["enum"]
    for option in schema.get("anyOf", []):
        if "enum" in option:
            return option["enum"]
    return None


def test_entity_and_jurisdiction_parameters_list_their_valid_values():
    seen = set()
    for tool, param, schema in _properties():
        if param == "entity":
            assert _enum(schema) == catalog.known_entity_names(), tool
            seen.add(param)
        elif param == "jurisdiction":
            assert _enum(schema) == list(known_jurisdictions()), tool
            seen.add(param)
    assert seen == {"entity", "jurisdiction"}


def test_wrong_entity_still_gets_the_package_message_not_a_schema_error():
    # The enum is advertised, not enforced by the SDK, so the model is told
    # which tool lists the valid names.
    with pytest.raises(ToolError, match="Use list_entities"):
        _call("get_field", {"entity": "loans", "field": "balance"})


def test_jurisdiction_stays_case_insensitive():
    result = _call(
        "validate_record",
        {
            "entity": "loan",
            "record": {"id": "L1", "date": "2026-01-01T00:00:00Z"},
            "jurisdiction": "us",
        },
    )
    assert result.structured_content["valid"] is True


def test_anticipated_errors_reach_the_model_with_their_message():
    with pytest.raises(ToolError, match="Use list_entities") as info:
        _call("list_fields", {"entity": "not_an_entity"})
    assert not isinstance(info.value, UnexpectedToolError)


def test_anticipated_resource_errors_keep_their_message():
    with pytest.raises(ResourceError, match="Use list_entities"):
        anyio.run(MCP.read_resource, "fire://schemas/not_an_entity")


def test_search_fields_rejects_limit_over_cap():
    with pytest.raises(ToolError, match="between 1 and 50"):
        _call("search_fields", {"query": "rate", "limit": tools.MAX_SEARCH_LIMIT + 1})


@pytest.mark.parametrize(
    "name, args",
    [
        ("search_fields", {"query": "  "}),
        ("find_examples", {"query": ""}),
        ("suggest_mapping", {"entity": "loan", "source_fields": ["cust_id", " "]}),
    ],
)
def test_blank_queries_are_rejected_instead_of_matching_everything(name, args):
    with pytest.raises(ToolError, match="blank"):
        _call(name, args)


def test_suggest_mapping_rejects_empty_source_fields():
    with pytest.raises(ToolError, match="must not be empty"):
        _call("suggest_mapping", {"entity": "loan", "source_fields": []})


def test_find_examples_rejects_limit_over_cap():
    with pytest.raises(
        ToolError, match=f"between 1 and {tools.MAX_FIND_EXAMPLES_LIMIT}"
    ):
        _call(
            "find_examples",
            {"query": "swap", "limit": tools.MAX_FIND_EXAMPLES_LIMIT + 1},
        )


def test_validate_batch_rejects_oversized_batch():
    records = [{"entity": "loan", "record": {}}] * (tools.MAX_BATCH_RECORDS + 1)
    with pytest.raises(ToolError, match="at most 1000 records"):
        _call("validate_batch", {"records": records})


def test_list_fields_returns_summaries_within_result_size_limit():
    result = _call("list_fields", {"entity": "loan"})
    fields = result.structured_content["result"]
    assert set(fields[0]) == set(tools._FIELD_SUMMARY_KEYS) | {"is_enum"}
    # claude.ai caps tool results at ~150k characters; Claude Code at 25k tokens.
    assert sum(len(block.text) for block in result.content) < 100_000


def test_validate_record_returns_visible_content_when_valid():
    result = _call(
        "validate_record",
        {"entity": "loan", "record": {"id": "L1", "date": "2026-01-01T00:00:00Z"}},
    )
    assert result.structured_content == {"valid": True, "issues": []}
    assert result.content, "a valid record must not produce an empty result"


def test_suggest_mapping_carries_its_basis_with_the_candidates():
    result = _call(
        "suggest_mapping", {"entity": "loan", "source_fields": ["cust_id", "bal_amt"]}
    )
    payload = result.structured_content
    assert payload["basis"] == tools.MAPPING_BASIS
    assert {c["source_field"] for c in payload["candidates"]} == {"cust_id", "bal_amt"}
    assert all(
        "used_in_examples" in c["example_evidence"] for c in payload["candidates"]
    )


@pytest.mark.parametrize("name", ["../schemas/loan", "/etc/hostname", "bond_future/.."])
def test_get_examples_rejects_names_that_are_paths(name):
    with pytest.raises(ToolError, match="No example named"):
        _call("get_examples", {"name": name})


def test_validate_batch_lists_only_records_with_issues():
    records = [
        {"entity": "loan", "record": {"id": "L1", "date": "2026-01-01T00:00:00Z"}},
        {"entity": "loan", "record": {"id": "L2"}},
    ]
    payload = _call("validate_batch", {"records": records}).structured_content
    assert payload["valid"] is False
    assert payload["record_count"] == 2
    assert payload["issue_count"] == 1
    assert payload["truncated"] is False
    assert [r["index"] for r in payload["records"]] == [1]


def test_validate_batch_truncates_issues_within_result_size_limit():
    records = [{"entity": "loan", "record": {"note": "x" * 3000}}] * 1000
    result = _call("validate_batch", {"records": records})
    payload = result.structured_content
    assert payload["issue_count"] == 2000
    assert payload["truncated"] is True
    returned = sum(len(r["issues"]) for r in payload["records"])
    assert returned == tools.MAX_BATCH_ISSUES
    assert sum(len(block.text) for block in result.content) < 100_000


def test_suggest_mapping_rejects_too_many_source_fields():
    fields = [f"f{i}" for i in range(tools.MAX_MAPPING_SOURCE_FIELDS + 1)]
    with pytest.raises(
        ToolError, match=f"at most {tools.MAX_MAPPING_SOURCE_FIELDS} source fields"
    ):
        _call("suggest_mapping", {"entity": "loan", "source_fields": fields})


def test_suggest_mapping_at_max_fields_stays_within_result_size_limit():
    # Worst case: source fields named like FIRE's own security fields, so every
    # candidate carries example evidence (names and enum values).
    props = list(
        refs.resolve_entity_schema("security", with_extension=True)["properties"]
    )
    source_fields = (props * 3)[: tools.MAX_MAPPING_SOURCE_FIELDS]
    result = _call(
        "suggest_mapping", {"entity": "security", "source_fields": source_fields}
    )
    # claude.ai caps tool results at ~150k characters; Claude Code at 25k tokens.
    assert sum(len(block.text) for block in result.content) < 100_000
