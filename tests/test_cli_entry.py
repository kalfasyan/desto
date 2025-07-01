"""Tests for the CLI entry point."""

from unittest.mock import Mock, patch

import pytest

from desto.cli.cli import cli_main


class TestCliMain:
    """Test the main CLI entry point."""

    @patch("desto.cli.main.app")
    def test_cli_main_with_typer(self, mock_app):
        """Test CLI main when typer is available."""
        cli_main()
        mock_app.assert_called_once()

    @patch("desto.cli.main.app", side_effect=ImportError("typer not found"))
    @patch("sys.argv", ["desto-cli"])
    def test_cli_main_no_typer_no_args(self, mock_app):
        """Test CLI main fallback when typer not available and no args."""
        with patch("builtins.print") as mock_print:
            cli_main()

            # Should print usage information
            mock_print.assert_called()
            calls = [str(call) for call in mock_print.call_args_list]
            assert any("Typer not available" in call for call in calls)
            assert any("Usage:" in call for call in calls)

    @patch("desto.cli.main.app", side_effect=ImportError("typer not found"))
    @patch("sys.argv", ["desto-cli", "list"])
    @patch("desto.cli.session_manager.CLISessionManager")
    def test_cli_main_no_typer_list_command(self, mock_manager_class, mock_app):
        """Test CLI main fallback list command."""
        mock_manager = Mock()
        mock_manager.list_sessions.return_value = {}
        mock_manager_class.return_value = mock_manager

        with patch("builtins.print") as mock_print:
            cli_main()

            mock_manager.list_sessions.assert_called_once()
            calls = [str(call) for call in mock_print.call_args_list]
            assert any("No active sessions" in call for call in calls)

    @patch("desto.cli.main.app", side_effect=ImportError("typer not found"))
    @patch("sys.argv", ["desto-cli", "list"])
    @patch("desto.cli.session_manager.CLISessionManager")
    def test_cli_main_no_typer_list_with_sessions(self, mock_manager_class, mock_app):
        """Test CLI main fallback list command with sessions."""
        mock_manager = Mock()
        mock_manager.list_sessions.return_value = {
            "session1": {"finished": False, "runtime": 3600},
            "session2": {"finished": True, "runtime": 1800},
        }
        mock_manager_class.return_value = mock_manager

        with patch("builtins.print") as mock_print:
            with patch(
                "desto.cli.utils.format_duration", side_effect=lambda x: f"{x}s"
            ):
                cli_main()

                mock_manager.list_sessions.assert_called_once()
                calls = [str(call) for call in mock_print.call_args_list]
                assert any("Active sessions" in call for call in calls)
                assert any("session1" in call for call in calls)
                assert any("session2" in call for call in calls)

    @patch("desto.cli.main.app", side_effect=ImportError("typer not found"))
    @patch("sys.argv", ["desto-cli", "start", "test_session", "echo", "hello"])
    @patch("desto.cli.session_manager.CLISessionManager")
    def test_cli_main_no_typer_start_command_success(
        self, mock_manager_class, mock_app
    ):
        """Test CLI main fallback start command success."""
        mock_manager = Mock()
        mock_manager.start_session.return_value = True
        mock_manager_class.return_value = mock_manager

        with patch("builtins.print") as mock_print:
            cli_main()

            mock_manager.start_session.assert_called_with("test_session", "echo hello")
            calls = [str(call) for call in mock_print.call_args_list]
            assert any("Session 'test_session' started" in call for call in calls)

    @patch("desto.cli.main.app", side_effect=ImportError("typer not found"))
    @patch("sys.argv", ["desto-cli", "start", "test_session", "echo", "hello"])
    @patch("desto.cli.session_manager.CLISessionManager")
    def test_cli_main_no_typer_start_command_failure(
        self, mock_manager_class, mock_app
    ):
        """Test CLI main fallback start command failure."""
        mock_manager = Mock()
        mock_manager.start_session.return_value = False
        mock_manager_class.return_value = mock_manager

        with patch("builtins.print") as mock_print:
            cli_main()

            mock_manager.start_session.assert_called_with("test_session", "echo hello")
            calls = [str(call) for call in mock_print.call_args_list]
            assert any("Failed to start session" in call for call in calls)

    @patch("desto.cli.main.app", side_effect=ImportError("typer not found"))
    @patch("sys.argv", ["desto-cli", "kill", "test_session"])
    @patch("desto.cli.session_manager.CLISessionManager")
    def test_cli_main_no_typer_kill_command_success(self, mock_manager_class, mock_app):
        """Test CLI main fallback kill command success."""
        mock_manager = Mock()
        mock_manager.kill_session.return_value = True
        mock_manager_class.return_value = mock_manager

        with patch("builtins.print") as mock_print:
            cli_main()

            mock_manager.kill_session.assert_called_with("test_session")
            calls = [str(call) for call in mock_print.call_args_list]
            assert any("Session 'test_session' killed" in call for call in calls)

    @patch("desto.cli.main.app", side_effect=ImportError("typer not found"))
    @patch("sys.argv", ["desto-cli", "kill", "test_session"])
    @patch("desto.cli.session_manager.CLISessionManager")
    def test_cli_main_no_typer_kill_command_failure(self, mock_manager_class, mock_app):
        """Test CLI main fallback kill command failure."""
        mock_manager = Mock()
        mock_manager.kill_session.return_value = False
        mock_manager_class.return_value = mock_manager

        with patch("builtins.print") as mock_print:
            cli_main()

            mock_manager.kill_session.assert_called_with("test_session")
            calls = [str(call) for call in mock_print.call_args_list]
            assert any("Failed to kill session" in call for call in calls)

    @patch("desto.cli.main.app", side_effect=ImportError("typer not found"))
    @patch("sys.argv", ["desto-cli", "logs", "test_session"])
    @patch("desto.cli.session_manager.CLISessionManager")
    def test_cli_main_no_typer_logs_command_success(self, mock_manager_class, mock_app):
        """Test CLI main fallback logs command success."""
        mock_manager = Mock()
        mock_manager.get_log_content.return_value = "Log content here"
        mock_manager_class.return_value = mock_manager

        with patch("builtins.print") as mock_print:
            cli_main()

            mock_manager.get_log_content.assert_called_with("test_session")
            calls = [str(call) for call in mock_print.call_args_list]
            assert any("--- Logs for test_session ---" in call for call in calls)
            assert any("Log content here" in call for call in calls)

    @patch("desto.cli.main.app", side_effect=ImportError("typer not found"))
    @patch("sys.argv", ["desto-cli", "logs", "test_session"])
    @patch("desto.cli.session_manager.CLISessionManager")
    def test_cli_main_no_typer_logs_command_no_logs(self, mock_manager_class, mock_app):
        """Test CLI main fallback logs command with no logs."""
        mock_manager = Mock()
        mock_manager.get_log_content.return_value = None
        mock_manager_class.return_value = mock_manager

        with patch("builtins.print") as mock_print:
            cli_main()

            mock_manager.get_log_content.assert_called_with("test_session")
            calls = [str(call) for call in mock_print.call_args_list]
            assert any("No logs found" in call for call in calls)

    @patch("desto.cli.main.app", side_effect=ImportError("typer not found"))
    @patch("sys.argv", ["desto-cli", "invalid_command"])
    def test_cli_main_no_typer_invalid_command(self, mock_app):
        """Test CLI main fallback with invalid command."""
        with patch("builtins.print") as mock_print:
            cli_main()

            calls = [str(call) for call in mock_print.call_args_list]
            assert any("Invalid command" in call for call in calls)

    @patch("desto.cli.main.app", side_effect=ImportError("typer not found"))
    @patch("sys.argv", ["desto-cli", "start"])  # Missing args
    def test_cli_main_no_typer_missing_args(self, mock_app):
        """Test CLI main fallback with missing arguments."""
        with patch("builtins.print") as mock_print:
            cli_main()

            calls = [str(call) for call in mock_print.call_args_list]
            assert any("Invalid command or missing arguments" in call for call in calls)

    def test_cli_main_as_main(self):
        """Test CLI main when run as __main__."""
        # Test that the module can be imported and the function exists
        try:
            from desto.cli.cli import cli_main

            assert callable(cli_main)
        except ImportError as e:
            pytest.fail(f"CLI module should be importable: {e}")


