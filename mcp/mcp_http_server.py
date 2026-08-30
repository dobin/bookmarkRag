"""Public, read-only BookmarkRag MCP server using streamable HTTP."""

import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

from bookmark_mcp_tools import MCP_INSTRUCTIONS, register_tools


def _public_host(domain: str) -> str:
    """Return the configured public Host header value."""
    value = domain.strip().rstrip("/")
    if not value:
        raise RuntimeError("BOOKMARK_RAG_DOMAIN is required for the public MCP server")
    return urlsplit(value if "://" in value else f"https://{value}").netloc


def _http_settings() -> tuple[str, int, str, TransportSecuritySettings]:
    """Read hosted-MCP settings and enforce the configured public host."""
    host = os.environ.get("MCP_HTTP_HOST", "127.0.0.1")
    path = os.environ.get("MCP_HTTP_PATH", "/mcp")
    if not path.startswith("/"):
        raise RuntimeError("MCP_HTTP_PATH must start with '/'")
    try:
        port = int(os.environ.get("MCP_HTTP_PORT", "8000"))
    except ValueError as exc:
        raise RuntimeError("MCP_HTTP_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise RuntimeError("MCP_HTTP_PORT must be from 1 to 65535")
    public_host = _public_host(os.environ.get("BOOKMARK_RAG_DOMAIN", ""))
    return host, port, path, TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[public_host],
        allowed_origins=[f"https://{public_host}"],
    )


mcp = MCPServer("bookmark-rag", instructions=MCP_INSTRUCTIONS)
register_tools(mcp)


if __name__ == "__main__":
    host, port, path, transport_security = _http_settings()
    mcp.run(
        transport="streamable-http",
        host=host,
        port=port,
        streamable_http_path=path,
        stateless_http=True,
        transport_security=transport_security,
    )