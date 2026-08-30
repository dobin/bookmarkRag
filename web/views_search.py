from flask import Blueprint, abort, render_template, request

import config
from services.bookmark_store import BookmarkStoreError, search_documents
from services.graphrag_api import SemanticSearchError, semantic_search_all

search_bp = Blueprint("search", __name__)

SEARCH_KINDS = ("content", "summary", "semantic")


def _limit(value: str | None) -> int:
    """Return a search limit from the optional query-string value."""
    try:
        return int(value) if value is not None else 100
    except ValueError:
        return 100


@search_bp.route("/search")
@search_bp.route("/<notebook>/search")
def search(notebook: str | None = None):
    """Render content, summary, or semantic search results.

    The unscoped route searches every notebook unless the optional ``notebook``
    query parameter selects one. The scoped route always uses its URL notebook.
    """
    if notebook is None:
        requested_notebook = request.args.get("notebook")
        if requested_notebook:
            notebook = requested_notebook
    if notebook is not None and notebook not in config.NOTEBOOKS:
        abort(404)

    query = request.args.get("query", "").strip()
    kind = request.args.get("kind", "summary")
    if kind not in SEARCH_KINDS:
        kind = "summary"
    limit = _limit(request.args.get("limit"))
    result: dict | None = None
    error: str | None = None

    if query:
        try:
            if kind == "semantic":
                result = semantic_search_all(query, notebook=notebook, limit=limit)
            else:
                source = "input" if kind == "content" else "summaries"
                result = search_documents(query, notebook=notebook, source=source, limit=limit)
        except BookmarkStoreError as exc:
            error = str(exc)
        except SemanticSearchError:
            error = "Semantic search is temporarily unavailable."

    return render_template(
        "search.html",
        query=query,
        kind=kind,
        limit=limit,
        result=result,
        error=error,
        current_notebook=notebook,
        scoped_notebook=notebook,
        notebooks=config.NOTEBOOKS,
    )
