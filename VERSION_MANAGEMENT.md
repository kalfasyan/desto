# Version Management & Publishing

This project uses a centralized version management system with fully automated publishing to PyPI.

## Current Setup

- **Version source**: `src/desto/_version.py` (single source of truth)
- **Build system**: Automatically reads version from `_version.py`
- **Package version**: Dynamically determined at build time
- **Publishing**: Fully automated via GitHub Actions (no MFA issues!)

## 🛠️ Development Setup

To work on the project locally:

```bash
# Install with dev dependencies (includes ruff for linting)
make dev-install

# Or manually:
uv sync --extra dev
```

## Quick Commands (Automated)

```bash
# Full automated release (recommended)
make release-patch    # 0.1.15 -> 0.1.16 + auto-publish to PyPI
make release-minor    # 0.1.15 -> 0.2.0 + auto-publish to PyPI  
make release-major    # 0.1.15 -> 1.0.0 + auto-publish to PyPI

# Just version bumping (no publishing)
make bump-patch       # Updates _version.py only
make bump-minor       # Updates _version.py only
make bump-major       # Updates _version.py only

# Development and utilities
make test             # Run tests
make lint             # Run linting
make build            # Build package
make version          # Show current version
make check-release    # Check if current version is on PyPI
```

## 🤖 Automated Publishing

🎉 **PyPI publishing is fully automated!** When you run `make release-*` commands:

1. ✅ Version gets bumped in `_version.py`
2. ✅ Tests and linting run automatically  
3. ✅ Changes are committed and tagged
4. ✅ Code is pushed to GitHub
5. ✅ **GitHub Actions automatically publishes to PyPI** (no MFA issues!)

📖 **Setup Guide**: See setup instructions below for PyPI trusted publishing.

## 🔧 PyPI Publishing Setup (One-time)

### Configure PyPI Trusted Publishing

1. **Go to PyPI**: Visit [https://pypi.org/manage/project/desto/](https://pypi.org/manage/project/desto/)
2. **Navigate to Publishing**: Click "Publishing" tab
3. **Add Trusted Publisher**: Click "Add a new pending publisher"
4. **Fill in details**:
   - **PyPI Project Name**: `desto`
   - **Owner**: `kalfasyan` (your GitHub username)
   - **Repository name**: `desto`
   - **Workflow filename**: `publish.yml`
   - **Environment name**: Leave empty

**That's it!** No API tokens needed, no MFA issues.

## 🎯 Benefits

- **No more MFA issues**: Trusted publishing bypasses token problems
- **Secure**: No API tokens stored anywhere
- **Automated**: Push a tag, get a PyPI release
- **Traceable**: All releases tracked in GitHub Actions
- **Safe**: Tests must pass before publishing

## 🔍 Monitoring Releases

- **GitHub Actions**: [https://github.com/kalfasyan/desto/actions](https://github.com/kalfasyan/desto/actions)
- **PyPI Releases**: [https://pypi.org/project/desto/#history](https://pypi.org/project/desto/#history)
- **Git Tags**: `git tag -l`

## Manual Process (Alternative)

If you prefer to do it manually:

1. **Update version**: Edit `src/desto/_version.py`
2. **Test**: `uv run pytest tests/`
3. **Lint**: `uv run ruff check .`
4. **Build**: `uv build`
5. **Commit**: `git add . && git commit -m "Bump version to X.Y.Z"`
6. **Tag**: `git tag vX.Y.Z`
7. **Push**: `git push && git push --tags`
8. **Publish**: GitHub Actions handles this automatically!

## 🐛 Troubleshooting

If publishing fails:
1. **"Failed to spawn: ruff"**: Run `uv sync --extra dev` to install dev dependencies
2. **Empty "v" tag created**: Fixed in release script with better error checking
3. Check GitHub Actions logs at [https://github.com/kalfasyan/desto/actions](https://github.com/kalfasyan/desto/actions)
4. Verify PyPI trusted publishing is configured correctly
5. Ensure the repository name and owner match exactly
6. Make sure workflow has `id-token: write` permissions (already configured)

## Tools

- `scripts/bump_version.py` - Version bumping utility
- `scripts/release.sh` - Full release automation
- `Makefile` - Convenient command shortcuts
- `.github/workflows/publish.yml` - Automated PyPI publishing
