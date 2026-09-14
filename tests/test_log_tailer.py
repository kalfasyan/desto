import os

from desto.app.log_tailer import LogTailer, read_last_lines


def test_initial_lines_returns_tail_and_positions_at_eof(tmp_path):
    log = tmp_path / "session.log"
    log.write_text("".join(f"line {i}\n" for i in range(1, 21)))

    tailer = LogTailer(log)
    lines = tailer.initial_lines(5)

    assert lines == ["line 16", "line 17", "line 18", "line 19", "line 20"]
    assert tailer.offset == log.stat().st_size
    assert tailer.poll() == []


def test_poll_returns_only_appended_lines_in_order(tmp_path):
    log = tmp_path / "session.log"
    log.write_text("first\n")

    tailer = LogTailer(log)
    tailer.initial_lines()

    with log.open("a") as f:
        f.write("second\nthird\n")

    assert tailer.poll() == ["second", "third"]
    assert tailer.poll() == []


def test_poll_holds_partial_line_until_completed(tmp_path):
    log = tmp_path / "session.log"
    log.write_text("")

    tailer = LogTailer(log)
    tailer.initial_lines()

    with log.open("a") as f:
        f.write("partial")

    assert tailer.poll() == []

    with log.open("a") as f:
        f.write("-done\n")

    assert tailer.poll() == ["partial-done"]
    assert tailer.poll() == []


def test_poll_recovers_from_truncation(tmp_path):
    log = tmp_path / "session.log"
    log.write_text("old line one\nold line two\n")

    tailer = LogTailer(log)
    tailer.initial_lines()

    log.write_text("new\n")

    assert tailer.poll() == ["new"]


def test_poll_detects_file_replacement(tmp_path):
    log = tmp_path / "session.log"
    log.write_text("original\n")

    tailer = LogTailer(log)
    tailer.initial_lines()

    replacement = tmp_path / "replacement.log"
    replacement.write_text("rotated line\n")
    os.replace(replacement, log)

    assert tailer.poll() == ["rotated line"]


def test_missing_file_returns_empty_and_recovers(tmp_path):
    log = tmp_path / "missing.log"

    tailer = LogTailer(log)
    assert tailer.initial_lines() == []
    assert tailer.poll() == []

    log.write_text("hello\n")

    assert tailer.poll() == ["hello"]


def test_invalid_utf8_is_replaced_without_raising(tmp_path):
    log = tmp_path / "session.log"
    log.write_bytes(b"ok\n\xff\xfe bad\n")

    tailer = LogTailer(log)
    lines = tailer.initial_lines()

    assert len(lines) == 2
    assert lines[0] == "ok"
    assert "bad" in lines[1]

    with log.open("ab") as f:
        f.write(b"\xff more\n")

    polled = tailer.poll()
    assert len(polled) == 1
    assert "more" in polled[0]


def test_poll_bounds_newline_free_fragment(tmp_path):
    log = tmp_path / "session.log"
    log.write_text("")

    tailer = LogTailer(log)
    tailer.initial_lines()

    with log.open("a") as f:
        f.write("x" * (LogTailer.MAX_LINE_CHARS + 100))

    lines = tailer.poll()

    assert lines and lines[0].endswith("...[truncated]")
    assert len(lines[0]) <= LogTailer.MAX_LINE_CHARS + len(" ...[truncated]")
    assert tailer.partial == ""


def test_read_last_lines_chunked_backward_read(tmp_path):
    log = tmp_path / "big.log"
    log.write_text("".join(f"line {i:03d}\n" for i in range(500)))

    lines = read_last_lines(log, 10, block_size=16)

    assert lines == [f"line {i:03d}" for i in range(490, 500)]
