#!/bin/bash

DIRECTORY=${1:-.}  # Default to the current directory if no argument is provided

echo "Starting directory listing script at $(date)"
echo "Listing contents of: $DIRECTORY"
echo "-------------------------------------"

# List all files in the specified directory and log it
ls -alh "$DIRECTORY"
echo "-------------------------------------"
echo "Finished listing at $(date)"
echo "Keeping session alive..."

# Keep the session alive
tail -f /dev/null