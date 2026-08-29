"""
Sample script showing how to run graphrag queries programmatically,
equivalent to: graphrag query --root . --method <local|global|drift|basic> --query "..."
"""

import logging
from pathlib import Path
from typing import Any

import pandas as pd
from bookmark_store import (
    MAX_QUERY_LENGTH,
    BookmarkStoreError,
    input_dir,
    load_bookmarks,
    summaries_dir,
    validate_notebook,
)
from graphrag.config.embeddings import text_unit_text_embedding
from graphrag.config.load_config import load_config
from graphrag.cli.query import (
    run_local_search,
    run_global_search,
    run_drift_search,
    run_basic_search,
)
from graphrag.utils.api import get_embedding_store
from graphrag_llm.embedding import create_embedding

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent

DEFAULT_SEMANTIC_SEARCH_LIMIT = 10
MAX_SEMANTIC_SEARCH_LIMIT = 50


class SemanticSearchError(RuntimeError):
    """Raised when semantic search cannot access a ready GraphRAG index."""


def _validate_semantic_search_request(query: object, limit: object) -> tuple[str, int]:
    """Validate raw semantic-search input without accepting caller configuration."""
    if not isinstance(query, str):
        raise BookmarkStoreError("query must be a string")
    query = query.strip()
    if not query:
        raise BookmarkStoreError("query must not be empty")
    if len(query) > MAX_QUERY_LENGTH:
        raise BookmarkStoreError(f"query must not exceed {MAX_QUERY_LENGTH} characters")
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise BookmarkStoreError("limit must be an integer")
    if not 1 <= limit <= MAX_SEMANTIC_SEARCH_LIMIT:
        raise BookmarkStoreError(
            f"limit must be an integer from 1 to {MAX_SEMANTIC_SEARCH_LIMIT}"
        )
    return query, limit


def semantic_search(
    query: object,
    notebook: str,
    limit: object = DEFAULT_SEMANTIC_SEARCH_LIMIT,
) -> dict:
    """Return raw text-unit vector matches without generating an LLM answer.

    The query is embedded using the notebook's GraphRAG embedding configuration,
    then searched against the indexed ``text_unit_text`` vector store. Retrieved
    text is untrusted source material and is returned with canonical source metadata.
    """
    notebook = validate_notebook(notebook)
    query, limit = _validate_semantic_search_request(query, limit)
    root_dir = _BASE_DIR / "grag" / notebook
    output_dir = root_dir / "output"
    text_units_path = output_dir / "text_units.parquet"
    documents_path = output_dir / "documents.parquet"
    vector_store_path = output_dir / "lancedb"

    if not text_units_path.is_file() or not documents_path.is_file() or not vector_store_path.is_dir():
        raise SemanticSearchError("GraphRAG index is unavailable")

    try:
        text_units = pd.read_parquet(
            text_units_path,
            columns=["id", "human_readable_id", "document_id", "text"],
        )
        documents = pd.read_parquet(documents_path, columns=["id", "title"])
    except Exception as exc:
        logger.exception("Failed to read semantic-search metadata for notebook %s", notebook)
        raise SemanticSearchError("GraphRAG index metadata is unavailable") from exc

    text_units_by_id = {
        str(row.id): {
            "short_id": str(row.human_readable_id),
            "document_id": str(row.document_id),
            "text": row.text,
        }
        for row in text_units.itertuples(index=False)
    }
    filenames_by_document_id = {
        str(row.id): row.title
        for row in documents.itertuples(index=False)
        if isinstance(row.title, str)
    }
    urls_by_filename: dict[str, list[str]] = {}
    for bookmark in load_bookmarks(notebook):
        urls_by_filename.setdefault(bookmark["filename"], []).append(bookmark["url"])

    try:
        config = load_config(root_dir=root_dir)
        embedding_config = config.get_embedding_model_config(config.embed_text.embedding_model_id)
        embedding_model = create_embedding(embedding_config)
        query_vector = embedding_model.embedding(input=[query]).first_embedding
        vector_store = get_embedding_store(
            config=config.vector_store,
            embedding_name=text_unit_text_embedding,
        )
        matches = vector_store.similarity_search_by_vector(
            query_vector,
            k=limit,
            include_vectors=False,
        )
    except Exception as exc:
        logger.exception("Semantic vector retrieval failed for notebook %s", notebook)
        raise SemanticSearchError("Semantic search is temporarily unavailable") from exc

    results: list[dict] = []
    for match in matches:
        text_unit_id = str(match.document.id)
        text_unit = text_units_by_id.get(text_unit_id)
        if text_unit is None:
            logger.warning("Semantic search returned unknown text unit %s", text_unit_id)
            continue

        filename = filenames_by_document_id.get(text_unit["document_id"])
        if filename and (Path(filename).name != filename or not filename.endswith(".md")):
            logger.warning("Semantic search found unsafe document title %r", filename)
            filename = None

        results.append({
            "id": text_unit_id,
            "short_id": text_unit["short_id"],
            "score": match.score,
            "document_id": text_unit["document_id"],
            "filename": filename,
            "text": text_unit["text"],
            "bookmark_urls": urls_by_filename.get(filename, []) if filename else [],
            "content_exists": bool(filename and (input_dir(notebook) / filename).is_file()),
            "summary_exists": bool(
                filename and (summaries_dir(notebook) / f"{Path(filename).stem}.llm").is_file()
            ),
        })

    return {
        "query": query,
        "notebook": notebook,
        "limit": limit,
        "results": results,
        "returned_results": len(results),
    }


