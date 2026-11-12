# suade-fire-mcp

An [MCP](https://modelcontextprotocol.io) server that exposes the [FIRE data
standard](https://github.com/SuadeLabs/fire) so a data engineering team's own AI assistant can
look up fields, validate draft records, and get mapping suggestions while mapping an internal
data format onto FIRE.

It works with any MCP client -- Claude, ChatGPT, Cursor, VS Code / GitHub Copilot, Windsurf,
Gemini CLI, OpenAI Codex and others. It reads a [`SuadeLabs/fire`](https://github.com/SuadeLabs/fire)
checkout's `schemas/`, `extensions/`, `documentation/` and `examples/` directly from disk at
runtime -- no build step, no network access.

## 1. Choose how to run it

There are three ways to run the server. Pick one, then follow
[Connect your client](#2-connect-your-client).

| Option | Needs | Best for |
| --- | --- | --- |
| **A. Docker** (recommended) | Docker | Most people. FIRE is built into the image, pinned to a release tag, so you don't clone anything. |
| **B. Python** | Python 3.10+, a FIRE clone | People without Docker, or who want to use a different FIRE version or a modified one. |
| **C. Remote URL** | A hosted instance ([Hosting](#hosting-a-shared-instance)) | Chat apps that only accept a URL (claude.ai, ChatGPT), or sharing one instance with a team. |

### A. Docker

The client starts the container itself and talks to it over stdin/stdout. You don't run it
yourself; just check that Docker can pull the image:

```bash
docker pull ghcr.io/suadelabs/suade-fire-mcp:latest
```

To run it, the client uses this command:

```bash
docker run -i --rm -e FIRE_MCP_TRANSPORT=stdio ghcr.io/suadelabs/suade-fire-mcp:latest
```

`-i` is required because the client talks to the server over stdin. `FIRE_MCP_TRANSPORT=stdio`
overrides the image's default, which is the HTTP transport.

### B. Python

The server and FIRE are separate repos. Clone both, and pin FIRE to a release tag unless you
want whatever `master` holds right now:

```bash
git clone --branch v26.10 https://github.com/SuadeLabs/fire.git
git clone https://github.com/SuadeLabs/suade-fire-mcp.git
cd suade-fire-mcp
python -m venv .venv && . .venv/bin/activate
pip install .
which fire-mcp   # note this absolute path -- you'll put it in your client config
```

`FIRE_REPO_ROOT` is required. It must point at the FIRE clone.

The client starts the server with:

- **command:** the absolute path from `which fire-mcp`, e.g. `/home/you/suade-fire-mcp/.venv/bin/fire-mcp`
- **env:** `FIRE_REPO_ROOT=/absolute/path/to/fire`

> **Use absolute paths.** Desktop apps (Claude Desktop, Cursor, VS Code, Windsurf) don't
> inherit your shell's `PATH` or activated virtualenv. A bare `fire-mcp` command, or a `~` in
> a path, usually fails with "command not found" or "spawn ENOENT".

With [uv](https://docs.astral.sh/uv/) you don't need a clone or virtualenv for the server.
Use `uvx` as the command and
`["--from", "git+https://github.com/SuadeLabs/suade-fire-mcp", "fire-mcp"]` as the args. You
still need the FIRE clone and `FIRE_REPO_ROOT`.

### C. Remote URL

If someone already runs a shared instance, all you need is its URL, e.g.
`https://fire-mcp.example.com/mcp`. Note the `/mcp` path. The server has no sign-in and every
tool is read-only, so there are no credentials to configure.

To run your own instance, see [Hosting a shared instance](#hosting-a-shared-instance).

## 2. Connect your client

The snippets below use **option A (Docker)** for local servers. For **option B (Python)**,
replace `command`/`args` with the absolute `fire-mcp` path and an empty args list, and add an
`env` block, as shown under [Claude Desktop](#claude-desktop). For **option C**, use the
"Remote" snippet for your client.

Where a client has a project-level config file, it's noted. Commit that file to share the
setup with your team.

### Claude Desktop

Edit `claude_desktop_config.json`. It's at `~/Library/Application Support/Claude/` on macOS
and `%APPDATA%\Claude\` on Windows; Settings -> Developer -> Edit Config opens it. Then
restart the app.

```json
{
  "mcpServers": {
    "fire": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "-e", "FIRE_MCP_TRANSPORT=stdio",
               "ghcr.io/suadelabs/suade-fire-mcp:latest"]
    }
  }
}
```

Option B (Python) looks like this. The same `command` + `env` shape works in every client
below:

```json
{
  "mcpServers": {
    "fire": {
      "command": "/absolute/path/to/suade-fire-mcp/.venv/bin/fire-mcp",
      "env": { "FIRE_REPO_ROOT": "/absolute/path/to/fire" }
    }
  }
}
```

**Remote:** Settings -> Connectors -> Add custom connector, and enter the URL.

### claude.ai (web and mobile)

Remote only. Go to Settings -> Connectors -> Add custom connector, and enter
`https://<your-host>/mcp`. On Team and Enterprise plans, an Owner adds the connector once for
the whole organization.

### Claude Code

```bash
# Local (Docker)
claude mcp add fire -- docker run -i --rm -e FIRE_MCP_TRANSPORT=stdio ghcr.io/suadelabs/suade-fire-mcp:latest

# Local (Python)
claude mcp add fire -e FIRE_REPO_ROOT=/absolute/path/to/fire -- /absolute/path/to/fire-mcp

# Remote
claude mcp add --transport http fire https://<your-host>/mcp
```

Add `--scope project` to write the server to a shared `.mcp.json` in the repo instead.

### ChatGPT

Remote only. Turn on developer mode under Settings -> Apps & Connectors -> Advanced. Then
create a connector with the URL `https://<your-host>/mcp` and **No authentication**. Menu
names differ between plans; on Business and Enterprise plans an admin may have to enable
custom connectors first.

### Cursor

Edit `~/.cursor/mcp.json`, or `.cursor/mcp.json` in a project:

```json
{
  "mcpServers": {
    "fire": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "-e", "FIRE_MCP_TRANSPORT=stdio",
               "ghcr.io/suadelabs/suade-fire-mcp:latest"]
    }
  }
}
```

**Remote:** `{ "mcpServers": { "fire": { "url": "https://<your-host>/mcp" } } }`

### VS Code (GitHub Copilot agent mode)

Edit `.vscode/mcp.json` in a workspace, or run **MCP: Open User Configuration** from the
command palette. VS Code uses a top-level `servers` key, not `mcpServers`, and each server
needs a `type`:

```json
{
  "servers": {
    "fire": {
      "type": "stdio",
      "command": "docker",
      "args": ["run", "-i", "--rm", "-e", "FIRE_MCP_TRANSPORT=stdio",
               "ghcr.io/suadelabs/suade-fire-mcp:latest"]
    }
  }
}
```

**Remote:** `{ "servers": { "fire": { "type": "http", "url": "https://<your-host>/mcp" } } }`

### Windsurf

Edit `~/.codeium/windsurf/mcp_config.json`. The local snippet is the same as Cursor's.

**Remote:** Windsurf names the URL key `serverUrl`:
`{ "mcpServers": { "fire": { "serverUrl": "https://<your-host>/mcp" } } }`

### Gemini CLI

Edit `~/.gemini/settings.json`, or `.gemini/settings.json` in a project. The local snippet is
the same as Cursor's.

**Remote:** Gemini CLI uses `httpUrl` for Streamable HTTP:
`{ "mcpServers": { "fire": { "httpUrl": "https://<your-host>/mcp" } } }`

### OpenAI Codex (CLI and IDE extension)

Edit `~/.codex/config.toml`:

```toml
[mcp_servers.fire]
command = "docker"
args = ["run", "-i", "--rm", "-e", "FIRE_MCP_TRANSPORT=stdio", "ghcr.io/suadelabs/suade-fire-mcp:latest"]

# Option B (Python) instead:
# command = "/absolute/path/to/fire-mcp"
# env = { FIRE_REPO_ROOT = "/absolute/path/to/fire" }
```

**Remote:** `url = "https://<your-host>/mcp"` in place of `command`/`args`.

### Any other client

Most MCP clients take a server definition in one of these shapes:

- **stdio:** a `command`, its `args`, and an optional `env`. Use the command from option A or B.
- **Streamable HTTP:** a URL ending in `/mcp`. The key may be called `url`, `serverUrl` or
  `httpUrl`, and some clients also want `"type": "http"`. This server does **not** offer the
  older SSE transport.

If a client only supports stdio but you want to use a remote instance, run it through the
[`mcp-remote`](https://www.npmjs.com/package/mcp-remote) bridge:
`"command": "npx", "args": ["-y", "mcp-remote", "https://<your-host>/mcp"]`.

### Check that it works

Ask your assistant to *"list the FIRE entities"*. It should call `list_entities` and return
`loan`, `account`, `customer`, and so on. If the tools don't appear:

- **"spawn ENOENT" / "command not found":** use an absolute path to `fire-mcp` or `docker`
  (see option B).
- **`FIRE_REPO_ROOT is not set` / `does not look like a FIRE repo`:** set `env` to the
  absolute path of the FIRE clone. That directory contains `schemas/` and `documentation/`.
- **The server starts, then exits immediately under Docker:** check that `-i` is in `args`.
- **`421 Misdirected Request` from a remote URL:** the host's `FIRE_MCP_ALLOWED_HOSTS` doesn't
  include the hostname you're using (see below).

To test the server without an assistant, use the
[MCP Inspector](https://github.com/modelcontextprotocol/inspector):
`npx @modelcontextprotocol/inspector docker run -i --rm -e FIRE_MCP_TRANSPORT=stdio ghcr.io/suadelabs/suade-fire-mcp:latest`.

## Hosting a shared instance

A shared instance serves the Streamable HTTP transport (`FIRE_MCP_TRANSPORT=streamable-http`),
and this is the image's default. Use one for clients that only accept a URL, or so a team
doesn't each run their own server.

```bash
docker run -p 8000:8000 \
  -e FIRE_MCP_ALLOWED_HOSTS=fire-mcp.example.com \
  -e FIRE_MCP_ALLOWED_ORIGINS=https://fire-mcp.example.com \
  ghcr.io/suadelabs/suade-fire-mcp:latest
```

Put it behind HTTPS (a reverse proxy or your platform's load balancer). Clients connect to
`https://fire-mcp.example.com/mcp`.

`FIRE_MCP_ALLOWED_HOSTS` and `FIRE_MCP_ALLOWED_ORIGINS` are required. Without them, the MCP
SDK's DNS-rebinding protection rejects every request from a real hostname with
`421 Misdirected Request`. Set both to wherever the instance is actually reachable. Each takes
a comma-separated list. `PORT` defaults to `8000`.

**Build your own image**, optionally pinned to a different FIRE tag:

```bash
docker build --build-arg FIRE_VERSION=v26.07 -t suade-fire-mcp .
```

It's a normal public image. Running your own copy needs nothing from Suade beyond the image,
just as cloning FIRE needs nothing beyond the repo.

**Operating notes:**

- The HTTP transport is stateless (no MCP sessions), so instances can restart or scale out
  without breaking anyone's conversation. `GET /health` returns `{"status": "ok"}` for load
  balancer checks.
- Don't rate-limit per IP. Hosted assistants send requests from shared egress ranges, so many
  users share one address. For example, claude.ai connects from Anthropic's `160.79.104.0/21`.
  Don't block that range at a firewall or WAF either.
- Tool arguments, including draft records passed to `validate_record` / `validate_batch`, are
  never stored and are only logged at DEBUG level. Don't run a public instance with debug
  logging on.
- Tool results are sized to fit hosted assistants' result limits; for example, claude.ai
  allows ~150k characters and Claude Code 25k tokens by default. `list_fields` returns
  per-field summaries; `get_field` returns one field's enum values and docs. `search_fields`
  is capped at 50 results and `suggest_mapping` at 100 source fields per call.
  `validate_batch` takes up to 1000 records per call and returns at most 250 issues, with
  a `truncated` flag and the full `issue_count`. Values echoed back in issues are shortened.

## Development

```bash
pip install -e ".[dev]"
export FIRE_REPO_ROOT=/absolute/path/to/fire
pytest
```

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
  against a FIRE schema; returns `{"valid": bool, "issues": [...]}`. `jurisdiction` (e.g.
  `US`) adds that jurisdiction's extension fields; an unknown value is an error
- `validate_batch(records, jurisdiction=None, strict=False)` -- validate up to 1000
  `{"entity", "record"}` pairs, plus cross-record `*_id` reference checks; returns
  `{"valid", "record_count", "issue_count", "truncated", "records", "referential_issues"}`,
  where `records` lists only the records with issues
- `suggest_mapping(entity, source_fields, sample_values=None)` -- ranked, non-authoritative
  mapping candidates for up to 100 of your own field names, in any naming style
  (`CustomerID`, `customer-id`, `cust_id`); returns
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
  tools, are not persisted, and are not logged outside DEBUG level.

## License

Apache 2.0 -- see [LICENSE](LICENSE), matching FIRE's own license.
