## Project configuration (`pyproject.toml`)

This project uses `pyproject.toml` for metadata and build configuration. Key sections:

- **[project]**: package metadata, dependencies, and scripts.
- **[project.optional-dependencies]**: extras groups, including `docs` which contains MkDocs and theme packages.
- **[build-system]**: `hatchling` is used as the build backend.

See the repository root `pyproject.toml` for the full configuration.
