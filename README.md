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
