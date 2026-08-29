"""Read-only access to BookmarkRag bookmark manifests and document files."""

from __future__ import annotations

from pathlib import Path
from typing import Literal
import re

BASE_DIR = Path(__file__).resolve().parent
GRAG_DIR = BASE_DIR / "grag"
BOOKMARKS_DIR = BASE_DIR / "bookmarks"

SearchSource = Literal["summaries", "input", "both"]
DEFAULT_SEARCH_LIMIT = 100
MAX_SEARCH_LIMIT = 1_000
MAX_QUERY_LENGTH = 1_000


class BookmarkStoreError(ValueError):
    """Raised when a bookmark-store request is invalid."""


def url_to_filename(url: str) -> str:
    """Convert a bookmark URL to its canonical artifact filename stem."""
    filename = url.lower()
    filename = re.sub(r"^https?://", "", filename)
    filename = re.sub(r"^www\.", "", filename)
    filename = re.sub(r"[^\w\-.]", "_", filename)
    filename = re.sub(r"_+", "_", filename)
    return filename.strip("_")[:144]


def list_notebooks() -> list[str]:
    """Return supported notebook names in deterministic order."""
    if not GRAG_DIR.is_dir():
        return []
    return sorted(
        path.name
        for path in GRAG_DIR.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    )


def validate_notebook(notebook: str) -> str:
    """Return a known notebook name or raise without accepting filesystem paths."""
    if not isinstance(notebook, str) or notebook not in list_notebooks():
        raise BookmarkStoreError(f"Unknown notebook: {notebook!r}")
    return notebook


def bookmarks_file(notebook: str) -> Path:
    """Return the bookmark manifest path for a validated notebook."""
    return BOOKMARKS_DIR / f"{validate_notebook(notebook)}.txt"


def input_dir(notebook: str) -> Path:
    """Return the Markdown input directory for a validated notebook."""
    return GRAG_DIR / validate_notebook(notebook) / "input"


def summaries_dir(notebook: str) -> Path:
    """Return the canonical summary directory for a validated notebook."""
    return GRAG_DIR / validate_notebook(notebook) / "summaries"


def load_bookmarks(notebook: str, *, include_notebook: bool = False) -> list[dict]:
    """Load manifest URLs with their derived artifact availability."""
    notebook = validate_notebook(notebook)
    manifest = bookmarks_file(notebook)
    if not manifest.is_file():
        return []

    entries: list[dict] = []
    seen: set[str] = set()
    try:
        lines = manifest.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

    markdown_dir = input_dir(notebook)
    summary_dir = summaries_dir(notebook)
    for line in lines:
        url = line.strip()
        if not url or url in seen:
            continue
        seen.add(url)
        base = url_to_filename(url)
        entry = {
            "url": url,
            "filename": f"{base}.md",
            "scraped": (markdown_dir / f"{base}.md").is_file(),
            "summarized": (summary_dir / f"{base}.llm").is_file(),
        }
        if include_notebook:
            entry["notebook"] = notebook
        entries.append(entry)
    return entries


def list_bookmarks(notebook: str | None = None) -> dict:
    """List bookmarks for one notebook or all discovered notebooks."""
    notebooks = [validate_notebook(notebook)] if notebook is not None else list_notebooks()
    entries = [
        entry
        for name in notebooks
        for entry in load_bookmarks(name, include_notebook=True)
    ]
    return {
        "notebooks": notebooks,
        "bookmarks": entries,
        "count": len(entries),
    }


def _validated_source(source: str) -> SearchSource:
    if source not in ("summaries", "input", "both"):
        raise BookmarkStoreError("source must be 'summaries', 'input', or 'both'")
    return source  # type: ignore[return-value]


def _validated_limit(limit: int) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_SEARCH_LIMIT:
        raise BookmarkStoreError(f"limit must be an integer from 1 to {MAX_SEARCH_LIMIT}")
    return limit


def search_documents(
    query: str,
    *,
    notebook: str | None = None,
    source: str = "both",
    limit: int = DEFAULT_SEARCH_LIMIT,
) -> dict:
    """Return literal case-insensitive line matches from Markdown and summaries.

    Only canonical `input/*.md` and `summaries/*.llm` files are searched. Text
    returned by this function is retrieved, untrusted source material.
    """
    if not isinstance(query, str):
        raise BookmarkStoreError("query must be a string")
    query = query.strip()
    if not query:
        raise BookmarkStoreError("query must not be empty")
    if len(query) > MAX_QUERY_LENGTH:
        raise BookmarkStoreError(f"query must not exceed {MAX_QUERY_LENGTH} characters")

    source = _validated_source(source)
    limit = _validated_limit(limit)
    notebooks = [validate_notebook(notebook)] if notebook is not None else list_notebooks()
    needle = query.casefold()
    results: list[dict] = []
    matched_files: set[tuple[str, str, str]] = set()
    skipped_files = 0
    truncated = False

    for name in notebooks:
        urls_by_filename: dict[str, list[str]] = {}
        for entry in load_bookmarks(name):
            urls_by_filename.setdefault(entry["filename"], []).append(entry["url"])

        locations: list[tuple[SearchSource, Path, str]] = []
        if source in ("summaries", "both"):
            locations.append(("summaries", summaries_dir(name), "*.llm"))
        if source in ("input", "both"):
            locations.append(("input", input_dir(name), "*.md"))

        for result_source, directory, pattern in locations:
            if not directory.is_dir():
                continue
            for filepath in sorted(directory.glob(pattern)):
                try:
                    lines = filepath.read_text(encoding="utf-8", errors="replace").splitlines()
                except OSError:
                    skipped_files += 1
                    continue

                content_filename = f"{filepath.stem}.md" if result_source == "summaries" else filepath.name
                content_exists = (input_dir(name) / content_filename).is_file()
                summary_exists = (summaries_dir(name) / f"{Path(content_filename).stem}.llm").is_file()
                for line_number, line in enumerate(lines, 1):
                    if needle not in line.casefold():
                        continue
                    matched_files.add((name, result_source, filepath.name))
                    if len(results) >= limit:
                        truncated = True
                        break
                    results.append({
                        "notebook": name,
                        "source": result_source,
                        "filename": filepath.name,
                        "line_number": line_number,
                        "line": line,
                        "content_exists": content_exists,
                        "summary_exists": summary_exists,
                        "bookmark_urls": urls_by_filename.get(content_filename, []),
                    })
                if truncated:
                    break
            if truncated:
                break
        if truncated:
            break

    return {
        "query": query,
        "source": source,
        "notebooks": notebooks,
        "matches": results,
        "matched_files": len(matched_files),
        "returned_matches": len(results),
        "truncated": truncated,
        "skipped_files": skipped_files,
    }