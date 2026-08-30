import json
import time
from datetime import datetime
from pathlib import Path

from flask import Blueprint, abort, redirect, render_template, request, url_for

import config
from web.auth import login_required
from services.graphrag_api import basic_search, drift_search, global_search, local_search, resolve_sources

ask_bp = Blueprint("ask", __name__)
current_sessions: dict[str, str] = {}


def _chat_dir(notebook: str) -> Path:
    return config._BASE_DIR / "data" / notebook / "chat"


def _create_session() -> dict:
    now = datetime.now()
    return {"id": now.strftime("%Y%m%d_%H%M%S"), "created": now.isoformat(timespec="seconds"), "entries": []}


def _save_session(notebook: str, chat_data: dict) -> None:
    d = _chat_dir(notebook)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{chat_data['id']}.json").write_text(json.dumps(chat_data, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_session(notebook: str, session_id: str) -> dict | None:
    if not session_id or session_id != Path(session_id).name or "/" in session_id:
        return None
    path = _chat_dir(notebook) / f"{session_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _list_sessions(notebook: str) -> list[dict]:
    d = _chat_dir(notebook)
    if not d.exists():
        return []
    sessions = []
    for path in sorted(d.glob("*.json"), reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        entries = data.get("entries", [])
        sessions.append({"id": data["id"], "created": data.get("created", ""),
                         "preview": entries[0]["query"][:60] if entries else "(empty)",
                         "count": len(entries)})
    return sessions


def _get_or_create_session(notebook: str, session_id: str | None = None) -> dict:
    if session_id:
        chat_data = _load_session(notebook, session_id)
        if chat_data:
            current_sessions[notebook] = chat_data["id"]
            return chat_data
    current_id = current_sessions.get(notebook)
    if current_id:
        chat_data = _load_session(notebook, current_id)
        if chat_data:
            return chat_data
    sessions = _list_sessions(notebook)
    if sessions:
        chat_data = _load_session(notebook, sessions[0]["id"])
        if chat_data:
            current_sessions[notebook] = chat_data["id"]
            return chat_data
    chat_data = _create_session()
    _save_session(notebook, chat_data)
    current_sessions[notebook] = chat_data["id"]
    return chat_data


def _run_ask(method: str, query: str, community_level: int, notebook: str):
    started_at = time.perf_counter()
    try:
        if method == "local":
            response, context_data = local_search(query, notebook=notebook, community_level=community_level)
        elif method == "global":
            response, context_data = global_search(query, notebook=notebook, community_level=community_level)
        elif method == "drift":
            response, context_data = drift_search(query, notebook=notebook, community_level=community_level)
        elif method == "basic":
            response, context_data = basic_search(query, notebook=notebook)
        else:
            return "", f"Unknown ask method: {method}", [], {}
        sources = resolve_sources(context_data, notebook) if context_data else []
        return response, None, sources, {"elapsed_seconds": time.perf_counter() - started_at}
    except Exception as exc:
        return "", str(exc), [], {"elapsed_seconds": time.perf_counter() - started_at}


def _validate_notebook(notebook: str):
    if notebook not in config.NOTEBOOKS:
        abort(404)


@ask_bp.route("/<notebook>/ask", methods=["GET"])
def ask(notebook: str):
    _validate_notebook(notebook)
    chat_data = _get_or_create_session(notebook, request.args.get("session", "") or None)
    history = chat_data.get("entries", [])
    return render_template("ask.html", history=history,
        last_method=history[-1]["method"] if history else "local",
        last_community_level=history[-1]["community_level"] if history else 2,
        notebooks=config.NOTEBOOKS, current_notebook=notebook,
        sessions=_list_sessions(notebook), current_session_id=chat_data["id"])


@ask_bp.route("/<notebook>/ask", methods=["POST"])
@login_required
def ask_post(notebook: str):
    _validate_notebook(notebook)
    query = request.form.get("query", "").strip()
    method = request.form.get("method", "local")
    try:
        community_level = int(request.form.get("community_level", 2))
    except ValueError:
        community_level = 2
    community_level = max(0, min(4, community_level))
    if method not in config.ASK_METHODS:
        method = "local"
    chat_data = _get_or_create_session(notebook, request.form.get("session", "") or None)
    if query:
        response, error, sources, metadata = _run_ask(method, query, community_level, notebook)
        chat_data["entries"].append({"query": query, "method": method, "community_level": community_level,
            "notebook": notebook, "response": response, "error": error, "sources": sources,
            "metadata": metadata, "timestamp": datetime.now().strftime("%H:%M:%S")})
        _save_session(notebook, chat_data)
    return redirect(url_for("ask.ask", notebook=notebook, session=chat_data["id"]))


@ask_bp.route("/<notebook>/ask/new", methods=["POST"])
@login_required
def ask_new(notebook: str):
    _validate_notebook(notebook)
    chat_data = _create_session()
    _save_session(notebook, chat_data)
    current_sessions[notebook] = chat_data["id"]
    return redirect(url_for("ask.ask", notebook=notebook, session=chat_data["id"]))


@ask_bp.route("/<notebook>/ask/delete", methods=["POST"])
@login_required
def ask_delete(notebook: str):
    _validate_notebook(notebook)
    session_id = request.form.get("session", "")
    if session_id and session_id == Path(session_id).name:
        path = _chat_dir(notebook) / f"{session_id}.json"
        if path.exists():
            path.unlink()
    if current_sessions.get(notebook) == session_id:
        current_sessions.pop(notebook, None)
    return redirect(url_for("ask.ask", notebook=notebook))
