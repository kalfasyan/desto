"""Utility script to synchronize the root README into the docs folder.

This provides a stable relative include path (`README.md`) for documentation
generation without relying on parent-directory traversal, which some
Markdown include mechanisms disallow or sandbox.
"""

import shutil
from pathlib import Path


def main():
    """Copy root `README.md` to `docs/README.md` preserving filename."""
    root = Path(__file__).parent.parent
    src = root / "README.md"
    dest_dir = root / "docs"
    dest = dest_dir / "README.md"
    if not src.exists():
        raise SystemExit("Root README.md not found")
    dest_dir.mkdir(exist_ok=True)
    shutil.copyfile(src, dest)
    print(f"Copied {src} -> {dest}")


if __name__ == "__main__":
    main()
