from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

import app
import config
from services import bookmark_store
from services import graphrag_api
from web import views_api


@pytest.fixture
def semantic_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "data"
    notebook_dir = data_dir / "alpha"
    output_dir = notebook_dir / "output"
    (output_dir / "lancedb").mkdir(parents=True)
    (notebook_dir / "input").mkdir()
    (notebook_dir / "input" / "example.test_page.md").write_text("source", encoding="utf-8")
    (notebook_dir / "input" / "example.test_page.llm").write_text("summary", encoding="utf-8")
    (notebook_dir / "input" / "example.test_page.json").write_text(
        '{"url": "https://example.test/page", "title": "Example"}', encoding="utf-8"
    )
    pd.DataFrame([{
        "id": "text-unit-id", "human_readable_id": 7,
        "document_id": "document-id", "text": "Retrieved source chunk.",
    }]).to_parquet(output_dir / "text_units.parquet")
    pd.DataFrame([{
        "id": "document-id", "title": "example.test_page.md",
    }]).to_parquet(output_dir / "documents.parquet")

    monkeypatch.setattr(bookmark_store, "BASE_DIR", tmp_path)
    monkeypatch.setattr(bookmark_store, "DATA_DIR", data_dir)
    bookmark_store.initialize_catalog()
    monkeypatch.setattr(graphrag_api, "_BASE_DIR", tmp_path)
    monkeypatch.setattr(config, "_BASE_DIR", tmp_path)
    monkeypatch.setattr(config, "NOTEBOOKS", ["alpha"])
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "test-password")
    app.app.config.update(TESTING=True, SECRET_KEY="test-secret")
    return tmp_path


def _mock_vector_retrieval(monkeypatch: pytest.MonkeyPatch) -> None:
    embedding_config = SimpleNamespace()
    config = SimpleNamespace(
        embed_text=SimpleNamespace(embedding_model_id="default"),
        vector_store=SimpleNamespace(),
        get_embedding_model_config=lambda model_id: embedding_config,
    )
    embedding_model = SimpleNamespace(
        embedding=lambda *, input: SimpleNamespace(first_embedding=[0.1, 0.2])
    )
    match = SimpleNamespace(
        document=SimpleNamespace(id="text-unit-id"),
        score=0.8,
    )
    vector_store = SimpleNamespace(
        similarity_search_by_vector=lambda vector, *, k, include_vectors: [match]
    )
    monkeypatch.setattr(graphrag_api, "load_config", lambda *, root_dir: config)
    monkeypatch.setattr(graphrag_api, "create_embedding", lambda value: embedding_model)
    monkeypatch.setattr(
        graphrag_api,
        "get_embedding_store",
        lambda *, config, embedding_name: vector_store,
    )


