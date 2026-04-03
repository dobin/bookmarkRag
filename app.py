import glob
import json
import os
import re
from datetime import datetime
from pathlib import Path

from flask import Flask, abort, flash, redirect, render_template, request, url_for
from markupsafe import Markup, escape

from graphrag_api import basic_search, drift_search, global_search, local_search, resolve_sources
from scraper import scrape_single_url, url_to_filename
from summarizer import summarize_all, summarize_url

app = Flask(__name__)
app.secret_key = os.urandom(24)

ASK_METHODS = ["local", "global", "drift", "basic"]
NOTEBOOKS = sorted(p.name for p in Path("grag").iterdir() if p.is_dir())

# Resolve once at startup so relative paths aren't affected by cwd changes.
_BASE_DIR = Path(__file__).resolve().parent

# Tracks which chat session is active per notebook (in-memory; on restart
# defaults to the most recent session).
current_sessions: dict[str, str] = {}


def _chat_dir(notebook: str) -> Path:
    return _BASE_DIR / "grag" / notebook / "chat"


def _create_session() -> dict:
    """Create a new empty session dict."""
    now = datetime.now()
    session_id = now.strftime("%Y%m%d_%H%M%S")
    return {
        "id": session_id,
        "created": now.isoformat(timespec="seconds"),
        "entries": [],
    }