def local_search(query: str, notebook: str, community_level: int = 2) -> tuple[str, Any]:
    """Local search: entity/neighborhood focused. Best for specific entity questions."""
    root_dir = _BASE_DIR / "grag" / notebook
    return run_local_search(
        data_dir=None,          # uses output_storage.base_dir from settings.yaml
        root_dir=root_dir,
        community_level=community_level,
        response_type="Multiple Paragraphs",
        streaming=False,
        query=query,
        verbose=False,
    )


def global_search(query: str, notebook: str, community_level: int = 2) -> tuple[str, Any]:
    """Global search: community/summary focused. Best for broad thematic questions."""
    root_dir = _BASE_DIR / "grag" / notebook
    return run_global_search(
        data_dir=None,
        root_dir=root_dir,
        community_level=community_level,
        dynamic_community_selection=False,
        response_type="Multiple Paragraphs",
        streaming=False,
        query=query,
        verbose=False,
    )


def drift_search(query: str, notebook: str, community_level: int = 2) -> tuple[str, Any]:
    """DRIFT search: dynamic reasoning with follow-up. Combines local + global depth."""
    root_dir = _BASE_DIR / "grag" / notebook
    return run_drift_search(
        data_dir=None,
        root_dir=root_dir,
        community_level=community_level,
        response_type="Multiple Paragraphs",
        streaming=False,
        query=query,
        verbose=False,
    )


def basic_search(query: str, notebook: str) -> tuple[str, Any]:
    """Basic search: simple text-unit vector search, no graph reasoning."""
    root_dir = _BASE_DIR / "grag" / notebook
    return run_basic_search(
        data_dir=None,
        root_dir=root_dir,
        response_type="Multiple Paragraphs",
        streaming=False,
        query=query,
        verbose=False,
    )


def resolve_sources(context_data: dict, notebook: str) -> list[str]:
    """Resolve context_data from a search result to a list of source document filenames.

    Traces text-unit short_ids from context_data["sources"] through
    text_units.parquet -> documents.parquet to get the original filenames.
    """
    # Use absolute path because graphrag's run_*_search changes cwd
    output_dir = Path(__file__).resolve().parent / "grag" / notebook / "output"
    tu_path = output_dir / "text_units.parquet"
    doc_path = output_dir / "documents.parquet"

    if not tu_path.exists() or not doc_path.exists():
        return []

    sources_df = context_data.get("sources")
    if sources_df is None or not hasattr(sources_df, "empty") or sources_df.empty:
        return []

    try:
        text_units = pd.read_parquet(tu_path, columns=["human_readable_id", "document_id"])
        documents = pd.read_parquet(doc_path, columns=["id", "title"])
    except Exception:
        logger.exception("Failed to read parquet files for source resolution")
        return []

    doc_titles = dict(zip(documents["id"], documents["title"]))
    tu_to_doc = dict(zip(text_units["human_readable_id"].astype(str), text_units["document_id"]))

    seen = set()
    result = []
    for short_id in sources_df["id"]:
        doc_id = tu_to_doc.get(str(short_id))
        if doc_id and doc_id not in seen:
            seen.add(doc_id)
            title = doc_titles.get(doc_id)
            if title:
                result.append(title)
    return result


if __name__ == "__main__":
    query = "What are the main topics covered?"

    notebook = "maldev"

    print("=== Local Search ===")
    response, context = local_search(query, notebook=notebook)
    print(response)

    # print("=== Global Search ===")
    # response, context = global_search(query, notebook=notebook)
    # print(response)

    # print("=== DRIFT Search ===")
    # response, context = drift_search(query, notebook=notebook)
    # print(response)

    # print("=== Basic Search ===")
    # response, context = basic_search(query, notebook=notebook)
    # print(response)
