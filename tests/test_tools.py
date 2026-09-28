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
