#!/usr/bin/env python3
"""
Script to scrape URLs from text files and save as markdown using Firecrawl.
"""
import os
import re
import json
from pathlib import Path
from firecrawl import FirecrawlApp

FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY")

def url_to_filename(url):
    """
    Convert a URL to a safe filename (without extension).
    """
    # Lowercase
    filename = url.lower()
    # Remove protocol
    filename = re.sub(r'^https?://', '', filename)
    # Remove www.
    filename = re.sub(r'^www\.', '', filename)
    # Replace invalid filename characters with underscores
    filename = re.sub(r'[^\w\-.]', '_', filename)
    # Remove multiple consecutive underscores
    filename = re.sub(r'_+', '_', filename)
    # Remove leading/trailing underscores
    filename = filename.strip('_')
    # Limit length to avoid filesystem issues
    if len(filename) > 144:
        filename = filename[:144]
    return filename


def scrape_single_url(url: str, output_dir: Path, force: bool = False) -> tuple[bool, str | None]:
    """
    Scrape a single URL and write the markdown file to output_dir.

    Returns (success, error_message).  error_message is None on success.
    Skips if the .md file already exists and force=False.
    """
    api_key = os.environ.get("FIRECRAWL_API_KEY")
    if not api_key:
        return False, "FIRECRAWL_API_KEY environment variable is not set"

    filename = url_to_filename(url)
    output_md_file = output_dir / f"{filename}.md"

    if output_md_file.exists() and not force:
        return True, None  # already done, treat as success

    try:
        fc_app = FirecrawlApp(api_key=api_key)
        result = fc_app.scrape(url, formats=["markdown"])

        markdown_content = result.markdown
        if not markdown_content:
            return False, f"No markdown content returned for {url}"

        output_dir.mkdir(parents=True, exist_ok=True)
        with open(output_md_file, "w", encoding="utf-8") as f:
            f.write(f"# {url}\n\n")
            f.write(markdown_content)

        return True, None

    except Exception as exc:
        return False, str(exc)

