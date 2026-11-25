"""Tests for the SQLite persistent store."""

import os
import sqlite3
import threading
from datetime import datetime
from unittest.mock import patch

import pytest

from desto.redis.models import DestoJob, DestoSession, JobStatus, SessionStatus
from desto.redis.sqlite_store import SQLiteStore


@pytest.fixture
def sqlite_store(tmp_path):
    """Create a SQLiteStore with a temporary database."""
    db_path = str(tmp_path / "test_desto.db")
    store = SQLiteStore(db_path=db_path, enabled=True)
    yield store
    store.close()


@pytest.fixture
def disabled_store(tmp_path):
    """Create a disabled SQLiteStore."""
    db_path = str(tmp_path / "test_disabled.db")
    store = SQLiteStore(db_path=db_path, enabled=False)
    yield store


@pytest.fixture
def sample_session():
    """Create a sample session for testing."""
    return DestoSession(
        session_id="test-session-001",
        session_name="my-test-session",
        tmux_session_name="my-test-session",
        status=SessionStatus.RUNNING,
        start_time=datetime(2025, 1, 15, 10, 30, 0),
        end_time=None,
        last_heartbeat=datetime(2025, 1, 15, 10, 35, 0),
        job_ids=["job-001", "job-002"],
        tmux_active=True,
        at_job_id=None,
    )


@pytest.fixture
def sample_job():
    """Create a sample job for testing."""
    return DestoJob(
        job_id="test-job-001",
        session_id="test-session-001",
        command="python my_script.py",
        script_path="/scripts/my_script.py",
        status=JobStatus.RUNNING,
        start_time=datetime(2025, 1, 15, 10, 30, 0),
        end_time=None,
        exit_code=None,
        error_message=None,
    )


class TestSQLiteStoreInitialization:
    def test_creates_database_file(self, tmp_path):
        db_path = str(tmp_path / "new_desto.db")
        store = SQLiteStore(db_path=db_path, enabled=True)
        assert os.path.exists(db_path)
        store.close()

    def test_creates_parent_directories(self, tmp_path):
        db_path = str(tmp_path / "nested" / "dir" / "desto.db")
        store = SQLiteStore(db_path=db_path, enabled=True)
        assert os.path.exists(db_path)
        store.close()

    def test_disabled_store_does_not_create_file(self, tmp_path):
        db_path = str(tmp_path / "should_not_exist.db")
        SQLiteStore(db_path=db_path, enabled=False)
        assert not os.path.exists(db_path)

    def test_schema_creates_tables(self, sqlite_store):
        conn = sqlite_store._get_connection()
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in cursor.fetchall()]
        assert "sessions" in tables
        assert "jobs" in tables
        assert "favorites" in tables


