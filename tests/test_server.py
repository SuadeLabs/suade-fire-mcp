from __future__ import annotations

import pytest

from fire_mcp import server


def test_split_env_list_parses_comma_separated(monkeypatch):
    monkeypatch.setenv(
        "FIRE_MCP_ALLOWED_HOSTS", "a.example.com, b.example.com ,c.example.com"
    )
    assert server._split_env_list("FIRE_MCP_ALLOWED_HOSTS") == [
        "a.example.com",
        "b.example.com",
        "c.example.com",
    ]


def test_split_env_list_requires_the_var(monkeypatch):
    monkeypatch.delenv("FIRE_MCP_ALLOWED_HOSTS", raising=False)
    with pytest.raises(RuntimeError, match="FIRE_MCP_ALLOWED_HOSTS"):
        server._split_env_list("FIRE_MCP_ALLOWED_HOSTS")


def test_main_defaults_to_stdio(monkeypatch):
    monkeypatch.delenv("FIRE_MCP_TRANSPORT", raising=False)
    calls = []
    monkeypatch.setattr(server.mcp, "run", lambda *a, **kw: calls.append((a, kw)))
    server.main()
    assert calls == [((), {})]


def test_main_rejects_unknown_transport(monkeypatch):
    monkeypatch.setenv("FIRE_MCP_TRANSPORT", "carrier-pigeon")
    with pytest.raises(RuntimeError, match="Unknown FIRE_MCP_TRANSPORT"):
        server.main()


def test_main_streamable_http_requires_allowed_hosts(monkeypatch):
    monkeypatch.setenv("FIRE_MCP_TRANSPORT", "streamable-http")
    monkeypatch.delenv("FIRE_MCP_ALLOWED_HOSTS", raising=False)
    monkeypatch.setenv("FIRE_MCP_ALLOWED_ORIGINS", "https://example.com")
    with pytest.raises(RuntimeError, match="FIRE_MCP_ALLOWED_HOSTS"):
        server.main()


def test_main_streamable_http_passes_security_settings(monkeypatch):
    monkeypatch.setenv("FIRE_MCP_TRANSPORT", "streamable-http")
    monkeypatch.setenv("PORT", "9001")
    monkeypatch.setenv("FIRE_MCP_ALLOWED_HOSTS", "example.com")
    monkeypatch.setenv("FIRE_MCP_ALLOWED_ORIGINS", "https://example.com")

    calls = []
    monkeypatch.setattr(server.mcp, "run", lambda *a, **kw: calls.append(kw))
    server.main()

    assert len(calls) == 1
    kwargs = calls[0]
    assert kwargs["transport"] == "streamable-http"
    assert kwargs["host"] == "0.0.0.0"
    assert kwargs["port"] == 9001
    assert kwargs["transport_security"].allowed_hosts == ["example.com"]
    assert kwargs["transport_security"].allowed_origins == ["https://example.com"]
    assert kwargs["stateless_http"] is True
    assert kwargs["max_request_body_size"] == server.MAX_REQUEST_BODY_SIZE


def test_health_route_bypasses_host_checks():
    # Load balancer health checks hit the instance directly, not via the public hostname.
    from starlette.testclient import TestClient

    app = server.mcp.streamable_http_app(
        transport_security=server.TransportSecuritySettings(
            allowed_hosts=["fire-mcp.example.com"],
            allowed_origins=["https://fire-mcp.example.com"],
        )
    )
    response = TestClient(app, base_url="http://10.0.0.1:8000").get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.fixture
def fresh_repo_root():
    """Let a test change FIRE_REPO_ROOT; restore the real checkout afterwards."""
    from fire_mcp import repo

    repo.root.cache_clear()
    yield
    repo.root.cache_clear()


@pytest.mark.parametrize(
    "value, message",
    [(None, "FIRE_REPO_ROOT is not set"), ("/", "does not look like a FIRE repo")],
)
def test_main_exits_with_one_line_when_fire_is_missing(
    monkeypatch, fresh_repo_root, value, message
):
    if value is None:
        monkeypatch.delenv("FIRE_REPO_ROOT", raising=False)
        # Don't let the walk-up fallback find a FIRE checkout above this package.
        monkeypatch.setattr(server.repo, "_looks_like_fire_repo", lambda path: False)
    else:
        monkeypatch.setenv("FIRE_REPO_ROOT", value)
    monkeypatch.setattr(server.mcp, "run", lambda *a, **kw: pytest.fail("ran"))
    with pytest.raises(SystemExit, match=message) as info:
        server.main()
    assert str(info.value).startswith("fire-mcp: ")
    assert "\n" not in str(info.value)
