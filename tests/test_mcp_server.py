import json
from pathlib import Path

from services import bookmark_store
import mcp_server


def test_server_publishes_only_read_only_bookmark_tools() -> None:
    assert mcp_server.list_bookmarks.__name__ == "list_bookmarks"
    assert mcp_server.search_documents.__name__ == "search_documents"


def test_search_tool_returns_validation_errors_as_data() -> None:
    result = mcp_server.search_documents("")
    assert result == {"error": "query must not be empty"}


def test_tools_read_startup_metadata_catalog(tmp_path: Path, monkeypatch) -> None:
    input_dir = tmp_path / "data" / "alpha" / "input"
    input_dir.mkdir(parents=True)
    (input_dir / "page.json").write_text(
        json.dumps({"url": "https://example.test/page", "title": "Example"}),
        encoding="utf-8",
    )
    (input_dir / "page.md").write_text("needle", encoding="utf-8")
    monkeypatch.setattr(bookmark_store, "BASE_DIR", tmp_path)
    monkeypatch.setattr(bookmark_store, "DATA_DIR", tmp_path / "data")
    bookmark_store.initialize_catalog()

    assert mcp_server.list_bookmarks("alpha")["bookmarks"][0]["url"] == "https://example.test/page"
    assert mcp_server.search_documents("needle", notebook="alpha")["matches"][0]["bookmark_urls"] == [
        "https://example.test/page"
    ]