"""Compatibility imports for the read-only MCP server.

Bookmark storage implementation lives in :mod:`services.bookmark_store`.
"""

from services.bookmark_store import BookmarkStoreError, list_bookmarks, search_documents

__all__ = ["BookmarkStoreError", "list_bookmarks", "search_documents"]
