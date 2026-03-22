import glob
import os
from datetime import datetime
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, session, url_for

from graphrag_api import basic_search, drift_search, global_search, local_search
from scraper import scrape_single_url, url_to_filename

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


def _bookmarks_file(notebook: str) -> Path:
    return Path("bookmarks") / f"{notebook}.txt"


def _input_dir(notebook: str) -> Path:
    return Path("grag") / notebook / "input"


def _load_bookmarks(notebook: str) -> list[dict]:
    """Return list of {url, filename, scraped} for the given notebook."""
    bfile = _bookmarks_file(notebook)
    input_dir = _input_dir(notebook)
    if not bfile.exists():
        return []
    entries = []
    seen = set()
    for line in bfile.read_text(encoding="utf-8").splitlines():
        url = line.strip()
        if not url or url in seen:
            continue
        seen.add(url)
        filename = url_to_filename(url) + ".md"
        scraped = (input_dir / filename).exists()
        entries.append({"url": url, "filename": filename, "scraped": scraped})
    return entries


@app.route("/bookmarks")
def bookmarks():
    current_notebook = get_current_notebook()
    entries = _load_bookmarks(current_notebook)
    return render_template("bookmarks.html", entries=entries, current_notebook=current_notebook)


@app.route("/bookmarks/add", methods=["POST"])
def bookmarks_add():
    current_notebook = get_current_notebook()
    url = request.form.get("url", "").strip()

    if not url.startswith("http://") and not url.startswith("https://"):
        flash("Invalid URL — must start with http:// or https://", "danger")
        return redirect(url_for("bookmarks"))

    bfile = _bookmarks_file(current_notebook)
    bfile.parent.mkdir(parents=True, exist_ok=True)

    # Check for duplicate
    existing_urls: set[str] = set()
    if bfile.exists():
        existing_urls = {l.strip() for l in bfile.read_text(encoding="utf-8").splitlines() if l.strip()}
    
    if url in existing_urls:
        flash(f"URL already in bookmarks: {url}", "warning")
        return redirect(url_for("bookmarks"))

    # Append to file
    with open(bfile, "a", encoding="utf-8") as f:
        f.write(url + "\n")

    # Scrape immediately
    output_dir = _input_dir(current_notebook)
    success, error = scrape_single_url(url, output_dir)
    if success:
        flash(f"Added and scraped: {url}", "success")
    else:
        flash(f"Added to bookmarks, but scraping failed: {error}", "warning")

    return redirect(url_for("bookmarks"))


@app.route("/bookmarks/scrape", methods=["POST"])
def bookmarks_scrape_one():
    """Re-scrape a single URL (force overwrite)."""
    current_notebook = get_current_notebook()
    url = request.form.get("url", "").strip()

    if not url.startswith("http://") and not url.startswith("https://"):
        flash("Invalid URL", "danger")
        return redirect(url_for("bookmarks"))

    output_dir = _input_dir(current_notebook)
    success, error = scrape_single_url(url, output_dir, force=True)
    if success:
        flash(f"Scraped: {url}", "success")
    else:
        flash(f"Scraping failed for {url}: {error}", "danger")

    return redirect(url_for("bookmarks"))


@app.route("/bookmarks/scrape_all", methods=["POST"])
def bookmarks_scrape_all():
    """Scrape all URLs that do not yet have a .md file."""
    current_notebook = get_current_notebook()
    entries = _load_bookmarks(current_notebook)
    output_dir = _input_dir(current_notebook)

    pending = [e for e in entries if not e["scraped"]]
    if not pending:
        flash("All bookmarks are already scraped.", "info")
        return redirect(url_for("bookmarks"))

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

    return redirect(url_for("bookmarks"))


@app.route("/bookmarks/view")
def bookmarks_view():
    current_notebook = get_current_notebook()
    notebook_param = request.args.get("notebook", current_notebook)
    filename = request.args.get("filename", "")

    # Security: only allow notebooks we know about
    if notebook_param not in NOTEBOOKS:
        flash("Unknown notebook.", "danger")
        return redirect(url_for("bookmarks"))

    # Security: prevent path traversal — filename must be a plain basename with .md extension
    safe_filename = Path(filename).name
    if safe_filename != filename or not safe_filename.endswith(".md") or not safe_filename:
        flash("Invalid filename.", "danger")
        return redirect(url_for("bookmarks"))

    md_path = _input_dir(notebook_param) / safe_filename
    if not md_path.exists():
        flash(f"File not found: {safe_filename}", "warning")
        return redirect(url_for("bookmarks"))

    try:
        content = md_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        flash(f"Could not read file: {exc}", "danger")
        return redirect(url_for("bookmarks"))

    return render_template(
        "bookmarks_view.html",
        content=content,
        filename=safe_filename,
        notebook=notebook_param,
        current_notebook=current_notebook,
    )


if __name__ == "__main__":
    app.run(debug=True)
