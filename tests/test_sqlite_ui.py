"""Tests for the SQLite History UI tab."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from desto.redis.models import DestoJob, DestoSession, JobStatus, SessionStatus

# ─── Helper formatting tests ──────────────────────────────────────────


class TestFormatHelpers:
    """Tests for _fmt_dt and _fmt_duration."""

    def test_fmt_dt_with_datetime(self):
        from desto.app.sqlite_ui import _fmt_dt

        dt = datetime(2025, 6, 15, 14, 30, 45)
        assert _fmt_dt(dt) == "2025-06-15 14:30:45"

    def test_fmt_dt_with_none(self):
        from desto.app.sqlite_ui import _fmt_dt

        assert _fmt_dt(None) == "—"

    def test_fmt_dt_with_iso_string(self):
        from desto.app.sqlite_ui import _fmt_dt

        result = _fmt_dt("2025-06-15T14:30:45")
        assert result == "2025-06-15 14:30:45"

    def test_fmt_dt_with_invalid_string(self):
        from desto.app.sqlite_ui import _fmt_dt

        assert _fmt_dt("not-a-date") == "not-a-date"

    def test_fmt_duration_seconds(self):
        from desto.app.sqlite_ui import _fmt_duration

        assert _fmt_duration(timedelta(seconds=42)) == "42s"

    def test_fmt_duration_minutes(self):
        from desto.app.sqlite_ui import _fmt_duration

        assert _fmt_duration(timedelta(minutes=5, seconds=10)) == "5m 10s"

    def test_fmt_duration_hours(self):
        from desto.app.sqlite_ui import _fmt_duration

        assert _fmt_duration(timedelta(hours=2, minutes=3, seconds=4)) == "2h 3m 4s"

    def test_fmt_duration_negative(self):
        from desto.app.sqlite_ui import _fmt_duration

        assert _fmt_duration(timedelta(seconds=-1)) == "—"


# ─── SQLiteStore.search_sessions tests ─────────────────────────────────


class TestSQLiteStoreSearchSessions:
    """Tests for the search_sessions method added to SQLiteStore."""

    @pytest.fixture
    def sqlite_store(self, tmp_path):
        from desto.redis.sqlite_store import SQLiteStore

        db_path = str(tmp_path / "test_search.db")
        store = SQLiteStore(db_path=db_path, enabled=True)
        yield store
        store.close()

    def _make_session(self, name, status=SessionStatus.FINISHED, session_id=None):
        import uuid

        return DestoSession(
            session_id=session_id or str(uuid.uuid4()),
            session_name=name,
            tmux_session_name=name,
            status=status,
            start_time=datetime(2025, 1, 15, 10, 0, 0),
            end_time=datetime(2025, 1, 15, 11, 0, 0),
        )

    def test_search_by_name(self, sqlite_store):
        sqlite_store.save_session(self._make_session("data-pipeline"))
        sqlite_store.save_session(self._make_session("web-server"))
        sqlite_store.save_session(self._make_session("data-cleanup"))

        results = sqlite_store.search_sessions("data")
        assert len(results) == 2
        names = {s.session_name for s in results}
        assert names == {"data-pipeline", "data-cleanup"}

    def test_search_with_status_filter(self, sqlite_store):
        sqlite_store.save_session(self._make_session("task-a", SessionStatus.FINISHED))
        sqlite_store.save_session(self._make_session("task-b", SessionStatus.FAILED))
        sqlite_store.save_session(self._make_session("task-c", SessionStatus.FINISHED))

        results = sqlite_store.search_sessions("task", status="finished")
        assert len(results) == 2
        names = {s.session_name for s in results}
        assert names == {"task-a", "task-c"}

    def test_search_no_match(self, sqlite_store):
        sqlite_store.save_session(self._make_session("alpha"))
        results = sqlite_store.search_sessions("zzz")
        assert results == []

    def test_search_disabled_store(self, tmp_path):
        from desto.redis.sqlite_store import SQLiteStore

        store = SQLiteStore(db_path=str(tmp_path / "disabled.db"), enabled=False)
        assert store.search_sessions("anything") == []

    def test_search_pagination(self, sqlite_store):
        for i in range(5):
            sqlite_store.save_session(self._make_session(f"batch-{i}"))

        page1 = sqlite_store.search_sessions("batch", limit=2, offset=0)
        page2 = sqlite_store.search_sessions("batch", limit=2, offset=2)
        assert len(page1) == 2
        assert len(page2) == 2


# ─── SQLiteHistoryTab logic tests ──────────────────────────────────────


class TestSQLiteHistoryTabRestart:
    """Test the restart logic of SQLiteHistoryTab (without NiceGUI rendering)."""

    def _make_tab(self, sqlite_store):
        from desto.app.sqlite_ui import SQLiteHistoryTab

        desto_manager = MagicMock()
        desto_manager.sqlite_store = sqlite_store
        ui_manager = MagicMock()
        tab = SQLiteHistoryTab(ui_manager, desto_manager)
        return tab

    def test_restart_extracts_command_and_starts_session(self, tmp_path):
        from desto.redis.sqlite_store import SQLiteStore

        store = SQLiteStore(db_path=str(tmp_path / "restart.db"), enabled=True)
        session = DestoSession(
            session_id="s1",
            session_name="my-job",
            tmux_session_name="my-job",
            status=SessionStatus.FINISHED,
            start_time=datetime(2025, 1, 1),
            end_time=datetime(2025, 1, 1, 1),
        )
        job = DestoJob(
            job_id="j1",
            session_id="s1",
            command="python train.py --epochs 10",
            script_path="/scripts/train.py",
            status=JobStatus.FINISHED,
        )
        store.save_session(session)
        store.save_job(job)

        tab = self._make_tab(store)
        # Make get_unique_session_name return the base name (no conflicts)
        tab.ui_manager.tmux_manager.get_unique_session_name.side_effect = lambda name: name

        # Mock NiceGUI's ui.notification to avoid import issues
        with patch("desto.app.sqlite_ui.ui"):
            tab._restart_session("s1")

        tab.ui_manager.tmux_manager.start_tmux_session.assert_called_once()
        call_args = tab.ui_manager.tmux_manager.start_tmux_session.call_args
        assert call_args[0][0] == "retry-my-job"
        assert call_args[0][1] == "python train.py --epochs 10"

    def test_restart_missing_session(self, tmp_path):
        from desto.redis.sqlite_store import SQLiteStore

        store = SQLiteStore(db_path=str(tmp_path / "empty.db"), enabled=True)
        tab = self._make_tab(store)

        with patch("desto.app.sqlite_ui.ui") as mock_ui:
            tab._restart_session("nonexistent")
            mock_ui.notification.assert_called_once()
            assert "not found" in mock_ui.notification.call_args[0][0]

    def test_restart_session_no_jobs(self, tmp_path):
        from desto.redis.sqlite_store import SQLiteStore

        store = SQLiteStore(db_path=str(tmp_path / "nojobs.db"), enabled=True)
        session = DestoSession(
            session_id="s2",
            session_name="empty-session",
            status=SessionStatus.FINISHED,
        )
        store.save_session(session)
        tab = self._make_tab(store)

        with patch("desto.app.sqlite_ui.ui") as mock_ui:
            tab._restart_session("s2")
            mock_ui.notification.assert_called_once()
            assert "No jobs" in mock_ui.notification.call_args[0][0]

    def test_delete_calls_sqlite_store(self, tmp_path):
        from desto.redis.sqlite_store import SQLiteStore

        store = SQLiteStore(db_path=str(tmp_path / "delete.db"), enabled=True)
        session = DestoSession(
            session_id="s3",
            session_name="to-delete",
            status=SessionStatus.FINISHED,
        )
        store.save_session(session)
        tab = self._make_tab(store)

        with patch("desto.app.sqlite_ui.ui"):
            tab.stats_container = MagicMock()
            tab.sessions_container = MagicMock()
            tab.status_filter = MagicMock(value="All")
            tab.search_input = MagicMock(value="")
            mock_dialog = MagicMock()
            tab._confirm_delete("s3", "to-delete", mock_dialog)

        # Session should be gone
        assert store.get_session("s3") is None
        mock_dialog.close.assert_called_once()
