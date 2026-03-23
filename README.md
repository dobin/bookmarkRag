# BookmarkRag

* Add links
* Get a LLM summary
* Download content as markdown
* Search through the content with RAG


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


