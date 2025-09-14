# desto Documentation

<!--
This page includes the repository README so that the GitHub landing page
and the documentation homepage stay in sync (single source of truth).
Edit README.md instead of this file for introductory content changes.
-->

<!-- Primary include via include-markdown plugin -->
{% include-markdown "README.md" %}

<!-- Fallback for pymdownx.snippets (kept commented to avoid duplicate injection) -->
<!--
--8<-- "README.md"
-->

## Additional Documentation

- Configuration reference: [Project settings](pyproject.md)
- CLI usage guide: [Command Line Interface](cli.md)

If the README content does not appear here when building docs, ensure you installed the docs extras:

```bash
uv sync --extra docs
uv run mkdocs serve
```

The include is powered by `mkdocs-include-markdown-plugin`.
