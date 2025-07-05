"""Tests for script management CLI commands."""

import os
import stat
from unittest.mock import Mock, patch

import pytest

from desto.cli.scripts import (
    copy_script,
    create_script,
    delete_script,
    get_script_icon,
    get_script_type,
    list_scripts,
    run_script,
    show_script,
    validate_script_name,
)


class TestScriptUtilities:
    """Test utility functions for script management."""

    def test_get_script_type(self):
        """Test script type detection."""
        assert get_script_type("test.py") == "python"
        assert get_script_type("test.sh") == "bash"
        assert get_script_type("test.txt") == "unknown"

    def test_get_script_icon(self):
        """Test script icon retrieval."""
        assert get_script_icon("python") == "🐍"
        assert get_script_icon("bash") == "🐚"
        assert get_script_icon("unknown") == "📄"

    def test_validate_script_name_valid(self):
        """Test valid script name validation."""
        assert validate_script_name("test_script") == "test_script"
        assert validate_script_name("my-script-123") == "my-script-123"
        assert validate_script_name("simple") == "simple"

    def test_validate_script_name_invalid(self):
        """Test invalid script name validation."""
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_script_name("")

        with pytest.raises(ValueError, match="must contain at least one"):
            validate_script_name("!@#$%")

    def test_validate_script_name_sanitization(self):
        """Test script name sanitization."""
        assert validate_script_name("test script") == "test_script"
        assert validate_script_name("test@script#") == "testscript"
        assert validate_script_name("a" * 60) == "a" * 50  # Length limit


