"""Text normalisation shared by field search, mapping and example lookup."""

from __future__ import annotations

import re

_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_NON_ALNUM_RE = re.compile(r"[^0-9a-zA-Z]+")


def normalise(text: str) -> str:
    """'OutstandingBalance' / 'outstanding_balance' -> 'outstanding balance'."""
    text = _CAMEL_BOUNDARY_RE.sub(" ", text)
    return " ".join(_NON_ALNUM_RE.sub(" ", text).lower().split())
