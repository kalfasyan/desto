#!/bin/bash

SEARCH_DIR=${1:-.}

echo "Searching for files matching '*.sh*' in: $SEARCH_DIR"
echo "Started at: $(date)"
echo "-------------------------------------"

find "$SEARCH_DIR" -type f -name "*.sh*" -print

echo "-------------------------------------"
echo "Finished at: $(date)"







# Keeps the session alive
tail -f /dev/null
