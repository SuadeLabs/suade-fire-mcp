# suade-fire-mcp

An [MCP](https://modelcontextprotocol.io) server that exposes the [FIRE data
standard](https://github.com/SuadeLabs/fire) so a data engineering team's own AI assistant can
look up fields, validate draft records, and get mapping suggestions while mapping an internal
data format onto FIRE.

It reads a separate [`SuadeLabs/fire`](https://github.com/SuadeLabs/fire) checkout's `schemas/`,
`extensions/`, `documentation/` and `examples/` directly from disk at runtime -- no build step,
no network access. This repo and FIRE are independent: clone them separately, and pin the FIRE
checkout to a release tag (e.g. `git checkout v26.07`) if you want a specific version of the
standard rather than whatever `master` currently holds.

## Install

You need **both** repos on disk:

```bash
git clone https://github.com/SuadeLabs/fire.git
git clone https://github.com/SuadeLabs/suade-fire-mcp.git
cd suade-fire-mcp
pip install -e .
```

For local development (running the MCP inspector, tests):

```bash
pip install -e ".[dev]"
```

## Run

Point `FIRE_REPO_ROOT` at your FIRE clone -- this is required, since the server has no FIRE
checkout of its own to fall back to:

```bash
export FIRE_REPO_ROOT=/path/to/your/clone/of/fire
fire-mcp
# or
python -m fire_mcp.server
```

This serves over stdio by default. Point an MCP client at it, for example a `mcp.json`/client
config entry like:

```json
{
  "mcpServers": {
    "fire": {
      "command": "fire-mcp",
      "env": { "FIRE_REPO_ROOT": "/path/to/your/clone/of/fire" }
    }
  }
}
```

## Remote / hosted

This serves over stdio by default (a local subprocess, for clients like Claude Code that launch
it themselves). For clients that only speak to a server over HTTPS -- claude.ai's chat
interface, Claude Desktop's remote connectors -- run it with the Streamable HTTP transport
instead, over `FIRE_MCP_TRANSPORT=streamable-http`.

**Run the published image** (a FIRE checkout is baked in at build time, pinned to a release
tag -- no separate clone needed):

```bash
docker run -p 8000:8000 \
  -e FIRE_MCP_ALLOWED_HOSTS=your-host.example.com \
  -e FIRE_MCP_ALLOWED_ORIGINS=https://your-host.example.com \
  ghcr.io/suadelabs/suade-fire-mcp:latest
```

`FIRE_MCP_ALLOWED_HOSTS` / `FIRE_MCP_ALLOWED_ORIGINS` are required -- without them every
request from a real hostname is rejected with `421 Misdirected Request` (DNS-rebinding
protection in the MCP SDK). Set them to wherever this is actually reachable.

**Build your own image**, optionally pinned to a different FIRE tag:

```bash
docker build --build-arg FIRE_VERSION=v26.07 -t suade-fire-mcp .
```

This is a normal public image -- running your own copy anywhere needs nothing from Suade
beyond the image itself, the same way cloning FIRE needs nothing beyond the repo.

**Adding it to claude.ai**: once a URL is reachable, go to Settings -> Connectors -> Add
custom connector, and enter `https://<your-host>/mcp`.

## What it exposes

Resources:
- `fire://schemas/{entity}` -- an entity's schema, with all `$ref`s resolved inline
- `fire://properties/{field}` -- the markdown documentation for one field
- `fire://examples/{name}` -- a worked example payload
- `fire://extensions/{entity}` -- an entity's jurisdiction-specific extension fields, if any

Tools:
- `list_entities` -- every FIRE entity with a short description
- `search_fields(query)` -- fuzzy search over field names, descriptions and enum values
- `get_field(entity, field)` -- full detail on one field
- `validate_record(entity, record)` -- validate a JSON record against a FIRE schema
- `suggest_mapping(entity, source_fields)` -- ranked, non-authoritative mapping candidates for a
  list of your own field names

## License

Apache 2.0 -- see [LICENSE](LICENSE), matching FIRE's own license.
