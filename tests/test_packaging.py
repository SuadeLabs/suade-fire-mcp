"""Release metadata that must agree across files. The MCP Registry rejects a
publish whose server.json doesn't match the PyPI package it points at."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python 3.10
    tomllib = None


def _server_json():
    return json.loads((ROOT / "server.json").read_text())


def _pyproject_version():
    text = (ROOT / "pyproject.toml").read_text()
    if tomllib is not None:
        return tomllib.loads(text)["project"]["version"]
    for line in text.splitlines():
        if line.startswith("version = "):
            return line.split('"')[1]
    raise AssertionError("no version in pyproject.toml")


def test_server_json_versions_match_pyproject():
    server = _server_json()
    version = _pyproject_version()
    assert server["version"] == version
    assert [p["version"] for p in server["packages"]] == [version]


def test_server_json_points_at_this_package():
    (package,) = _server_json()["packages"]
    assert package["registryType"] == "pypi"
    assert package["identifier"] == "suade-fire-mcp"


def test_readme_carries_the_registry_ownership_marker():
    # The registry verifies PyPI ownership by finding "mcp-name: <name>" in the
    # package README (the PyPI long description).
    name = _server_json()["name"]
    assert f"mcp-name: {name}" in (ROOT / "README.md").read_text()


def test_server_json_description_fits_the_registry_limit():
    assert len(_server_json()["description"]) <= 100
