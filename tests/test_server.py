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
