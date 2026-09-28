"""Entity/field catalog built on top of the eagerly-resolved schemas."""

from __future__ import annotations

from dataclasses import dataclass

from . import docs, loader, refs

# example.json is a meta-schema describing the structure of worked FIRE
# example payloads, not a real business entity -- exclude it from the public
# entity surface (list_entities, search index, etc).
_EXCLUDED_ENTITIES = {"example"}


class UnknownEntityError(ValueError):
    def __init__(self, entity: str):
        super().__init__(
            f"Unknown FIRE entity: {entity!r}. Use list_entities to see valid names."
        )
        self.entity = entity


class UnknownFieldError(ValueError):
    def __init__(
        self, entity: str, field_name: str, exists_on: list[str] | None = None
    ):
        detail = f" It does exist on: {', '.join(exists_on)}." if exists_on else ""
        super().__init__(f"Unknown field {field_name!r} on entity {entity!r}.{detail}")
        self.entity = entity
        self.field_name = field_name
        self.exists_on = exists_on or []


class FieldNotEnumError(ValueError):
    def __init__(self, entity: str, field_name: str):
        super().__init__(f"Field {field_name!r} on entity {entity!r} is not an enum.")
        self.entity = entity
        self.field_name = field_name


@dataclass
class Entity:
    name: str
    title: str | None
    description: str | None
    has_extension: bool


@dataclass
class Field:
    name: str
    entity: str
    type: str | None = None
    format: str | None = None
    enum: list[str] | None = None
    monetary: bool = False
    description: str | None = None
    doc_excerpt: str | None = None
    jurisdictions: list[str] | None = None
    required: bool = False


@dataclass
class EnumDefinitions:
    entity: str
    field: str
    definitions: dict[str, str]
    undocumented_values: list[str]


@dataclass
class ExampleSummary:
    name: str
    title: str | None
    comment: str | None


_KNOWN_ENTITIES = set(loader.list_schema_names()) - _EXCLUDED_ENTITIES


def known_entity_names() -> list[str]:
    return sorted(_KNOWN_ENTITIES)


def is_known_entity(entity: str) -> bool:
    return entity in _KNOWN_ENTITIES


def ensure_known_entity(entity: str) -> None:
    if not is_known_entity(entity):
        raise UnknownEntityError(entity)


def list_entities() -> list[Entity]:
    extension_names = set(loader.list_extension_names())
    entities = []
    for name in known_entity_names():
        schema = loader.load_schema(name)
        entities.append(
            Entity(
                name=name,
                title=schema.get("title"),
                description=schema.get("description"),
                has_extension=name in extension_names,
            )
        )
    return entities


def _field_from_spec(
    name: str, entity: str, spec: dict, is_extension: bool, required: bool = False
) -> Field:
    doc = docs.load_field_doc(name, extension=is_extension)
    return Field(
        name=name,
        entity=entity,
        type=spec.get("type"),
        format=spec.get("format"),
        enum=spec.get("enum"),
        monetary=bool(spec.get("monetary", False)),
        description=spec.get("description"),
        doc_excerpt=doc.excerpt if doc else None,
        jurisdictions=spec.get("jurisdictions"),
        required=required,
    )


def list_fields(entity: str, with_extension: bool = True) -> list[Field]:
    ensure_known_entity(entity)
    resolved = refs.resolve_entity_schema(entity, with_extension=with_extension)
    required_names = set(resolved.get("required", []))
    extension = loader.load_extension_schema(entity) if with_extension else None
    extension_field_names = set(extension.get("properties", {})) if extension else set()
    return [
        _field_from_spec(
            name, entity, spec, name in extension_field_names, name in required_names
        )
        for name, spec in resolved.get("properties", {}).items()
    ]


def _find_field_on_other_entities(entity: str, field_name: str) -> list[str]:
    found = []
    for other in known_entity_names():
        if other == entity:
            continue
        resolved = refs.resolve_entity_schema(other, with_extension=True)
        if field_name in resolved.get("properties", {}):
            found.append(other)
    return found


def get_field(entity: str, field_name: str) -> Field:
    ensure_known_entity(entity)
    resolved = refs.resolve_entity_schema(entity, with_extension=True)
    properties = resolved.get("properties", {})
    if field_name not in properties:
        raise UnknownFieldError(
            entity,
            field_name,
            exists_on=_find_field_on_other_entities(entity, field_name),
        )
    extension = loader.load_extension_schema(entity)
    is_extension = bool(extension and field_name in extension.get("properties", {}))
    required = field_name in set(resolved.get("required", []))
    return _field_from_spec(
        field_name, entity, properties[field_name], is_extension, required
    )


def get_enum_definitions(entity: str, field_name: str) -> EnumDefinitions:
    field_obj = get_field(entity, field_name)
    if not field_obj.enum:
        raise FieldNotEnumError(entity, field_name)
    raw_defs = docs.get_enum_definitions(field_name, entity)
    definitions = {
        value: raw_defs[value] for value in field_obj.enum if value in raw_defs
    }
    undocumented = [value for value in field_obj.enum if value not in raw_defs]
    return EnumDefinitions(
        entity=entity,
        field=field_name,
        definitions=definitions,
        undocumented_values=undocumented,
    )


def list_examples() -> list[ExampleSummary]:
    summaries = []
    for name in loader.list_example_names():
        data = loader.load_example(name)
        summaries.append(
            ExampleSummary(
                name=name, title=data.get("title"), comment=data.get("comment")
            )
        )
    return summaries
