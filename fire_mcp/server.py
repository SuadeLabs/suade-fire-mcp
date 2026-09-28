"""Entry point: wires up the FIRE MCPServer and runs it.

Transport is chosen via FIRE_MCP_TRANSPORT: "stdio" (default, for Claude Code / local
clients that launch this as a subprocess) or "streamable-http" (for a long-running hosted
instance reachable over HTTPS, e.g. for claude.ai's remote connectors).
"""

from __future__ import annotations

import os
from importlib.metadata import PackageNotFoundError, version

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from . import resources, tools

try:
    _VERSION = version("suade-fire-mcp")
except PackageNotFoundError:  # running from a source tree without installing
    _VERSION = "0.0.0"

mcp = MCPServer(
    "fire",
    title="FIRE data standard",
    version=_VERSION,
    website_url="https://github.com/SuadeLabs/suade-fire-mcp",
    instructions=(
        "Read-only reference for the FIRE (Financial Regulatory) data standard: "
        "entity schemas, field definitions and enum values, worked examples, record "
        "and batch validation, and suggested mappings from internal field names to "
        "FIRE fields."
    ),
)
resources.register(mcp)
tools.register(mcp)


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> Response:
    return JSONResponse({"status": "ok", "version": _VERSION})


def _split_env_list(name: str) -> list[str]:
    raw = os.environ.get(name)
    if not raw:
        raise RuntimeError(
            f"{name} is not set. Streamable HTTP transport requires it -- without an "
            f"explicit allow-list, every request from a real hostname is rejected. Set it "
            f"to a comma-separated list, e.g. {name}=fire-mcp.example.com."
        )
    return [item.strip() for item in raw.split(",") if item.strip()]


def _run_streamable_http() -> None:
    port = int(os.environ.get("PORT", "8000"))
    security = TransportSecuritySettings(
        allowed_hosts=_split_env_list("FIRE_MCP_ALLOWED_HOSTS"),
        allowed_origins=_split_env_list("FIRE_MCP_ALLOWED_ORIGINS"),
    )
    mcp.run(
        transport="streamable-http",
        # Every tool is a pure read of the baked-in FIRE checkout, so there is no
        # session state worth keeping -- and without it, requests survive machine
        # restarts and can land on any instance behind the load balancer.
        stateless_http=True,
        json_response=True,
        host="0.0.0.0",
        port=port,
        transport_security=security,
    )


def main() -> None:
    transport = os.environ.get("FIRE_MCP_TRANSPORT", "stdio")
    if transport == "stdio":
        mcp.run()
    elif transport == "streamable-http":
        _run_streamable_http()
    else:
        raise RuntimeError(
            f"Unknown FIRE_MCP_TRANSPORT={transport!r}. Use 'stdio' or 'streamable-http'."
        )


if __name__ == "__main__":
    main()
