import os
from pathlib import Path

# Resolve once at startup so relative paths aren't affected by cwd changes.
_BASE_DIR = Path(__file__).resolve().parent

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
BOOKMARK_RAG_DOMAIN = os.environ.get("BOOKMARK_RAG_DOMAIN", "").strip().rstrip("/")
NOTEBOOK_DESCRIPTIONS_ENABLED = os.environ.get(
    "NOTEBOOK_DESCRIPTIONS_ENABLED", "true"
).casefold() not in {"0", "false", "no", "off"}

ASK_METHODS = ["local", "global", "drift", "basic"]
_DATA_DIR = _BASE_DIR / "data"
NOTEBOOKS = sorted(p.name for p in _DATA_DIR.iterdir() if p.is_dir()) if _DATA_DIR.is_dir() else []
