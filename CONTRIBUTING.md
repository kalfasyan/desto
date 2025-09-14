# Contributing to desto

Thank you for your interest in contributing! This project values kind communication, understanding, and respect. Whether you're fixing bugs, improving documentation, or suggesting new features, your contributions are welcome.

## How to Contribute

- **Open Communication:** Please discuss any major changes or ideas in an issue before making a pull request. This helps ensure your work aligns with the project's goals.
- **Respect:** Be kind and constructive in all interactions.
- **Transparency:** Be clear about what your change does and why. Include context and reasoning in issues and pull requests.

## Submitting Issues

- Provide as much detail as possible (steps to reproduce, environment, etc.).

## Submitting Pull Requests

1. Fork the repository and create your branch from `main`.
2. Make your changes, following good code practices and adding tests if appropriate.
3. Ensure your code passes linting and tests (`uv run --extra dev pytest tests/` and `uv run --extra dev ruff check .`).
4. Open a pull request with a clear description of your changes.

## Style & Docstrings

We use [ruff](https://docs.astral.sh/ruff/) for formatting and linting and enforce **Google-style docstrings** (`D` rules via pydocstyle). Please:

- Keep line length within the configured limit (`line-length` in `pyproject.toml`).
- Write a concise summary line (imperative mood) followed by a blank line for multi-line docstrings.
- Include `Args:`, `Returns:`, `Raises:` where applicable.
- Avoid redundancy—do not restate parameter types if already type-annotated unless clarification helps.
- Use triple double quotes for all docstrings.

Minimal examples:

```python
def add(a: int, b: int) -> int:
	"""Return the sum of two integers."""

def fetch_item(key: str) -> dict:
	"""Fetch an item by key.

	Args:
		key: Cache or datastore lookup key.

	Returns:
		A dictionary representing the stored item.

	Raises:
		KeyError: If the key is not found.
	"""
```

You can auto-fix many issues:

```bash
uv run --extra dev ruff check . --fix
uv run --extra dev ruff format
```

Pre-commit will run these checks automatically (see `.pre-commit-config.yaml`).

## Code of Conduct

Please be respectful and inclusive. Disrespectful or inappropriate behavior will not be tolerated.