"""Lookup and light parsing of documentation/properties/*.md files."""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import loader

_FRONT_MATTER_RE = re.compile(r"^---\n.*?\n---\n", re.DOTALL)
_SCHEMAS_LINE_RE = re.compile(r"^schemas:\s*\[(?P<names>.*?)\]", re.MULTILINE)
_HEADING_RE = re.compile(r"^(#{1,3})\s+(.*)$", re.MULTILINE)


@dataclass
class Doc:
    field: str
    excerpt: str
    full: str
    raw: str


class EnumDocsNotFoundError(ValueError):
    def __init__(self, field: str, entity: str):
        super().__init__(
            f"No enum value definitions found for field {field!r} on entity {entity!r}."
        )
        self.field = field
        self.entity = entity


def _strip_front_matter(text: str) -> str:
    return _FRONT_MATTER_RE.sub("", text, count=1).strip()


def _first_paragraph(text: str) -> str:
    for paragraph in text.split("\n\n"):
        paragraph = paragraph.strip()
        if not paragraph or paragraph.startswith("#") or set(paragraph) <= {"-"}:
            continue
        return paragraph
    return ""


def load_field_doc(field: str, extension: bool = False) -> Doc | None:
    raw = loader.load_extension_doc(field) if extension else loader.load_doc(field)
    if raw is None and extension:
        raw = loader.load_doc(field)
    if raw is None:
        return None
    body = _strip_front_matter(raw)
    return Doc(field=field, excerpt=_first_paragraph(body), full=body, raw=raw)


# --- Enum value definitions -------------------------------------------------
#
# documentation/properties/<field>.md files use three structural patterns for
# per-enum-value prose definitions (all confirmed against the real FIRE docs):
#
#  * flat: no per-entity heading split at all -- a single set of `###`
#    subsections applies to every schema listed in the front matter's
#    `schemas: [...]` line (e.g. accounting_treatment.md).
#  * H2-split: one `## <Entity>` heading per entity (casing is inconsistent
#    in the source docs), each with its own `###` subsections underneath
#    (e.g. repayment_type.md, status.md).
#  * H1-split: one `# <Entity[, Entity...]>` heading per entity or comma-
#    joined group of entities, `###` leaves underneath (type.md is the only
#    field using this pattern today). The very first `#` heading in the file
#    is just the field's title and is skipped.


def _front_matter_schemas(raw: str) -> list[str]:
    match = _SCHEMAS_LINE_RE.search(raw)
    if not match:
        return []
    return [name.strip() for name in match.group("names").split(",") if name.strip()]


def _headings(body: str) -> list[tuple[int, str, int, int]]:
    """[(level, text, heading_start, heading_end), ...] in document order."""
    out = []
    for m in _HEADING_RE.finditer(body):
        out.append((len(m.group(1)), m.group(2).strip(), m.start(), m.end()))
    return out


def _matches_entity(heading_text: str, entity: str) -> bool:
    tokens = {t.strip().lower() for t in heading_text.split(",")}
    return entity.lower() in tokens


def _section_span(
    headings: list[tuple[int, str, int, int]], idx: int, body_len: int
) -> tuple[int, int]:
    level = headings[idx][0]
    start = headings[idx][3]
    end = body_len
    for other_level, _, other_start, _ in headings[idx + 1 :]:
        if other_level <= level:
            end = other_start
            break
    return start, end


def _extract_h3_definitions(text: str) -> dict[str, str]:
    definitions: dict[str, str] = {}
    subheadings = [h for h in _headings(text) if h[0] == 3]
    for i, (_, name, _, end) in enumerate(subheadings):
        stop = subheadings[i + 1][2] if i + 1 < len(subheadings) else len(text)
        definitions[name.lower()] = text[end:stop].strip()
    return definitions


def get_enum_definitions(field: str, entity: str) -> dict[str, str]:
    """Parse documentation/properties/<field>.md for the ###-level per-value
    definitions that apply to `entity`, trying each structural tier above in
    order. Raises EnumDocsNotFoundError if none matched or no doc exists.
    """
    doc = load_field_doc(field)
    if doc is None:
        raise EnumDocsNotFoundError(field, entity)
    body = doc.full
    all_headings = _headings(body)

    # Tier 1: H2-level entity split.
    for i, h in enumerate(all_headings):
        if h[0] == 2 and _matches_entity(h[1], entity):
            start, end = _section_span(all_headings, i, len(body))
            defs = _extract_h3_definitions(body[start:end])
            if defs:
                return defs

    # Tier 2: H1-level entity split, skipping the first H1 (the field title).
    first_h1_seen = False
    for i, h in enumerate(all_headings):
        if h[0] != 1:
            continue
        if not first_h1_seen:
            first_h1_seen = True
            continue
        if _matches_entity(h[1], entity):
            start, end = _section_span(all_headings, i, len(body))
            defs = _extract_h3_definitions(body[start:end])
            if defs:
                return defs

    # Tier 3: flat -- no per-entity split; applies to every schema listed in
    # front matter. Because there's no split, this returns every ### section
    # in the document -- callers should intersect against the entity's own
    # real enum values (as catalog.get_enum_definitions does) rather than
    # trust this dict wholesale.
    if entity in _front_matter_schemas(doc.raw):
        defs = _extract_h3_definitions(body)
        if defs:
            return defs

    raise EnumDocsNotFoundError(field, entity)
