# MCP server reference

The local MCP integration uses the official Python MCP SDK documentation:
https://py.sdk.modelcontextprotocol.io/

Keep `mcp_server.py` read-only and on the `stdio` transport. Its tools may
access only bookmark manifests and canonical Markdown/summary content through
`bookmark_store.py`; never expose credentials, arbitrary paths, write actions,
or GraphRAG API-backed queries.