# suade-fire-mcp

<!-- mcp-name: io.github.SuadeLabs/suade-fire-mcp -->

An [MCP](https://modelcontextprotocol.io) server for the
[FIRE data standard](https://github.com/SuadeLabs/fire). It lets your AI assistant look up
FIRE fields, validate draft records and suggest mappings while you map an internal data format
onto FIRE.

It works with any MCP client (Claude, ChatGPT, Cursor, VS Code, Windsurf, Gemini CLI, Codex and
others). It's read-only, needs no sign-in, and makes no network calls: the FIRE schemas, docs
and examples are bundled from a pinned FIRE release (currently v26.10).

## Quick start

With [uv](https://docs.astral.sh/uv/) installed, add this server to your client:

```json
{
  "mcpServers": {
    "fire": { "command": "uvx", "args": ["suade-fire-mcp"] }
  }
}
```

In Claude Code: `claude mcp add fire -- uvx suade-fire-mcp`

Then ask your assistant *"list the FIRE entities"*. It should return `loan`, `account`,
`customer`, and so on.

**Other clients, Docker, or a remote URL:** see
[client setup](https://github.com/SuadeLabs/suade-fire-mcp/blob/main/docs/clients.md). Apps
that only accept a URL (claude.ai, ChatGPT) need a
[hosted instance](https://github.com/SuadeLabs/suade-fire-mcp/blob/main/docs/hosting.md).

## What you can ask

- *"Which FIRE fields hold interest rate information on a loan?"*
- *"How does FIRE represent a buy-to-let mortgage? Show me the example."*
- *"Map these columns onto the FIRE loan schema: cust_id, bal_amt, int_rate, maturity_dt"*
- *"Why does this record fail validation?"* (paste the record)

For the last two, your client may also offer the `map_source_schema` and
`explain_validation_failure` prompts, which walk the assistant through the checks step by step.

## Tools

All tools are read-only. Each one documents its parameters and result shape in its schema.

| Tool | What it does |
| --- | --- |
| `list_entities` | Every FIRE entity with a short description |
| `list_fields` | Summary of every field on an entity (type, required, enum or not) |
| `search_fields` | Search field names, descriptions and enum values across entities |
| `get_field` | Full detail on one field; optionally the definition of each enum value |
| `find_examples` | FIRE's worked examples for a product type (e.g. "fx swap"), with the enum values they use |
| `get_example` | One worked example in full |
| `suggest_mapping` | Ranked candidate FIRE fields for up to 100 of your own field names |
| `validate_record` | Check one record against an entity schema, optionally for a jurisdiction |
| `validate_batch` | Check up to 1000 records, including `*_id` references between them |

**Prompts:** `map_source_schema(entity, source_fields)` builds a reviewed mapping table;
`explain_validation_failure(entity, record)` explains and fixes a failing record.

**Resources:** `fire://schemas/{entity}`, `fire://extensions/{entity}`,
`fire://properties/{field}` and `fire://examples/{name}`, with autocomplete.

## Configuration

Released packages need no configuration. These environment variables cover everything else:

| Variable | Default | Purpose |
| --- | --- | --- |
| `FIRE_REPO_ROOT` | bundled data | Path to a FIRE checkout to use instead of the bundled release, e.g. a newer or modified FIRE. Required when running from source. |
| `FIRE_MCP_TRANSPORT` | `stdio` (`streamable-http` in the Docker image) | `stdio` for clients that launch the server, `streamable-http` for a hosted instance. |
| `PORT` | `8000` | HTTP port (`streamable-http` only). |
| `FIRE_MCP_ALLOWED_HOSTS` | none, required | Comma-separated `Host` values the hosted instance answers to (`streamable-http` only). |
| `FIRE_MCP_ALLOWED_ORIGINS` | none, required | Comma-separated allowed `Origin` values (`streamable-http` only). |

## Troubleshooting

- **"spawn ENOENT" / "command not found":** desktop apps don't inherit your shell's `PATH`. Use
  the absolute path from `which uvx`.
- **"no bundled FIRE data":** you installed from git or a source checkout. Install from PyPI, or
  set `FIRE_REPO_ROOT` to a FIRE clone.
- **Tools don't appear:** test the server on its own with the
  [MCP Inspector](https://github.com/modelcontextprotocol/inspector):
  `npx @modelcontextprotocol/inspector uvx suade-fire-mcp`.

Docker and hosted-instance problems are covered in
[client setup](https://github.com/SuadeLabs/suade-fire-mcp/blob/main/docs/clients.md#troubleshooting)
and [hosting](https://github.com/SuadeLabs/suade-fire-mcp/blob/main/docs/hosting.md).

## Limitations and disclaimer

This is an open-source, AI-assisted tool, provided as-is under the Apache 2.0 license, with no
warranty, SLA or support commitment.

- **Schemas, definitions, examples and validation** come straight from the pinned
  [FIRE release](https://github.com/SuadeLabs/fire), and are only as current as it is. Some of
  FIRE v26.10's own examples use dates without a UTC offset, which validation correctly reports
  as `format_mismatch` ([fixed upstream](https://github.com/SuadeLabs/fire/pull/710)).
- **Mapping suggestions are not advice.** `suggest_mapping` ranks candidates by how similar the
  names look, not by what the fields mean, and the assistant can misread any result. Check every
  mapping against the FIRE definitions. Nothing here is a Suade recommendation for regulatory
  reporting.
- **Nothing you send is stored.** Tool arguments, including records you validate, are not
  persisted and are only logged at DEBUG level.

## Contributing

See [CONTRIBUTING.md](https://github.com/SuadeLabs/suade-fire-mcp/blob/main/CONTRIBUTING.md).

## License

Apache 2.0, matching FIRE's own license. See
[LICENSE](https://github.com/SuadeLabs/suade-fire-mcp/blob/main/LICENSE).
