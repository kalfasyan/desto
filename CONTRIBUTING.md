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

## Code structure rules

These keep desto small and its front ends (web dashboard, TUI, CLI and scheduled jobs) behaving the same:

- **One launch path.** Every tmux session starts through `DestoService.start_tmux_session` in `src/desto/core/service.py`, which wraps the command with `core.scripts.session_script`. Do not build tmux or log-wrapper commands anywhere else; `tests/test_launch_paths.py` checks every launcher against the same behaviour.
- **Front ends stay thin.** `app/`, `tui/` and `cli/` handle display and input only. Logic they share belongs in `core/`, storage in `store/`, settings in `desto/config.py`.
- **Delete rather than add.** Before adding a helper, look for one in `core/`. CI runs [vulture](https://github.com/jendrikseipp/vulture) (`uvx vulture@2.14`) for dead code: remove what it finds, and only add a name to `vulture_whitelist.py` when a framework uses it.
- **Keep functions small.** ruff's C901 check fails functions over complexity 15. Split them rather than adding a `noqa`.
- **Coverage does not go down.** CI fails if test coverage drops below the `--cov-fail-under` floor in `.github/workflows/ci.yml`.

You can auto-fix many issues:

```bash
uv run --extra dev ruff check . --fix
uv run --extra dev ruff format
```

Pre-commit will run these checks automatically (see `.pre-commit-config.yaml`).

## Code of Conduct

Please be respectful and inclusive. Disrespectful or inappropriate behavior will not be tolerated.