def test_semantic_search_returns_raw_matches(semantic_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_vector_retrieval(monkeypatch)

    result = graphrag_api.semantic_search("related concept", "alpha", limit=1)

    assert result["query"] == "related concept"
    assert result["returned_results"] == 1
    assert result["results"] == [{
        "id": "text-unit-id", "short_id": "7", "score": 0.8,
        "document_id": "document-id", "filename": "example.test_page.md",
        "text": "Retrieved source chunk.",
        "bookmark_urls": ["https://example.test/page"],
        "content_exists": True, "summary_exists": True,
    }]


def test_semantic_search_rejects_invalid_input(semantic_root: Path) -> None:
    with pytest.raises(bookmark_store.BookmarkStoreError, match="query must not be empty"):
        graphrag_api.semantic_search("  ", "alpha")
    with pytest.raises(bookmark_store.BookmarkStoreError, match="limit must be an integer from 1 to 2000"):
        graphrag_api.semantic_search("query", "alpha", limit=2001)


def test_semantic_endpoint_validates_authentication_and_input(
    semantic_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = app.app.test_client()

    response = client.post("/alpha/api/semantic-search", json={"query": "test"})
    assert response.status_code == 401
    assert response.get_json() == {"error": "authentication_required"}

    response = client.post("/unknown/api/semantic-search", json={"query": "test"})
    assert response.status_code == 404

    with client.session_transaction() as session:
        session["authenticated"] = True
    response = client.post("/alpha/api/semantic-search", data="{}", content_type="text/plain")
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_request"

    response = client.post("/alpha/api/semantic-search", json={"query": ""})
    assert response.status_code == 400
    assert response.get_json()["message"] == "query must not be empty"


def test_file_search_endpoint_supports_summary_and_content_sources(semantic_root: Path) -> None:
    client = app.app.test_client()

    response = client.post(
        "/alpha/api/file-search",
        json={"query": "summary", "source": "summaries"},
    )
    assert response.status_code == 200
    summary_match = response.get_json()["matches"][0]
    assert summary_match["filename"] == "example.test_page.llm"
    assert summary_match["metadata_url"] == "http://localhost/alpha/api/documents/example.test_page.json"
    assert summary_match["summary_url"] == "http://localhost/alpha/api/documents/example.test_page.llm"
    assert summary_match["content_url"] == "http://localhost/alpha/api/documents/example.test_page.md"

    response = client.post(
        "/alpha/api/file-search",
        json={"query": "source", "source": "input"},
    )
    assert response.status_code == 200
    assert response.get_json()["matches"][0]["filename"] == "example.test_page.md"


def test_file_search_uses_configured_domain_and_artifact_urls(semantic_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "BOOKMARK_RAG_DOMAIN", "bookmark-rag.ch")
    client = app.app.test_client()

    response = client.post("/alpha/api/file-search", json={"query": "source", "source": "input"})

    match = response.get_json()["matches"][0]
    assert match["metadata_exists"] is True
    assert match["metadata_url"] == "https://bookmark-rag.ch/alpha/api/documents/example.test_page.json"
    assert match["summary_url"] == "https://bookmark-rag.ch/alpha/api/documents/example.test_page.llm"
    assert match["content_url"] == "https://bookmark-rag.ch/alpha/api/documents/example.test_page.md"

    content_response = client.get("/alpha/api/documents/example.test_page.md")
    assert content_response.status_code == 200
    assert content_response.get_data(as_text=True) == "source"

    metadata_response = client.get("/alpha/api/documents/example.test_page.json")
    assert metadata_response.status_code == 200
    assert metadata_response.get_json()["url"] == "https://example.test/page"

    assert client.get("/alpha/api/documents/../app.py").status_code == 404


def test_index_loads_configured_notebook_descriptions(
    semantic_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (semantic_root / "notebook_descriptions.yaml").write_text(
        'alpha: "A test notebook."\n', encoding="utf-8"
    )
    monkeypatch.setattr(config, "NOTEBOOK_DESCRIPTIONS_ENABLED", True)

    response = app.app.test_client().get("/")

    assert response.status_code == 200
    assert b"A test notebook." in response.data


def test_index_hides_descriptions_when_disabled(
    semantic_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (semantic_root / "notebook_descriptions.yaml").write_text(
        'alpha: "A test notebook."\n', encoding="utf-8"
    )
    monkeypatch.setattr(config, "NOTEBOOK_DESCRIPTIONS_ENABLED", False)

    response = app.app.test_client().get("/")

    assert response.status_code == 200
    assert b"A test notebook." not in response.data


def test_semantic_endpoint_returns_results_and_hides_backend_errors(
    semantic_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_vector_retrieval(monkeypatch)
    client = app.app.test_client()
    with client.session_transaction() as session:
        session["authenticated"] = True

    response = client.post("/alpha/api/semantic-search", json={"query": "test", "limit": 1})
    assert response.status_code == 200
    assert response.get_json()["results"][0]["text"] == "Retrieved source chunk."

    monkeypatch.setattr(
        views_api,
        "semantic_search",
        lambda query, notebook, limit: (_ for _ in ()).throw(
            graphrag_api.SemanticSearchError("sensitive provider detail")
        ),
    )
    response = client.post("/alpha/api/semantic-search", json={"query": "test"})
    assert response.status_code == 503
    assert response.get_json() == {"error": "semantic_search_unavailable"}