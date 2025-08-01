"""Tests for the CLI session manager."""

import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from desto.cli.session_manager import CLISessionManager

# Add missing imports for Redis session manager and datetime
from desto.redis.session_manager import SessionManager


@pytest.fixture
def temp_dirs():
    """Create temporary directories for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        log_dir = temp_path / "logs"
        scripts_dir = temp_path / "scripts"
        log_dir.mkdir()
        scripts_dir.mkdir()
        yield {
            "log_dir": log_dir,
            "scripts_dir": scripts_dir,
            "temp_path": temp_path,
        }


@pytest.fixture
def session_manager(temp_dirs):
    """Create a session manager with temporary directories."""
    return CLISessionManager(log_dir=temp_dirs["log_dir"], scripts_dir=temp_dirs["scripts_dir"])


class TestCLISessionManagerInit:
    """Test initialization of CLISessionManager."""

    def test_init_with_default_dirs(self):
        """Test initialization with default directories."""
        with patch("pathlib.Path.mkdir"):
            manager = CLISessionManager()
            assert manager.scripts_dir.name == "desto_scripts"
            assert manager.log_dir.name == "desto_logs"

    def test_init_with_custom_dirs(self, temp_dirs):
        """Test initialization with custom directories."""
        manager = CLISessionManager(log_dir=temp_dirs["log_dir"], scripts_dir=temp_dirs["scripts_dir"])
        assert manager.log_dir == temp_dirs["log_dir"]
        assert manager.scripts_dir == temp_dirs["scripts_dir"]

    def test_init_with_env_vars(self, temp_dirs):
        """Test initialization with environment variables."""
        env_scripts = str(temp_dirs["temp_path"] / "env_scripts")
        env_logs = str(temp_dirs["temp_path"] / "env_logs")

        with patch.dict(os.environ, {"DESTO_SCRIPTS_DIR": env_scripts, "DESTO_LOGS_DIR": env_logs}):
            with patch("pathlib.Path.mkdir"):
                manager = CLISessionManager()
                assert str(manager.scripts_dir) == env_scripts
                assert str(manager.log_dir) == env_logs

    def test_init_directory_creation_failure(self):
        """Test handling of directory creation failure."""
        with patch("pathlib.Path.mkdir", side_effect=PermissionError("Access denied")):
            with pytest.raises(PermissionError):
                CLISessionManager()


class TestSessionManagement:
    """Test session management operations."""

    def test_start_session_success(self, session_manager, temp_dirs):
        """Test successful session start."""
        with (
            patch("desto.cli.session_manager.subprocess.run") as mock_run,
            patch("desto.cli.session_manager.SessionManager.get_session_by_name", return_value=None),
            patch("desto.cli.session_manager.SessionManager.create_session") as mock_create,
            patch("desto.cli.session_manager.SessionManager.start_session", return_value=True),
        ):
            mock_run.return_value = Mock(returncode=0)
            mock_create.return_value = Mock(session_id="1", session_name="test_session")
            result = session_manager.start_session("test_session", "echo hello")
        assert result is True
        assert "test_session" in session_manager.sessions
        mock_run.assert_called()

    def test_start_session_duplicate_name(self, session_manager):
        """Test starting session with duplicate name."""
        session_manager.sessions["existing"] = "some_command"
        with (
            patch("desto.cli.session_manager.subprocess.run") as mock_run,
            patch("desto.cli.session_manager.SessionManager.get_session_by_name", return_value=None),
        ):
            result = session_manager.start_session("existing", "echo hello")
        assert result is False
        mock_run.assert_not_called()

    def test_start_session_subprocess_error(self, session_manager):
        """Test session start with subprocess error."""
        import subprocess as real_subprocess

        with (
            patch("desto.cli.session_manager.subprocess.run") as mock_run,
            patch("desto.cli.session_manager.SessionManager.get_session_by_name", return_value=None),
            patch("desto.cli.session_manager.SessionManager.create_session") as mock_create,
            patch("desto.cli.session_manager.SessionManager.start_session", return_value=True),
        ):
            mock_run.side_effect = real_subprocess.CalledProcessError(1, "tmux")
            mock_create.return_value = Mock(session_id="1", session_name="test")
            result = session_manager.start_session("test", "echo hello")
        assert result is False

    # Legacy marker file logic removed; no longer relevant with Redis-centric manager.
    # def test_start_session_removes_finished_marker(self, session_manager, temp_dirs):
    #     pass

    def test_list_sessions_empty(self, session_manager):
        """Test listing sessions when none exist (Redis-centric)."""
        with patch.object(SessionManager, "list_all_sessions", return_value=[]):
            sessions = session_manager.list_sessions()
            assert sessions == {}

    def test_list_sessions_with_active_sessions(self, session_manager):
        """Test listing active sessions (Redis-centric)."""
        mock_sessions = [
            Mock(session_name="session1", session_id="1", start_time=datetime.now(), end_time=None, status=Mock(value="running")),
            Mock(session_name="session2", session_id="2", start_time=datetime.now(), end_time=datetime.now(), status=Mock(value="finished")),
        ]
        with patch.object(SessionManager, "list_all_sessions", return_value=mock_sessions):
            sessions = session_manager.list_sessions()
            assert "session1" in sessions
            assert "session2" in sessions
            assert sessions["session1"]["finished"] is False
            assert sessions["session2"]["finished"] is True

    @pytest.mark.skipif(os.getenv("CI") == "true", reason="Integration tests not run in CI")
    def test_kill_session_not_found(self, session_manager):
        """Test killing non-existent session."""
        import subprocess as real_subprocess

        with patch("desto.cli.session_manager.subprocess.run") as mock_run:
            mock_run.side_effect = real_subprocess.CalledProcessError(1, "tmux")
            result = session_manager.kill_session("nonexistent")
        assert result is False

    def test_kill_all_sessions_success(self, session_manager):
        """Test killing all sessions successfully."""
        with patch.object(session_manager, "list_sessions") as mock_list, patch.object(session_manager, "kill_session", return_value=True):
            mock_list.return_value = {"session1": {}, "session2": {}}
            with patch("desto.cli.session_manager.subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=0)
                success, total, errors = session_manager.kill_all_sessions()
            assert success == 2
            assert total == 2
            assert errors == []

    def test_kill_all_sessions_no_sessions(self, session_manager):
        """Test killing all sessions when none exist."""
        with patch.object(session_manager, "list_sessions") as mock_list:
            mock_list.return_value = {}

            success, total, errors = session_manager.kill_all_sessions()

            assert success == 0
            assert total == 0
            assert errors == []

    def test_kill_all_sessions_partial_failure(self, session_manager):
        """Test killing all sessions with some failures."""
        with patch.object(session_manager, "list_sessions") as mock_list, patch.object(session_manager, "kill_session", side_effect=[True, False]):
            mock_list.return_value = {"session1": {}, "session2": {}}
            with patch("desto.cli.session_manager.subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=0)
                success, total, errors = session_manager.kill_all_sessions()
            assert success == 1
            assert total == 2
            assert len(errors) == 1

    @pytest.mark.skipif(os.getenv("CI") == "true", reason="Integration tests not run in CI")
    def test_attach_session_no_tmux(self, session_manager):
        """Test session attachment when tmux not available."""
        with patch("os.execvp") as mock_execvp:
            mock_execvp.side_effect = FileNotFoundError()
            result = session_manager.attach_session("test_session")
        assert result is False

    def test_session_exists_true(self, session_manager):
        """Test session_exists returns True for existing session."""
        with patch.object(session_manager, "list_sessions") as mock_list:
            mock_list.return_value = {"existing_session": {}}

            result = session_manager.session_exists("existing_session")

            assert result is True

    def test_session_exists_false(self, session_manager):
        """Test session_exists returns False for non-existent session."""
        with patch.object(session_manager, "list_sessions") as mock_list:
            mock_list.return_value = {}

            result = session_manager.session_exists("nonexistent")

            assert result is False

    def test_start_chain_session_creates_redis_and_log(self, tmp_path):
        # Setup
        scripts_dir = tmp_path / "scripts"
        log_dir = tmp_path / "logs"
        scripts_dir.mkdir()
        log_dir.mkdir()
        # Create dummy scripts
        script1 = scripts_dir / "a.sh"
        script1.write_text("#!/bin/bash\necho 'A'\n")
        script1.chmod(0o755)
        script2 = scripts_dir / "b.sh"
        script2.write_text("#!/bin/bash\necho 'B'\n")
        script2.chmod(0o755)

        manager = CLISessionManager(log_dir=log_dir, scripts_dir=scripts_dir)
        scripts_with_args = [["a.sh"], ["b.sh"]]

        # Patch subprocess and Redis
        with (
            patch("desto.cli.session_manager.subprocess.run") as mock_run,
            patch("desto.redis.session_manager.SessionManager.create_session") as mock_create,
            patch("desto.redis.session_manager.SessionManager.start_session") as mock_start,
            patch("desto.redis.session_manager.SessionManager.get_session_by_name", return_value=None),
        ):
            mock_run.return_value.returncode = 0
            mock_create.return_value = Mock(session_id="id1", session_name="chain_test", metadata={})
            mock_start.return_value = True

            session_name = manager.start_chain_session(scripts_with_args)
            assert session_name is not None

            # Check Redis registration
            mock_create.assert_called()
            args, kwargs = mock_create.call_args
            assert "chain" in kwargs.get("metadata", {}).get("type", "chain")

            # Check log file
            log_file = log_dir / f"{session_name}.log"
            assert log_file.exists()
            content = log_file.read_text()
            assert "# Session:" in content
            # Do not check for script markers, as they are only written by tmux at runtime

    def test_chain_session_registers_in_redis_and_logs(self, tmp_path):
        from unittest.mock import Mock, patch

        from desto.cli.session_manager import CLISessionManager

        scripts_dir = tmp_path / "scripts"
        log_dir = tmp_path / "logs"
        scripts_dir.mkdir()
        log_dir.mkdir()
        script1 = scripts_dir / "a.sh"
        script1.write_text("#!/bin/bash\necho 'A'\n")
        script1.chmod(0o755)
        script2 = scripts_dir / "b.sh"
        script2.write_text("#!/bin/bash\necho 'B'\n")
        script2.chmod(0o755)

        manager = CLISessionManager(log_dir=log_dir, scripts_dir=scripts_dir)
        scripts_with_args = [["a.sh"], ["b.sh"]]

        with (
            patch("desto.cli.session_manager.subprocess.run") as mock_run,
            patch("desto.redis.session_manager.SessionManager.create_session") as mock_create,
            patch("desto.redis.session_manager.SessionManager.start_session") as mock_start,
            patch("desto.redis.session_manager.SessionManager.get_session_by_name", return_value=None),
        ):
            mock_run.return_value.returncode = 0
            mock_create.return_value = Mock(session_id="id1", session_name="chain_test", metadata={})
            mock_start.return_value = True

            session_name = manager.start_chain_session(scripts_with_args)
            assert session_name is not None

            # Check Redis registration
            mock_create.assert_called()
            args, kwargs = mock_create.call_args
            assert "chain" in kwargs.get("metadata", {}).get("type", "chain")

            # Check log file
            log_file = log_dir / f"{session_name}.log"
            assert log_file.exists()
            content = log_file.read_text()
            assert "# Session:" in content
            # Do not check for script markers, as they are only written by tmux at runtime


class TestLogManagement:
    """Test log management operations."""

    def test_get_log_file(self, session_manager, temp_dirs):
        """Test getting log file path."""
        log_file = session_manager.get_log_file("test_session")

        expected = temp_dirs["log_dir"] / "test_session.log"
        assert log_file == expected

    def test_get_script_file(self, session_manager, temp_dirs):
        """Test getting script file path."""
        script_file = session_manager.get_script_file("test_script.sh")

        expected = temp_dirs["scripts_dir"] / "test_script.sh"
        assert script_file == expected

    def test_get_log_content_file_exists(self, session_manager, temp_dirs):
        """Test getting log content when file exists."""
        log_file = temp_dirs["log_dir"] / "test.log"
        log_content = "Line 1\nLine 2\nLine 3\n"
        log_file.write_text(log_content)

        content = session_manager.get_log_content("test")

        assert content == log_content

    def test_get_log_content_file_not_exists(self, session_manager):
        """Test getting log content when file doesn't exist."""
        content = session_manager.get_log_content("nonexistent")

        assert content is None

    def test_get_log_content_with_lines_limit(self, session_manager, temp_dirs):
        """Test getting log content with line limit."""
        log_file = temp_dirs["log_dir"] / "test.log"
        log_content = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5\n"
        log_file.write_text(log_content)

        with patch("desto.cli.session_manager.subprocess.run") as mock_run:
            mock_run.return_value = Mock(stdout="Line 4\nLine 5\n", returncode=0)
            session_manager.get_log_content("test", lines=2)

            mock_run.assert_called_with(
                ["tail", "-n", "2", str(log_file)],
                capture_output=True,
                text=True,
                check=True,
            )

    def test_get_log_content_tail_error(self, session_manager, temp_dirs):
        """Test getting log content when tail command fails."""
        log_file = temp_dirs["log_dir"] / "test.log"
        log_file.write_text("some content")

        with patch("desto.cli.session_manager.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, "tail")
            content = session_manager.get_log_content("test", lines=5)

            assert content is None


class TestErrorHandling:
    """Test error handling scenarios."""

    @pytest.mark.skipif(os.getenv("CI") == "true", reason="Integration tests not run in CI")
    def test_start_session_general_exception(self, session_manager):
        """Test handling of general exception during session start."""
        with patch("desto.cli.session_manager.subprocess.run") as mock_run:
            mock_run.side_effect = Exception("Unexpected error")
            result = session_manager.start_session("test", "echo hello")
        assert result is False

    def test_list_sessions_general_exception(self, session_manager):
        """Test handling of general exception during session listing."""
        with patch("desto.cli.session_manager.SessionManager.list_all_sessions", side_effect=Exception("Unexpected error")):
            sessions = session_manager.list_sessions()
        assert sessions == {}

    @pytest.mark.skip(reason="Requires real tmux, not suitable for CI/test environments.")
    def test_start_session_real_subprocess_success(self, session_manager, temp_dirs):
        """Test successful session start with real subprocess (skipped in CI)."""
        pass
