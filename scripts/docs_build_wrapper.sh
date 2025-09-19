#!/usr/bin/env bash
set -euo pipefail

# Temporary wrapper to run a strict MkDocs build while avoiding the
# README vs index conflict. It temporarily moves the repo root README out of
# the way, syncs the docs index, runs the build, and restores the README.

ROOT_README=README.md
BACKUP_README=README.md.bak

if [[ -f "$BACKUP_README" ]]; then
  echo "Backup file $BACKUP_README already exists. Aborting to avoid data loss."
  exit 1
fi

# First, sync README into docs/index.md (this reads the root README).
python3 scripts/sync_readme_to_docs.py

# Now temporarily move the root README to avoid MkDocs detecting it as a
# conflicting page during the strict build.
mv "$ROOT_README" "$BACKUP_README"
echo "Temporarily moved $ROOT_README -> $BACKUP_README"

uv run mkdocs build -f mkdocs.yml --strict

# Restore the root README
mv "$BACKUP_README" "$ROOT_README"
echo "Restored $BACKUP_README -> $ROOT_README"

echo "Docs build completed successfully."
