import os
from pathlib import Path

# Resolve once at startup so relative paths aren't affected by cwd changes.
_BASE_DIR = Path(__file__).resolve().parent

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
BOOKMARK_RAG_DOMAIN = os.environ.get("BOOKMARK_RAG_DOMAIN", "").strip().rstrip("/")
APP_NAME = os.environ.get("BOOKMARK_RAG_APP_NAME", "").strip() or "BookmarkRAG"
APP_DESCRIPTION = (
    os.environ.get("BOOKMARK_RAG_APP_DESCRIPTION", "").strip()
    or "Browse indexed notebooks and access their bookmark knowledge bases."
)
NOTEBOOK_DESCRIPTIONS_ENABLED = os.environ.get(
    "NOTEBOOK_DESCRIPTIONS_ENABLED", "true"
).casefold() not in {"0", "false", "no", "off"}
HIDE_MYNOTEBOOK = os.environ.get("HIDE_MYNOTEBOOK", "false").casefold() in {
    "1", "true", "yes", "on"
}

ASK_METHODS = ["local", "global", "drift", "basic"]
_DATA_DIR = _BASE_DIR / "data"


def _visible_notebooks(data_dir: Path, *, hide_mynotebook: bool) -> list[str]:
    """Return data directories that should be available in the web application."""
    if not data_dir.is_dir():
        return []
    return sorted(
        path.name
        for path in data_dir.iterdir()
        if path.is_dir() and (not hide_mynotebook or path.name != "mynotebook")
    )


NOTEBOOKS = _visible_notebooks(_DATA_DIR, hide_mynotebook=HIDE_MYNOTEBOOK)
