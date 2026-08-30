import json
import importlib.util
from pathlib import Path

from services import bookmark_store

_MCP_SERVER_PATH = Path(__file__).resolve().parents[1] / "mcp" / "mcp_server.py"
_SPEC = importlib.util.spec_from_file_location("bookmark_rag_mcp_server", _MCP_SERVER_PATH)
assert _SPEC is not None and _SPEC.loader is not None
mcp_server = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mcp_server)


def test_server_publishes_only_read_only_bookmark_tools() -> None:
    assert mcp_server.list_bookmarks.__name__ == "list_bookmarks"
    assert mcp_server.search_documents.__name__ == "search_documents"
    assert mcp_server.get_documents.__name__ == "get_documents"


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
    assert mcp_server.search_documents("needle", notebook="alpha", source="input")["matches"][0]["bookmark_urls"] == [
        "https://example.test/page"
    ]


def test_search_references_support_follow_up_artifact_reads(tmp_path: Path, monkeypatch) -> None:
    input_dir = tmp_path / "data" / "alpha" / "input"
    input_dir.mkdir(parents=True)
    (input_dir / "page.json").write_text(
        json.dumps({"url": "https://example.test/page", "title": "Example"}),
        encoding="utf-8",
    )
    (input_dir / "page.md").write_text("content line one\ncontent line two", encoding="utf-8")
    (input_dir / "page.llm").write_text("summary needle", encoding="utf-8")
    monkeypatch.setattr(bookmark_store, "DATA_DIR", tmp_path / "data")
    bookmark_store.initialize_catalog()

    match = mcp_server.search_documents("needle", notebook="alpha")["matches"][0]

    assert match["document_ref"] == "alpha/page"
    assert "available_artifacts" not in match
    assert "content_exists" not in match
    assert "summary_exists" not in match
    summary = mcp_server.get_documents([match["document_ref"]])
    assert summary["documents"][0]["content"] == "summary needle"
    metadata = mcp_server.get_documents([match["document_ref"]], artifact="metadata")
    assert metadata["documents"][0]["content"]["title"] == "Example"
    content = mcp_server.get_documents(
        [match["document_ref"]], artifact="content", start_line=2, end_line=2
    )
    assert content["documents"][0]["content"] == "content line two"


def test_search_pages_documents_and_caps_excerpts(tmp_path: Path, monkeypatch) -> None:
    input_dir = tmp_path / "data" / "alpha" / "input"
    input_dir.mkdir(parents=True)
    for stem in ("a", "b", "c"):
        (input_dir / f"{stem}.llm").write_text("needle one\nneedle two", encoding="utf-8")
    monkeypatch.setattr(bookmark_store, "DATA_DIR", tmp_path / "data")
    bookmark_store.initialize_catalog()

    first = mcp_server.search_documents(
        "needle", notebook="alpha", max_documents=2, max_matches_per_document=1
    )
    second = mcp_server.search_documents(
        "needle", notebook="alpha", max_documents=2, max_matches_per_document=1,
        offset=first["next_offset"],
    )

    assert [match["document_ref"] for match in first["matches"]] == ["alpha/a", "alpha/b"]
    assert all(len(match["lines"]) == 1 for match in first["matches"])
    assert first["has_more"] is True
    assert [match["document_ref"] for match in second["matches"]] == ["alpha/c"]
    assert second["next_offset"] is None


def test_get_documents_rejects_paths_and_oversized_batches() -> None:
    assert "document_ref" in mcp_server.get_documents(["alpha/../secret"])["documents"][0]["error"]
    assert "at most 20" in mcp_server.get_documents(["alpha/page"] * 21)["error"]