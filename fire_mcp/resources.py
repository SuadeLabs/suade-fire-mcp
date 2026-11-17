"""Registers the fire:// resource URIs against an MCPServer instance."""

from __future__ import annotations

import functools
import json
from collections.abc import Callable
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ResourceError
from mcp.types import (
    Completion,
    CompletionArgument,
    CompletionContext,
    PromptReference,
    ResourceTemplateReference,
)

from . import catalog, docs, loader, refs


def _resource(mcp: MCPServer, uri: str) -> Callable[[Callable[..., str]], Any]:
    """Register a resource whose ValueErrors reach the client as their message.

    Same reasoning as tools._tool: the SDK hides any exception other than
    ResourceError behind a generic message naming only the URI.
    """

    def decorator(fn: Callable[..., str]) -> Callable[..., str]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> str:
            try:
                return fn(*args, **kwargs)
            except ValueError as exc:
                raise ResourceError(str(exc)) from exc

        mcp.resource(uri)(wrapper)
        return fn

    return decorator


# The SDK caps a completion response at 100 values; more than that and the
# client is told there are more, so the user keeps typing to narrow it down.
_MAX_COMPLETIONS = 100

# Which names each resource template's parameter takes, keyed by
# (template URI, parameter name).
_COMPLETION_SOURCES: dict[tuple[str, str], Callable[[], list[str]]] = {
    ("fire://schemas/{entity}", "entity"): catalog.known_entity_names,
    ("fire://extensions/{entity}", "entity"): lambda: [
        name for name in loader.list_extension_names() if catalog.is_known_entity(name)
    ],
    ("fire://properties/{field}", "field"): loader.list_doc_names,
    ("fire://examples/{name}", "name"): loader.list_example_names,
}


def complete(
    ref: ResourceTemplateReference, argument: CompletionArgument
) -> Completion:
    """Names starting with what the user has typed so far, for one template
    parameter. Unknown templates or parameters get no suggestions."""
    source = _COMPLETION_SOURCES.get((ref.uri, argument.name))
    if source is None:
        return Completion(values=[])
    prefix = argument.value.lower()
    matches = [name for name in source() if name.lower().startswith(prefix)]
    return Completion(
        values=matches[:_MAX_COMPLETIONS],
        total=len(matches),
        has_more=len(matches) > _MAX_COMPLETIONS,
    )


def register(mcp: MCPServer) -> None:
    @mcp.completion()
    async def handle_completion(
        ref: PromptReference | ResourceTemplateReference,
        argument: CompletionArgument,
        context: CompletionContext | None,
    ) -> Completion | None:
        if isinstance(ref, ResourceTemplateReference):
            return complete(ref, argument)
        return None

    @_resource(mcp, "fire://schemas/{entity}")
    def schema_resource(entity: str) -> str:
        """The FIRE schema for one entity, with all $refs resolved inline."""
        catalog.ensure_known_entity(entity)
        return json.dumps(
            refs.resolve_entity_schema(entity, with_extension=False), indent=2
        )

    @_resource(mcp, "fire://extensions/{entity}")
    def extension_resource(entity: str) -> str:
        """The jurisdiction-specific extension fields for one entity, if any."""
        catalog.ensure_known_entity(entity)
        resolved = refs.resolve_extension_only(entity)
        if resolved is None:
            raise ValueError(f"No extension schema exists for entity {entity!r}.")
        return json.dumps(resolved, indent=2)

    @_resource(mcp, "fire://properties/{field}")
    def property_resource(field: str) -> str:
        """The markdown documentation for one FIRE field."""
        doc = docs.load_field_doc(field)
        if doc is None:
            raise ValueError(f"No documentation found for field {field!r}.")
        return doc.full

    @_resource(mcp, "fire://examples/{name}")
    def example_resource(name: str) -> str:
        """A worked example FIRE payload, as stored in examples/."""
        try:
            example = loader.load_example(name)
        except FileNotFoundError as exc:
            raise ValueError(f"No example named {name!r}.") from exc
        return json.dumps(example, indent=2)
