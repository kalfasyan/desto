"""Utility script to synchronize the root README into the docs folder.

This provides a stable relative include path (`README.md`) for documentation
generation without relying on parent-directory traversal, which some
Markdown include mechanisms disallow or sandbox.
"""

from pathlib import Path


def main():
    """Copy root `README.md` to `docs/README.md` preserving filename."""
    root = Path(__file__).parent.parent
    src = root / "README.md"
    dest_dir = root / "docs"
    # Write the README into the docs index so MkDocs has a single homepage
    # source and we avoid README/index conflicts under strict mode.
    dest = dest_dir / "index.md"
    if not src.exists():
        raise SystemExit("Root README.md not found")
    dest_dir.mkdir(exist_ok=True)
    # Read and rewrite image paths for the docs site only. The root README is
    # preserved for GitHub; the docs copy should reference images relative to
    # the `docs/` directory (i.e. `images/...`). Also rewrite reference to
    # the configuration file so docs link to the generated `pyproject.md`.
    text = src.read_text(encoding="utf8")
    text = text.replace("docs/images/", "images/")
    text = text.replace("pyproject.toml", "pyproject.md")
    dest.write_text(text, encoding="utf8")
    print(f"Copied {src} -> {dest} (rewrote docs/images/ -> images/ and pyproject.toml -> pyproject.md)")


if __name__ == "__main__":
    main()
