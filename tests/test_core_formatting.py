from datetime import datetime, timedelta

import pytest

from desto.core.formatting import (
    decode_hash,
    extract_at_command,
    format_duration,
    format_scheduled_datetime,
    format_seconds,
    format_timestamp,
    parse_atq_output,
    session_row_times,
    session_sort_key,
    summarize_jobs,
)


def test_decode_hash_handles_bytes_and_str():
    assert decode_hash({b"a": b"1", "b": "2"}) == {"a": "1", "b": "2"}


@pytest.mark.parametrize(
    "seconds, expected",
    [(-1, "N/A"), (0, "0s"), (59, "59s"), (61, "1m 1s"), (3661, "1h 1m 1s")],
)
def test_format_seconds(seconds, expected):
    assert format_seconds(seconds) == expected


@pytest.mark.parametrize(
    "value, expected",
    [
        ("N/A", "N/A"),
        ("0:00:05", "5s"),
        ("0:02:05.5", "2m 5s"),
        ("1 day, 2:03:04", "26h 3m 4s"),
        ("12s", "12s"),
        (None, "None"),
    ],
)
def test_format_duration(value, expected):
    assert format_duration(value) == expected


def test_format_timestamp_parses_iso_and_falls_back():
    assert format_timestamp("2025-01-02T03:04:05Z") == "2025-01-02 03:04:05"
    assert format_timestamp("not a timestamp but quite long") == "not a timestamp but"


def test_session_sort_key_falls_back_to_created():
    assert session_sort_key({"start_time": "2025-01-01T00:00:00"}) == "2025-01-01T00:00:00"
    created = datetime(2025, 1, 1, 12, 0, 0)
    assert session_sort_key({"created": str(created.timestamp())}) == created.isoformat()
    assert session_sort_key({}) == ""


def test_session_row_times_finished_session():
    times = session_row_times({"start_time": "2025-01-01T00:00:00", "end_time": "2025-01-01T00:01:30"})
    assert times["started"] == "2025-01-01 00:00:00"
    assert times["finished"] == "2025-01-01 00:01:30"
    assert times["job_duration"] == "1m 30s"
    assert times["session_duration"] == "1m 30s"


def test_session_row_times_running_session():
    start = (datetime.now() - timedelta(seconds=10)).isoformat()
    times = session_row_times({"start_time": start, "job_status": "running", "job_elapsed": "0:00:09"})
    assert times["finished"] == "Running"
    assert times["job_duration"] == "9s"
    assert times["session_duration"].endswith("s")
    assert times["end_time"] is None


def test_session_row_times_without_times():
    times = session_row_times({})
    assert times["started"] == "Unknown"
    assert times["finished"] == "N/A"
    assert times["job_duration"] == "N/A"
    assert times["session_duration"] == "N/A"


def test_summarize_jobs_prefers_running_and_reads_exit_code_from_error():
    jobs = [
        {"job_id": "2", "status": "failed", "error_message": "exit code: 3", "command": "b"},
        {"job_id": "1", "status": "finished", "exit_code": "0", "command": "a"},
    ]
    assert summarize_jobs(jobs) == {"status": "failed", "exit_code": "3", "command": "a"}
    assert summarize_jobs([{"status": "running"}, {"status": "failed"}])["status"] == "running"
    assert summarize_jobs([{"status": "queued"}])["status"] == "queued"


def test_parse_atq_output():
    out = "5\tMon Jul 14 07:59:00 2025 a alice\n\n7\tTue Jul 15 08:00:00 2025 a bob\n"
    assert parse_atq_output(out) == [
        ("5", "Mon Jul 14 07:59:00 2025", "alice"),
        ("7", "Tue Jul 15 08:00:00 2025", "bob"),
    ]


def test_extract_at_command():
    out = "#!/bin/sh\nexport FOO=1\ncd /tmp || exit 1\necho hello\n\n"
    assert extract_at_command(out) == "echo hello"
    assert extract_at_command("x" * 80) == "x" * 57 + "..."
    assert extract_at_command("# only comments\n") == "Unknown command"


def test_format_scheduled_datetime():
    assert format_scheduled_datetime("Mon Jul 14 07:59:00 2025") == "2025-07-14T07:59:00"
    assert format_scheduled_datetime("garbage") == "garbage"


# --- Table rows shared by the web dashboard and the terminal UI ---------------------------

from desto.core.formatting import count_by_category, scheduled_job_rows, session_event_message, session_rows  # noqa: E402


def _session(name, status, start, session_id=None):
    return {"session_name": name, "status": status, "start_time": start, "session_id": session_id or name}


def test_session_rows_skip_scheduled_sort_newest_first_and_carry_command():
    sessions = {
        "old": _session("old", "finished", "2026-01-01T10:00:00"),
        "new": _session("new", "running", "2026-01-02T10:00:00"),
        "later": _session("later", "scheduled", "2026-01-03T10:00:00"),
    }
    job_info = {"new": {"status": "running", "command": "bash new.sh"}}

    rows = session_rows(sessions, tmux_active={"new"}, job_info=job_info)

    assert [r.name for r in rows] == ["new", "old"]
    assert rows[0].category == "running" and rows[0].tmux_active and rows[0].command == "bash new.sh"
    assert rows[1].category == "finished" and not rows[1].tmux_active


def test_count_by_category_counts_rows():
    sessions = {"a": _session("a", "finished", "1"), "b": _session("b", "failed", "2"), "c": _session("c", "finished", "3")}
    assert count_by_category(session_rows(sessions, set(), {})) == {"total": 3, "running": 0, "finished": 2, "failed": 1}


def test_scheduled_job_rows_hide_internal_jobs_and_label_recurring():
    jobs = [
        {"id": "1", "datetime": "2026-01-01T10:00:00", "user": "ann", "metadata": None},
        {"id": "2", "metadata": {"status": "finished_internal"}},
        {"id": "3", "datetime": "x", "user": "x", "metadata": {"status": "scheduled", "recurring_id": "r1", "recurrence": "every day", "scheduled_time": "2026-01-02T08:00:00", "user": "bob"}},
    ]

    rows = scheduled_job_rows(jobs)

    assert [r.job_id for r in rows] == ["1", "3"]
    assert (rows[0].scheduled_time, rows[0].user, rows[0].status) == ("2026-01-01T10:00:00", "ann", "scheduled")
    assert (rows[1].scheduled_time, rows[1].user, rows[1].status) == ("2026-01-02T08:00:00", "bob", "scheduled · every day")


@pytest.mark.parametrize(
    "update, expected",
    [
        ({"session_name": "s", "status": "finished"}, ("Session 's' finished!", "positive")),
        ({"session_name": "s", "status": "failed"}, ("Session 's' failed!", "negative")),
        ({"session_name": "s", "status": "running"}, None),
    ],
)
def test_session_event_message(update, expected):
    assert session_event_message(update) == expected
