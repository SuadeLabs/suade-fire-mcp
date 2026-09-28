"""Registers the FIRE mapping-assistant tools against an MCPServer instance."""

from __future__ import annotations

import functools
from collections.abc import Callable
from dataclasses import asdict
from typing import Any, TypeVar

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from . import batch, catalog, loader, search, validation

# Every tool only reads the local FIRE checkout -- nothing is written, and the same
# arguments always give the same result. Claude uses these hints to decide whether a
# call needs per-call confirmation.
_READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

# Keep tool results well inside Claude's result size limits (~150k characters on
# claude.ai, 25k tokens by default in Claude Code).
MAX_SEARCH_LIMIT = 50
MAX_BATCH_RECORDS = 1000

_F = TypeVar("_F", bound=Callable[..., Any])

# Per-field keys returned by list_fields. The full field (enum values, doc excerpt)
# is what get_field is for -- including it here puts the loan entity over the limit.
_FIELD_SUMMARY_KEYS = (
    "name",
    "type",
    "format",
    "monetary",
    "required",
    "jurisdictions",
    "description",
)


def _field_summary(field: catalog.Field) -> dict[str, Any]:
    summary = {key: getattr(field, key) for key in _FIELD_SUMMARY_KEYS}
    summary["is_enum"] = field.enum is not None
    return summary


def _tool(mcp: MCPServer, title: str) -> Callable[[_F], _F]:
    """Register a read-only tool whose ValueErrors reach the model as their message.

    Every anticipated failure in this package (unknown entity/field, non-enum field,
    bad example name, out-of-range argument) is a ValueError. The SDK treats any
    exception other than ToolError as a crash and hides its message behind a generic
    "Error executing tool <name>", which gives the caller nothing to act on.
    """

    def decorator(fn: _F) -> _F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return fn(*args, **kwargs)
            except ValueError as exc:
                raise ToolError(str(exc)) from exc

        mcp.tool(title=title, annotations=_READ_ONLY)(wrapper)
        return fn

    return decorator


def register(mcp: MCPServer) -> None:
    @_tool(mcp, "List FIRE entities")
    def list_entities() -> list[dict[str, Any]]:
        """List all FIRE entities (top-level schemas) with a short description."""
        return [asdict(entity) for entity in catalog.list_entities()]

    @_tool(mcp, "List entity fields")
    def list_fields(entity: str) -> list[dict[str, Any]]:
        """List every field on a FIRE entity (including jurisdiction extensions and
        fields inherited via allOf) as a summary: name, type, format, monetary,
        required, jurisdictions, description and is_enum.

        Enum values and documentation excerpts are not included; get_field returns
        them for one field.
        """
        return [_field_summary(field) for field in catalog.list_fields(entity)]

    @_tool(mcp, "Search FIRE fields")
    def search_fields(query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search FIRE field names, descriptions and enum values for a query string.

        Returns at most 50 results.
        """
        if not 1 <= limit <= MAX_SEARCH_LIMIT:
            raise ValueError(
                f"limit must be between 1 and {MAX_SEARCH_LIMIT}, got {limit}."
            )
        return [asdict(result) for result in search.search_fields(query, limit=limit)]

    @_tool(mcp, "Get field detail")
    def get_field(entity: str, field: str) -> dict[str, Any]:
        """Get full detail (type, format, enum, monetary flag, description, doc,
        required flag) for one FIRE field.

        If the field doesn't exist on this entity, returns a structured
        {"error": "unknown_field", ...} payload naming any other entities it
        does exist on, instead of raising.
        """
        try:
            return asdict(catalog.get_field(entity, field))
        except catalog.UnknownFieldError as exc:
            return {
                "error": "unknown_field",
                "entity": exc.entity,
                "field": exc.field_name,
                "exists_on": exc.exists_on,
                "message": str(exc),
            }

    @_tool(mcp, "Get enum definitions")
    def get_enum_definitions(entity: str, field: str) -> dict[str, Any]:
        """Get the per-value prose definitions for an enum field on a FIRE entity,
        parsed from documentation/properties/<field>.md.

        Raises if the field doesn't exist, isn't an enum, or has no parseable
        per-value documentation.
        """
        return asdict(catalog.get_enum_definitions(entity, field))

    @_tool(mcp, "Get worked examples")
    def get_examples(name: str | None = None) -> Any:
        """List all worked FIRE example payloads (name/title/comment), or return
        one example's full content by name."""
        if name is None:
            return [asdict(summary) for summary in catalog.list_examples()]
        try:
            return loader.load_example(name)
        except FileNotFoundError as exc:
            raise ValueError(
                f"No example named {name!r}. Call get_examples() with no arguments "
                "to list available names."
            ) from exc

    @_tool(mcp, "Validate record")
    def validate_record(
        entity: str,
        record: dict[str, Any],
        jurisdiction: str | None = None,
        strict: bool = False,
    ) -> dict[str, Any]:
        """Validate a JSON record against a FIRE entity schema.

        With strict=True, also flags any record key that isn't a recognised FIRE
        field for this entity (base schema, allOf-inherited fields, or any
        jurisdiction extension) as kind="unknown_field" -- FIRE's own schemas set
        additionalProperties: true, so this check is not otherwise enforced.

        Returns {"valid": bool, "issues": [...]}; issues is empty when valid.
        """
        # Wrapped in an object rather than returning the bare issue list: an empty
        # list serialises to no content blocks at all, so a valid record would
        # come back to the model as an empty result.
        issues = validation.validate_record(
            entity, record, jurisdiction=jurisdiction, strict=strict
        )
        return {"valid": not issues, "issues": [asdict(issue) for issue in issues]}

    @_tool(mcp, "Validate batch")
    def validate_batch(
        records: list[dict[str, Any]],
        jurisdiction: str | None = None,
        strict: bool = False,
    ) -> dict[str, Any]:
        """Validate a batch of {"entity": str, "record": dict} pairs.

        Runs validate_record on each item, plus checks that *_id fields (e.g.
        customer_id, loan_id, guarantor_id, issuer_id, security_id,
        derivative_id, and the *_ids array fields on collateral) refer to an id
        actually present among this batch's own records of the expected entity
        type. A referential issue here means "not found in this batch" -- it
        does not imply the reference is wrong if this is a partial extract.

        Cash-flow reconciliation and joint_customer_ids/joint_customer_structure
        length-matching are explicitly out of scope for this check.

        Accepts at most 1000 records per call.
        """
        if len(records) > MAX_BATCH_RECORDS:
            raise ValueError(
                f"validate_batch accepts at most {MAX_BATCH_RECORDS} records per call, "
                f"got {len(records)}. Split the batch; referential checks only see "
                "ids within the same call, so keep related records together."
            )
        result = batch.validate_batch(records, jurisdiction=jurisdiction, strict=strict)
        return {
            "records": [
                {
                    "index": r.index,
                    "entity": r.entity,
                    "issues": [asdict(issue) for issue in r.issues],
                }
                for r in result.records
            ],
            "referential_issues": [
                asdict(issue) for issue in result.referential_issues
            ],
        }

    @_tool(mcp, "Suggest field mapping")
    def suggest_mapping(
        entity: str,
        source_fields: list[str],
        sample_values: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Suggest FIRE field mappings for a list of internal/source field names.

        Ranked, non-authoritative candidates -- a starting point for a mapping
        table, not a substitute for review.
        """
        candidates = search.suggest_mapping(
            entity, source_fields, sample_values=sample_values
        )
        return [asdict(candidate) for candidate in candidates]
