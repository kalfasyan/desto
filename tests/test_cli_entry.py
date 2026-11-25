"""Tests for the CLI entry point."""

from unittest.mock import patch

import pytest

from desto.cli.cli import cli_main


@patch("desto.cli.main.app")
def test_cli_main_runs_the_typer_app(mock_app):
    cli_main()
    mock_app.assert_called_once()


@patch("desto.cli.main.app", side_effect=RuntimeError("boom"))
def test_cli_main_does_not_hide_errors(mock_app):
    with pytest.raises(RuntimeError):
        cli_main()