class TestSessionOperations:
    def test_save_session(self, sqlite_store, sample_session):
        assert sqlite_store.save_session(sample_session) is True

    def test_get_session(self, sqlite_store, sample_session):
        sqlite_store.save_session(sample_session)
        result = sqlite_store.get_session("test-session-001")
        assert result is not None
        assert result.session_id == "test-session-001"
        assert result.session_name == "my-test-session"
        assert result.status == SessionStatus.RUNNING
        assert result.tmux_active is True
        assert result.job_ids == ["job-001", "job-002"]

    def test_get_session_not_found(self, sqlite_store):
        result = sqlite_store.get_session("nonexistent")
        assert result is None

    def test_get_session_by_name(self, sqlite_store, sample_session):
        sqlite_store.save_session(sample_session)
        result = sqlite_store.get_session_by_name("my-test-session")
        assert result is not None
        assert result.session_id == "test-session-001"

    def test_update_session(self, sqlite_store, sample_session):
        sqlite_store.save_session(sample_session)

        # Update the session
        sample_session.status = SessionStatus.FINISHED
        sample_session.end_time = datetime(2025, 1, 15, 11, 0, 0)
        sqlite_store.save_session(sample_session)

        result = sqlite_store.get_session("test-session-001")
        assert result.status == SessionStatus.FINISHED
        assert result.end_time == datetime(2025, 1, 15, 11, 0, 0)

    def test_get_all_sessions(self, sqlite_store):
        for i in range(5):
            session = DestoSession(
                session_id=f"session-{i}",
                session_name=f"session-{i}",
                tmux_session_name=f"session-{i}",
                status=SessionStatus.FINISHED if i < 3 else SessionStatus.RUNNING,
                start_time=datetime(2025, 1, 15, 10 + i, 0, 0),
            )
            sqlite_store.save_session(session)

        all_sessions = sqlite_store.get_all_sessions()
        assert len(all_sessions) == 5

    def test_get_all_sessions_with_status_filter(self, sqlite_store):
        for i in range(5):
            session = DestoSession(
                session_id=f"session-{i}",
                session_name=f"session-{i}",
                tmux_session_name=f"session-{i}",
                status=SessionStatus.FINISHED if i < 3 else SessionStatus.RUNNING,
                start_time=datetime(2025, 1, 15, 10 + i, 0, 0),
            )
            sqlite_store.save_session(session)

        running = sqlite_store.get_all_sessions(status="running")
        assert len(running) == 2

    def test_get_all_sessions_with_pagination(self, sqlite_store):
        for i in range(10):
            session = DestoSession(
                session_id=f"session-{i:02d}",
                session_name=f"session-{i:02d}",
                tmux_session_name=f"session-{i:02d}",
                status=SessionStatus.FINISHED,
                start_time=datetime(2025, 1, 15, 10 + i, 0, 0),
            )
            sqlite_store.save_session(session)

        page1 = sqlite_store.get_all_sessions(limit=3, offset=0)
        page2 = sqlite_store.get_all_sessions(limit=3, offset=3)
        assert len(page1) == 3
        assert len(page2) == 3
        assert page1[0].session_id != page2[0].session_id

    def test_get_session_count(self, sqlite_store):
        for i in range(5):
            session = DestoSession(
                session_id=f"session-{i}",
                session_name=f"session-{i}",
                tmux_session_name=f"session-{i}",
                status=SessionStatus.FINISHED if i < 3 else SessionStatus.RUNNING,
                start_time=datetime(2025, 1, 15, 10 + i, 0, 0),
            )
            sqlite_store.save_session(session)

        assert sqlite_store.get_session_count() == 5
        assert sqlite_store.get_session_count(status="finished") == 3
        assert sqlite_store.get_session_count(status="running") == 2

    def test_delete_session(self, sqlite_store, sample_session, sample_job):
        sqlite_store.save_session(sample_session)
        sqlite_store.save_job(sample_job)

        assert sqlite_store.delete_session("test-session-001") is True
        assert sqlite_store.get_session("test-session-001") is None
        # Associated jobs should also be deleted
        assert sqlite_store.get_job("test-job-001") is None


class TestJobOperations:
    def test_save_job(self, sqlite_store, sample_session, sample_job):
        sqlite_store.save_session(sample_session)
        assert sqlite_store.save_job(sample_job) is True

    def test_get_job(self, sqlite_store, sample_session, sample_job):
        sqlite_store.save_session(sample_session)
        sqlite_store.save_job(sample_job)

        result = sqlite_store.get_job("test-job-001")
        assert result is not None
        assert result.job_id == "test-job-001"
        assert result.session_id == "test-session-001"
        assert result.command == "python my_script.py"
        assert result.status == JobStatus.RUNNING

    def test_get_job_not_found(self, sqlite_store):
        result = sqlite_store.get_job("nonexistent")
        assert result is None

    def test_get_jobs_for_session(self, sqlite_store, sample_session):
        sqlite_store.save_session(sample_session)

        for i in range(3):
            job = DestoJob(
                job_id=f"job-{i:03d}",
                session_id="test-session-001",
                command=f"echo {i}",
                script_path=f"/scripts/script_{i}.sh",
                status=JobStatus.FINISHED,
                start_time=datetime(2025, 1, 15, 10 + i, 0, 0),
                end_time=datetime(2025, 1, 15, 10 + i, 30, 0),
                exit_code=0,
            )
            sqlite_store.save_job(job)

        jobs = sqlite_store.get_jobs_for_session("test-session-001")
        assert len(jobs) == 3

    def test_update_job(self, sqlite_store, sample_session, sample_job):
        sqlite_store.save_session(sample_session)
        sqlite_store.save_job(sample_job)

        # Update the job
        sample_job.status = JobStatus.FINISHED
        sample_job.end_time = datetime(2025, 1, 15, 11, 0, 0)
        sample_job.exit_code = 0
        sqlite_store.save_job(sample_job)

        result = sqlite_store.get_job("test-job-001")
        assert result.status == JobStatus.FINISHED
        assert result.exit_code == 0


class TestDisabledStore:
    def test_disabled_save_session(self, disabled_store, sample_session):
        assert disabled_store.save_session(sample_session) is False

    def test_disabled_get_session(self, disabled_store):
        assert disabled_store.get_session("anything") is None

    def test_disabled_get_all_sessions(self, disabled_store):
        assert disabled_store.get_all_sessions() == []

    def test_disabled_save_job(self, disabled_store, sample_job):
        assert disabled_store.save_job(sample_job) is False


