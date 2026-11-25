"""Tests for desto.core.scripts: the script helpers shared by the dashboard, the TUI and the CLI."""

import os
import shlex

import pytest

from desto.core import scripts


@pytest.mark.parametrize("name, kind", [("a.py", "python"), ("a.sh", "bash"), ("a.rb", "unknown")])
def test_script_type_and_icon(name, kind):
    assert scripts.script_type(name) == kind
    assert scripts.script_icon(kind) == scripts.SCRIPT_ICONS[kind]


@pytest.mark.parametrize(
    "name, valid", [("build-1", True), ("a_b", True), ("", False), ("has space", False), ("x" * 16, False)]
)
def test_is_valid_name(name, valid):
    assert scripts.is_valid_name(name) is valid


def test_list_scripts_returns_sorted_supported_files(tmp_path):
    for name in ("b.sh", "a.py", "notes.txt"):
        (tmp_path / name).write_text("")
    (tmp_path / "dir.sh").mkdir()
    assert scripts.list_scripts(tmp_path) == ["a.py", "b.sh"]


def test_build_execution_command_picks_interpreter():
    assert scripts.build_execution_command("/s/a.py", "-v", "py3") == "py3 '/s/a.py' -v"
    assert scripts.build_execution_command("/s/a.sh", "x") == "bash '/s/a.sh' x"
    assert scripts.build_execution_command("/s/a.rb", "") == "'/s/a.rb' "


def test_launch_command_adds_banner():
    assert scripts.launch_command("/s/a.sh", "x") == "echo '=== Running script: a.sh ===' && (bash '/s/a.sh' x)"


def test_chain_command_runs_in_order_and_numbers_steps():
    assert scripts.chain_command([("/s/a.sh", "1"), ("/s/b.py", "")], "python3") == (
        "echo '=== Running script 1 of 2: a.sh ===' && (bash '/s/a.sh' 1) && echo '=== Running script 2 of 2: b.py ===' && (python3 '/s/b.py' )"
    )


def test_create_script_writes_executable_file_with_shebang(tmp_path):
    path = scripts.create_script(tmp_path, "my job", "echo hi\n", "bash")

    assert path == tmp_path / "my_job.sh"
    assert path.read_text() == "#!/bin/bash\necho hi\n"
    assert os.access(path, os.X_OK)


@pytest.mark.parametrize("name, kind", [("", "bash"), ("x" * 16, "bash"), ("ok", "ruby")])
def test_create_script_rejects_bad_input(tmp_path, name, kind):
    with pytest.raises(ValueError):
        scripts.create_script(tmp_path, name, "", kind)


def test_session_script_creates_then_appends(tmp_path):
    log_file = tmp_path / "it's.log"
    fresh = scripts.session_script("s1", "echo hi", log_file)
    assert "NEW SESSION" not in fresh
    assert "> " + shlex.quote(str(log_file)) in fresh
    assert "-m desto.hooks.mark_job_finished s1 $SCRIPT_EXIT_CODE" in fresh
    log_file.write_text("old run\n")
    again = scripts.session_script("s1", "echo hi", log_file)
    assert "NEW SESSION" in again
    assert ">> " + shlex.quote(str(log_file)) in again


def test_completion_hook_runs_the_bundled_module_with_the_exit_code():
    import sys

    command = scripts.completion_hook("my session", "$SCRIPT_EXIT_CODE")
    assert command.startswith(sys.executable) or command.startswith(f"'{sys.executable}'")
    assert "-m desto.hooks.mark_job_finished 'my session' $SCRIPT_EXIT_CODE" in command
