# Hosting a shared instance

A hosted instance serves the Streamable HTTP transport, so apps that only accept a URL
(claude.ai, ChatGPT) can use it, and a team can share one server instead of each running their
own. The Docker image uses this transport by default.

```bash
docker run -p 8000:8000 \
  -e FIRE_MCP_ALLOWED_HOSTS=fire-mcp.example.com \
  -e FIRE_MCP_ALLOWED_ORIGINS=https://fire-mcp.example.com \
  ghcr.io/suadelabs/suade-fire-mcp:latest
```

Put it behind HTTPS (a reverse proxy or your platform's load balancer). Clients connect to
`https://fire-mcp.example.com/mcp`. There is no sign-in: every tool is read-only and serves
public FIRE data.

## Required settings

`FIRE_MCP_ALLOWED_HOSTS` and `FIRE_MCP_ALLOWED_ORIGINS` are required. Without them, the MCP
SDK's DNS-rebinding protection rejects every request from a real hostname with
`421 Misdirected Request`.

- Each takes a comma-separated list, matched exactly against the request's `Host` or `Origin`
  header.
- Include the port when clients send one: `localhost:8000`, or `localhost:*` for any port.
- `PORT` defaults to `8000`.

## Operating notes

- **Stateless.** There are no MCP sessions, so instances can restart or scale out without
  breaking anyone's conversation.
- **Health check.** `GET /health` returns `{"status": "ok", "version": ...}`. The image's
  Docker `HEALTHCHECK` uses it.
- **Unprivileged.** The image runs as user `fire` (uid 10001).
- **Don't rate-limit per IP.** Hosted assistants send requests from shared egress ranges, so
  many users share one address. claude.ai, for example, connects from Anthropic's
  `160.79.104.0/21`; don't block that range at a firewall or WAF.
- **Request size.** Bodies up to 16 MiB are accepted, enough for a full 1000-record
  `validate_batch` call. A reverse proxy in front needs at least the same limit.
- **Privacy.** Tool arguments, including records sent for validation, are never stored and are
  only logged at DEBUG level. Don't run a public instance with debug logging on.
- **Result sizes.** Results are capped to fit hosted assistants' limits (about 150k characters
  on claude.ai, 25k tokens by default in Claude Code). `search_fields` returns at most 50
  results, `suggest_mapping` takes at most 100 source fields, and `validate_batch` takes 1000
  records and returns at most 250 issues, with a `truncated` flag.

## A different FIRE release

The image clones FIRE at the tag set by `ARG FIRE_VERSION` in the Dockerfile. To build one
against another release:

```bash
docker build --build-arg FIRE_VERSION=v26.07 -t suade-fire-mcp .
```

Running your own copy needs nothing from Suade beyond the image, or this repo to build it.
