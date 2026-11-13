"""Thin, cached file-IO over the FIRE repo's schemas/extensions/docs/examples.

Every function here takes a bare name (no file extension) and returns parsed
content, or None/raises FileNotFoundError depending on whether the caller can
sensibly expect the file to be missing (extensions and docs are optional;
base schemas and examples are not).

Names often come straight from a tool argument, so each one is checked before it
touches the filesystem: anything other than a plain file stem (a path separator,
"..", an absolute path) is treated as missing. Only files that actually exist are
cached, so a stream of made-up names can't grow the cache without bound.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from . import repo

# Every schema, doc and example file name in FIRE is a plain snake_case stem.
_NAME_RE = re.compile(r"[A-Za-z0-9_]+")


def _existing_file(directory: Path, name: str, suffix: str) -> Path | None:
    if not _NAME_RE.fullmatch(name):
        return None
    path = directory / f"{name}{suffix}"
    return path if path.is_file() else None


@lru_cache(maxsize=None)
def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=None)
def _load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _require_json(directory: Path, name: str) -> dict:
    path = _existing_file(directory, name, ".json")
    if path is None:
        raise FileNotFoundError(f"No {name!r} in {directory}")
    return _load_json(path)


def _optional_json(directory: Path, name: str) -> dict | None:
    path = _existing_file(directory, name, ".json")
    return _load_json(path) if path else None


def _optional_text(directory: Path, name: str) -> str | None:
    path = _existing_file(directory, name, ".md")
    return _load_text(path) if path else None


def load_schema(entity: str) -> dict:
    return _require_json(repo.schemas_dir(), entity)


def load_extension_schema(entity: str) -> dict | None:
    return _optional_json(repo.extension_schemas_dir(), entity)


def load_doc(field: str) -> str | None:
    return _optional_text(repo.docs_dir(), field)


def load_extension_doc(field: str) -> str | None:
    return _optional_text(repo.extension_docs_dir(), field)


def load_example(name: str) -> dict:
    return _require_json(repo.examples_dir(), name)


def list_schema_names() -> list[str]:
    # common.json holds shared field definitions referenced via $ref by the
    # other schemas; it isn't itself an entity (no properties/title/records).
    return sorted(
        p.stem for p in repo.schemas_dir().glob("*.json") if p.stem != "common"
    )


def list_extension_names() -> list[str]:
    return sorted(p.stem for p in repo.extension_schemas_dir().glob("*.json"))


def list_example_names() -> list[str]:
    return sorted(p.stem for p in repo.examples_dir().glob("*.json"))
