"""
Sample script showing how to run graphrag queries programmatically,
equivalent to: graphrag query --root . --method <local|global|drift|basic> --query "..."
"""

from pathlib import Path
from typing import Any

from graphrag.cli.query import (
    run_local_search,
    run_global_search,
    run_drift_search,
    run_basic_search,
)


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
