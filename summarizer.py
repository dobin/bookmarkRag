#!/usr/bin/env python3
"""
LLM Summarizer for scraped markdown files.

Processes .md files in grag/<notebook>/input/ and generates
LLM summaries saved as .llm files in grag/<notebook>/summaries/.
"""

import os
from pathlib import Path
from typing import Optional

from openai import OpenAI

from scraper import url_to_filename


PROMPT = """
You are a senior red team operator and security researcher.

Your task is to analyze the provided link or its extracted content and generate a concise, short, structured summary.

The content may be:
- A GitHub repository for a security tool
- A technical blog post (e.g., Windows internals, EDR bypass, AD abuse)
- A conference talk
- A research paper
- A proof-of-concept exploit
- A detection or defensive write-up

OUTPUT FORMAT (strictly follow this structure):

Title:
<Extracted or inferred title>

Type:
<GitHub Tool / Blog Post / Research Paper / Conference Talk / Documentation / Other>

Short Summary (4–8 sentences max):
- What is this about?
- What problem does it solve?
- What techniques or concepts are discussed?
- Who is it useful for (Red Team, Pentester, Malware Dev, Blue Team, etc.)?
- Why is it interesting or important?

Technical Focus:
<List 3–6 core technical concepts covered>

Use Cases:
- Bullet list of practical applications

Keywords:
<10–20 important keywords, comma-separated>
(Include technologies, protocols, APIs, attack techniques, CVEs, Windows internals components, etc.)

Be concise. Avoid marketing language. Focus on technical value.
Do not repeat generic cybersecurity explanations.
"""


class LlmSummarizer:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenAI API key not provided. Set OPENAI_API_KEY environment variable."
            )
        self.client = OpenAI(api_key=self.api_key)

    def summarize(self, content: str, max_retries: int = 3) -> Optional[str]:
        max_chars = 256_000
        if len(content) > max_chars:
            content = content[:max_chars] + "\n\n[... content truncated ...]"

        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model="gpt-5.2",
                    messages=[
                        {"role": "user", "content": f"{PROMPT}\n\nContent:\n{content}"}
                    ],
                    temperature=0.2,
                )
                return (
                    response.choices[0].message.content.strip()
                    if response.choices[0].message.content
                    else None
                )
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"  Warning: API call failed (attempt {attempt + 1}/{max_retries}): {e}, retrying...")
                else:
                    print(f"  Error: OpenAI API failed after {max_retries} attempts: {e}")
                    return None

        return None


def summarize_url(url: str, notebook: str, force: bool = False) -> tuple[bool, str | None]:
    """
    Generate an LLM summary for a single URL.

    Reads grag/<notebook>/input/<url_to_filename(url)>.md and writes the
    summary to grag/<notebook>/summaries/<url_to_filename(url)>.llm.

    Returns (success, error_message). error_message is None on success.
    Skips (returns True, None) if the .llm already exists and force=False.
    """
    base = url_to_filename(url)
    input_path = Path("grag") / notebook / "input" / f"{base}.md"
    summaries_dir = Path("grag") / notebook / "summaries"
    llm_path = summaries_dir / f"{base}.llm"

    if llm_path.exists() and not force:
        return True, None  # already summarized

    if not input_path.exists():
        return False, f"Scraped file not found: {input_path}"

    try:
        content = input_path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return False, f"Could not read {input_path}: {exc}"

    try:
        summarizer = LlmSummarizer()
    except ValueError as exc:
        return False, str(exc)

    summary = summarizer.summarize(content)
    if summary is None:
        return False, "LLM returned no summary"

    summaries_dir.mkdir(parents=True, exist_ok=True)
    llm_path.write_text(summary, encoding="utf-8")
    return True, None


def summarize_all(notebook: str) -> tuple[int, int, list[str]]:
    """
    Summarize all scraped .md files in grag/<notebook>/input/ that do not yet
    have a corresponding .llm file in grag/<notebook>/summaries/.

    Returns (ok_count, skipped_count, error_messages).
    """
    input_dir = Path("grag") / notebook / "input"
    summaries_dir = Path("grag") / notebook / "summaries"

    if not input_dir.exists():
        return 0, 0, [f"Input directory does not exist: {input_dir}"]

    md_files = sorted(input_dir.glob("*.md"))
    if not md_files:
        return 0, 0, []

    try:
        summarizer = LlmSummarizer()
    except ValueError as exc:
        return 0, 0, [str(exc)]

    summaries_dir.mkdir(parents=True, exist_ok=True)

    ok_count = 0
    skipped_count = 0
    errors: list[str] = []

    for md_path in md_files:
        llm_path = summaries_dir / md_path.with_suffix(".llm").name
        if llm_path.exists():
            skipped_count += 1
            continue

        try:
            content = md_path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            errors.append(f"{md_path.name}: could not read — {exc}")
            continue

        summary = summarizer.summarize(content)
        if summary is None:
            errors.append(f"{md_path.name}: LLM returned no summary")
        else:
            llm_path.write_text(summary, encoding="utf-8")
            ok_count += 1

    return ok_count, skipped_count, errors
