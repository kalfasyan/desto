#!/bin/bash
# Usage: ./search_pattern.sh <directory> <pattern>
dir="$1"
pattern="$2"
grep -rnw "$dir" -e "$pattern"