class TestScriptCommands:
    """Test script management commands."""

    @pytest.fixture
    def temp_scripts_dir(self, tmp_path):
        """Create temporary scripts directory."""
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        return scripts_dir

    @pytest.fixture
    def mock_session_manager(self, temp_scripts_dir):
        """Mock session manager with temporary directory."""
        with patch("desto.cli.scripts.CLISessionManager") as mock:
            manager = Mock()
            manager.scripts_dir = temp_scripts_dir
            manager.get_script_file.side_effect = lambda name: temp_scripts_dir / name
            mock.return_value = manager
            yield manager

    def test_create_bash_script(self, mock_session_manager, temp_scripts_dir):
        """Test creating a bash script."""
        with patch("desto.cli.scripts.console") as mock_console:
            create_script("test_script", "bash", template=True, edit=False)

        script_path = temp_scripts_dir / "test_script.sh"
        assert script_path.exists()

        content = script_path.read_text()
        assert content.startswith("#!/bin/bash")
        assert "test_script.sh" in content

        # Check if executable
        assert os.access(script_path, os.X_OK)

        mock_console.print.assert_called_with("[green]✅ Created 🐚 test_script.sh in " + str(temp_scripts_dir) + "[/green]")

    def test_create_python_script(self, mock_session_manager, temp_scripts_dir):
        """Test creating a python script."""
        with patch("desto.cli.scripts.console"):
            create_script("test_script", "python", template=True, edit=False)

        script_path = temp_scripts_dir / "test_script.py"
        assert script_path.exists()

        content = script_path.read_text()
        assert content.startswith("#!/usr/bin/env python3")
        assert "test_script.py" in content

        # Check if executable
        assert os.access(script_path, os.X_OK)

    def test_create_script_without_template(self, mock_session_manager, temp_scripts_dir):
        """Test creating script without template."""
        with patch("desto.cli.scripts.console"):
            create_script("minimal", "bash", template=False, edit=False)

        script_path = temp_scripts_dir / "minimal.sh"
        content = script_path.read_text()
        assert content == "#!/bin/bash\n\n"

    def test_list_scripts_empty(self, mock_session_manager, temp_scripts_dir):
        """Test listing scripts when directory is empty."""
        with patch("desto.cli.scripts.console") as mock_console:
            list_scripts(show_details=False)

        mock_console.print.assert_any_call(f"[yellow]No scripts found in {temp_scripts_dir}[/yellow]")

    def test_list_scripts_with_content(self, mock_session_manager, temp_scripts_dir):
        """Test listing scripts with content."""
        # Create test scripts
        bash_script = temp_scripts_dir / "test.sh"
        bash_script.write_text("#!/bin/bash\necho hello")
        bash_script.chmod(bash_script.stat().st_mode | stat.S_IEXEC)

        python_script = temp_scripts_dir / "test.py"
        python_script.write_text("#!/usr/bin/env python3\nprint('hello')")
        python_script.chmod(python_script.stat().st_mode | stat.S_IEXEC)

        with patch("desto.cli.scripts.console") as mock_console:
            list_scripts(show_details=False)

        # Should show both scripts with icons
        mock_console.print.assert_any_call("  🐚 test.sh")
        mock_console.print.assert_any_call("  🐍 test.py")

    def test_delete_script_success(self, mock_session_manager, temp_scripts_dir):
        """Test successful script deletion."""
        # Create test script
        script_path = temp_scripts_dir / "delete_me.sh"
        script_path.write_text("#!/bin/bash\necho test")

        with patch("desto.cli.scripts.console") as mock_console, patch("desto.cli.scripts.Confirm.ask", return_value=True):
            delete_script("delete_me", force=False)

        assert not script_path.exists()
        mock_console.print.assert_called_with("[green]✅ Deleted delete_me.sh[/green]")

    def test_delete_script_cancelled(self, mock_session_manager, temp_scripts_dir):
        """Test cancelled script deletion."""
        # Create test script
        script_path = temp_scripts_dir / "keep_me.sh"
        script_path.write_text("#!/bin/bash\necho test")

        with patch("desto.cli.scripts.console") as mock_console, patch("desto.cli.scripts.Confirm.ask", return_value=False):
            delete_script("keep_me", force=False)

        assert script_path.exists()
        mock_console.print.assert_called_with("[yellow]Deletion cancelled[/yellow]")

    def test_show_script_success(self, mock_session_manager, temp_scripts_dir):
        """Test showing script content."""
        # Create test script
        script_path = temp_scripts_dir / "show_me.py"
        content = "#!/usr/bin/env python3\nprint('Hello, World!')"
        script_path.write_text(content)
        script_path.chmod(script_path.stat().st_mode | stat.S_IEXEC)

        with patch("desto.cli.scripts.console") as mock_console, patch("desto.cli.scripts.Syntax") as mock_syntax:
            show_script("show_me", line_numbers=False, max_lines=None)

        mock_console.print.assert_any_call("[bold]🐍 show_me.py[/bold]")
        mock_syntax.assert_called_with(content, "python", line_numbers=False, theme="default")

    def test_copy_script_success(self, mock_session_manager, temp_scripts_dir):
        """Test successful script copying."""
        # Create source script
        source_path = temp_scripts_dir / "original.sh"
        content = "#!/bin/bash\necho 'original'"
        source_path.write_text(content)
        source_path.chmod(source_path.stat().st_mode | stat.S_IEXEC)

        with patch("desto.cli.scripts.console") as mock_console:
            copy_script("original", "copy", edit=False)

        dest_path = temp_scripts_dir / "copy.sh"
        assert dest_path.exists()
        assert dest_path.read_text() == content
        assert os.access(dest_path, os.X_OK)  # Should preserve executable permission

        mock_console.print.assert_called_with("[green]✅ Copied original.sh to 🐚 copy.sh[/green]")

    def test_run_script_direct_success(self, mock_session_manager, temp_scripts_dir):
        """Test running script directly."""
        # Create test script
        script_path = temp_scripts_dir / "runner.sh"
        script_path.write_text("#!/bin/bash\necho 'success'")
        script_path.chmod(script_path.stat().st_mode | stat.S_IEXEC)

        with patch("desto.cli.scripts.console") as mock_console, patch("desto.cli.scripts.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0

            run_script("runner", args=[], direct=True)

        mock_run.assert_called_with(["bash", str(script_path)], check=False)
        mock_console.print.assert_any_call("[green]✅ runner.sh completed successfully[/green]")

    def test_run_script_in_session(self, mock_session_manager, temp_scripts_dir):
        """Test running script in tmux session."""
        # Create test script
        script_path = temp_scripts_dir / "session_runner.py"
        script_path.write_text("#!/usr/bin/env python3\nprint('session test')")
        script_path.chmod(script_path.stat().st_mode | stat.S_IEXEC)

        # Mock session manager methods
        mock_session_manager.start_session.return_value = True

        with patch("desto.cli.scripts.console") as mock_console:
            run_script("session_runner", args=["arg1"], session_name="test_session", direct=False)

        mock_session_manager.start_session.assert_called_once()
        call_args = mock_session_manager.start_session.call_args
        assert "python3" in call_args[0][1]  # Command should contain python3
        assert str(script_path) in call_args[0][1]  # Command should contain script path

        mock_console.print.assert_any_call("[green]✅ Started 🐍 session_runner.py in session 'test_session'[/green]")


class TestScriptEditing:
    """Test script editing functionality."""

    def test_get_editor_from_env(self):
        """Test getting editor from environment."""
        with patch.dict(os.environ, {"EDITOR": "vim"}):
            from desto.cli.scripts import get_editor

            assert get_editor() == "vim"

    def test_get_editor_default(self):
        """Test getting default editor."""
        with patch.dict(os.environ, {}, clear=True):
            from desto.cli.scripts import get_editor

            assert get_editor() == "nano"


class TestScriptNameValidation:
    """Test edge cases for script name validation."""

    def test_script_name_with_extension_preserved(self):
        """Test that existing extensions are preserved."""
        assert validate_script_name("test.py") == "test.py"
        assert validate_script_name("test.sh") == "test.sh"

    def test_script_name_special_chars_removed(self):
        """Test that special characters are removed."""
        assert validate_script_name("test@#$script") == "testscript"
        assert validate_script_name("my script!") == "my_script"

    def test_script_name_length_limit(self):
        """Test that script names are limited in length."""
        long_name = "a" * 100
        result = validate_script_name(long_name)
        assert len(result) == 50
