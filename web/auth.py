from functools import wraps

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, session, url_for

import config

auth_bp = Blueprint("auth", __name__)


def _is_authenticated() -> bool:
    """Return whether this request may access administrative features."""
    return not config.ADMIN_PASSWORD or session.get("authenticated", False)


def login_required(f):
    """Decorator: redirect to /login if not authenticated."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _is_authenticated():
            flash("Please log in to access this feature.", "warning")
            return redirect(url_for("auth.login", next=request.url))
        return f(*args, **kwargs)

    return decorated


def api_login_required(f):
    """Decorator: return JSON 401 rather than redirecting API clients to login."""
    @wraps(f)
    def decorated(*args, **kwargs):
        notebook = kwargs.get("notebook")
        if isinstance(notebook, str) and notebook not in config.NOTEBOOKS:
            abort(404)
        if not _is_authenticated():
            return jsonify(error="authentication_required"), 401
        return f(*args, **kwargs)

    return decorated


def write_required(f):
    """Decorator: redirect to /login if not authenticated (for bookmark write ops)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _is_authenticated():
            flash("Please log in to modify bookmarks.", "warning")
            return redirect(url_for("auth.login", next=request.url))
        return f(*args, **kwargs)

    return decorated


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == config.ADMIN_PASSWORD:
            session["authenticated"] = True
            next_url = request.args.get("next")
            if next_url:
                return redirect(next_url)
            return redirect(url_for("index.index"))
        flash("Incorrect password.", "danger")
    return render_template("login.html")


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.pop("authenticated", None)
    flash("Logged out.", "info")
    return redirect(url_for("index.index"))
