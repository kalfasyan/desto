"""Tests for SQLite integration in DestoManager and SQLiteSettings config."""

import os
from datetime import datetime
from unittest.mock import MagicMock, patch

from desto.app.config import UISettings
from desto.redis.desto_manager import DestoManager
from desto.redis.models import DestoJob, DestoSession, JobStatus, SessionStatus
from desto.redis.sqlite_store import SQLiteStore

# ─── SQLiteSettings Configuration Tests ──────────────────────────────────────


class TestSQLiteSettingsConfig:
    def test_sqlite_disabled_by_default(self):
        """SQLite should be disabled by default."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove any pre-existing SQLITE_ENABLED from env
            env = {k: v for k, v in os.environ.items() if not k.startswith("SQLITE")}
            with patch.dict(os.environ, env, clear=True):
                settings = UISettings()
                assert settings.sqlite.enabled is False

    def test_sqlite_enabled_true(self):
        with patch.dict(os.environ, {"SQLITE_ENABLED": "true"}, clear=False):
            settings = UISettings()
            assert settings.sqlite.enabled is True

    def test_sqlite_enabled_1(self):
        with patch.dict(os.environ, {"SQLITE_ENABLED": "1"}, clear=False):
            settings = UISettings()
            assert settings.sqlite.enabled is True

    def test_sqlite_enabled_yes(self):
        with patch.dict(os.environ, {"SQLITE_ENABLED": "yes"}, clear=False):
            settings = UISettings()
            assert settings.sqlite.enabled is True

    def test_sqlite_enabled_on(self):
        with patch.dict(os.environ, {"SQLITE_ENABLED": "on"}, clear=False):
            settings = UISettings()
            assert settings.sqlite.enabled is True

    def test_sqlite_enabled_false(self):
        with patch.dict(os.environ, {"SQLITE_ENABLED": "false"}, clear=False):
            settings = UISettings()
            assert settings.sqlite.enabled is False

    def test_sqlite_enabled_case_insensitive(self):
        with patch.dict(os.environ, {"SQLITE_ENABLED": "TRUE"}, clear=False):
            settings = UISettings()
            assert settings.sqlite.enabled is True

    def test_sqlite_db_path_from_env(self):
        with patch.dict(os.environ, {"SQLITE_DB_PATH": "/custom/path/desto.db"}, clear=False):
            settings = UISettings()
            assert settings.sqlite.db_path == "/custom/path/desto.db"

    def test_sqlite_db_path_default_empty(self):
        env = {k: v for k, v in os.environ.items() if k != "SQLITE_DB_PATH"}
        with patch.dict(os.environ, env, clear=True):
            settings = UISettings()
            assert settings.sqlite.db_path == ""


# ─── DestoManager SQLite Integration Tests ───────────────────────────────────


class TestDestoManagerSQLiteHelpers:
    """Test the _sqlite_save_session and _sqlite_save_job helper methods."""

    def _make_manager(self, sqlite_store=None):
        """Create a DestoManager with a mock Redis client."""
        mock_redis = MagicMock()
        mock_redis.client = MagicMock()
        return DestoManager(redis_client=mock_redis, sqlite_store=sqlite_store)

    def test_sqlite_save_session_when_store_enabled(self, tmp_path):
        store = SQLiteStore(db_path=str(tmp_path / "test.db"), enabled=True)
        manager = self._make_manager(sqlite_store=store)
        session = DestoSession(
            session_id="mgr-session-001",
            session_name="manager-test",
            tmux_session_name="manager-test",
            status=SessionStatus.RUNNING,
            start_time=datetime(2025, 1, 15, 10, 0, 0),
        )
        manager._sqlite_save_session(session)
        result = store.get_session("mgr-session-001")
        assert result is not None
        assert result.session_name == "manager-test"
        store.close()

    def test_sqlite_save_session_when_store_disabled(self, tmp_path):
        store = SQLiteStore(db_path=str(tmp_path / "test.db"), enabled=False)
        manager = self._make_manager(sqlite_store=store)
        session = DestoSession(
            session_id="mgr-disabled",
            session_name="disabled-test",
            tmux_session_name="disabled-test",
            status=SessionStatus.RUNNING,
        )
        # Should not raise
        manager._sqlite_save_session(session)

    def test_sqlite_save_session_when_no_store(self):
        manager = self._make_manager(sqlite_store=None)
        session = DestoSession(
            session_id="mgr-none",
            session_name="no-store",
            tmux_session_name="no-store",
            status=SessionStatus.RUNNING,
        )
        # Should not raise
        manager._sqlite_save_session(session)

    def test_sqlite_save_job_when_store_enabled(self, tmp_path):
        store = SQLiteStore(db_path=str(tmp_path / "test.db"), enabled=True)
        manager = self._make_manager(sqlite_store=store)

        # Save a parent session first (FK constraint)
        session = DestoSession(
            session_id="job-parent",
            session_name="parent",
            tmux_session_name="parent",
            status=SessionStatus.RUNNING,
        )
        store.save_session(session)

        job = DestoJob(
            job_id="mgr-job-001",
            session_id="job-parent",
            command="echo test",
            script_path="/s/test.sh",
            status=JobStatus.RUNNING,
            start_time=datetime(2025, 1, 15, 10, 0, 0),
        )
        manager._sqlite_save_job(job)
        result = store.get_job("mgr-job-001")
        assert result is not None
        assert result.command == "echo test"
        store.close()

    def test_sqlite_save_job_when_no_store(self):
        manager = self._make_manager(sqlite_store=None)
        job = DestoJob(
            job_id="mgr-job-none",
            session_id="nonexistent",
            command="echo test",
            script_path="/s/test.sh",
            status=JobStatus.RUNNING,
        )
        # Should not raise
        manager._sqlite_save_job(job)

    def test_sqlite_save_session_exception_handled(self, tmp_path):
        """Exceptions in SQLite save should be caught, not propagated."""
        store = MagicMock()
        store.enabled = True
        store.save_session.side_effect = Exception("DB error")
        manager = self._make_manager(sqlite_store=store)
        session = DestoSession(
            session_id="err-session",
            session_name="error-test",
            tmux_session_name="error-test",
            status=SessionStatus.RUNNING,
        )
        # Should not raise despite the exception
        manager._sqlite_save_session(session)

    def test_sqlite_save_job_exception_handled(self, tmp_path):
        """Exceptions in SQLite job save should be caught, not propagated."""
        store = MagicMock()
        store.enabled = True
        store.save_job.side_effect = Exception("DB error")
        manager = self._make_manager(sqlite_store=store)
        job = DestoJob(
            job_id="err-job",
            session_id="err-session",
            command="echo fail",
            script_path="/s/fail.sh",
            status=JobStatus.RUNNING,
        )
        # Should not raise despite the exception
        manager._sqlite_save_job(job)
