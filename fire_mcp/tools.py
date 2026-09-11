"""Registers the FIRE mapping-assistant tools against an MCPServer instance."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from mcp.server import MCPServer

from . import batch, catalog, loader, search, validation


def register(mcp: MCPServer) -> None:
    @mcp.tool()
    def list_entities() -> list[dict[str, Any]]:
        """List all FIRE entities (top-level schemas) with a short description."""
        return [asdict(entity) for entity in catalog.list_entities()]

    @mcp.tool()
    def list_fields(entity: str) -> list[dict[str, Any]]:
        """List every field on a FIRE entity (including jurisdiction extensions and
        fields inherited via allOf), each flagged with whether it is required."""
        return [asdict(field) for field in catalog.list_fields(entity)]

    @mcp.tool()
    def search_fields(query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search FIRE field names, descriptions and enum values for a query string."""
        return [asdict(result) for result in search.search_fields(query, limit=limit)]

    @mcp.tool()
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

    @mcp.tool()
    def get_enum_definitions(entity: str, field: str) -> dict[str, Any]:
        """Get the per-value prose definitions for an enum field on a FIRE entity,
        parsed from documentation/properties/<field>.md.

        Raises if the field doesn't exist, isn't an enum, or has no parseable
        per-value documentation.
        """
        return asdict(catalog.get_enum_definitions(entity, field))

    @mcp.tool()
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

    @mcp.tool()
    def validate_record(
        entity: str,
        record: dict[str, Any],
        jurisdiction: str | None = None,
        strict: bool = False,
    ) -> list[dict[str, Any]]:
        """Validate a JSON record against a FIRE entity schema.

        With strict=True, also flags any record key that isn't a recognised FIRE
        field for this entity (base schema, allOf-inherited fields, or any
        jurisdiction extension) as kind="unknown_field" -- FIRE's own schemas set
        additionalProperties: true, so this check is not otherwise enforced.

        Returns a list of validation issues (empty if the record is valid).
        """
        issues = validation.validate_record(
            entity, record, jurisdiction=jurisdiction, strict=strict
        )
        return [asdict(issue) for issue in issues]

    @mcp.tool()
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
        """
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

    @mcp.tool()
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
