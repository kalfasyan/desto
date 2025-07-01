# Version Management

This project uses a centralized version management system with automated tooling.

## Current Setup

- **Version source**: `src/desto/_version.py` (single source of truth)
- **Build system**: Automatically reads version from `_version.py`
- **Package version**: Dynamically determined at build time

## Quick Commands

```bash
# Show current version
make version

# Bump version (updates _version.py only)
make bump-patch    # 0.1.14 -> 0.1.15
make bump-minor    # 0.1.14 -> 0.2.0  
make bump-major    # 0.1.14 -> 1.0.0

# Full release process (bump + test + build + commit + tag)
make release-patch
make release-minor  
make release-major

# Development
make test          # Run tests
make lint          # Run linting
make build         # Build package
make publish       # Publish to PyPI
```

## Manual Process

If you prefer to do it manually:

1. **Update version**: Edit `src/desto/_version.py`
2. **Test**: `uv run pytest tests/`
3. **Lint**: `uv run ruff check .`
4. **Build**: `uv build`
5. **Commit**: `git add . && git commit -m "Bump version to X.Y.Z"`
6. **Tag**: `git tag vX.Y.Z`
7. **Push**: `git push && git push --tags`
8. **Publish**: `uv publish`

## Tools

- `scripts/bump_version.py` - Version bumping utility
- `scripts/release.sh` - Full release automation
- `Makefile` - Convenient command shortcuts
