from pathlib import Path

import pytest

import bookmark_store


@pytest.fixture
def store_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "grag" / "alpha" / "input").mkdir(parents=True)
    (tmp_path / "grag" / "alpha" / "summaries").mkdir(parents=True)
    (tmp_path / "grag" / "empty").mkdir(parents=True)
    (tmp_path / "bookmarks").mkdir()
    monkeypatch.setattr(bookmark_store, "BASE_DIR", tmp_path)
    monkeypatch.setattr(bookmark_store, "GRAG_DIR", tmp_path / "grag")
    monkeypatch.setattr(bookmark_store, "BOOKMARKS_DIR", tmp_path / "bookmarks")
    return tmp_path


def test_list_bookmarks_deduplicates_and_reports_artifacts(store_root: Path) -> None:
    url = "https://example.test/page"
    (store_root / "bookmarks" / "alpha.txt").write_text(f"\n{url}\n{url}\n", encoding="utf-8")
    (store_root / "grag" / "alpha" / "input" / "example.test_page.md").write_text("source", encoding="utf-8")
    (store_root / "grag" / "alpha" / "summaries" / "example.test_page.llm").write_text("summary", encoding="utf-8")

    result = bookmark_store.list_bookmarks()

    assert result["notebooks"] == ["alpha", "empty"]
    assert result["count"] == 1
    assert result["bookmarks"] == [{
        "notebook": "alpha", "url": url, "filename": "example.test_page.md",
        "scraped": True, "summarized": True,
    }]


def test_searches_both_sources_literally_and_tracks_collisions(store_root: Path) -> None:
    first_url = "https://example.test/a"
    second_url = "http://example.test/a"
    (store_root / "bookmarks" / "alpha.txt").write_text(f"{first_url}\n{second_url}\n", encoding="utf-8")
    (store_root / "grag" / "alpha" / "input" / "example.test_a.md").write_text("A [special] match\n", encoding="utf-8")
    (store_root / "grag" / "alpha" / "summaries" / "example.test_a.llm").write_text("special SUMMARY\n", encoding="utf-8")

    result = bookmark_store.search_documents("[SPECIAL]", source="both")

    assert result["returned_matches"] == 1
    assert result["matches"][0]["source"] == "input"
    assert result["matches"][0]["line"] == "A [special] match"
    assert result["matches"][0]["bookmark_urls"] == [first_url, second_url]


def test_search_limit_and_invalid_notebook(store_root: Path) -> None:
    document = store_root / "grag" / "alpha" / "input" / "orphan.md"
    document.write_text("needle\nneedle\n", encoding="utf-8")

    result = bookmark_store.search_documents("needle", notebook="alpha", source="input", limit=1)

    assert result["truncated"] is True
    assert result["returned_matches"] == 1
    with pytest.raises(bookmark_store.BookmarkStoreError):
        bookmark_store.list_bookmarks("../alpha")