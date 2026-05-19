# BookmarkRag

A knowledge management system.

* Add links
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


## Directories

* `bookmarks/`: <notebook>.txt with links
* `grag/<notebook>/`: graphrag directory
  * `input/`: downloaded content as markdown
  * `summaries/`: The LLM generated summary

## Setup

Setup an initial document database called `mynotebook`:

```
$ mkdir grag/mynotebook
$ cd grag/mynotebook
grag/mynotebook$ graphrag init
grag/mynotebook$ cp <documents>/* input/
grag/mynotebook$ graphrag index
```

To update:
```
grag/mynotebook$ graphrag index
```

If input is `.md` files, edit `settings.yaml`:
```
input:
  type: text # [csv, text, json, jsonl]
  file_pattern: ".*\\.md$$"
```


## Start

```
$ python app.py
```

Browse to http://localhost:5000


## Cost

Using `grag/maldev/`, with 11MB of `input/` data:
* Using `gpt-5.4-mini` and `text-embedding-3-small`
* Indexing cost 130$
* One query cost around 5$

Using `grag/maldev/`, with 3MB of `input/` data:
* Using `gpt-5-mini` (input 0.25$, output 2$) and `text-embedding-3-small`:
* indexing 100 documents (3MB): 16$


## Update Dependencies

Update libraries:
```
$ uv pip install --upgrade graphrag firecrawl openai
```
