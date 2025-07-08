#!/bin/bash

# Long-running demo script for testing tmux session management
echo "=== Long Running Demo Script ==="
echo "This script will run for 30 seconds to demonstrate session management"
echo "Started at: $(date)"

# Simulate a long-running process
for i in {1..30}; do
    echo "Progress: $i/30 seconds - $(date)"
    sleep 1
done

echo "Long running script completed at: $(date)"
