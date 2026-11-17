from __future__ import annotations

import anyio
import pytest
from mcp.types import CompletionArgument, ResourceTemplateReference

from fire_mcp import catalog, resources, server


def _complete(uri, name, value):
    return resources.complete(
        ResourceTemplateReference(type="ref/resource", uri=uri),
        CompletionArgument(name=name, value=value),
    )


def test_every_resource_template_parameter_has_completions():
    templates = anyio.run(server.create_server().list_resource_templates)
    for template in templates:
        param = template.uri_template.split("{")[1].rstrip("}")
        assert (template.uri_template, param) in resources._COMPLETION_SOURCES


def test_entity_completion_filters_by_prefix():
    completion = _complete("fire://schemas/{entity}", "entity", "loan")
    assert completion.values == ["loan", "loan_cash_flow", "loan_transaction"]
    assert completion.has_more is False


def test_empty_prefix_lists_every_entity():
    completion = _complete("fire://schemas/{entity}", "entity", "")
    assert completion.values == catalog.known_entity_names()


def test_extension_completion_only_offers_entities_with_extensions():
    values = _complete("fire://extensions/{entity}", "entity", "").values
    assert values
    assert set(values) < set(catalog.known_entity_names())


def test_field_completion_is_capped_and_says_there_are_more():
    completion = _complete("fire://properties/{field}", "field", "")
    assert len(completion.values) == resources._MAX_COMPLETIONS
    assert completion.has_more is True
    assert completion.total > resources._MAX_COMPLETIONS


@pytest.mark.parametrize(
    "uri, name",
    [("fire://schemas/{entity}", "field"), ("fire://nope/{x}", "x")],
)
def test_unknown_template_or_parameter_gets_no_suggestions(uri, name):
    assert _complete(uri, name, "").values == []


def test_completion_round_trips_through_a_client():
    from mcp import Client

    async def run():
        async with Client(server.create_server()) as client:
            return await client.complete(
                ResourceTemplateReference(
                    type="ref/resource", uri="fire://examples/{name}"
                ),
                {"name": "name", "value": "bond"},
            )

    result = anyio.run(run)
    assert result.completion.values
    assert all(v.startswith("bond") for v in result.completion.values)
