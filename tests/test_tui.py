"""Tests for the terminal UI, driven headlessly with Textual's Pilot against a fake DestoService."""

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from textual.widgets import Button, DataTable, Input, Label, TabbedContent, TextArea

from desto.core import scripts
from desto.core.formatting import ScheduledJobRow, SessionRow
from desto.core.scheduled_jobs import ScheduleError
from desto.core.service import DestoService, Snapshot
from desto.core.system_stats import SystemStats
from desto.tui.app import DestoApp
from desto.tui.modals import ConfirmScreen, FormScreen, LogScreen, ScheduleScreen, UsageScreen
from desto.tui.sessions import attach_command
from desto.tui.stats import meter

STATS = SystemStats(12.0, [], 40.0, 1.5, 6.0, 70.0, 30.0, 10.0, "0.1%", "3.0 MB")


def session_row(name, category="running", tmux_active=True, command="bash job.sh"):
    session = {"session_name": name, "status": category, "start_time": "2026-01-01T10:00:00"}
    return SessionRow(name, session, tmux_active, category, category.title(), "green", command)


@pytest.fixture
def service(tmp_path):
    svc = MagicMock(spec=DestoService)
    svc.SCRIPTS_DIR = tmp_path / "scripts"
    svc.LOG_DIR = tmp_path / "logs"
    svc.SCRIPTS_DIR.mkdir()
    svc.LOG_DIR.mkdir()
    (svc.SCRIPTS_DIR / "build.sh").write_text("#!/bin/bash\necho build\n")
    (svc.SCRIPTS_DIR / "report.py").write_text("print('report')\n")
    svc.python_executable = "python3"
    svc.pubsub = None
    svc.get_script_file.side_effect = lambda name: svc.SCRIPTS_DIR / name
    svc.get_log_file.side_effect = lambda name: svc.LOG_DIR / f"{name}.log"
    svc.snapshot.return_value = Snapshot(
        rows=[session_row("live-job"), session_row("done-job", "finished", tmux_active=False)],
        counts={"total": 2, "running": 1, "finished": 1, "failed": 0},
        scheduled=[ScheduledJobRow("7", "2026-01-02T08:00:00", "ann", "scheduled", None)],
    )
    svc.list_favorites.return_value = [SimpleNamespace(favorite_id="f1", name="deploy", command="make deploy", use_count=3, last_used_at=None)]
    svc.start_tmux_session.return_value = True
    return svc


def run(service, scenario, size=(140, 40)):
    """Run scenario(app, pilot) inside a headless app."""

    async def main():
        monitor = MagicMock()
        monitor.read.return_value = STATS
        with patch("desto.core.at_job_manager.AtJobManager.is_atd_running", return_value=True):
            app = DestoApp(service, monitor=monitor)
            async with app.run_test(size=size) as pilot:
                await settle(app, pilot)
                await scenario(app, pilot)

    asyncio.run(main())


async def settle(app, pilot):
    await app.workers.wait_for_complete()
    await pilot.pause()


# --- Sessions tab ---------------------------------------------------------------------------


def test_usage_columns_and_usage_screen(service):
    live = session_row("live-job")
    live.session["session_id"] = "sid-live"
    service.snapshot.return_value = Snapshot(
        rows=[live],
        counts={"total": 1, "running": 1, "finished": 0, "failed": 0},
        usage={"sid-live": {"active": "1", "cpu": "250", "rss": str(512 * 1024**2), "peak_rss": str(600 * 1024**2), "cpu_seconds": "90"}},
    )
    service.session_usage.return_value = service.snapshot.return_value.usage
    service.session_usage_history.return_value = [{"t": 0, "cpu": 10, "cpu_max": 10, "rss": 100, "rss_max": 100}, {"t": 60, "cpu": 250, "cpu_max": 300, "rss": 200, "rss_max": 250}]

    async def scenario(app, pilot):
        table = app.query_one("#sessions-table", DataTable)
        assert [str(c) for c in table.get_row_at(0)[2:4]] == ["250%", "512 MB"]
        await pilot.press("u")
        await settle(app, pilot)
        assert isinstance(app.screen, UsageScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, UsageScreen)

    run(service, scenario)


