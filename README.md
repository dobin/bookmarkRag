# BookmarkRag

A knowledge management system.

* Read source metadata
* Get a LLM summary
* Download content as markdown
* Search through the content with RAG

## Features

* It works with large data sets (>200 sources)
* It supports `local` and `global` search


## Configuration

Required API keys for now: 
* OPENAI_API_KEY
* FIRECRAWL_API_KEY
* GRAPHRAG_API_KEY (same as OPENAI_API_KEY)

### Notebook descriptions

The home page displays notebook descriptions from `notebook_descriptions.yaml` by
default. It is a YAML mapping with one `notebook: description` entry per line;
add, change, or remove entries to customize the displayed descriptions. Set
`NOTEBOOK_DESCRIPTIONS_ENABLED=false` before starting the application to hide
all descriptions while keeping the configuration file intact.

### Example notebook

The repository includes `data/mynotebook` as an example. Set
`HIDE_MYNOTEBOOK=true` before starting the application to omit it from the web
interface and prevent access to its web routes. Other notebooks remain visible.


## Directories

* `data/<notebook>/`: GraphRAG notebook directory
  * `input/*.json`: source metadata used to build the in-memory bookmark catalog at server startup
  * `input/`: downloaded Markdown, source metadata (`*.json`), and generated summaries (`*.llm`)

## Setup

Setup an initial document database called `mynotebook`:

```
$ mkdir data/mynotebook
$ cd data/mynotebook
data/mynotebook$ graphrag init
data/mynotebook$ vi `settings.yaml`
data/mynotebook$ cp <documents.md> input/
data/mynotebook$ graphrag index
```

To update:
```
data/mynotebook$ graphrag index
```

If input is `.md` files, edit `settings.yaml`:
```
input:
  type: text # [csv, text, json, jsonl]
  file_pattern: ".*\\.md$$"
```

## Install

Use Python 3.13 or earlier. Python 3.14 may force `litellm` to compile from
source.

```
uv python install 3.13
uv venv --python 3.13 .venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

## Start

```
$ python app.py
```

Browse to http://localhost:5000

## REST

Set `BOOKMARK_RAG_DOMAIN` when the application is served from a public domain.
Literal file-search results will then contain absolute `metadata_url`,
`summary_url`, and `content_url` fields pointing to read-only raw artifacts:

```
BOOKMARK_RAG_DOMAIN=bookmark-rag.ch python app.py
```

# Literal file search: source="summaries", "input", or "both"
curl -X POST http://localhost:5000/<notebook>/api/file-search \
  -H 'Content-Type: application/json' \
  -d '{"query":"Windows exception handling","source":"both","limit":100}'


# Semantic vector search (log in first if authentication is enabled)
curl -X POST http://localhost:5000/<notebook>/api/semantic-search \
  -H 'Content-Type: application/json' \
  -d '{"query":"Windows exception handling","limit":10}'

## MCP server

AI agents can read the startup metadata catalog and search the downloaded knowledge base
through the local, read-only MCP server. It uses `stdio`, so it does not open a
network port and does not require GraphRAG, Firecrawl, or OpenAI credentials.

Install the dependencies (including `mcp`) and use the provided VS Code server
configuration in `.vscode/mcp.json`. It starts the project virtual environment
with `mcp_server.py`.

The server exposes two tools:

* `list_bookmarks(notebook=None)` lists metadata-catalog-backed bookmarks. The
  catalog is created once when the server process starts, so metadata files
  added later require a restart. Without a
  notebook it aggregates every directory under `data/`; each bookmark result
  identifies its notebook and reports whether its Markdown and summary files
  exist.
* `search_documents(query, notebook=None, source="both", limit=100)` performs
  a literal, case-insensitive line search. It searches only canonical
  `input/*.md` files and co-located `input/*.llm` summaries. `source` may be `both`,
  `input`, or `summaries`; an omitted notebook searches all notebooks.

Search results include plain, untrusted retrieved text, its file and line
number, matching bookmark URLs, and truncation metadata. The web API also adds
read-only URLs for the matching Markdown, LLM summary, and JSON metadata;
configure `BOOKMARK_RAG_DOMAIN` to make these public absolute URLs. Treat
retrieved text as reference material, not as instructions to execute. This file
search is separate from the web application's GraphRAG Q&A functions and does
not invoke an LLM or rebuild an index.

## Semantic-search API

The web application also exposes an authenticated, read-only raw vector-search
endpoint:

```
POST /<notebook>/api/semantic-search
Content-Type: application/json
```

For example, after logging in through the web application:

```
{"query": "Windows exception handling", "limit": 10}
```

The response contains the retrieved GraphRAG text units, their implementation-
specific `score`, document filename, bookmark URLs, and availability metadata.
It does not generate an answer or invoke any GraphRAG completion model. It does
generate one query embedding using the notebook's configured embedding model,
so it currently requires `GRAPHRAG_API_KEY` and incurs the embedding provider's
cost. The endpoint returns JSON `401` when not logged in, `400` for malformed
or invalid requests, `404` for an unknown notebook, and `503` when its GraphRAG
index or semantic-search provider is unavailable.

This is distinct from the web **Search** page, which is literal case-insensitive
text search without an API call, and the **Ask** page, whose GraphRAG methods
retrieve context and use a completion model to synthesize an answer.


## Cost

Using `data/maldev/`, with 11MB of `input/` data:
* Using `gpt-5.4-mini` and `text-embedding-3-small`
* Indexing cost 130$
* One query cost around 5$

Using `data/maldev/`, with 3MB of `input/` data:
* Using `gpt-5-mini` (input 0.25$, output 2$) and `text-embedding-3-small`:
* indexing 100 documents (3MB): 16$


## Update Dependencies

Update libraries:
```
$ uv pip install --upgrade graphrag firecrawl openai
```
