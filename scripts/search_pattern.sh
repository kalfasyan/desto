#!/bin/bash

if [ "$#" -lt 2 ]; then
    echo "Usage: $0 <directory> <pattern> [extension]"
    exit 1
fi

SEARCH_DIR="$1"
PATTERN="$2"
EXTENSION="${3:-*}"  # Optional third argument, defaults to all files

echo "Searching for pattern '$PATTERN' in directory '$SEARCH_DIR' (files: *.$EXTENSION)"
echo "Started at: $(date)"
echo "-------------------------------------"

find "$SEARCH_DIR" -type f -name "*.$EXTENSION" -print0 | xargs -0 grep -H --color=never "$PATTERN"

echo "-------------------------------------"
echo "Finished at: $(date)"
