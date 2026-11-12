"""Locates a FIRE (SuadeLabs/fire) checkout on disk so the rest of the package can read
schemas, extensions, documentation and examples without ever making a network call.

This package and FIRE are separate repos, so FIRE_REPO_ROOT is the required way to point
at a checkout. The walk-up-from-__file__ fallback below only helps if this package happens
to be installed from inside a FIRE clone (e.g. local development against a vendored copy);
it is not the supported path.

The checkout is located on first use rather than at import, so a missing or wrong
FIRE_REPO_ROOT surfaces as a one-line error from server.main() instead of a traceback
from deep inside an import."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


def _looks_like_fire_repo(path: Path) -> bool:
    return (path / "schemas").is_dir() and (path / "documentation").is_dir()


def _find_repo_root() -> Path:
    override = os.environ.get("FIRE_REPO_ROOT")
    if override:
        path = Path(override).expanduser().resolve()
        if not _looks_like_fire_repo(path):
            raise RuntimeError(
                f"FIRE_REPO_ROOT={path} does not look like a FIRE repo "
                "(expected schemas/ and documentation/ subdirectories)."
            )
        return path

    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if _looks_like_fire_repo(candidate):
            return candidate

    raise RuntimeError(
        "FIRE_REPO_ROOT is not set. Clone https://github.com/SuadeLabs/fire and point "
        "FIRE_REPO_ROOT at it -- there is no FIRE checkout to read schemas, docs or "
        "examples from otherwise."
    )


@lru_cache(maxsize=None)
def root() -> Path:
    return _find_repo_root()


def schemas_dir() -> Path:
    return root() / "schemas"


def extension_schemas_dir() -> Path:
    return root() / "extensions" / "schemas"


def docs_dir() -> Path:
    return root() / "documentation" / "properties"


def extension_docs_dir() -> Path:
    return root() / "extensions" / "documentation" / "properties"


def examples_dir() -> Path:
    return root() / "examples"
