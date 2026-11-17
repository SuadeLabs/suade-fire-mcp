"""Registers the FIRE mapping-assistant tools against an MCPServer instance."""

# No `from __future__ import annotations`: register() builds parameter types from
# the FIRE checkout at runtime, and the SDK reads them from the live signature.

import functools
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any, TypeVar

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from . import batch, catalog, examples, loader, search, validation
from .validation import known_jurisdictions

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

# --- Result types ------------------------------------------------------------
#
# Every tool returns an object (never a bare list) of a declared type, so its
# output schema says exactly what comes back. A bare list would be wrapped by
# the SDK in {"result": [...]}, and a dict[str, Any] return publishes no schema.


@dataclass
class EntityList:
    entities: list[catalog.Entity]


@dataclass
class FieldSummary:
    """One field as list_fields returns it. Enum values and the doc excerpt are
    left out -- get_field has them; including them puts loan over the limit."""

    name: str
    type: str | None
    format: str | None
    monetary: bool
    required: bool
    jurisdictions: list[str] | None
    description: str | None
    is_enum: bool


@dataclass
class FieldList:
    entity: str
    fields: list[FieldSummary]


@dataclass
class SearchResults:
    results: list[search.SearchResult]


@dataclass
class ExampleMatches:
    matches: list[examples.ExampleMatch]


@dataclass
class RecordValidation:
    valid: bool
    # Empty when valid.
    issues: list[validation.ValidationIssue]


@dataclass
class RecordIssues:
    index: int
    entity: str
    issues: list[validation.ValidationIssue]


@dataclass
class BatchValidation:
    valid: bool
    record_count: int
    # Every issue found, including any not returned because of the cap.
    issue_count: int
    truncated: bool
    # Only the records that have issues.
    records: list[RecordIssues]
    referential_issues: list[batch.ReferentialIssue]


@dataclass
class MappingSuggestion:
    source_field: str
    entity_field: str
    score: float
    reason: str
    example_boost: float
    example_evidence: examples.ExampleEvidence


@dataclass
class MappingSuggestions:
    candidates: list[MappingSuggestion]
    basis: str


def _field_summary(field: catalog.Field) -> FieldSummary:
    return FieldSummary(
        name=field.name,
        type=field.type,
        format=field.format,
        monetary=field.monetary,
        required=field.required,
        jurisdictions=field.jurisdictions,
        description=field.description,
        is_enum=field.enum is not None,
    )


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


def _choice(description: str, values: list[str] | tuple[str, ...]) -> Any:
    """A string parameter whose schema lists its valid values.

    The enum is advertised in the schema only; the tool itself still checks the
    value, so a wrong one gets this package's message (which names the tool to
    call for valid values) instead of a bare schema-validation error.
    """
    return Annotated[
        str, Field(description=description, json_schema_extra={"enum": list(values)})
    ]


