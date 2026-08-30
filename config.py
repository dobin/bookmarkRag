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
_GRAG_DIR = _BASE_DIR / "grag"
NOTEBOOKS = sorted(p.name for p in _GRAG_DIR.iterdir() if p.is_dir()) if _GRAG_DIR.is_dir() else []
