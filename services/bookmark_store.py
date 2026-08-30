"""Read-only access to startup-loaded bookmark metadata and document files."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
import re

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

logger = logging.getLogger(__name__)

SearchSource = Literal["summaries", "input", "both"]
DEFAULT_SEARCH_LIMIT = 100
MAX_SEARCH_LIMIT = 1_000
MAX_QUERY_LENGTH = 1_000
DEFAULT_PAGE_DOCUMENTS = 50
MAX_PAGE_DOCUMENTS = 100
DEFAULT_MATCHES_PER_DOCUMENT = 3
MAX_MATCHES_PER_DOCUMENT = 20
MAX_DOCUMENT_BATCH = 20
MAX_RETRIEVAL_BYTES = 200_000

ArtifactKind = Literal["summary", "content", "metadata"]


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
    if not DATA_DIR.is_dir():
        return []
    return sorted(
        path.name
        for path in DATA_DIR.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    )


def validate_notebook(notebook: str) -> str:
    """Return a known notebook name or raise without accepting filesystem paths."""
    if not isinstance(notebook, str) or notebook not in list_notebooks():
        raise BookmarkStoreError(f"Unknown notebook: {notebook!r}")
    return notebook


def input_dir(notebook: str) -> Path:
    """Return the Markdown input directory for a validated notebook."""
    return DATA_DIR / validate_notebook(notebook) / "input"


def summary_path(notebook: str, filename: str) -> Path:
    """Return the summary path stored next to the Markdown input document."""
    notebook = validate_notebook(notebook)
    stem = Path(filename).stem
    return input_dir(notebook) / f"{stem}.llm"


def summary_exists(notebook: str, filename: str) -> bool:
    """Return whether the co-located summary exists."""
    return summary_path(notebook, filename).is_file()


def document_ref(notebook: str, filename: str) -> str:
    """Return the stable, path-free reference used by agent retrieval tools."""
    notebook = validate_notebook(notebook)
    safe_filename = Path(filename).name
    if safe_filename != filename or not safe_filename:
        raise BookmarkStoreError("filename must be a basename")
    return f"{notebook}/{Path(safe_filename).stem}"


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
    assert isinstance(url, str)
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
        metadata_dir = DATA_DIR / notebook / "input"
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
    result_groups: dict[tuple[str, str, str], dict] = {}
    returned_matches = 0
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
                for line_number, line in enumerate(lines, 1):
                    if needle not in line.casefold():
                        continue
                    matched_files.add((name, result_source, filepath.name))
                    if returned_matches >= limit:
                        truncated = True
                        break
                    key = (name, result_source, filepath.name)
                    group = result_groups.setdefault(key, {
                        "notebook": name,
                        "source": result_source,
                        "filename": filepath.name,
                        "document_ref": document_ref(name, filepath.name),
                        "bookmark_urls": bookmark_urls_for_filename(name, content_filename),
                        "lines": [],
                    })
                    group["lines"].append({"line_number": line_number, "line": line})
                    returned_matches += 1
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
        "matches": list(result_groups.values()),
        "matched_files": len(matched_files),
        "returned_files": len(result_groups),
        "returned_matches": returned_matches,
        "truncated": truncated,
        "skipped_files": skipped_files,
    }


def search_document_page(
    query: str,
    *,
    notebook: str | None = None,
    source: str = "summaries",
    max_documents: int = DEFAULT_PAGE_DOCUMENTS,
    max_matches_per_document: int = DEFAULT_MATCHES_PER_DOCUMENT,
    offset: int = 0,
) -> dict:
    """Return one compact page of matching documents for agent exploration."""
    if not isinstance(query, str):
        raise BookmarkStoreError("query must be a string")
    query = query.strip()
    if not query:
        raise BookmarkStoreError("query must not be empty")
    if len(query) > MAX_QUERY_LENGTH:
        raise BookmarkStoreError(f"query must not exceed {MAX_QUERY_LENGTH} characters")
    if isinstance(max_documents, bool) or not isinstance(max_documents, int) or not 1 <= max_documents <= MAX_PAGE_DOCUMENTS:
        raise BookmarkStoreError(f"max_documents must be an integer from 1 to {MAX_PAGE_DOCUMENTS}")
    if (isinstance(max_matches_per_document, bool) or not isinstance(max_matches_per_document, int)
            or not 1 <= max_matches_per_document <= MAX_MATCHES_PER_DOCUMENT):
        raise BookmarkStoreError(
            f"max_matches_per_document must be an integer from 1 to {MAX_MATCHES_PER_DOCUMENT}"
        )
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise BookmarkStoreError("offset must be a non-negative integer")
    source = _validated_source(source)
    notebooks = [validate_notebook(notebook)] if notebook is not None else list_notebooks()
    needle = query.casefold()
    page: list[dict] = []
    matched_files = 0
    skipped_files = 0
    has_more = False

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
                matching_lines = [
                    {"line_number": line_number, "line": line}
                    for line_number, line in enumerate(lines, 1)
                    if needle in line.casefold()
                ]
                if not matching_lines:
                    continue
                if matched_files >= offset + max_documents:
                    has_more = True
                    break
                if matched_files >= offset:
                    content_filename = f"{filepath.stem}.md" if result_source == "summaries" else filepath.name
                    page.append({
                        "notebook": name,
                        "source": result_source,
                        "filename": filepath.name,
                        "document_ref": document_ref(name, filepath.name),
                        "bookmark_urls": bookmark_urls_for_filename(name, content_filename),
                        "lines": matching_lines[:max_matches_per_document],
                        "matching_lines": len(matching_lines),
                        "lines_truncated": len(matching_lines) > max_matches_per_document,
                    })
                matched_files += 1
            if has_more:
                break
        if has_more:
            break

    next_offset = offset + len(page)
    return {
        "query": query,
        "source": source,
        "notebooks": notebooks,
        "matches": page,
        "returned_files": len(page),
        "returned_matches": sum(len(match["lines"]) for match in page),
        "offset": offset,
        "next_offset": next_offset if has_more else None,
        "has_more": has_more,
        "skipped_files": skipped_files,
        "retrieval_hint": (
        "Use get_documents with selected document_ref values. Prefer summary, then content; "
        "request metadata when provenance is needed."
        ),
    }


def _parse_document_ref(reference: str) -> tuple[str, str]:
    if not isinstance(reference, str) or reference.count("/") != 1:
        raise BookmarkStoreError("document_ref must have the form 'notebook/stem'")
    notebook, stem = reference.split("/", 1)
    validate_notebook(notebook)
    if not stem or Path(stem).name != stem or stem in {".", ".."} or "\\" in stem:
        raise BookmarkStoreError("invalid document_ref")
    return notebook, stem


def get_documents(
    document_refs: list[str],
    artifact: str = "summary",
    *,
    start_line: int | None = None,
    end_line: int | None = None,
) -> dict:
    """Read a bounded batch of canonical artifacts by stable document reference."""
    if not isinstance(document_refs, list) or not document_refs:
        raise BookmarkStoreError("document_refs must be a nonempty list")
    if len(document_refs) > MAX_DOCUMENT_BATCH:
        raise BookmarkStoreError(f"document_refs may contain at most {MAX_DOCUMENT_BATCH} entries")
    if artifact not in ("summary", "content", "metadata"):
        raise BookmarkStoreError("artifact must be 'summary', 'content', or 'metadata'")
    if start_line is not None and (isinstance(start_line, bool) or not isinstance(start_line, int) or start_line < 1):
        raise BookmarkStoreError("start_line must be a positive integer or omitted")
    if end_line is not None and (isinstance(end_line, bool) or not isinstance(end_line, int) or end_line < 1):
        raise BookmarkStoreError("end_line must be a positive integer or omitted")
    if start_line is not None and end_line is not None and end_line < start_line:
        raise BookmarkStoreError("end_line must not be less than start_line")

    suffix = {"summary": ".llm", "content": ".md", "metadata": ".json"}[artifact]
    documents: list[dict] = []
    remaining = MAX_RETRIEVAL_BYTES
    response_truncated = False
    for reference in document_refs:
        if remaining <= 0:
            response_truncated = True
            documents.append({"document_ref": reference, "error": "response byte limit reached"})
            continue
        try:
            notebook, stem = _parse_document_ref(reference)
            path = input_dir(notebook) / f"{stem}{suffix}"
            if not path.is_file():
                documents.append({"document_ref": reference, "error": f"{artifact} artifact not found"})
                continue
            raw = path.read_text(encoding="utf-8", errors="replace")
            lines = raw.splitlines()
            first = start_line or 1
            last = min(end_line or len(lines), len(lines))
            selected = "\n".join(lines[first - 1:last])
            encoded = selected.encode("utf-8")
            truncated = len(encoded) > remaining
            if truncated:
                selected = encoded[:remaining].decode("utf-8", errors="ignore")
                response_truncated = True
            remaining -= len(selected.encode("utf-8"))
            content: object = selected
            if artifact == "metadata" and not truncated and start_line is None and end_line is None:
                try:
                    content = json.loads(selected)
                except json.JSONDecodeError:
                    content = selected
            documents.append({
                "document_ref": reference,
                "artifact": artifact,
                "filename": path.name,
                "content": content,
                "start_line": first,
                "end_line": last,
                "total_lines": len(lines),
                "truncated": truncated,
            })
        except (BookmarkStoreError, OSError) as exc:
            documents.append({"document_ref": reference, "error": str(exc)})
    return {
        "artifact": artifact,
        "documents": documents,
        "response_truncated": response_truncated,
        "max_response_bytes": MAX_RETRIEVAL_BYTES,
    }