import json
from pathlib import Path

import pytest

from services import bookmark_store


@pytest.fixture
def store_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "data" / "alpha" / "input").mkdir(parents=True)
    (tmp_path / "data" / "empty").mkdir(parents=True)
    monkeypatch.setattr(bookmark_store, "BASE_DIR", tmp_path)
    monkeypatch.setattr(bookmark_store, "DATA_DIR", tmp_path / "data")
    return tmp_path


def _write_metadata(directory: Path, filename: str, data: object) -> None:
    (directory / filename).write_text(json.dumps(data), encoding="utf-8")


def test_catalog_lists_legacy_metadata_and_live_artifacts(store_root: Path) -> None:
    input_dir = store_root / "data" / "alpha" / "input"
    _write_metadata(
        input_dir,
        "page.html.json",
        "title='Example title' description='Example description' "
        "url='https://example.test/page' source_url='https://other.test/page'",
    )
    (input_dir / "page.html.md").write_text("source", encoding="utf-8")
    (input_dir / "page.html.llm").write_text("summary", encoding="utf-8")
    bookmark_store.initialize_catalog()

    result = bookmark_store.list_bookmarks()

    assert result["notebooks"] == ["alpha", "empty"]
    assert result["count"] == 1
    assert result["bookmarks"] == [{
        "notebook": "alpha", "url": "https://example.test/page",
        "title": "Example title", "description": "Example description",
        "filename": "page.html.md", "scraped": True, "summarized": True,
    }]


def test_catalog_recognizes_co_located_summary(store_root: Path) -> None:
    input_dir = store_root / "data" / "alpha" / "input"
    _write_metadata(input_dir, "page.json", {"url": "https://example.test/page"})
    (input_dir / "page.md").write_text("source", encoding="utf-8")
    (input_dir / "page.llm").write_text("summary needle", encoding="utf-8")
    bookmark_store.initialize_catalog()

    assert bookmark_store.load_bookmarks("alpha")[0]["summarized"] is True
    assert bookmark_store.summary_path("alpha", "page.md") == input_dir / "page.llm"
    result = bookmark_store.search_documents("needle", notebook="alpha", source="summaries")
    assert result["matches"][0]["filename"] == "page.llm"
    assert result["matches"][0]["summary_exists"] is True


def test_catalog_supports_json_objects_duplicates_and_snapshot_behavior(store_root: Path) -> None:
    input_dir = store_root / "data" / "alpha" / "input"
    _write_metadata(input_dir, "a.json", {"url": "https://example.test/a", "title": "A"})
    _write_metadata(input_dir, "b.json", {"url": "https://example.test/a", "title": "B"})
    bookmark_store.initialize_catalog()
    _write_metadata(input_dir, "later.json", {"url": "https://example.test/later"})

    assert [entry["filename"] for entry in bookmark_store.load_bookmarks("alpha")] == ["a.md", "b.md"]
    assert "https://example.test/later" not in [entry["url"] for entry in bookmark_store.load_bookmarks("alpha")]
    (input_dir / "a.md").write_text("source", encoding="utf-8")
    assert bookmark_store.load_bookmarks("alpha")[0]["scraped"] is True


def test_catalog_skips_invalid_metadata_and_falls_back_to_source_url(store_root: Path) -> None:
    input_dir = store_root / "data" / "alpha" / "input"
    _write_metadata(input_dir, "fallback.json", {
        "url": "mailto:invalid@example.test", "source_url": "https://example.test/fallback",
    })
    _write_metadata(input_dir, "missing.json", {"title": "No URL"})
    (input_dir / "broken.json").write_text("not json", encoding="utf-8")
    bookmark_store.initialize_catalog()

    assert bookmark_store.load_bookmarks("alpha") == [{
        "url": "https://example.test/fallback", "title": None, "description": None,
        "filename": "fallback.md", "scraped": False, "summarized": False,
    }]


def test_searches_both_sources_literally(store_root: Path) -> None:
    input_dir = store_root / "data" / "alpha" / "input"
    _write_metadata(input_dir, "example.test_a.json", {"url": "https://example.test/a"})
    (input_dir / "example.test_a.md").write_text("A [special] match\n", encoding="utf-8")
    (input_dir / "example.test_a.llm").write_text("special SUMMARY\n", encoding="utf-8")
    bookmark_store.initialize_catalog()

    result = bookmark_store.search_documents("[SPECIAL]", source="both")

    assert result["returned_matches"] == 1
    assert result["returned_files"] == 1
    assert result["matches"][0]["source"] == "input"
    assert result["matches"][0]["lines"] == [{"line_number": 1, "line": "A [special] match"}]
    assert result["matches"][0]["bookmark_urls"] == ["https://example.test/a"]


def test_search_limit_and_invalid_notebook(store_root: Path) -> None:
    document = store_root / "data" / "alpha" / "input" / "orphan.md"
    document.write_text("needle\nneedle\n", encoding="utf-8")
    bookmark_store.initialize_catalog()

    result = bookmark_store.search_documents("needle", notebook="alpha", source="input", limit=1)

    assert result["truncated"] is True
    assert result["returned_matches"] == 1
    assert result["returned_files"] == 1
    assert result["matches"][0]["lines"] == [{"line_number": 1, "line": "needle"}]
    with pytest.raises(bookmark_store.BookmarkStoreError):
        bookmark_store.list_bookmarks("../alpha")


def test_search_groups_all_matching_lines_by_file(store_root: Path) -> None:
    input_dir = store_root / "data" / "alpha" / "input"
    _write_metadata(input_dir, "page.json", {"url": "https://example.test/page"})
    (input_dir / "page.md").write_text("needle one\nnot a match\nneedle two\n", encoding="utf-8")
    bookmark_store.initialize_catalog()

    result = bookmark_store.search_documents("needle", notebook="alpha", source="input")

    assert result["matched_files"] == 1
    assert result["returned_files"] == 1
    assert result["returned_matches"] == 2
    assert len(result["matches"]) == 1
    assert result["matches"][0]["lines"] == [
        {"line_number": 1, "line": "needle one"},
        {"line_number": 3, "line": "needle two"},
    ]