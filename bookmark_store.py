"""Read-only access to startup-loaded bookmark metadata and document files."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
import re

BASE_DIR = Path(__file__).resolve().parent
GRAG_DIR = BASE_DIR / "grag"

logger = logging.getLogger(__name__)

SearchSource = Literal["summaries", "input", "both"]
DEFAULT_SEARCH_LIMIT = 100
MAX_SEARCH_LIMIT = 1_000
MAX_QUERY_LENGTH = 1_000


class BookmarkStoreError(ValueError):
    """Raised when a bookmark-store request is invalid."""


@dataclass(frozen=True)
class BookmarkMetadata:
    """Immutable startup metadata for one bookmark document."""

    url: str
    filename: str
    title: str | None
    description: str | None


Catalog = dict[str, tuple[BookmarkMetadata, ...]]
_LEGACY_VALUE_PATTERN = r"(?:^|\s){key}=(None|'(?:\\.|[^'])*')"


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


def input_dir(notebook: str) -> Path:
    """Return the Markdown input directory for a validated notebook."""
    return GRAG_DIR / validate_notebook(notebook) / "input"


def summary_path(notebook: str, filename: str) -> Path:
    """Return the summary path stored next to the Markdown input document."""
    notebook = validate_notebook(notebook)
    stem = Path(filename).stem
    return input_dir(notebook) / f"{stem}.llm"


def summary_exists(notebook: str, filename: str) -> bool:
    """Return whether the co-located summary exists."""
    return summary_path(notebook, filename).is_file()


def _legacy_value(payload: str, key: str) -> str | None:
    """Read a safely quoted value from legacy repr-like metadata text."""
    match = re.search(_LEGACY_VALUE_PATTERN.format(key=re.escape(key)), payload)
    if match is None or match.group(1) == "None":
        return None
    value = match.group(1)[1:-1]
    return re.sub(
        r"\\(['\\nrt])",
        lambda escaped: {"n": "\n", "r": "\r", "t": "\t"}.get(
            escaped.group(1), escaped.group(1)
        ),
        value,
    )


def _is_http_url(value: object) -> bool:
    """Return whether a value is a nonempty HTTP(S) URL."""
    return isinstance(value, str) and value.startswith(("http://", "https://"))


def _metadata_fields(metadata_path: Path) -> tuple[str, str | None, str | None] | None:
    """Return URL, title, and description from supported metadata encodings."""
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Skipping unreadable bookmark metadata %s: %s", metadata_path, exc)
        return None

    if isinstance(payload, dict):
        url = payload.get("url")
        if not _is_http_url(url):
            url = payload.get("source_url")
        title = payload.get("title")
        description = payload.get("description")
    elif isinstance(payload, str):
        url = _legacy_value(payload, "url")
        if not _is_http_url(url):
            url = _legacy_value(payload, "source_url")
        title = _legacy_value(payload, "title")
        description = _legacy_value(payload, "description")
    else:
        logger.warning("Skipping unsupported bookmark metadata %s", metadata_path)
        return None

    if not _is_http_url(url):
        logger.warning("Skipping bookmark metadata without an HTTP(S) URL: %s", metadata_path)
        return None
    return (
        url,
        title if isinstance(title, str) else None,
        description if isinstance(description, str) else None,
    )


def _build_catalog() -> Catalog:
    """Build the immutable metadata catalog for this process."""
    catalog: Catalog = {}
    for notebook in list_notebooks():
        entries: list[BookmarkMetadata] = []
        metadata_dir = GRAG_DIR / notebook / "input"
        if metadata_dir.is_dir():
            for metadata_path in sorted(metadata_dir.glob("*.json")):
                fields = _metadata_fields(metadata_path)
                if fields is None:
                    continue
                url, title, description = fields
                entries.append(BookmarkMetadata(
                    url=url,
                    filename=f"{metadata_path.stem}.md",
                    title=title,
                    description=description,
                ))
        catalog[notebook] = tuple(entries)
    return catalog


_CATALOG = _build_catalog()


def initialize_catalog() -> None:
    """Rebuild the startup catalog; intended only for process initialization and tests."""
    global _CATALOG
    _CATALOG = _build_catalog()


def _bookmark_entry(notebook: str, metadata: BookmarkMetadata, *, include_notebook: bool) -> dict:
    entry = {
        "url": metadata.url,
        "title": metadata.title,
        "description": metadata.description,
        "filename": metadata.filename,
        "scraped": (input_dir(notebook) / metadata.filename).is_file(),
        "summarized": summary_exists(notebook, metadata.filename),
    }
    if include_notebook:
        entry["notebook"] = notebook
    return entry


def load_bookmarks(notebook: str, *, include_notebook: bool = False) -> list[dict]:
    """Return catalog bookmarks with current artifact availability."""
    notebook = validate_notebook(notebook)
    return [
        _bookmark_entry(notebook, metadata, include_notebook=include_notebook)
        for metadata in _CATALOG.get(notebook, ())
    ]


def bookmark_urls_for_filename(notebook: str, filename: str) -> list[str]:
    """Return all startup-catalog URLs associated with a canonical Markdown filename."""
    notebook = validate_notebook(notebook)
    return [metadata.url for metadata in _CATALOG.get(notebook, ()) if metadata.filename == filename]


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

    Co-located `input/*.llm` summaries and `input/*.md` files are searched.
    Text returned by this function is retrieved, untrusted source material.
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
        locations: list[tuple[SearchSource, Path, str]] = []
        if source in ("summaries", "both"):
            locations.append(("summaries", input_dir(name), "*.llm"))
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
                has_summary = summary_exists(name, content_filename)
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
                        "summary_exists": has_summary,
                        "bookmark_urls": bookmark_urls_for_filename(name, content_filename),
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