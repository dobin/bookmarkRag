from pathlib import Path

from flask import Blueprint, abort, jsonify, request, send_file, url_for

import config
from web.auth import api_login_required
from services.bookmark_store import BookmarkStoreError, input_dir, search_documents
from services.graphrag_api import DEFAULT_SEMANTIC_SEARCH_LIMIT, SemanticSearchError, semantic_search

api_bp = Blueprint("api", __name__)


def _artifact_url(notebook: str, filename: str) -> str:
    path = url_for("api.document_artifact", notebook=notebook, filename=filename)
    if not config.BOOKMARK_RAG_DOMAIN:
        return url_for("api.document_artifact", notebook=notebook, filename=filename, _external=True)
    domain = config.BOOKMARK_RAG_DOMAIN
    if "://" not in domain:
        domain = f"https://{domain}"
    return f"{domain}{path}"


def _add_artifact_urls(notebook: str, result: dict) -> dict:
    directory = input_dir(notebook)
    for match in result["matches"]:
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


@api_bp.route("/<notebook>/api/file-search", methods=["POST"])
def file_search_api(notebook: str):
    _validate_notebook(notebook)
    if not request.is_json:
        return jsonify(error="invalid_request", message="Content-Type must be application/json"), 400
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="invalid_request", message="JSON body must be an object"), 400
    try:
        query, source, limit = data.get("query"), data.get("source", "both"), data.get("limit", 100)
        if not isinstance(query, str):
            raise BookmarkStoreError("query must be a string")
        if not isinstance(source, str):
            raise BookmarkStoreError("source must be 'summaries', 'input', or 'both'")
        if not isinstance(limit, int):
            raise BookmarkStoreError("limit must be an integer from 1 to 1000")
        result = search_documents(query, notebook=notebook, source=source, limit=limit)
    except BookmarkStoreError as exc:
        return jsonify(error="invalid_request", message=str(exc)), 400
    return jsonify(_add_artifact_urls(notebook, result))


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


@api_bp.route("/<notebook>/api/semantic-search", methods=["POST"])
@api_login_required
def semantic_search_api(notebook: str):
    _validate_notebook(notebook)
    if not request.is_json:
        return jsonify(error="invalid_request", message="Content-Type must be application/json"), 400
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="invalid_request", message="JSON body must be an object"), 400
    try:
        result = semantic_search(data.get("query"), notebook=notebook, limit=data.get("limit", DEFAULT_SEMANTIC_SEARCH_LIMIT))
    except BookmarkStoreError as exc:
        return jsonify(error="invalid_request", message=str(exc)), 400
    except SemanticSearchError:
        return jsonify(error="semantic_search_unavailable"), 503
    return jsonify(result)
