#!/usr/bin/env python3
"""Parse a graphrag query.log and report per-query token costs and durations."""

import json
import re
import sys

PRICE_INPUT_PER_M  = 0.75   # $ per 1M prompt tokens
PRICE_OUTPUT_PER_M = 4.50   # $ per 1M completion tokens

# Matches the header line of a metrics block, e.g.:
# 2026-04-03 07:38:07.0666 - INFO - ... - Metrics for openai/gpt-5.4-mini: {
HEADER_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)"   # timestamp
    r".+?Metrics for ([^:]+):\s*(\{.*)$"               # model + start of JSON
)


def parse_log(path: str) -> list[dict]:
    """Return a list of parsed metric records from the log file."""
    records = []

    with open(path, encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()

    i = 0
    while i < len(lines):
        m = HEADER_RE.match(lines[i].rstrip())
        if not m:
            i += 1
            continue

        timestamp, model, json_start = m.group(1), m.group(2).strip(), m.group(3)

        # Accumulate lines until the JSON object closes
        brace_depth = json_start.count("{") - json_start.count("}")
        json_lines = [json_start]
        i += 1
        while i < len(lines) and brace_depth > 0:
            line = lines[i].rstrip()
            brace_depth += line.count("{") - line.count("}")
            json_lines.append(line)
            i += 1

        try:
            data = json.loads("\n".join(json_lines))
        except json.JSONDecodeError:
            continue

        records.append({
            "timestamp": timestamp,
            "model": model,
            "prompt_tokens": data.get("prompt_tokens", 0),
            "completion_tokens": data.get("completion_tokens", 0),
            "requests": data.get("attempted_request_count", 0),
        })

    return records


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <query.log>")
        sys.exit(1)

    records = parse_log(sys.argv[1])

    if not records:
        print("No metric records found.")
        sys.exit(0)

    total_cost = 0.0
    total_input_tokens = 0
    total_output_tokens = 0

    print(f"{'Timestamp':<26} {'Model':<35} {'Input tok':>10} {'Output tok':>11} {'Cost ($)':>9}")
    print("-" * 95)

    for r in records:
        cost = (r["prompt_tokens"] / 1_000_000 * PRICE_INPUT_PER_M
                + r["completion_tokens"] / 1_000_000 * PRICE_OUTPUT_PER_M)

        print(
            f"{r['timestamp']:<26} "
            f"{r['model']:<35} "
            f"{r['prompt_tokens']:>10,} "
            f"{r['completion_tokens']:>11,} "
            f"{cost:>9.4f}"
        )

        total_cost += cost
        total_input_tokens += r["prompt_tokens"]
        total_output_tokens += r["completion_tokens"]

    print("-" * 95)
    print(
        f"{'TOTAL':<26} {'':<35} "
        f"{total_input_tokens:>10,} "
        f"{total_output_tokens:>11,} "
        f"{total_cost:>9.4f}"
    )
    print(f"\nTotal cost: ${total_cost:.4f}")
    print(f"  Input:  {total_input_tokens:,} tokens  @ ${PRICE_INPUT_PER_M}/M  = ${total_input_tokens / 1_000_000 * PRICE_INPUT_PER_M:.4f}")
    print(f"  Output: {total_output_tokens:,} tokens  @ ${PRICE_OUTPUT_PER_M}/M  = ${total_output_tokens / 1_000_000 * PRICE_OUTPUT_PER_M:.4f}")


if __name__ == "__main__":
    main()
