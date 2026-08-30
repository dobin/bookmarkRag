"""Local stdio MCP server for read-only BookmarkRag access."""

import sys
from pathlib import Path

from mcp.server import MCPServer

# When launched as ``mcp/mcp_server.py``, Python adds ``mcp/`` rather than the
# repository root to sys.path. Make only this project's compatibility module
# importable; this does not grant access to caller-provided filesystem paths.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bookmark_mcp_tools import MCP_INSTRUCTIONS, get_documents, list_bookmarks, register_tools, search_documents

mcp = MCPServer(
    "bookmark-rag",
    instructions=MCP_INSTRUCTIONS,
)
register_tools(mcp)


if __name__ == "__main__":
    mcp.run(transport="stdio")