from __future__ import annotations

import anyio
import pytest
from mcp.server.mcpserver.exceptions import (
    ResourceError,
    ToolError,
    UnexpectedToolError,
)

from fire_mcp import server, tools


def _call(name, args):
    return anyio.run(server.mcp.call_tool, name, args)


def test_every_tool_has_a_title_and_read_only_annotations():
    listed = anyio.run(server.mcp.list_tools)
    assert len(listed) == 9
    for tool in listed:
        assert tool.title, tool.name
        assert len(tool.name) <= 64
        assert tool.annotations.read_only_hint is True, tool.name
        assert tool.annotations.destructive_hint is False, tool.name


def test_anticipated_errors_reach_the_model_with_their_message():
    with pytest.raises(ToolError, match="Use list_entities") as info:
        _call("list_fields", {"entity": "not_an_entity"})
    assert not isinstance(info.value, UnexpectedToolError)


def test_anticipated_resource_errors_keep_their_message():
    with pytest.raises(ResourceError, match="Use list_entities"):
        anyio.run(server.mcp.read_resource, "fire://schemas/not_an_entity")


def test_search_fields_rejects_limit_over_cap():
    with pytest.raises(ToolError, match="between 1 and 50"):
        _call("search_fields", {"query": "rate", "limit": tools.MAX_SEARCH_LIMIT + 1})


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
    with pytest.raises(ToolError, match="at most 200 source fields"):
        _call("suggest_mapping", {"entity": "loan", "source_fields": fields})
