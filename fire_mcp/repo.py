"""Locates the FIRE (SuadeLabs/fire) data on disk so the rest of the package can read
schemas, extensions, documentation and examples without ever making a network call.

In order:
1. FIRE_REPO_ROOT, if set -- a FIRE checkout of the user's choosing (a different or
   modified release). Always wins, so it can override the bundled copy.
2. The copy bundled into released wheels at fire_mcp/_fire/, pinned to the FIRE
   release the Dockerfile names (see scripts/vendor_fire.py). A source checkout or
   a git install doesn't have it.
3. A FIRE checkout above this package (only when installed from inside a FIRE
   clone; not a supported path).

The checkout is located on first use rather than at import, so a missing or wrong
FIRE_REPO_ROOT surfaces as a one-line error from server.main() instead of a traceback
from deep inside an import."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

BUNDLED_ROOT = Path(__file__).resolve().parent / "_fire"


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

    if _looks_like_fire_repo(BUNDLED_ROOT):
        return BUNDLED_ROOT

    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if _looks_like_fire_repo(candidate):
            return candidate

    raise RuntimeError(
        "FIRE_REPO_ROOT is not set and this install has no bundled FIRE data (only "
        "released packages from PyPI include it). Install with `pip install "
        "suade-fire-mcp`, or clone https://github.com/SuadeLabs/fire and point "
        "FIRE_REPO_ROOT at it."
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