def register(mcp: MCPServer) -> None:
    entity_names = catalog.known_entity_names()
    Entity = _choice("FIRE entity name, e.g. loan or customer.", entity_names)
    Jurisdiction = Annotated[
        _choice("Jurisdiction code.", known_jurisdictions()) | None,
        Field(
            description=(
                "Also validate this jurisdiction's extension fields (e.g. US). "
                "Omit to validate against the base schema only."
            )
        ),
    ]
    Strict = Annotated[
        bool,
        Field(
            description=(
                "Also flag record keys that aren't FIRE fields for the entity, as "
                'kind="unknown_field". FIRE\'s schemas allow extra keys, so this '
                "is the only way to catch misspelt field names."
            )
        ),
    ]
    FieldName = Annotated[
        str, Field(description="FIRE field name, e.g. balance or repayment_type.")
    ]

    @_tool(mcp, "List FIRE entities")
    def list_entities() -> EntityList:
        """List all FIRE entities (top-level schemas) with a short description."""
        return EntityList(entities=catalog.list_entities())

    @_tool(mcp, "List entity fields")
    def list_fields(entity: Entity) -> FieldList:
        """List every field on a FIRE entity (including jurisdiction extensions and
        fields inherited via allOf) as a summary: name, type, format, monetary,
        required, jurisdictions, description and is_enum.

        Enum values and documentation excerpts are not included; get_field returns
        them for one field.
        """
        return FieldList(
            entity=entity,
            fields=[_field_summary(field) for field in catalog.list_fields(entity)],
        )

    @_tool(mcp, "Search FIRE fields")
    def search_fields(
        query: Annotated[
            str,
            Field(
                description=(
                    "Words to look for in field names, descriptions and enum "
                    'values, e.g. "interest rate" or "buy_to_let".'
                )
            ),
        ],
        limit: Annotated[
            int,
            Field(description=f"Maximum results to return (1-{MAX_SEARCH_LIMIT})."),
        ] = 10,
    ) -> SearchResults:
        """Search FIRE field names, descriptions and enum values across all
        entities.

        One result per field: `entities` lists every entity the field appears on
        with that type and enum. A field whose enum differs by entity (e.g.
        repayment_type on loan vs security) appears once per variant.
        """
        _ensure_not_blank("query", query)
        if not 1 <= limit <= MAX_SEARCH_LIMIT:
            raise ValueError(
                f"limit must be between 1 and {MAX_SEARCH_LIMIT}, got {limit}."
            )
        return SearchResults(results=search.search_fields(query, limit=limit))

    @_tool(mcp, "Get field detail")
    def get_field(entity: Entity, field: FieldName) -> catalog.Field:
        """Get full detail (type, format, enum, monetary flag, description, doc,
        required flag) for one FIRE field.

        If the field doesn't exist on this entity, the error names any other
        entities it does exist on.
        """
        return catalog.get_field(entity, field)

    @_tool(mcp, "Get enum definitions")
    def get_enum_definitions(
        entity: Entity, field: FieldName
    ) -> catalog.EnumDefinitions:
        """Get the per-value prose definitions for an enum field on a FIRE entity,
        parsed from documentation/properties/<field>.md.

        Raises if the field doesn't exist, isn't an enum, or has no parseable
        per-value documentation.
        """
        return catalog.get_enum_definitions(entity, field)

    @_tool(mcp, "Get worked examples")
    def get_examples(
        name: Annotated[
            str | None,
            Field(
                description=(
                    "Example name, as listed by calling this tool without it or by "
                    "find_examples. Omit to list every example."
                )
            ),
        ] = None,
    ) -> dict[str, Any]:
        """List all worked FIRE example payloads as {"examples": [{name, title,
        comment}]}, or return one example's full content by name."""
        if name is None:
            return {
                "examples": [
                    {"name": e.name, "title": e.title, "comment": e.comment}
                    for e in catalog.list_examples()
                ]
            }
        try:
            return loader.load_example(name)
        except FileNotFoundError as exc:
            raise ValueError(
                f"No example named {name!r}. Call get_examples() with no arguments "
                "to list available names."
            ) from exc

    @_tool(mcp, "Validate record")
    def validate_record(
        entity: Entity,
        record: Annotated[
            dict[str, Any],
            Field(description="The record to check, as a JSON object."),
        ],
        jurisdiction: Jurisdiction = None,
        strict: Strict = False,
    ) -> RecordValidation:
        """Validate a JSON record against a FIRE entity schema.

        Returns {"valid": bool, "issues": [...]}; issues is empty when valid. Each
        issue's kind is one of missing_required, type_mismatch, enum_mismatch,
        format_mismatch (a date-time field not in RFC 3339 form, e.g. missing the
        trailing Z), unknown_field (strict only) or other.
        """
        issues = validation.validate_record(
            entity, record, jurisdiction=jurisdiction, strict=strict
        )
        return RecordValidation(valid=not issues, issues=issues)

    @_tool(mcp, "Validate batch")
    def validate_batch(
        records: Annotated[
            list[dict[str, Any]],
            Field(
                description=(
                    'Up to 1000 items, each {"entity": <entity name>, "record": '
                    "<record object>}. Keep records that refer to each other in "
                    "the same call: id references are only checked within it."
                )
            ),
        ],
        jurisdiction: Jurisdiction = None,
        strict: Strict = False,
    ) -> BatchValidation:
        """Validate a batch of records, each against its own entity schema, and
        check references between them.

        Runs validate_record on each item, plus checks that *_id fields (e.g.
        customer_id, loan_id, guarantor_id, issuer_id, security_id,
        derivative_id, and the *_ids array fields on collateral) refer to an id
        actually present among this batch's own records of the expected entity
        type. A referential issue here means "not found in this batch" -- it
        does not imply the reference is wrong if this is a partial extract.

        Cash-flow reconciliation and joint_customer_ids/joint_customer_structure
        length-matching are explicitly out of scope for this check.

        "records" lists only the records that have issues; a malformed item or
        unknown entity is reported against that item. At most 250 issues are
        returned per call -- "truncated" says whether more were found, and
        "issue_count" is the full total.
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
                RecordIssues(index=r.index, entity=r.entity, issues=shown)
            )
        referential_out = result.referential_issues[: max(budget, 0)]
        returned = sum(len(r.issues) for r in records_out) + len(referential_out)
        return BatchValidation(
            valid=issue_count == 0,
            record_count=len(records),
            issue_count=issue_count,
            truncated=returned < issue_count,
            records=records_out,
            referential_issues=referential_out,
        )

    @_tool(mcp, "Suggest field mapping")
    def suggest_mapping(
        entity: Annotated[
            Entity, Field(description="The FIRE entity to map the source fields onto.")
        ],
        source_fields: Annotated[
            list[str],
            Field(
                description=(
                    "1-100 of your own field or column names, in any naming style "
                    "(CustomerID, customer-id, cust_id)."
                )
            ),
        ],
        sample_values: Annotated[
            dict[str, Any] | None,
            Field(
                description=(
                    "Optional sample value per source field name. A value that is "
                    "a FIRE enum value helps pick the right enum field."
                )
            ),
        ] = None,
    ) -> MappingSuggestions:
        """Suggest FIRE field mappings for a list of internal/source field names.

        Ranked, non-authoritative candidates -- a starting point for a mapping
        table, not a substitute for review. Each candidate's `reason` says how it
        was matched, and `example_boost` how many of its score's points come from
        FIRE's worked examples using that field; the result's `basis` restates
        what the scores do and don't mean.
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
        return MappingSuggestions(
            candidates=[
                MappingSuggestion(
                    source_field=c.source_field,
                    entity_field=c.entity_field,
                    score=c.score,
                    reason=c.reason,
                    example_boost=c.example_boost,
                    example_evidence=examples.evidence_for(entity, c.entity_field),
                )
                for c in candidates
            ],
            basis=MAPPING_BASIS,
        )

    @_tool(mcp, "Find worked examples")
    def find_examples(
        query: Annotated[
            str,
            Field(
                description=(
                    'A product or trade type, e.g. "buy to let mortgage", '
                    '"bridging loan" or "fx swap".'
                )
            ),
        ],
        entity: Annotated[
            _choice("Only return examples containing this entity.", entity_names)
            | None,
            Field(description="Only return examples containing this entity."),
        ] = None,
        limit: Annotated[
            int,
            Field(
                description=f"Maximum matches to return (1-{MAX_FIND_EXAMPLES_LIMIT})."
            ),
        ] = 5,
    ) -> ExampleMatches:
        """Find FIRE's worked example records for a product or trade type.

        Each match includes the example's description, the entities it contains,
        and the classification (enum) values its records use -- such as loan type,
        purpose and repayment_type. Fetch the full records with get_examples(name).
        """
        _ensure_not_blank("query", query)
        if not 1 <= limit <= MAX_FIND_EXAMPLES_LIMIT:
            raise ValueError(
                f"limit must be between 1 and {MAX_FIND_EXAMPLES_LIMIT}, got {limit}."
            )
        return ExampleMatches(
            matches=examples.find_examples(query, entity=entity, limit=limit)
        )
