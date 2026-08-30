import importlib.util
from pathlib import Path

import pytest


_SERVER_PATH = Path(__file__).resolve().parents[1] / "mcp" / "mcp_http_server.py"
_SPEC = importlib.util.spec_from_file_location("bookmark_rag_mcp_http_server", _SERVER_PATH)
assert _SPEC is not None and _SPEC.loader is not None
mcp_http_server = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mcp_http_server)


def test_hosted_server_publishes_read_only_bookmark_tools() -> None:
    tool_names = {tool.name for tool in mcp_http_server.mcp._tool_manager.list_tools()}

    assert tool_names == {"get_documents", "list_bookmarks", "search_documents"}


def test_http_settings_accepts_public_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOOKMARK_RAG_DOMAIN", "https://bookmarks.example.test")
    monkeypatch.setenv("MCP_HTTP_HOST", "127.0.0.1")
    monkeypatch.setenv("MCP_HTTP_PORT", "8123")
    monkeypatch.setenv("MCP_HTTP_PATH", "/public-mcp")

    host, port, path, security = mcp_http_server._http_settings()

    assert (host, port, path) == ("127.0.0.1", 8123, "/public-mcp")
    assert security.allowed_hosts == ["bookmarks.example.test"]
    assert security.allowed_origins == ["https://bookmarks.example.test"]


def test_http_settings_requires_public_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BOOKMARK_RAG_DOMAIN", raising=False)

    with pytest.raises(RuntimeError, match="BOOKMARK_RAG_DOMAIN is required"):
        mcp_http_server._http_settings()


def test_http_settings_binds_all_interfaces_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOOKMARK_RAG_DOMAIN", "bookmarks.example.test")
    monkeypatch.setenv("PROD", "true")
    monkeypatch.delenv("MCP_HTTP_HOST", raising=False)

    host, *_ = mcp_http_server._http_settings()

    assert host == "0.0.0.0"