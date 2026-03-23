"""
Sample script showing how to run graphrag queries programmatically,
equivalent to: graphrag query --root . --method <local|global|drift|basic> --query "..."
"""

import logging
from pathlib import Path
from typing import Any

import pandas as pd
from graphrag.cli.query import (
    run_local_search,
    run_global_search,
    run_drift_search,
    run_basic_search,
)

logger = logging.getLogger(__name__)


def local_search(query: str, notebook: str, community_level: int = 2) -> tuple[str, Any]:
    """Local search: entity/neighborhood focused. Best for specific entity questions."""
    root_dir = Path("grag") / notebook
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
    root_dir = Path("grag") / notebook
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
    root_dir = Path("grag") / notebook
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
    root_dir = Path("grag") / notebook
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
