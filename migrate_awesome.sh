#!/usr/bin/env bash
# Copy AwesomeMalDevLinks topic data into matching GraphRAG input directories.
#
# Usage:
#   ./migrate_awesome.sh [awesome-maldev-data-directory]
#
# Existing files with the same names are overwritten; unrelated files already 
# in an input directory are retained.

set -euo pipefail

SOURCE_DIR="${1:-/mnt/c/Users/dobin/Repos/AwesomeMalDevLinks/data/out}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="$REPO_DIR/data"

if [[ ! -d "$SOURCE_DIR" ]]; then
	printf 'Source directory does not exist: %s\n' "$SOURCE_DIR" >&2
	exit 1
fi

if [[ ! -d "$DATA_DIR" ]]; then
	printf 'Data directory does not exist: %s\n' "$DATA_DIR" >&2
	exit 1
fi

copied=0
while IFS= read -r -d '' topic_dir; do
	topic="$(basename "$topic_dir")"
	source_topic_dir="$SOURCE_DIR/$topic"

	if [[ ! -d "$source_topic_dir" ]]; then
		printf 'Skipping %s: no matching source directory.\n' "$topic"
		continue
	fi

	destination_dir="$topic_dir/input"
	mkdir -p "$destination_dir"
	cp -a "$source_topic_dir/." "$destination_dir/"
	printf 'Copied %s -> %s\n' "$source_topic_dir" "$destination_dir"
	((copied += 1))
done < <(find "$DATA_DIR" -mindepth 1 -maxdepth 1 -type d -print0)

printf 'Finished: copied %d topic(s).\n' "$copied"
