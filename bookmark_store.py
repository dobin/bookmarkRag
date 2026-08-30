"""Compatibility imports for the read-only MCP server.

Bookmark storage implementation lives in :mod:`services.bookmark_store`.
"""

from services.bookmark_store import (
	BookmarkStoreError,
	get_documents,
	list_bookmarks,
	search_document_page,
	search_documents,
)

__all__ = [
	"BookmarkStoreError",
	"get_documents",
	"list_bookmarks",
	"search_document_page",
	"search_documents",
]
