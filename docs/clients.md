# Client setup

Every client needs one of three things:

| Run it with | Client config | Use when |
| --- | --- | --- |
| **uv** (recommended) | command `uvx`, args `["suade-fire-mcp"]` | Almost always. Nothing else to install; FIRE is bundled. |
| **Docker** | command `docker`, args `["run", "-i", "--rm", "-e", "FIRE_MCP_TRANSPORT=stdio", "ghcr.io/suadelabs/suade-fire-mcp:latest"]` | You prefer containers. |
| **A URL** | `https://<your-host>/mcp` | The app only accepts URLs (claude.ai, ChatGPT), or your team shares one [hosted instance](hosting.md). |

Notes:
- **Docker:** the image is currently private. SuadeLabs members can `docker login ghcr.io` with a
  GitHub token that has `read:packages`; everyone else should use uv. `-i` is required, and
  `FIRE_MCP_TRANSPORT=stdio` overrides the image's default HTTP transport.
- **Your own FIRE checkout:** add `"env": { "FIRE_REPO_ROOT": "/absolute/path/to/fire" }`. It
  takes precedence over the bundled data.
- **Without uv:** `pip install suade-fire-mcp` into a virtualenv, and use the absolute path of
  its `suade-fire-mcp` script as the command.
- **Desktop apps** (Claude Desktop, Cursor, VS Code, Windsurf) don't inherit your shell's `PATH`.
  If the command isn't found, use its absolute path (`which uvx`).
- **A URL ends in `/mcp`.** There's no sign-in. This server uses Streamable HTTP and does not
  offer the older SSE transport.

Where a client has a project-level config file, commit it to share the setup with your team.

## Claude Code

```bash
claude mcp add fire -- uvx suade-fire-mcp                               # uv
claude mcp add fire -- docker run -i --rm -e FIRE_MCP_TRANSPORT=stdio ghcr.io/suadelabs/suade-fire-mcp:latest
claude mcp add --transport http fire https://<your-host>/mcp            # URL
```

Add `--scope project` to write it to a shared `.mcp.json` instead.

## Claude Desktop

Settings → Developer → Edit Config opens `claude_desktop_config.json`. Add the server, then
restart the app:

```json
{
  "mcpServers": {
    "fire": { "command": "uvx", "args": ["suade-fire-mcp"] }
  }
}
```

**URL:** Settings → Connectors → Add custom connector.

## claude.ai (web and mobile)

URL only. Settings → Connectors → Add custom connector, and enter `https://<your-host>/mcp`. On
Team and Enterprise plans, an Owner adds it once for the organization.

## ChatGPT

URL only. Turn on developer mode under Settings → Apps & Connectors → Advanced, then create a
connector with your URL and **No authentication**. On Business and Enterprise plans an admin
may have to enable custom connectors first.

## Cursor, Windsurf and Gemini CLI

These use the same `mcpServers` shape as Claude Desktop. Only the file and the URL key differ:

| Client | Config file | Key for a URL |
| --- | --- | --- |
| Cursor | `~/.cursor/mcp.json` or `.cursor/mcp.json` | `url` |
| Windsurf | `~/.codeium/windsurf/mcp_config.json` | `serverUrl` |
| Gemini CLI | `~/.gemini/settings.json` or `.gemini/settings.json` | `httpUrl` |

For example, a URL in Windsurf: `{ "mcpServers": { "fire": { "serverUrl": "https://<your-host>/mcp" } } }`

## VS Code (GitHub Copilot agent mode)

Edit `.vscode/mcp.json`, or run **MCP: Open User Configuration**. VS Code uses `servers` (not
`mcpServers`), and each server needs a `type`:

```json
{
  "servers": {
    "fire": { "type": "stdio", "command": "uvx", "args": ["suade-fire-mcp"] }
  }
}
```

**URL:** `{ "servers": { "fire": { "type": "http", "url": "https://<your-host>/mcp" } } }`

## OpenAI Codex (CLI and IDE extension)

Edit `~/.codex/config.toml`:

```toml
[mcp_servers.fire]
command = "uvx"
args = ["suade-fire-mcp"]
```

**URL:** `url = "https://<your-host>/mcp"` in place of `command`/`args`.

## Any other client

Use the command and args, or the URL, from the table at the top. If a client supports only
stdio but you want a hosted instance, bridge it with
[`mcp-remote`](https://www.npmjs.com/package/mcp-remote):
`"command": "npx", "args": ["-y", "mcp-remote", "https://<your-host>/mcp"]`.

## Troubleshooting

- **"spawn ENOENT" / "command not found":** use the absolute path to `uvx` or `docker`.
- **"no bundled FIRE data" / "does not look like a FIRE repo":** you installed from git or a
  source checkout. Install from PyPI, or set `FIRE_REPO_ROOT` to a FIRE clone (the directory
  that contains `schemas/` and `documentation/`).
- **Under Docker, the server starts and exits immediately:** `-i` is missing from `args`.
- **`421 Misdirected Request` from a URL:** the host's `FIRE_MCP_ALLOWED_HOSTS` doesn't include
  that hostname. See [hosting](hosting.md#required-settings).
- **To test without an assistant:** `npx @modelcontextprotocol/inspector uvx suade-fire-mcp`.
