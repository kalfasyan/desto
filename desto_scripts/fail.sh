#!/bin/bash
# Start a for loop that iterates from 1 to 3.
for i in $(seq 1 3); do
  # Print the current number.
  echo $i
  # Pause for 1 second.
  sleep 1
done
# Force the script to fail
exit 1