def test_sessions_table_shows_snapshot_and_counts(service):
    async def scenario(app, pilot):
        table = app.query_one("#sessions-table", DataTable)
        assert table.row_count == 2
        assert app.focused is table
        assert app.query_one("#scheduled-table", DataTable).row_count == 1
        assert "1" in str(app.query_one("#filter-running", Button).label)

    run(service, scenario)


def test_filter_key_cycles_categories(service):
    async def scenario(app, pilot):
        await pilot.press("f")
        await settle(app, pilot)
        service.snapshot.assert_called_with("running")
        await pilot.click("#filter-running")  # clicking the active filter clears it
        await settle(app, pilot)
        service.snapshot.assert_called_with(None)

    run(service, scenario)


def test_kill_asks_for_confirmation(service):
    async def scenario(app, pilot):
        await pilot.press("k")
        assert isinstance(app.screen, ConfirmScreen)
        await pilot.click("#confirm")
        await pilot.pause()
        service.kill_session.assert_called_once_with("live-job")

    run(service, scenario)


def test_cancelled_confirmation_does_nothing(service):
    async def scenario(app, pilot):
        await pilot.press("d")
        await pilot.press("escape")
        service.clear_session.assert_not_called()

    run(service, scenario)


def test_rerun_only_for_finished_sessions(service):
    async def scenario(app, pilot):
        await pilot.press("r")  # live-job is still running
        service.rerun_session.assert_not_called()
        await pilot.press("down", "r")
        service.rerun_session.assert_called_once_with("done-job", "bash job.sh")

    run(service, scenario)


def test_enter_opens_live_log(service):
    (service.LOG_DIR / "live-job.log").write_text("line one\nline two\n")
    service.is_tmux_session_active.return_value = True

    async def scenario(app, pilot):
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, LogScreen)
        assert "line two" in "\n".join(app.screen.query_one("#log-view").lines)
        assert "LIVE" in str(app.screen.query_one("#live-badge", Label).render())
        await pilot.press("escape")
        assert not isinstance(app.screen, LogScreen)

    run(service, scenario)


def test_cancel_scheduled_job(service):
    service.get_recurring_info.return_value = None

    async def scenario(app, pilot):
        await pilot.press("c", "y")
        service.cancel_scheduled_job.assert_called_once_with("7")

    run(service, scenario)


def test_kill_all_and_clear_actions_call_service(service):
    async def scenario(app, pilot):
        for key, method in (("K", service.kill_all_and_notify), ("H", service.clear_session_history), ("L", service.clear_log_files)):
            await pilot.press(key, "y")
            method.assert_called_once()

    run(service, scenario)


@pytest.mark.parametrize("in_tmux, verb", [(False, "attach-session"), (True, "switch-client")])
def test_attach_command(monkeypatch, in_tmux, verb):
    if in_tmux:
        monkeypatch.setenv("TMUX", "/tmp/tmux-1/default,1,0")
    else:
        monkeypatch.delenv("TMUX", raising=False)
    assert attach_command("job") == ["tmux", verb, "-t", "job"]


# --- Scripts tab ----------------------------------------------------------------------------


def test_tab_keys_switch_tabs_and_focus(service):
    async def scenario(app, pilot):
        for key, tab, widget in (("2", "scripts", "#script-list"), ("3", "favorites", "#favorites-table"), ("1", "sessions", "#sessions-table")):
            await pilot.press(key)
            await pilot.pause()
            assert app.query_one(TabbedContent).active == tab
            assert app.focused is app.query_one(widget)

    run(service, scenario)


def test_launch_selected_script(service):
    async def scenario(app, pilot):
        await pilot.press("2")
        await pilot.pause()
        assert app.query_one("#editor", TextArea).text == "#!/bin/bash\necho build\n"
        assert app.query_one("#session-name", Input).value == "build"
        await pilot.press("ctrl+r")
        expected = scripts.launch_command(service.SCRIPTS_DIR / "build.sh", ".", "python3")
        service.start_tmux_session.assert_called_once_with("build", expected)

    run(service, scenario)


def test_unsaved_changes_block_launch_until_saved(service):
    async def scenario(app, pilot):
        await pilot.press("2")
        await pilot.pause()
        app.query_one("#editor", TextArea).insert("echo more\n")
        await pilot.pause()
        await pilot.press("ctrl+r")
        service.start_tmux_session.assert_not_called()
        await pilot.press("ctrl+s", "ctrl+r")
        assert "echo more" in (service.SCRIPTS_DIR / "build.sh").read_text()
        service.start_tmux_session.assert_called_once()

    run(service, scenario)


