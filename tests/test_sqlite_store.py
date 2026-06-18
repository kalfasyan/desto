"""Tests for the SQLite persistent store."""

import os
from datetime import datetime

import pytest

from desto.redis.models import DestoJob, DestoSession, FavoriteCommand, JobStatus, SessionStatus
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


@pytest.fixture
def sample_favorite():
    """Create a sample favorite for testing."""
    return FavoriteCommand(
        favorite_id="test-fav-001",
        name="Deploy Script",
        command="bash deploy.sh --production",
        created_at=datetime(2025, 1, 10, 8, 0, 0),
        last_used_at=datetime(2025, 1, 15, 12, 0, 0),
        use_count=5,
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


class TestFavoriteOperations:
    def test_save_favorite(self, sqlite_store, sample_favorite):
        assert sqlite_store.save_favorite(sample_favorite) is True

    def test_get_all_favorites(self, sqlite_store):
        for i in range(3):
            fav = FavoriteCommand(
                favorite_id=f"fav-{i}",
                name=f"Command {i}",
                command=f"echo {i}",
                created_at=datetime(2025, 1, 10, 8 + i, 0, 0),
                use_count=i * 2,
            )
            sqlite_store.save_favorite(fav)

        favorites = sqlite_store.get_all_favorites()
        assert len(favorites) == 3
        # Should be sorted by use_count DESC
        assert favorites[0].use_count >= favorites[1].use_count

    def test_delete_favorite(self, sqlite_store, sample_favorite):
        sqlite_store.save_favorite(sample_favorite)
        assert sqlite_store.delete_favorite("test-fav-001") is True
        favorites = sqlite_store.get_all_favorites()
        assert len(favorites) == 0


class TestDisabledStore:
    def test_disabled_save_session(self, disabled_store, sample_session):
        assert disabled_store.save_session(sample_session) is False

    def test_disabled_get_session(self, disabled_store):
        assert disabled_store.get_session("anything") is None

    def test_disabled_get_all_sessions(self, disabled_store):
        assert disabled_store.get_all_sessions() == []

    def test_disabled_save_job(self, disabled_store, sample_job):
        assert disabled_store.save_job(sample_job) is False

    def test_disabled_save_favorite(self, disabled_store, sample_favorite):
        assert disabled_store.save_favorite(sample_favorite) is False

    def test_disabled_get_stats(self, disabled_store):
        assert disabled_store.get_stats() == {"sessions": 0, "jobs": 0, "favorites": 0}


class TestUtilityMethods:
    def test_get_stats(self, sqlite_store, sample_session, sample_job, sample_favorite):
        sqlite_store.save_session(sample_session)
        sqlite_store.save_job(sample_job)
        sqlite_store.save_favorite(sample_favorite)

        stats = sqlite_store.get_stats()
        assert stats == {"sessions": 1, "jobs": 1, "favorites": 1}

    def test_clear_all(self, sqlite_store, sample_session, sample_job, sample_favorite):
        sqlite_store.save_session(sample_session)
        sqlite_store.save_job(sample_job)
        sqlite_store.save_favorite(sample_favorite)

        assert sqlite_store.clear_all() is True
        stats = sqlite_store.get_stats()
        assert stats == {"sessions": 0, "jobs": 0, "favorites": 0}

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

        stats = sqlite_store.get_stats()
        assert stats["sessions"] == 10
