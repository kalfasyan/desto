# CLAUDE.md

## Git and GitHub

- Never add AI co-author or attribution lines to commits, PR descriptions, or GitHub comments
  (no `Co-Authored-By: Claude ...`, `Claude-Session: ...`, "Generated with Claude Code", or similar).

## Code structure

- Start every tmux session through `DestoService.start_tmux_session` (`src/desto/core/service.py`); never build tmux or log-wrapper commands elsewhere.
- Shared logic goes in `core/`, storage in `store/`, settings in `desto/config.py`; `app/`, `tui/` and `cli/` stay thin.
- Prefer deleting or reusing code over adding layers or dependencies. CI runs ruff (with C901), vulture and a coverage floor; see CONTRIBUTING.md.
