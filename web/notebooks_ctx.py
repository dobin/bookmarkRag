import json
import logging
from datetime import datetime

from flask import request

import config
from web.auth import _is_authenticated

logger = logging.getLogger(__name__)


def _graphrag_status(notebook: str) -> dict | None:
    """Return a concise readiness summary for a notebook's GraphRAG output."""
    if not notebook:
        return None

    output_dir = config._BASE_DIR / "data" / notebook / "output"
    required_files = (
        "documents.parquet",
        "text_units.parquet",
        "entities.parquet",
        "relationships.parquet",
        "communities.parquet",
        "community_reports.parquet",
    )
    missing = [name for name in required_files if not (output_dir / name).is_file()]
    if not (output_dir / "lancedb").is_dir():
        missing.append("lancedb")

    stats: dict = {}
    try:
        stats = json.loads((output_dir / "stats.json").read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        pass

    newest_output = max(
        (path.stat().st_mtime for path in output_dir.iterdir()),
        default=None,
    ) if output_dir.is_dir() else None

    return {
        "ready": not missing,
        "missing": missing,
        "documents": stats.get("num_documents"),
        "updated": datetime.fromtimestamp(newest_output).strftime("%Y-%m-%d %H:%M") if newest_output else None,
    }


def inject_notebooks():
    """Make notebooks and current_notebook available to all templates."""
    notebook = request.view_args.get("notebook", "") if request.view_args else ""
    return {
        "app_name": config.APP_NAME,
        "app_description": config.APP_DESCRIPTION,
        "notebooks": config.NOTEBOOKS,
        "current_notebook": notebook,
        "is_authenticated": _is_authenticated(),
        "authentication_enabled": bool(config.ADMIN_PASSWORD),
        "graphrag_status": _graphrag_status(notebook),
    }
