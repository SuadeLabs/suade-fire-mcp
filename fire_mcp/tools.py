"""Registers the FIRE mapping-assistant tools against an MCPServer instance."""

from __future__ import annotations

import functools
from collections.abc import Callable
from dataclasses import asdict
from typing import Any, TypeVar

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from . import batch, catalog, examples, loader, search, validation

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
MAX_FIND_EXAMPLES_LIMIT = 20
MAX_BATCH_RECORDS = 1000
MAX_BATCH_ISSUES = 250
MAX_MAPPING_SOURCE_FIELDS = 100

_F = TypeVar("_F", bound=Callable[..., Any])

# Returned with every suggest_mapping result, so the caveat travels with the
# suggestions rather than living only in the README. It describes the result; it
# is deliberately not phrased as an instruction to the model.
MAPPING_BASIS = (
    "Automated suggestions from text similarity between the source field names "
    "and FIRE field names, plus enum membership of any sample values. They are "
    "not reviewed or endorsed by Suade and can be wrong: a high score means the "
    "names look alike, not that the meaning matches. Scores also include a small "
    "boost (up to 8 points, shown as `example_boost`) for fields that FIRE's "
    "reviewed worked examples populate, and `example_evidence` counts those "
    "examples -- that shows a field is used in practice, not that it is the "
    "right target for this source field. Check each mapping against the field's "
    "definition (get_field) before relying on it."
)

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


def _ensure_not_blank(name: str, value: str) -> None:
    # A blank query matches nothing, so fuzzy scoring returns arbitrary fields
    # at score 0 -- a result that looks like an answer but isn't one.
    if not value.strip():
        raise ValueError(f"{name} must not be blank.")


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

        One result per field: `entities` lists every entity the field appears on
        with that type and enum. A field whose enum differs by entity (e.g.
        repayment_type on loan vs security) appears once per variant. Returns
        at most 50 results.
        """
        _ensure_not_blank("query", query)
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

        jurisdiction (e.g. "US") also validates that jurisdiction's extension
        fields; an unknown jurisdiction is an error.

        Returns {"valid": bool, "issues": [...]}; issues is empty when valid. Each
        issue's kind is one of missing_required, type_mismatch, enum_mismatch,
        format_mismatch (a date-time field not in RFC 3339 form, e.g. missing the
        trailing Z), unknown_field (strict only) or other.
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

        Returns {"valid", "record_count", "issue_count", "truncated", "records",
        "referential_issues"}. "records" lists only the records that have
        issues; a malformed item or unknown entity is reported against that
        item. At most 250 issues are returned per call -- "truncated" says
        whether more were found, and "issue_count" is the full total.

        Accepts at most 1000 records per call.
        """
        if len(records) > MAX_BATCH_RECORDS:
            raise ValueError(
                f"validate_batch accepts at most {MAX_BATCH_RECORDS} records per call, "
                f"got {len(records)}. Split the batch; referential checks only see "
                "ids within the same call, so keep related records together."
            )
        result = batch.validate_batch(records, jurisdiction=jurisdiction, strict=strict)
        issue_count = sum(len(r.issues) for r in result.records) + len(
            result.referential_issues
        )
        budget = MAX_BATCH_ISSUES
        records_out = []
        for r in result.records:
            if not r.issues or budget <= 0:
                continue
            shown = r.issues[:budget]
            budget -= len(shown)
            records_out.append(
                {
                    "index": r.index,
                    "entity": r.entity,
                    "issues": [asdict(issue) for issue in shown],
                }
            )
        referential_out = [
            asdict(issue) for issue in result.referential_issues[: max(budget, 0)]
        ]
        returned = sum(len(r["issues"]) for r in records_out) + len(referential_out)
        return {
            "valid": issue_count == 0,
            "record_count": len(records),
            "issue_count": issue_count,
            "truncated": returned < issue_count,
            "records": records_out,
            "referential_issues": referential_out,
        }

    @_tool(mcp, "Suggest field mapping")
    def suggest_mapping(
        entity: str,
        source_fields: list[str],
        sample_values: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Suggest FIRE field mappings for a list of internal/source field names.

        Ranked, non-authoritative candidates -- a starting point for a mapping
        table, not a substitute for review. Each candidate's `reason` says how it
        was matched, and `example_boost` how many of its score's points come from
        FIRE's worked examples using that field; the result's `basis` restates
        what the scores do and don't mean.

        Accepts between 1 and 100 source fields per call.
        """
        if not source_fields:
            raise ValueError("source_fields must not be empty.")
        if len(source_fields) > MAX_MAPPING_SOURCE_FIELDS:
            raise ValueError(
                f"suggest_mapping accepts at most {MAX_MAPPING_SOURCE_FIELDS} source "
                f"fields per call, got {len(source_fields)}. Split them across calls."
            )
        blank = [i for i, name in enumerate(source_fields) if not name.strip()]
        if blank:
            raise ValueError(
                f"source_fields must not contain blank names (at positions {blank})."
            )
        candidates = search.suggest_mapping(
            entity, source_fields, sample_values=sample_values
        )
        return {
            "candidates": [
                {
                    **asdict(candidate),
                    "example_evidence": examples.evidence_for(
                        entity, candidate.entity_field
                    ),
                }
                for candidate in candidates
            ],
            "basis": MAPPING_BASIS,
        }

    @_tool(mcp, "Find worked examples")
    def find_examples(
        query: str, entity: str | None = None, limit: int = 5
    ) -> list[dict[str, Any]]:
        """Find FIRE's worked example records for a product or trade type, e.g.
        "buy to let mortgage", "bridging loan" or "fx swap".

        Each match includes the example's description, the entities it contains,
        and the classification (enum) values its records use -- such as loan type,
        purpose and repayment_type. Fetch the full records with get_examples(name).
        Optionally restrict to examples containing one entity. Returns at most
        20 matches.
        """
        _ensure_not_blank("query", query)
        if not 1 <= limit <= MAX_FIND_EXAMPLES_LIMIT:
            raise ValueError(
                f"limit must be between 1 and {MAX_FIND_EXAMPLES_LIMIT}, got {limit}."
            )
        return [
            asdict(match)
            for match in examples.find_examples(query, entity=entity, limit=limit)
        ]
