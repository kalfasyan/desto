#!/bin/bash
# Release script for des# Build package
echo "📦 Building package..."
uv build

# Git operations
echo "📝 Committing changes..."
git add src/desto/_version.py
git commit -m "Bump version to $NEW_VERSION"

echo "🏷️ Creating tag..."
git tag "v$NEW_VERSION"

echo "📤 Pushing to GitHub..."
git push && git push --tags

echo "✅ Release $NEW_VERSION complete!"
echo ""
echo "🎉 GitHub Actions will automatically publish to PyPI!"
echo "👀 Check the progress at: https://github.com/kalfasyan/desto/actions"

if [ $# -eq 0 ]; then
    echo "Usage: $0 [major|minor|patch]"
    echo "Example: $0 patch"
    exit 1
fi

BUMP_TYPE=$1

echo "🚀 Starting release process..."

# Check if working directory is clean
if ! git diff-index --quiet HEAD --; then
    echo "❌ Working directory is not clean. Please commit your changes first."
    exit 1
fi

# Bump version
echo "📝 Bumping version..."
python scripts/bump_version.py $BUMP_TYPE

# Get new version
NEW_VERSION=$(python -c "from src.desto._version import __version__; print(__version__)")

# Run tests
echo "🧪 Running tests..."
uv run pytest tests/

# Run linting
echo "🔍 Running linting..."
uv run ruff check .

# Build package
echo "📦 Building package..."
uv build --wheel

# Git operations
echo "📝 Committing changes..."
git add src/desto/_version.py
git commit -m "Bump version to $NEW_VERSION"

echo "🏷️ Creating tag..."
git tag "v$NEW_VERSION"

echo "✅ Release $NEW_VERSION ready!"
echo ""
echo "Next steps:"
echo "1. Push changes: git push && git push --tags"
echo "2. Upload to PyPI: uv publish"
echo "3. Create GitHub release"
