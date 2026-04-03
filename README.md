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

## Cost

Using `grag/maldev/`, with 11MB of `input/` data:
* Indexing cost 130$ (`text-embedding-3-small`)
* One query cost around 5$ (`gpt-5.4-mini`, 5M input tokens, 200K output tokens)


## Update Dependencies

Update libraries:
```
$ uv pip install --upgrade graphrag firecrawl openai
```
