from pathlib import Path

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

import config
from web.auth import write_required
from services.bookmark_store import input_dir, load_bookmarks, summary_path
from services.scraper import scrape_single_url
from services.summarizer import summarize_all, summarize_url

bookmarks_bp = Blueprint("bookmarks", __name__)


def _validate_notebook(notebook: str):
    if notebook not in config.NOTEBOOKS:
        abort(404)


def _valid_url(url: str) -> bool:
    return url.startswith(("http://", "https://"))


@bookmarks_bp.route("/<notebook>/bookmarks")
def bookmarks(notebook: str):
    _validate_notebook(notebook)
    return render_template("bookmarks.html", entries=load_bookmarks(notebook), current_notebook=notebook)


@bookmarks_bp.route("/<notebook>/bookmarks/scrape", methods=["POST"])
@write_required
def bookmarks_scrape_one(notebook: str):
    _validate_notebook(notebook)
    url = request.form.get("url", "").strip()
    if not _valid_url(url):
        flash("Invalid URL", "danger")
        return redirect(url_for("bookmarks.bookmarks", notebook=notebook))
    success, error = scrape_single_url(url, input_dir(notebook), force=True)
    flash(f"Scraped: {url}" if success else f"Scraping failed for {url}: {error}", "success" if success else "danger")
    return redirect(url_for("bookmarks.bookmarks", notebook=notebook))


@bookmarks_bp.route("/<notebook>/bookmarks/scrape_all", methods=["POST"])
@write_required
def bookmarks_scrape_all(notebook: str):
    _validate_notebook(notebook)
    entries = load_bookmarks(notebook)
    pending = [entry for entry in entries if not entry["scraped"]]
    if not pending:
        flash("All bookmarks are already scraped.", "info")
        return redirect(url_for("bookmarks.bookmarks", notebook=notebook))
    ok_count, fail_msgs = 0, []
    for entry in pending:
        success, error = scrape_single_url(entry["url"], input_dir(notebook))
        if success:
            ok_count += 1
        else:
            fail_msgs.append(f"{entry['url']}: {error}")
    if ok_count:
        flash(f"Scraped {ok_count} URL(s) successfully.", "success")
    for message in fail_msgs:
        flash(f"Failed — {message}", "danger")
    return redirect(url_for("bookmarks.bookmarks", notebook=notebook))


@bookmarks_bp.route("/<notebook>/bookmarks/view")
def bookmarks_view(notebook: str):
    _validate_notebook(notebook)
    filename = request.args.get("filename", "")
    safe_filename = Path(filename).name
    if safe_filename != filename or not safe_filename.endswith(".md") or not safe_filename:
        flash("Invalid filename.", "danger")
        return redirect(url_for("bookmarks.bookmarks", notebook=notebook))
    path = input_dir(notebook) / safe_filename
    if not path.exists():
        flash(f"File not found: {safe_filename}", "warning")
        return redirect(url_for("bookmarks.bookmarks", notebook=notebook))
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        flash(f"Could not read file: {exc}", "danger")
        return redirect(url_for("bookmarks.bookmarks", notebook=notebook))
    return render_template("bookmarks_view.html", content=content, filename=safe_filename,
                           notebook=notebook, current_notebook=notebook)


@bookmarks_bp.route("/<notebook>/bookmarks/view_summary")
def bookmarks_view_summary(notebook: str):
    _validate_notebook(notebook)
    filename = request.args.get("filename", "")
    safe_filename = Path(filename).name
    if safe_filename != filename or not safe_filename.endswith(".md") or not safe_filename:
        flash("Invalid filename.", "danger")
        return redirect(url_for("bookmarks.bookmarks", notebook=notebook))
    llm_filename = safe_filename[:-3] + ".llm"
    path = summary_path(notebook, safe_filename)
    if not path.exists():
        flash(f"Summary file not found: {llm_filename}", "warning")
        return redirect(url_for("bookmarks.bookmarks", notebook=notebook))
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        flash(f"Could not read file: {exc}", "danger")
        return redirect(url_for("bookmarks.bookmarks", notebook=notebook))
    return render_template("bookmarks_view.html", content=content, filename=llm_filename,
                           notebook=notebook, current_notebook=notebook)


@bookmarks_bp.route("/<notebook>/bookmarks/summarize", methods=["POST"])
@write_required
def bookmarks_summarize_one(notebook: str):
    _validate_notebook(notebook)
    url = request.form.get("url", "").strip()
    if not _valid_url(url):
        flash("Invalid URL", "danger")
        return redirect(url_for("bookmarks.bookmarks", notebook=notebook))
    success, error = summarize_url(url, notebook, force=True)
    flash(f"Summary generated: {url}" if success else f"Summarization failed for {url}: {error}", "success" if success else "danger")
    return redirect(url_for("bookmarks.bookmarks", notebook=notebook))


@bookmarks_bp.route("/<notebook>/bookmarks/summarize_all", methods=["POST"])
@write_required
def bookmarks_summarize_all(notebook: str):
    _validate_notebook(notebook)
    ok_count, skipped_count, errors = summarize_all(notebook)
    if ok_count:
        flash(f"Summarized {ok_count} file(s). {skipped_count} already had summaries.", "success")
    elif not errors:
        flash("All scraped bookmarks already have summaries.", "info")
    for message in errors:
        flash(f"Failed — {message}", "danger")
    return redirect(url_for("bookmarks.bookmarks", notebook=notebook))