def _save_session(notebook: str, session: dict) -> None:
    """Write a session dict to its JSON file."""
    d = _chat_dir(notebook)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{session['id']}.json"
    path.write_text(json.dumps(session, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_session(notebook: str, session_id: str) -> dict | None:
    """Load a session by ID. Returns None if not found."""
    # Validate session_id is a safe basename (no path traversal)
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
    """Return [{id, created, preview}] for all sessions, newest first."""
    d = _chat_dir(notebook)
    if not d.exists():
        return []
    sessions = []
    for p in sorted(d.glob("*.json"), reverse=True):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        entries = data.get("entries", [])
        preview = entries[0]["query"][:60] if entries else "(empty)"
        sessions.append({
            "id": data["id"],
            "created": data.get("created", ""),
            "preview": preview,
            "count": len(entries),
        })
    return sessions


def _get_or_create_session(notebook: str, session_id: str | None = None) -> dict:
    """Resolve the session to display: requested > current > latest > new."""
    # Try the explicitly requested session
    if session_id:
        sess = _load_session(notebook, session_id)
        if sess:
            current_sessions[notebook] = sess["id"]
            return sess

    # Try the in-memory current session
    cur = current_sessions.get(notebook)
    if cur:
        sess = _load_session(notebook, cur)
        if sess:
            return sess

    # Try the latest session on disk
    all_sessions = _list_sessions(notebook)
    if all_sessions:
        sess = _load_session(notebook, all_sessions[0]["id"])
        if sess:
            current_sessions[notebook] = sess["id"]
            return sess

    # Create a brand-new session
    sess = _create_session()
    _save_session(notebook, sess)
    current_sessions[notebook] = sess["id"]
    return sess


@app.context_processor
def inject_notebooks():
    """Make notebooks and current_notebook available to all templates."""
    notebook = request.view_args.get("notebook", "") if request.view_args else ""
    return {
        "notebooks": NOTEBOOKS,
        "current_notebook": notebook,
    }


def _run_ask(method: str, query: str, community_level: int, notebook: str) -> tuple[str, str | None, list[str]]:
    """Dispatch to the correct ask function. Returns (response, error, sources)."""
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
            return "", f"Unknown ask method: {method}", []
        sources = resolve_sources(context_data, notebook) if context_data else []
        return response, None, sources
    except Exception as exc:
        return "", str(exc), []


@app.route("/")
def index():
    if NOTEBOOKS:
        return redirect(url_for("ask", notebook=NOTEBOOKS[0]))
    return "No notebooks found.", 404


@app.route("/<notebook>/ask", methods=["GET", "POST"])
def ask(notebook: str):
    if notebook not in NOTEBOOKS:
        abort(404)

    if request.method == "POST":
        query = request.form.get("query", "").strip()
        method = request.form.get("method", "local")
        community_level = int(request.form.get("community_level", 2))
        session_id = request.form.get("session", "")

        if method not in ASK_METHODS:
            method = "local"
        community_level = max(0, min(4, community_level))

        sess = _get_or_create_session(notebook, session_id or None)

        if query:
            response, error, sources = _run_ask(method, query, community_level, notebook)
            sess["entries"].append({
                "query": query,
                "method": method,
                "community_level": community_level,
                "notebook": notebook,
                "response": response,
                "error": error,
                "sources": sources,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
            })
            _save_session(notebook, sess)

        return redirect(url_for("ask", notebook=notebook, session=sess["id"]))

    # GET — load requested or current session
    requested = request.args.get("session", "")
    sess = _get_or_create_session(notebook, requested or None)
    hist = sess.get("entries", [])
    sessions = _list_sessions(notebook)

    last_method = hist[-1]["method"] if hist else "local"
    last_community_level = hist[-1]["community_level"] if hist else 2
    return render_template(
        "ask.html",
        history=hist,
        last_method=last_method,
        last_community_level=last_community_level,
        notebooks=NOTEBOOKS,
        current_notebook=notebook,
        sessions=sessions,
        current_session_id=sess["id"],
    )


@app.route("/<notebook>/ask/new", methods=["POST"])
def ask_new(notebook: str):
    """Create a new chat session."""
    if notebook not in NOTEBOOKS:
        abort(404)
    sess = _create_session()
    _save_session(notebook, sess)
    current_sessions[notebook] = sess["id"]
    return redirect(url_for("ask", notebook=notebook, session=sess["id"]))


@app.route("/<notebook>/ask/delete", methods=["POST"])
def ask_delete(notebook: str):
    """Delete a specific chat session file."""
    if notebook not in NOTEBOOKS:
        abort(404)
    session_id = request.form.get("session", "")
    if session_id and session_id == Path(session_id).name:
        path = _chat_dir(notebook) / f"{session_id}.json"
        if path.exists():
            path.unlink()
    # If we deleted the current session, clear the tracking
    if current_sessions.get(notebook) == session_id:
        current_sessions.pop(notebook, None)
    return redirect(url_for("ask", notebook=notebook))


@app.route("/<notebook>/logs")
def logs(notebook: str):
    if notebook not in NOTEBOOKS:
        abort(404)
    logs_dir = Path("grag") / notebook / "logs"
    
    log_files = {}
    if logs_dir.exists():
        for path in sorted(logs_dir.glob("*.log")):
            try:
                log_files[path.name] = path.read_text(errors="replace")
            except OSError as exc:
                log_files[path.name] = f"[Could not read file: {exc}]"
    
    return render_template("logs.html", log_files=log_files, current_notebook=notebook, notebooks=NOTEBOOKS)


def _bookmarks_file(notebook: str) -> Path:
    return Path("bookmarks") / f"{notebook}.txt"


def _input_dir(notebook: str) -> Path:
    return Path("grag") / notebook / "input"


def _summaries_dir(notebook: str) -> Path:
    return Path("grag") / notebook / "summaries"


def _load_bookmarks(notebook: str) -> list[dict]:
    """Return list of {url, filename, scraped, summarized} for the given notebook."""
    bfile = _bookmarks_file(notebook)
    input_dir = _input_dir(notebook)
    summaries_dir = _summaries_dir(notebook)
    if not bfile.exists():
        return []
    entries = []
    seen = set()
    for line in bfile.read_text(encoding="utf-8").splitlines():
        url = line.strip()
        if not url or url in seen:
            continue
        seen.add(url)
        base = url_to_filename(url)
        filename = base + ".md"
        scraped = (input_dir / filename).exists()
        summarized = (summaries_dir / (base + ".llm")).exists()
        entries.append({"url": url, "filename": filename, "scraped": scraped, "summarized": summarized})
    return entries


@app.route("/<notebook>/bookmarks")
def bookmarks(notebook: str):
    if notebook not in NOTEBOOKS:
        abort(404)
    entries = _load_bookmarks(notebook)
    return render_template("bookmarks.html", entries=entries, current_notebook=notebook)


@app.route("/<notebook>/bookmarks/add", methods=["POST"])
def bookmarks_add(notebook: str):
    if notebook not in NOTEBOOKS:
        abort(404)
    url = request.form.get("url", "").strip()

    if not url.startswith("http://") and not url.startswith("https://"):
        flash("Invalid URL — must start with http:// or https://", "danger")
        return redirect(url_for("bookmarks", notebook=notebook))

    bfile = _bookmarks_file(notebook)
    bfile.parent.mkdir(parents=True, exist_ok=True)

    # Check for duplicate
    existing_urls: set[str] = set()
    if bfile.exists():
        existing_urls = {l.strip() for l in bfile.read_text(encoding="utf-8").splitlines() if l.strip()}

    if url in existing_urls:
        flash(f"URL already in bookmarks: {url}", "warning")
        return redirect(url_for("bookmarks", notebook=notebook))

    # Append to file
    with open(bfile, "a", encoding="utf-8") as f:
        f.write(url + "\n")

    # Scrape immediately
    output_dir = _input_dir(notebook)
    success, error = scrape_single_url(url, output_dir)
    if success:
        flash(f"Added and scraped: {url}", "success")
        # Summarize the newly scraped file
        ok, sum_err = summarize_url(url, notebook)
        if ok:
            flash(f"Summary generated for: {url}", "success")
        else:
            flash(f"Scraping OK but summarization failed: {sum_err}", "warning")
    else:
        flash(f"Added to bookmarks, but scraping failed: {error}", "warning")

    return redirect(url_for("bookmarks", notebook=notebook))


@app.route("/<notebook>/bookmarks/scrape", methods=["POST"])
def bookmarks_scrape_one(notebook: str):
    """Re-scrape a single URL (force overwrite)."""
    if notebook not in NOTEBOOKS:
        abort(404)
    url = request.form.get("url", "").strip()

    if not url.startswith("http://") and not url.startswith("https://"):
        flash("Invalid URL", "danger")
        return redirect(url_for("bookmarks", notebook=notebook))

    output_dir = _input_dir(notebook)
    success, error = scrape_single_url(url, output_dir, force=True)
    if success:
        flash(f"Scraped: {url}", "success")
    else:
        flash(f"Scraping failed for {url}: {error}", "danger")

    return redirect(url_for("bookmarks", notebook=notebook))


@app.route("/<notebook>/bookmarks/scrape_all", methods=["POST"])
def bookmarks_scrape_all(notebook: str):
    """Scrape all URLs that do not yet have a .md file."""
    if notebook not in NOTEBOOKS:
        abort(404)
    entries = _load_bookmarks(notebook)
    output_dir = _input_dir(notebook)

    pending = [e for e in entries if not e["scraped"]]
    if not pending:
        flash("All bookmarks are already scraped.", "info")
        return redirect(url_for("bookmarks", notebook=notebook))

    ok_count = 0
    fail_msgs: list[str] = []
    for entry in pending:
        success, error = scrape_single_url(entry["url"], output_dir)
        if success:
            ok_count += 1
        else:
            fail_msgs.append(f"{entry['url']}: {error}")

    if ok_count:
        flash(f"Scraped {ok_count} URL(s) successfully.", "success")
    for msg in fail_msgs:
        flash(f"Failed — {msg}", "danger")

    return redirect(url_for("bookmarks", notebook=notebook))


@app.route("/<notebook>/bookmarks/view")
def bookmarks_view(notebook: str):
    if notebook not in NOTEBOOKS:
        abort(404)
    filename = request.args.get("filename", "")

    # Security: prevent path traversal — filename must be a plain basename with .md extension
    safe_filename = Path(filename).name
    if safe_filename != filename or not safe_filename.endswith(".md") or not safe_filename:
        flash("Invalid filename.", "danger")
        return redirect(url_for("bookmarks", notebook=notebook))

    md_path = _input_dir(notebook) / safe_filename
    if not md_path.exists():
        flash(f"File not found: {safe_filename}", "warning")
        return redirect(url_for("bookmarks", notebook=notebook))

    try:
        content = md_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        flash(f"Could not read file: {exc}", "danger")
        return redirect(url_for("bookmarks", notebook=notebook))

    return render_template(
        "bookmarks_view.html",
        content=content,
        filename=safe_filename,
        notebook=notebook,
        current_notebook=notebook,
    )


@app.route("/<notebook>/bookmarks/view_summary")
def bookmarks_view_summary(notebook: str):
    if notebook not in NOTEBOOKS:
        abort(404)
    filename = request.args.get("filename", "")

    # Security: prevent path traversal — filename must be a plain basename with .md extension
    safe_filename = Path(filename).name
    if safe_filename != filename or not safe_filename.endswith(".md") or not safe_filename:
        flash("Invalid filename.", "danger")
        return redirect(url_for("bookmarks", notebook=notebook))

    llm_filename = safe_filename[:-3] + ".llm"
    llm_path = _summaries_dir(notebook) / llm_filename
    if not llm_path.exists():
        flash(f"Summary file not found: {llm_filename}", "warning")
        return redirect(url_for("bookmarks", notebook=notebook))

    try:
        content = llm_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        flash(f"Could not read file: {exc}", "danger")
        return redirect(url_for("bookmarks", notebook=notebook))

    return render_template(
        "bookmarks_view.html",
        content=content,
        filename=llm_filename,
        notebook=notebook,
        current_notebook=notebook,
    )


@app.route("/<notebook>/bookmarks/summarize", methods=["POST"])
def bookmarks_summarize_one(notebook: str):
    """Summarize (or re-summarize) a single URL."""
    if notebook not in NOTEBOOKS:
        abort(404)
    url = request.form.get("url", "").strip()

    if not url.startswith("http://") and not url.startswith("https://"):
        flash("Invalid URL", "danger")
        return redirect(url_for("bookmarks", notebook=notebook))

    success, error = summarize_url(url, notebook, force=True)
    if success:
        flash(f"Summary generated: {url}", "success")
    else:
        flash(f"Summarization failed for {url}: {error}", "danger")

    return redirect(url_for("bookmarks", notebook=notebook))


@app.route("/<notebook>/bookmarks/summarize_all", methods=["POST"])
def bookmarks_summarize_all(notebook: str):
    """Summarize all scraped .md files that do not yet have a .llm summary."""
    if notebook not in NOTEBOOKS:
        abort(404)

    ok_count, skipped_count, errors = summarize_all(notebook)

    if ok_count:
        flash(f"Summarized {ok_count} file(s). {skipped_count} already had summaries.", "success")
    elif not errors:
        flash("All scraped bookmarks already have summaries.", "info")
    for msg in errors:
        flash(f"Failed — {msg}", "danger")

    return redirect(url_for("bookmarks", notebook=notebook))


@app.route("/<notebook>/search", methods=["GET", "POST"])
def search(notebook: str):
    if notebook not in NOTEBOOKS:
        abort(404)

    query = ""
    search_in = "summaries"
    results = []
    searched = False

    if request.method == "POST":
        query = request.form.get("query", "").strip()
        search_in = request.form.get("search_in", "summaries")
        if search_in not in ("summaries", "input"):
            search_in = "summaries"
        searched = True

        if query:
            if search_in == "summaries":
                search_dir = _summaries_dir(notebook)
                pattern = "*.llm"
            else:
                search_dir = _input_dir(notebook)
                pattern = "*.md"

            if search_dir.exists():
                escaped_query = re.escape(query)
                for filepath in sorted(search_dir.glob(pattern)):
                    try:
                        text = filepath.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        continue
                    matches = []
                    for lineno, line in enumerate(text.splitlines(), 1):
                        if re.search(escaped_query, line, re.IGNORECASE):
                            highlighted = Markup(re.sub(
                                f"({escaped_query})",
                                r"<mark>\1</mark>",
                                escape(line),
                                flags=re.IGNORECASE,
                            ))
                            matches.append({"lineno": lineno, "text": highlighted})
                    if matches:
                        results.append({"filename": filepath.name, "matches": matches})

    return render_template(
        "search.html",
        query=query,
        search_in=search_in,
        results=results,
        searched=searched,
        current_notebook=notebook,
    )


if __name__ == "__main__":
    app.run(debug=True)