def test_chain_launches_all_scripts(service):
    async def scenario(app, pilot):
        await pilot.press("2")
        await pilot.pause()
        await pilot.press("ctrl+b", "down", "ctrl+b", "ctrl+r")
        command = service.start_tmux_session.call_args.args[1]
        assert "1 of 2: build.sh" in command and "2 of 2: report.py" in command
        assert app.query_one("#scripts-pane").chain == []

    run(service, scenario)


def test_schedule_dialog_passes_time_and_repeat(service):
    when = (datetime.now() + timedelta(days=1)).replace(second=0, microsecond=0)

    async def scenario(app, pilot):
        await pilot.press("2")
        await pilot.pause()
        await pilot.press("ctrl+t")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ScheduleScreen)
        screen.query_one("#date", Input).value = when.strftime("%Y-%m-%d")
        screen.query_one("#time", Input).value = when.strftime("%H:%M")
        screen.query_one("#unit").value = "hours"
        screen.query_one("#count", Input).value = "2"
        await pilot.click("#submit")
        await pilot.pause()
        args = service.schedule_launch.call_args.args
        assert args[0] == "build" and args[4] == when and args[5] == 120
        assert not isinstance(app.screen, ScheduleScreen)

    run(service, scenario)


def test_schedule_errors_keep_dialog_open(service):
    service.schedule_launch.side_effect = ScheduleError("Scheduled time is in the past.")

    async def scenario(app, pilot):
        await pilot.press("2")
        await pilot.pause()
        await pilot.press("ctrl+t")
        await pilot.pause()
        await pilot.click("#submit")
        await pilot.pause()
        assert isinstance(app.screen, ScheduleScreen)
        assert "in the past" in str(app.screen.query_one("#form-error", Label).render())

    run(service, scenario)


def test_new_script_from_template(service):
    async def scenario(app, pilot):
        await pilot.press("2")
        await pilot.pause()
        await pilot.press("ctrl+n")
        await pilot.pause()
        assert isinstance(app.screen, FormScreen)
        app.screen.query_one("#field-name", Input).value = "nightly"
        app.screen.query_one("#field-type", Input).value = "python"
        await pilot.click("#submit")
        await pilot.pause()
        assert (service.SCRIPTS_DIR / "nightly.py").read_text() == scripts.TEMPLATES["python"]
        assert app.query_one("#scripts-pane").current == "nightly.py"

    run(service, scenario)


def test_invalid_script_name_keeps_form_open(service):
    async def scenario(app, pilot):
        await pilot.press("2")
        await pilot.pause()
        await pilot.press("ctrl+n")
        await pilot.pause()
        app.screen.query_one("#field-name", Input).value = "bad name!"
        await pilot.click("#submit")
        await pilot.pause()
        assert isinstance(app.screen, FormScreen)

    run(service, scenario)


# --- Favorites tab, app wiring ------------------------------------------------------------


def test_enter_runs_favorite(service):
    async def scenario(app, pilot):
        await pilot.press("3")
        await pilot.pause()
        await pilot.press("enter")
        service.run_favorite.assert_called_once_with("f1", "deploy", "make deploy")

    run(service, scenario)


def test_favorites_search_filters(service):
    async def scenario(app, pilot):
        await pilot.press("3", "slash", "d", "e", "p")
        await pilot.pause()
        service.list_favorites.assert_called_with("dep")

    run(service, scenario)


def test_service_messages_become_toasts(service):
    async def scenario(app, pilot):
        service.notifier("Session 'x' finished!", "positive")
        await pilot.pause()
        assert any(n.message == "Session 'x' finished!" for n in app._notifications)

    run(service, scenario)


def test_redis_events_notify_and_refresh(service):
    async def scenario(app, pilot):
        calls = service.snapshot.call_count
        app.pending_events.append({"session_name": "x", "status": "failed"})
        app.tick()
        await settle(app, pilot)
        assert any(n.message == "Session 'x' failed!" and n.severity == "error" for n in app._notifications)
        assert service.snapshot.call_count > calls

    run(service, scenario)


def test_meter_colors_by_load():
    assert meter("CPU", 10).spans[1].style == "green"
    assert meter("CPU", 70).spans[1].style == "yellow"
    assert meter("CPU", 95).spans[1].style == "red"
