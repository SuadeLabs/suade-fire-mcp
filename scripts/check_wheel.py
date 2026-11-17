"""Smoke-test an installed release build: start its server over stdio with no
FIRE_REPO_ROOT, so it has to find the bundled FIRE data, and call a tool.

Run with the Python of a clean virtualenv the wheel was installed into, from a
directory outside the source tree (so the checkout's fire_mcp isn't imported):

    /tmp/venv/bin/python -I scripts/check_wheel.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import anyio
from mcp import Client, StdioServerParameters


async def check() -> None:
    import fire_mcp

    package = Path(fire_mcp.__file__).resolve().parent
    if not (package / "_fire" / "FIRE_VERSION").is_file():
        raise SystemExit(f"No bundled FIRE data in {package}.")
    fire_version = (package / "_fire" / "FIRE_VERSION").read_text().strip()

    command = Path(sys.executable).parent / "suade-fire-mcp"
    # Only PATH: no FIRE_REPO_ROOT, so the bundled copy is the only source.
    env = {"PATH": os.environ.get("PATH", "")}
    async with Client(StdioServerParameters(command=str(command), env=env)) as client:
        tools = (await client.list_tools()).tools
        result = await client.call_tool(
            "validate_record",
            {"entity": "loan", "record": {"id": "L1", "date": "2026-01-01T00:00:00Z"}},
        )
    if result.is_error or not result.structured_content.get("valid"):
        raise SystemExit(f"validate_record failed: {result.content}")
    print(f"OK: {len(tools)} tools, bundled FIRE {fire_version}.")


if __name__ == "__main__":
    anyio.run(check)
