import logging
import yaml
from flask import Blueprint, abort, render_template, request

import config
from services.bookmark_store import load_bookmarks
from web.auth import login_required
from web.notebooks_ctx import _graphrag_status

index_bp = Blueprint("index", __name__)
logger = logging.getLogger(__name__)


def _notebook_descriptions() -> dict[str, str]:
    path = config._BASE_DIR / "notebook_descriptions.yaml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("Could not load notebook descriptions from %s: %s", path, exc)
        return {}
    if not isinstance(data, dict):
        logger.warning("Notebook descriptions in %s must be a YAML mapping", path)
        return {}
    return {name: description.strip() for name, description in data.items()
            if isinstance(name, str) and isinstance(description, str) and description.strip()}


@index_bp.route("/")
def index():
    descriptions = _notebook_descriptions() if config.NOTEBOOK_DESCRIPTIONS_ENABLED else {}
    notebook_rows = []
    for notebook in config.NOTEBOOKS:
        bookmarks = load_bookmarks(notebook)
        notebook_rows.append({
            "name": notebook,
            "bookmarks": len(bookmarks),
            "scraped": sum(bookmark["scraped"] for bookmark in bookmarks),
            "summarized": sum(bookmark["summarized"] for bookmark in bookmarks),
            "status": _graphrag_status(notebook),
            "description": descriptions.get(notebook),
        })
    return render_template("index.html", notebook_rows=notebook_rows)


@index_bp.route("/<notebook>/logs")
@login_required
def logs(notebook: str):
    if notebook not in config.NOTEBOOKS:
        abort(404)
    logs_dir = config._BASE_DIR / "grag" / notebook / "logs"
    log_files = {}
    if logs_dir.exists():
        for path in sorted(logs_dir.glob("*.log")):
            try:
                log_files[path.name] = path.read_text(errors="replace")
            except OSError as exc:
                log_files[path.name] = f"[Could not read file: {exc}]"
    return render_template("logs.html", log_files=log_files, current_notebook=notebook, notebooks=config.NOTEBOOKS)
