#!/bin/bash

# Example bash script for desto Docker demo
echo "=== Docker Demo Script ==="
echo "Starting at: $(date)"
echo "Container hostname: $(hostname)"
echo "Current directory: $(pwd)"
echo "Available environment variables:"
env | grep DESTO
echo ""

echo "Creating some demo output..."
for i in {1..5}; do
    echo "Step $i: Processing data..."
    sleep 2
done

echo "Demo completed successfully at: $(date)"
