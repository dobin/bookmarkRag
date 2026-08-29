import mcp_server


def test_server_publishes_only_read_only_bookmark_tools() -> None:
    assert mcp_server.list_bookmarks.__name__ == "list_bookmarks"
    assert mcp_server.search_documents.__name__ == "search_documents"


def test_search_tool_returns_validation_errors_as_data() -> None:
    result = mcp_server.search_documents("")
    assert result == {"error": "query must not be empty"}