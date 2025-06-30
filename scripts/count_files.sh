#!/bin/bash

# Check if the directory exists
if [ ! -d "$1" ]; then
  echo "Error: $1 is not a valid directory."
  exit 1
fi

# Use find to count files directly
file_count=$(find "$1" -type f | wc -l)

# Print the total number of files
echo "Total number of files in $1 and its subdirectories: $file_count"

# Start a for loop that iterates from 1 to 100.
for i in $(seq 1 5); do
  # Print the current number.
  echo $i
  # Pause for 1 second.
  sleep 1
done