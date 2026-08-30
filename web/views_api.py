from pathlib import Path

from flask import Blueprint, abort, jsonify, request, send_file, url_for

import config
from services.bookmark_store import BookmarkStoreError, input_dir, search_documents
from services.graphrag_api import semantic_search_all

api_bp = Blueprint("api", __name__)

SEARCH_KINDS = ("content", "summary", "semantic")


def _artifact_url(notebook: str, filename: str) -> str:
    path = url_for("api.document_artifact", notebook=notebook, filename=filename)
    if not config.BOOKMARK_RAG_DOMAIN:
        return url_for("api.document_artifact", notebook=notebook, filename=filename, _external=True)
    domain = config.BOOKMARK_RAG_DOMAIN
    if "://" not in domain:
        domain = f"https://{domain}"
    return f"{domain}{path}"


def _add_artifact_urls(result: dict) -> dict:
    """Attach artifact URLs to file-search matches that may span notebooks.

    Each match carries its own ``notebook`` (``search_documents`` sets it on
    every row), so directories are resolved per match instead of once.
    """
    for match in result["matches"]:
        notebook = match["notebook"]
        directory = input_dir(notebook)
        content_filename = f"{Path(match['filename']).stem}.md" if match["source"] == "summaries" else match["filename"]
        stem = Path(content_filename).stem
        metadata_filename, summary_filename = f"{stem}.json", f"{stem}.llm"
        match["metadata_exists"] = (directory / metadata_filename).is_file()
        match["metadata_url"] = _artifact_url(notebook, metadata_filename) if match["metadata_exists"] else None
        match["summary_url"] = _artifact_url(notebook, summary_filename) if match["summary_exists"] else None
        match["content_url"] = _artifact_url(notebook, content_filename) if match["content_exists"] else None
    return result


def _validate_notebook(notebook: str):
    if notebook not in config.NOTEBOOKS:
        abort(404)


def _search_request_data() -> dict | None:
    """Return a JSON object request body, or return a JSON error response."""
    if not request.is_json:
        return None
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


@api_bp.route("/api/search", methods=["POST"])
@api_bp.route("/<notebook>/api/search", methods=["POST"])
def search_api(notebook: str | None = None):
    """Public literal or semantic search, scoped to one notebook or all.

    Use ``kind`` = ``content``, ``summary``, or ``semantic``. The unscoped
    route accepts an optional ``notebook`` in the JSON body; the scoped route
    takes it from its URL. Semantic search skips unavailable notebook indexes.
    """
    data = _search_request_data()
    if data is None:
        message = "Content-Type must be application/json" if not request.is_json else "JSON body must be an object"
        return jsonify(error="invalid_request", message=message), 400

    if notebook is None:
        notebook = data.get("notebook")
        if notebook is not None and not isinstance(notebook, str):
            return jsonify(error="invalid_request", message="notebook must be a string or omitted"), 400
    if notebook is not None:
        _validate_notebook(notebook)

    kind = data.get("kind", "summary")
    if kind not in SEARCH_KINDS:
        return jsonify(error="invalid_request", message="kind must be 'content', 'summary', or 'semantic'"), 400
    query = data.get("query")
    if not isinstance(query, str):
        return jsonify(error="invalid_request", message="query must be a string"), 400

    try:
        if kind == "semantic":
            result = semantic_search_all(query, notebook=notebook, limit=data.get("limit", 100))
        else:
            source = "input" if kind == "content" else "summaries"
            result = _add_artifact_urls(search_documents(
                query, notebook=notebook, source=source, limit=data.get("limit", 100)
            ))
    except BookmarkStoreError as exc:
        return jsonify(error="invalid_request", message=str(exc)), 400
    return jsonify(kind=kind, notebook=notebook, result=result)


@api_bp.route("/<notebook>/api/documents/<filename>", methods=["GET"])
def document_artifact(notebook: str, filename: str):
    _validate_notebook(notebook)
    safe_filename = Path(filename).name
    if safe_filename != filename or "\\" in filename or Path(safe_filename).suffix not in {".json", ".llm", ".md"}:
        abort(404)
    artifact_path = input_dir(notebook) / safe_filename
    if not artifact_path.is_file():
        abort(404)
    return send_file(artifact_path, conditional=True)


