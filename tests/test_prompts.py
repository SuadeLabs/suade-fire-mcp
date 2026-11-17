from __future__ import annotations

import anyio
import pytest
from mcp import Client
from mcp.shared.exceptions import MCPError
from mcp.types import INVALID_PARAMS, PromptReference

from fire_mcp import catalog, prompts, server


def _with_client(fn):
    async def run():
        async with Client(server.create_server()) as client:
            return await fn(client)

    return anyio.run(run)


def test_prompts_are_listed_with_described_arguments():
    listed = _with_client(lambda c: c.list_prompts()).prompts
    assert {p.name for p in listed} == {
        "map_source_schema",
        "explain_validation_failure",
    }
    for prompt in listed:
        assert prompt.title and prompt.description
        for argument in prompt.arguments:
            assert argument.required and argument.description, argument.name


def test_map_source_schema_accepts_a_pasted_header_row():
    text = prompts.map_source_schema_text("loan", "cust_id\tbal_amt, rate\nccy")
    for name in ("cust_id", "bal_amt", "rate", "ccy"):
        assert f"- {name}\n" in text or text.endswith(f"- {name}")
    assert "suggest_mapping" in text and "get_field" in text


def test_explain_validation_failure_embeds_the_record():
    text = prompts.explain_validation_failure_text("loan", '{"id": "L1"}')
    assert '"id": "L1"' in text
    assert "strict=true" in text


@pytest.mark.parametrize(
    "name, args, message",
    [
        (
            "map_source_schema",
            {"entity": "loans", "source_fields": "x"},
            "Use list_entities",
        ),
        (
            "map_source_schema",
            {"entity": "loan", "source_fields": " , \n"},
            "at least one field",
        ),
        (
            "explain_validation_failure",
            {"entity": "loan", "record": "{not json"},
            "not valid JSON",
        ),
        (
            "explain_validation_failure",
            {"entity": "loan", "record": "[1, 2]"},
            "JSON object",
        ),
    ],
)
def test_bad_arguments_reach_the_user_with_their_message(name, args, message):
    # Called on the server directly: through the in-process Client the error
    # arrives wrapped in the client's task-group ExceptionGroup.
    with pytest.raises(MCPError, match=message) as info:
        anyio.run(server.create_server().get_prompt, name, args)
    assert info.value.error.code == INVALID_PARAMS


def test_prompt_entity_argument_autocompletes():
    result = _with_client(
        lambda c: c.complete(
            PromptReference(type="ref/prompt", name="map_source_schema"),
            {"name": "entity", "value": "loan_"},
        )
    )
    assert result.completion.values == [
        n for n in catalog.known_entity_names() if n.startswith("loan_")
    ]


def test_instructions_name_only_tools_that_exist():
    import re

    mcp = server.create_server()
    names = {t.name for t in anyio.run(mcp.list_tools)}
    mentioned = set(re.findall(r"\b([a-z]+_[a-z_]+)\b", server.INSTRUCTIONS))
    # Parameter names that appear in the instructions alongside tool names.
    mentioned -= {"include_enum_definitions"}
    assert mentioned <= names, mentioned - names
