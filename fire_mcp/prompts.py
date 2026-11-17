"""User-started workflows (MCP prompts) for the two jobs this server is for:
mapping an internal format onto FIRE, and fixing records that fail validation.

A prompt only builds the opening user message; the assistant then works through
it with the tools. Each one spells out the order of tool calls that gives
checked answers, which a model would otherwise have to work out from the tool
descriptions alone.
"""

from __future__ import annotations

import functools
import json
from collections.abc import Callable
from typing import Annotated, TypeVar

from mcp.server import MCPServer
from mcp.shared.exceptions import MCPError
from mcp.types import INVALID_PARAMS
from pydantic import Field

from . import catalog

_ENTITY = Field(description="The FIRE entity to work with, e.g. loan or customer.")


def _split_fields(source_fields: str) -> list[str]:
    """Accept a pasted header row or list: comma-, tab- or newline-separated."""
    for sep in ("\t", "\n"):
        source_fields = source_fields.replace(sep, ",")
    return [name.strip() for name in source_fields.split(",") if name.strip()]


def map_source_schema_text(entity: str, source_fields: str) -> str:
    catalog.ensure_known_entity(entity)
    names = _split_fields(source_fields)
    if not names:
        raise ValueError("source_fields must name at least one field.")
    listed = "\n".join(f"- {name}" for name in names)
    return f"""Map these source fields onto the FIRE `{entity}` entity:

{listed}

Use the FIRE tools as follows:
1. If the fields describe a specific product (a mortgage, a bond, an FX swap...),
   call find_examples with entity="{entity}" to see how FIRE's reviewed examples
   represent it, including which enum values they use.
2. Call suggest_mapping for the source fields (at most 100 per call).
3. Treat each suggestion as a candidate only. Confirm it with get_field, and
   for enum fields pass include_enum_definitions=true so the value meanings
   can be compared. Reject candidates whose definition doesn't match.
4. Call list_fields for `{entity}` and note any required FIRE fields that no
   source field maps to.

Reply with:
- a table: source field | FIRE field | confidence (high/medium/low) | notes
  (any conversion needed, e.g. units, date format, enum value mapping)
- source fields with no good FIRE match
- required FIRE fields left unmapped

Flag every low-confidence row for human review. The mapping suggestions are
automated name matching, not a Suade recommendation."""


def explain_validation_failure_text(entity: str, record: str) -> str:
    catalog.ensure_known_entity(entity)
    try:
        parsed = json.loads(record)
    except json.JSONDecodeError as exc:
        raise ValueError(f"record is not valid JSON: {exc.msg}.") from exc
    if not isinstance(parsed, dict):
        raise ValueError("record must be a JSON object.")
    pretty = json.dumps(parsed, indent=2)
    return f"""Explain why this FIRE `{entity}` record fails validation, and fix it:

```json
{pretty}
```

Use the FIRE tools as follows:
1. Call validate_record with entity="{entity}" and strict=true, so misspelt
   field names are reported too. If the record targets a jurisdiction (for
   example US-only fields), also pass jurisdiction.
2. For each issue, call get_field on the field concerned to explain what FIRE
   expects. For enum_mismatch, pass include_enum_definitions=true and pick
   the value whose definition fits. For unknown_field, use search_fields to
   find the intended field.
3. Call validate_record again on the corrected record to confirm it passes.

Reply with each issue in plain language, the change that fixes it, and the
corrected record. Don't invent values for missing required fields; mark them
as needing data from the source system."""


_F = TypeVar("_F", bound=Callable[..., str])


def _invalid_arguments_reach_the_user(fn: _F) -> _F:
    """Report a bad argument (unknown entity, malformed JSON) as an
    invalid-params error with its message. The SDK turns any other exception
    from a prompt into a bare "Internal server error"."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ValueError as exc:
            raise MCPError(code=INVALID_PARAMS, message=str(exc)) from exc

    return wrapper  # type: ignore[return-value]


def register(mcp: MCPServer) -> None:
    @mcp.prompt(title="Map source fields to FIRE")
    @_invalid_arguments_reach_the_user
    def map_source_schema(
        entity: Annotated[str, _ENTITY],
        source_fields: Annotated[
            str,
            Field(
                description=(
                    "Your field or column names, separated by commas, tabs or "
                    "new lines (a pasted header row works)."
                )
            ),
        ],
    ) -> str:
        """Build a reviewed mapping table from your own field names to a FIRE
        entity, checking each suggestion against FIRE's field definitions."""
        return map_source_schema_text(entity, source_fields)

    @mcp.prompt(title="Explain a validation failure")
    @_invalid_arguments_reach_the_user
    def explain_validation_failure(
        entity: Annotated[str, _ENTITY],
        record: Annotated[
            str, Field(description="The record that fails, as a JSON object.")
        ],
    ) -> str:
        """Explain each validation issue in a FIRE record, with the fix and a
        re-validated corrected record."""
        return explain_validation_failure_text(entity, record)