class TestUtilityMethods:
    def test_thread_safety(self, sqlite_store, sample_session):
        """Test that concurrent writes don't corrupt data."""
        import threading

        def write_session(idx):
            session = DestoSession(
                session_id=f"thread-session-{idx}",
                session_name=f"thread-session-{idx}",
                tmux_session_name=f"thread-session-{idx}",
                status=SessionStatus.RUNNING,
                start_time=datetime(2025, 1, 15, 10, 0, 0),
            )
            sqlite_store.save_session(session)

        threads = [threading.Thread(target=write_session, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert sqlite_store.get_session_count() == 10


class TestConnectionManagement:
    def test_wal_mode_enabled(self, sqlite_store):
        """Verify WAL journal mode is set."""
        conn = sqlite_store._get_connection()
        result = conn.execute("PRAGMA journal_mode").fetchone()
        assert result[0] == "wal"

    def test_foreign_keys_enabled(self, sqlite_store):
        """Verify foreign keys are enforced."""
        conn = sqlite_store._get_connection()
        result = conn.execute("PRAGMA foreign_keys").fetchone()
        assert result[0] == 1

    def test_connection_reuse_same_thread(self, sqlite_store):
        """Verify the same connection is returned on the same thread."""
        conn1 = sqlite_store._get_connection()
        conn2 = sqlite_store._get_connection()
        assert conn1 is conn2

    def test_close_and_reconnect(self, sqlite_store, sample_session):
        """Verify store works after close and reconnect."""
        sqlite_store.save_session(sample_session)
        sqlite_store.close()

        # Should auto-create a new connection
        result = sqlite_store.get_session("test-session-001")
        assert result is not None
        assert result.session_id == "test-session-001"

    def test_close_idempotent(self, sqlite_store):
        """Closing multiple times should not error."""
        sqlite_store.close()
        sqlite_store.close()

    def test_row_factory_is_row(self, sqlite_store):
        """Verify row_factory is set to sqlite3.Row."""
        conn = sqlite_store._get_connection()
        assert conn.row_factory is sqlite3.Row


class TestSessionEdgeCases:
    def test_session_with_empty_job_ids(self, sqlite_store):
        """Sessions with no jobs should round-trip correctly."""
        session = DestoSession(
            session_id="empty-jobs",
            session_name="empty-jobs",
            tmux_session_name="empty-jobs",
            status=SessionStatus.STARTING,
            start_time=datetime(2025, 1, 15, 10, 0, 0),
            job_ids=[],
        )
        sqlite_store.save_session(session)
        result = sqlite_store.get_session("empty-jobs")
        assert result.job_ids == []

    def test_session_with_at_job_id(self, sqlite_store):
        """Sessions with at_job_id should round-trip correctly."""
        session = DestoSession(
            session_id="scheduled-session",
            session_name="scheduled",
            tmux_session_name="scheduled",
            status=SessionStatus.SCHEDULED,
            start_time=datetime(2025, 1, 15, 10, 0, 0),
            at_job_id="42",
        )
        sqlite_store.save_session(session)
        result = sqlite_store.get_session("scheduled-session")
        assert result.at_job_id == "42"
        assert result.status == SessionStatus.SCHEDULED

    def test_session_with_none_timestamps(self, sqlite_store):
        """Sessions with None timestamps should round-trip correctly."""
        session = DestoSession(
            session_id="no-times",
            session_name="no-times",
            tmux_session_name="no-times",
            status=SessionStatus.STARTING,
            start_time=None,
            end_time=None,
            last_heartbeat=None,
        )
        sqlite_store.save_session(session)
        result = sqlite_store.get_session("no-times")
        assert result.start_time is None
        assert result.end_time is None
        assert result.last_heartbeat is None

    def test_session_tmux_active_false(self, sqlite_store):
        """tmux_active=False should round-trip correctly."""
        session = DestoSession(
            session_id="inactive-tmux",
            session_name="inactive",
            tmux_session_name="inactive",
            status=SessionStatus.FINISHED,
            tmux_active=False,
        )
        sqlite_store.save_session(session)
        result = sqlite_store.get_session("inactive-tmux")
        assert result.tmux_active is False

    def test_get_session_by_name_not_found(self, sqlite_store):
        """get_session_by_name returns None for nonexistent name."""
        result = sqlite_store.get_session_by_name("nonexistent-name")
        assert result is None

    def test_get_session_by_name_returns_most_recent(self, sqlite_store):
        """get_session_by_name returns the most recently created session with that name."""
        for i in range(3):
            session = DestoSession(
                session_id=f"dup-{i}",
                session_name="same-name",
                tmux_session_name="same-name",
                status=SessionStatus.FINISHED if i < 2 else SessionStatus.RUNNING,
                start_time=datetime(2025, 1, 15, 10 + i, 0, 0),
            )
            sqlite_store.save_session(session)

        result = sqlite_store.get_session_by_name("same-name")
        assert result is not None
        # The most recent one should be returned (ordered by created_at DESC)
        assert result.session_id in ["dup-0", "dup-1", "dup-2"]

    def test_delete_nonexistent_session(self, sqlite_store):
        """Deleting a nonexistent session should still return True (no error)."""
        result = sqlite_store.delete_session("nonexistent-id")
        assert result is True

    def test_get_all_sessions_empty(self, sqlite_store):
        """Empty store returns empty list."""
        assert sqlite_store.get_all_sessions() == []

    def test_get_session_count_empty(self, sqlite_store):
        """Empty store returns 0."""
        assert sqlite_store.get_session_count() == 0

    def test_session_all_statuses(self, sqlite_store):
        """All SessionStatus values should round-trip correctly."""
        for status in SessionStatus:
            session = DestoSession(
                session_id=f"status-{status.value}",
                session_name=f"status-{status.value}",
                tmux_session_name=f"status-{status.value}",
                status=status,
            )
            sqlite_store.save_session(session)
            result = sqlite_store.get_session(f"status-{status.value}")
            assert result.status == status


class TestJobEdgeCases:
    def test_job_with_error_message(self, sqlite_store, sample_session):
        """Jobs with error messages should round-trip correctly."""
        sqlite_store.save_session(sample_session)
        job = DestoJob(
            job_id="error-job",
            session_id="test-session-001",
            command="failing_script.py",
            script_path="/scripts/failing.py",
            status=JobStatus.FAILED,
            start_time=datetime(2025, 1, 15, 10, 0, 0),
            end_time=datetime(2025, 1, 15, 10, 5, 0),
            exit_code=1,
            error_message="Script crashed with ImportError",
        )
        sqlite_store.save_job(job)
        result = sqlite_store.get_job("error-job")
        assert result.status == JobStatus.FAILED
        assert result.exit_code == 1
        assert result.error_message == "Script crashed with ImportError"

    def test_job_with_none_error_message(self, sqlite_store, sample_session):
        """Jobs with None error_message should round-trip as None."""
        sqlite_store.save_session(sample_session)
        job = DestoJob(
            job_id="ok-job",
            session_id="test-session-001",
            command="echo ok",
            script_path="/scripts/ok.sh",
            status=JobStatus.FINISHED,
            exit_code=0,
            error_message=None,
        )
        sqlite_store.save_job(job)
        result = sqlite_store.get_job("ok-job")
        assert result.error_message is None

    def test_job_with_none_timestamps(self, sqlite_store, sample_session):
        """Jobs with None start/end times should round-trip correctly."""
        sqlite_store.save_session(sample_session)
        job = DestoJob(
            job_id="queued-job",
            session_id="test-session-001",
            command="echo queued",
            script_path="/scripts/queued.sh",
            status=JobStatus.QUEUED,
            start_time=None,
            end_time=None,
        )
        sqlite_store.save_job(job)
        result = sqlite_store.get_job("queued-job")
        assert result.start_time is None
        assert result.end_time is None

    def test_get_jobs_for_session_empty(self, sqlite_store, sample_session):
        """Session with no jobs returns empty list."""
        sqlite_store.save_session(sample_session)
        jobs = sqlite_store.get_jobs_for_session("test-session-001")
        assert jobs == []

    def test_get_jobs_for_nonexistent_session(self, sqlite_store):
        """Querying jobs for nonexistent session returns empty list."""
        jobs = sqlite_store.get_jobs_for_session("nonexistent")
        assert jobs == []

    def test_job_all_statuses(self, sqlite_store, sample_session):
        """All JobStatus values should round-trip correctly."""
        sqlite_store.save_session(sample_session)
        for status in JobStatus:
            job = DestoJob(
                job_id=f"status-{status.value}",
                session_id="test-session-001",
                command=f"echo {status.value}",
                script_path=f"/scripts/{status.value}.sh",
                status=status,
            )
            sqlite_store.save_job(job)
            result = sqlite_store.get_job(f"status-{status.value}")
            assert result.status == status

    def test_job_exit_code_zero(self, sqlite_store, sample_session):
        """Exit code 0 should be preserved (not confused with None)."""
        sqlite_store.save_session(sample_session)
        job = DestoJob(
            job_id="exit-zero",
            session_id="test-session-001",
            command="echo success",
            script_path="/scripts/ok.sh",
            status=JobStatus.FINISHED,
            exit_code=0,
        )
        sqlite_store.save_job(job)
        result = sqlite_store.get_job("exit-zero")
        assert result.exit_code == 0


class TestDisabledStoreExtended:
    def test_disabled_get_session_by_name(self, disabled_store):
        assert disabled_store.get_session_by_name("anything") is None

    def test_disabled_get_session_count(self, disabled_store):
        assert disabled_store.get_session_count() == 0

    def test_disabled_delete_session(self, disabled_store):
        assert disabled_store.delete_session("anything") is False

    def test_disabled_get_job(self, disabled_store):
        assert disabled_store.get_job("anything") is None

    def test_disabled_get_jobs_for_session(self, disabled_store):
        assert disabled_store.get_jobs_for_session("anything") == []

    def test_disabled_close(self, disabled_store):
        """Close on disabled store should not error."""
        disabled_store.close()


class TestThreadSafetyExtended:
    def test_concurrent_reads_and_writes(self, sqlite_store):
        """Test concurrent reads and writes don't interfere."""
        results = {"write_errors": 0, "read_errors": 0}

        def write_sessions(start, count):
            for i in range(start, start + count):
                session = DestoSession(
                    session_id=f"concurrent-{i}",
                    session_name=f"concurrent-{i}",
                    tmux_session_name=f"concurrent-{i}",
                    status=SessionStatus.RUNNING,
                )
                if not sqlite_store.save_session(session):
                    results["write_errors"] += 1

        def read_sessions():
            for _ in range(20):
                sqlite_store.get_all_sessions()

        writers = [threading.Thread(target=write_sessions, args=(i * 5, 5)) for i in range(4)]
        readers = [threading.Thread(target=read_sessions) for _ in range(3)]

        for t in writers + readers:
            t.start()
        for t in writers + readers:
            t.join()

        assert results["write_errors"] == 0
        assert sqlite_store.get_session_count() == 20

    def test_concurrent_writes_to_different_tables(self, sqlite_store):
        """Test concurrent writes across the sessions and jobs tables."""
        session = DestoSession(
            session_id="parent-session",
            session_name="parent",
            tmux_session_name="parent",
            status=SessionStatus.RUNNING,
        )
        sqlite_store.save_session(session)

        def write_jobs():
            for i in range(10):
                job = DestoJob(
                    job_id=f"cjob-{i}",
                    session_id="parent-session",
                    command=f"echo {i}",
                    script_path=f"/s/{i}.sh",
                    status=JobStatus.QUEUED,
                )
                sqlite_store.save_job(job)

        def write_sessions():
            for i in range(10):
                sqlite_store.save_session(
                    DestoSession(
                        session_id=f"csession-{i}",
                        session_name=f"csession-{i}",
                        tmux_session_name=f"csession-{i}",
                        status=SessionStatus.RUNNING,
                    )
                )

        t1 = threading.Thread(target=write_jobs)
        t2 = threading.Thread(target=write_sessions)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(sqlite_store.get_jobs_for_session("parent-session")) == 10
        assert sqlite_store.get_session_count() == 11


class TestEnvironmentVariableDefaults:
    def test_default_db_path_from_env(self, tmp_path):
        """SQLITE_DB_PATH env var sets the db path."""
        env_path = str(tmp_path / "env_test.db")
        with patch.dict(os.environ, {"SQLITE_DB_PATH": env_path}):
            store = SQLiteStore(enabled=True)
            assert store.db_path == env_path
            store.close()

    def test_explicit_db_path_overrides_env(self, tmp_path):
        """Explicit db_path param takes precedence over env var."""
        explicit_path = str(tmp_path / "explicit.db")
        with patch.dict(os.environ, {"SQLITE_DB_PATH": "/should/not/use"}):
            store = SQLiteStore(db_path=explicit_path, enabled=True)
            assert store.db_path == explicit_path
            store.close()


class TestSchemaIndices:
    def test_indices_exist(self, sqlite_store):
        """Verify all expected indices are created."""
        conn = sqlite_store._get_connection()
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index' ORDER BY name")
        indices = [row[0] for row in cursor.fetchall()]
        expected = [
            "idx_favorites_name",
            "idx_jobs_session_id",
            "idx_jobs_status",
            "idx_sessions_session_name",
            "idx_sessions_start_time",
            "idx_sessions_status",
        ]
        for idx in expected:
            assert idx in indices
