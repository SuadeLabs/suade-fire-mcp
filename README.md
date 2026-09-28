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

**Connecting from Claude**: the server is authless and every tool is read-only, so there is
nothing to sign in to. Once a URL is reachable:

- **claude.ai / Claude Desktop / mobile**: Customize -> Connectors -> Add custom connector, and
  enter `https://<your-host>/mcp`. On Team and Enterprise plans an Owner adds it once for the
  whole organization.
- **Claude Code**: `claude mcp add --transport http fire https://<your-host>/mcp`

**Operating a hosted instance**:

- The HTTP transport is stateless (no MCP sessions), so machines can restart or scale out
  without breaking anyone's conversation. `GET /health` returns `{"status": "ok"}` for load
  balancer checks.
- Claude's requests come from Anthropic's egress range `160.79.104.0/21`. Don't block it at a
  firewall/WAF, and don't rate-limit per IP -- every claude.ai user shares those addresses.
- Tool arguments (including draft records passed to `validate_record` / `validate_batch`) are
  never stored, and are only logged at DEBUG level. Don't run a public instance with debug
  logging on.
- Tool results are sized to stay inside Claude's limits (~150k characters on claude.ai, 25k
  tokens by default in Claude Code): `list_fields` returns per-field summaries, with enum
  values and docs available one field at a time through `get_field`. `search_fields` is capped
  at 50 results, and `validate_batch` at 1000 records per call.

## What it exposes

Resources:
- `fire://schemas/{entity}` -- an entity's schema, with all `$ref`s resolved inline
- `fire://properties/{field}` -- the markdown documentation for one field
- `fire://examples/{name}` -- a worked example payload
- `fire://extensions/{entity}` -- an entity's jurisdiction-specific extension fields, if any

Tools (all read-only):
- `list_entities` -- every FIRE entity with a short description
- `list_fields(entity)` -- summary of every field on an entity, flagged required / enum
- `search_fields(query, limit=10)` -- fuzzy search over field names, descriptions and enum
  values (max 50 results)
- `get_field(entity, field)` -- full detail on one field, including enum values and docs
- `get_enum_definitions(entity, field)` -- the prose definition of each value of an enum field
- `get_examples(name=None)` -- list the worked example payloads, or fetch one by name
- `find_examples(query, entity=None, limit=5)` -- find worked examples for a product or trade
  type ("buy to let mortgage", "fx swap"), with the classification (enum) values each uses
- `validate_record(entity, record, jurisdiction=None, strict=False)` -- validate a JSON record
  against a FIRE schema; returns `{"valid": bool, "issues": [...]}`
- `validate_batch(records, jurisdiction=None, strict=False)` -- validate up to 1000
  `{"entity", "record"}` pairs, plus cross-record `*_id` reference checks
- `suggest_mapping(entity, source_fields, sample_values=None)` -- ranked, non-authoritative
  mapping candidates for a list of your own field names; returns
  `{"candidates": [...], "basis": "..."}`, where `basis` explains what the scores mean and each
  candidate's `example_evidence` says how many worked examples populate that field

## Disclaimer

This is an open-source, AI-assisted tool, provided as-is under the Apache 2.0 license, with no
warranty, SLA or support commitment. Use it at your own risk.

- **Schemas, field definitions, examples and validation** come straight from the published
  [FIRE standard](https://github.com/SuadeLabs/fire) at the pinned release. They are only as
  current as that release.
- **Mapping suggestions are not advice.** `suggest_mapping` ranks candidates by how similar
  field names look, not by what the fields mean. The AI assistant using this server can also
  misread or misapply any result. Check every mapping against the FIRE field definitions before
  relying on it, and don't treat anything this server or an assistant says as a Suade
  recommendation for regulatory reporting.
- **Nothing you send is stored.** Tool arguments, including records passed to the validation
  tools, are not persisted, and the hosted instance does not log them.

## License

Apache 2.0 -- see [LICENSE](LICENSE), matching FIRE's own license.
