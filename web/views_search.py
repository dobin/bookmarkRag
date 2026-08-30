import re

from flask import Blueprint, abort, render_template, request, url_for
from markupsafe import Markup, escape

import config
from services.bookmark_store import bookmark_urls_for_filename, input_dir, summary_exists

search_bp = Blueprint("search", __name__)


@search_bp.route("/<notebook>/search", methods=["GET", "POST"])
def search(notebook: str):
    if notebook not in config.NOTEBOOKS:
        abort(404)
    query, search_in, results, searched = "", "summaries", [], False
    if request.method == "POST":
        query = request.form.get("query", "").strip()
        search_in = request.form.get("search_mode", request.form.get("search_in", "summaries"))
        if search_in not in ("summaries", "input"):
            search_in = "summaries"
        searched = True
        if query:
            pattern = "*.llm" if search_in == "summaries" else "*.md"
            search_dir = input_dir(notebook)
            escaped_query = re.escape(query)
            if search_dir.exists():
                for filepath in sorted(search_dir.glob(pattern)):
                    try:
                        text = filepath.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        continue
                    content_filename = filepath.name[:-4] + ".md" if filepath.suffix == ".llm" else filepath.name
                    bookmark_urls = bookmark_urls_for_filename(notebook, content_filename)
                    for lineno, line in enumerate(text.splitlines(), 1):
                        if re.search(escaped_query, line, re.IGNORECASE):
                            results.append({
                                "filename": filepath.name, "lineno": lineno,
                                "text": Markup(re.sub(f"({escaped_query})", r"<mark>\1</mark>", escape(line), flags=re.IGNORECASE)),
                                "content_exists": (input_dir(notebook) / content_filename).is_file(),
                                "summary_exists": summary_exists(notebook, content_filename),
                                "bookmark_url": bookmark_urls[0] if len(bookmark_urls) == 1 else None,
                                "view_url": url_for("bookmarks.bookmarks_view", notebook=notebook, filename=content_filename),
                                "summary_url": url_for("bookmarks.bookmarks_view_summary", notebook=notebook, filename=content_filename),
                            })
    return render_template("search.html", query=query, search_in=search_in, results=results,
                           result_file_count=len({result["filename"] for result in results}),
                           searched=searched, current_notebook=notebook)