class TestCliMainErrorHandling:
    """Test error handling in CLI main."""

    @patch("desto.cli.main.app")
    def test_cli_main_app_exception(self, mock_app):
        """Test CLI main when app raises an exception."""
        mock_app.side_effect = Exception("Unexpected error")

        # Should not raise exception, might print error or exit gracefully
        with pytest.raises(Exception):
            cli_main()

    @patch("desto.cli.main.app", side_effect=ImportError("typer not found"))
    @patch("sys.argv", ["desto-cli", "list"])
    @patch("desto.cli.session_manager.CLISessionManager")
    def test_cli_main_fallback_exception(self, mock_manager_class, mock_app):
        """Test CLI main fallback when session manager raises exception."""
        mock_manager_class.side_effect = Exception("Manager error")

        # Should not raise exception, should handle gracefully
        with patch("builtins.print"):
            try:
                cli_main()
            except Exception:
                pytest.fail("cli_main should handle exceptions gracefully")


class TestCliMainImportBehavior:
    """Test import behavior and fallback mechanisms."""

    def test_import_error_handling(self):
        """Test that import errors are handled properly."""
        # This test ensures that the module structure handles missing dependencies
        try:
            from desto.cli.cli import cli_main

            # If we get here, the import succeeded
            assert callable(cli_main)
        except ImportError as e:
            pytest.fail(f"CLI module should not fail to import: {e}")

    @patch("desto.cli.main.app", side_effect=ImportError("typer not found"))
    def test_fallback_import_success(self, mock_app):
        """Test that fallback imports work when typer is not available."""
        # This should not raise ImportError
        try:
            cli_main()
        except ImportError:
            pytest.fail("Fallback should handle missing typer gracefully")
        except SystemExit:
            # This is OK, might exit due to missing args
            pass
