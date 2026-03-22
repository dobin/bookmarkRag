import glob
import os
from datetime import datetime
from pathlib import Path

from flask import Flask, redirect, render_template, request, session, url_for

from graphrag_api import basic_search, drift_search, global_search, local_search

app = Flask(__name__)
app.secret_key = os.urandom(24)

# In-memory search history – kept at module level to avoid Flask session
# cookie size limits (LLM responses can easily exceed 4 KB).
search_history: list[dict] = []

SEARCH_METHODS = ["local", "global", "drift", "basic"]
NOTEBOOKS = sorted(p.name for p in Path("grag").iterdir() if p.is_dir())


def get_current_notebook() -> str:
    """Get the currently selected notebook from session, with fallback to first available."""
    current = session.get("notebook")
    if current and current in NOTEBOOKS:
        return current
    if NOTEBOOKS:
        return NOTEBOOKS[0]
    return ""


@app.context_processor
def inject_notebooks():
    """Make notebooks and current_notebook available to all templates."""
    return {
        "notebooks": NOTEBOOKS,
        "current_notebook": get_current_notebook(),
    }


def _run_search(method: str, query: str, community_level: int, notebook: str) -> tuple[str, str | None]:
    """Dispatch to the correct search function. Returns (response, error)."""
    try:
        if method == "local":
            response, _ = local_search(query, notebook=notebook, community_level=community_level)
        elif method == "global":
            response, _ = global_search(query, notebook=notebook, community_level=community_level)
        elif method == "drift":
            response, _ = drift_search(query, notebook=notebook, community_level=community_level)
        elif method == "basic":
            response, _ = basic_search(query, notebook=notebook)
        else:
            return "", f"Unknown search method: {method}"
        return response, None
    except Exception as exc:
        return "", str(exc)


@app.route("/")
def index():
    return redirect(url_for("search"))


@app.route("/notebook/<name>", methods=["GET", "POST"])
def select_notebook(name: str):
    """Switch to a different notebook."""
    if name in NOTEBOOKS:
        session["notebook"] = name
    return redirect(request.referrer or url_for("search"))


@app.route("/search", methods=["GET", "POST"])
def search():
    current_notebook = get_current_notebook()
    
    if request.method == "POST":
        query = request.form.get("query", "").strip()
        method = request.form.get("method", "local")
        community_level = int(request.form.get("community_level", 2))

        if method not in SEARCH_METHODS:
            method = "local"
        community_level = max(0, min(4, community_level))

        if query:
            response, error = _run_search(method, query, community_level, current_notebook)
            search_history.append({
                "query": query,
                "method": method,
                "community_level": community_level,
                "notebook": current_notebook,
                "response": response,
                "error": error,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
            })

        return redirect(url_for("search"))

    return render_template("search.html", history=search_history, notebooks=NOTEBOOKS, current_notebook=current_notebook)


@app.route("/search/clear", methods=["POST"])
def search_clear():
    search_history.clear()
    return redirect(url_for("search"))


@app.route("/logs")
def logs():
    current_notebook = get_current_notebook()
    logs_dir = Path("grag") / current_notebook / "logs"
    
    log_files = {}
    if logs_dir.exists():
        for path in sorted(logs_dir.glob("*.log")):
            try:
                log_files[path.name] = path.read_text(errors="replace")
            except OSError as exc:
                log_files[path.name] = f"[Could not read file: {exc}]"
    
    return render_template("logs.html", log_files=log_files, current_notebook=current_notebook, notebooks=NOTEBOOKS)


if __name__ == "__main__":
    app.run(debug=True)
