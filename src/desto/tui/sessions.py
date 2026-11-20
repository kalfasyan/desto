"""The Sessions tab: counts, the sessions table and the scheduled jobs table."""

import os
import subprocess

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Label

from desto.core.formatting import session_row_times
from desto.core.service import DestoService, Snapshot
from desto.tui.modals import ConfirmScreen, LogScreen

# (filter, label, style) of the count buttons; None shows every session
FILTERS = [(None, "Total", "bold"), ("running", "Running", "bold yellow"), ("finished", "Finished", "bold green"), ("failed", "Failed", "bold red")]


def attach_command(session_name: str) -> list[str]:
    """The tmux command that shows a session: attach from a plain terminal, switch client from inside tmux."""
    if os.environ.get("TMUX"):
        return ["tmux", "switch-client", "-t", session_name]
    return ["tmux", "attach-session", "-t", session_name]


class SessionsPane(Vertical):
    BINDINGS = [
        Binding("l", "view_log", "Log"),
        Binding("a", "attach", "Attach"),
        Binding("k", "kill", "Kill"),
        Binding("r", "rerun", "Re-run"),
        Binding("d", "clear_session", "Clear"),
        Binding("c", "cancel_job", "Cancel job"),
        Binding("f", "cycle_filter", "Filter"),
        Binding("K", "kill_all", "Kill all"),
        Binding("H", "clear_history", "Clear history", show=False),
        Binding("L", "clear_logs", "Clear logs", show=False),
    ]

    def __init__(self, service: DestoService, **kwargs) -> None:
        super().__init__(**kwargs)
        self.service = service
        self.status_filter = None
        self.snapshot = Snapshot()

    def compose(self) -> ComposeResult:
        with Horizontal(id="counts"):
            for category, label, _ in FILTERS:
                yield Button(label, id=f"filter-{category or 'all'}", classes="count")
        yield DataTable(id="sessions-table", cursor_type="row", zebra_stripes=True)
        yield Label("Scheduled jobs", classes="section-title")
        yield DataTable(id="scheduled-table", cursor_type="row", zebra_stripes=True)

    def on_mount(self) -> None:
        self.query_one("#sessions-table", DataTable).add_columns("Session", "Status", "Job time", "Session time", "Started", "Finished", "tmux")
        self.query_one("#scheduled-table", DataTable).add_columns("Job", "Scheduled for", "User", "Status")
        self.refresh_sessions()

    # --- Data -----------------------------------------------------------------------

    @work(thread=True, exclusive=True, group="sessions")
    def refresh_sessions(self) -> None:
        """Gather a snapshot off the UI thread (tmux and Redis calls block), then show it."""
        snapshot = self.service.snapshot(self.status_filter)
        self.app.call_from_thread(self.show, snapshot)

    def show(self, snapshot: Snapshot) -> None:
        self.snapshot = snapshot
        for category, label, style in FILTERS:
            button = self.query_one(f"#filter-{category or 'all'}", Button)
            button.label = Text.assemble((str(snapshot.counts.get(category or "total", 0)), style), f"  {label}")
            button.set_class(category == self.status_filter, "active")

        table = self.query_one("#sessions-table", DataTable)
        rows = []
        for row in snapshot.rows:
            times = session_row_times(row.session)
            rows.append(
                (
                    row.name,
                    (
                        Text(row.name, style="bold"),
                        Text(row.label, style=row.color),
                        times["job_duration"],
                        times["session_duration"],
                        times["started"],
                        times["finished"],
                        Text("● live", style="green") if row.tmux_active else Text("○", style="dim"),
                    ),
                )
            )
        self._fill(table, rows)

        scheduled = self.query_one("#scheduled-table", DataTable)
        self._fill(scheduled, [(job.job_id, (job.job_id, job.scheduled_time, job.user, job.status)) for job in snapshot.scheduled])
        scheduled.display = bool(snapshot.scheduled)
        self.query_one(".section-title").display = bool(snapshot.scheduled)

    @staticmethod
    def _fill(table: DataTable, rows) -> None:
        """Replace the table's rows, keeping the cursor on the same key where possible."""
        selected = _selected_key(table)
        table.clear()
        for key, cells in rows:
            table.add_row(*cells, key=key)
        keys = [key for key, _ in rows]
        if selected in keys:
            table.move_cursor(row=keys.index(selected), animate=False)

    def selected_row(self):
        """The SessionRow under the cursor, or None."""
        key = _selected_key(self.query_one("#sessions-table", DataTable))
        return next((row for row in self.snapshot.rows if row.name == key), None)

    # --- Actions --------------------------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        category = event.button.id.removeprefix("filter-")
        category = None if category == "all" or category == self.status_filter else category
        self.set_filter(category)

    def set_filter(self, category) -> None:
        self.status_filter = category
        self.refresh_sessions()

    def action_cycle_filter(self) -> None:
        order = [category for category, _, _ in FILTERS]
        self.set_filter(order[(order.index(self.status_filter) + 1) % len(order)])

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Enter on a session opens its log."""
        if event.data_table.id == "sessions-table":
            self.action_view_log()

    def action_view_log(self) -> None:
        row = self.selected_row()
        if row:
            self.app.push_screen(LogScreen(row.name, self.service.get_log_file(row.name), self.service.is_tmux_session_active))

    def action_attach(self) -> None:
        row = self.selected_row()
        if not row:
            return
        if not row.tmux_active:
            self.notify(f"'{row.name}' has no running tmux session to attach to.", severity="warning")
            return
        with self.app.suspend():
            subprocess.run(attach_command(row.name))
        self.refresh_sessions()

    def action_kill(self) -> None:
        row = self.selected_row()
        if not row:
            return
        if not row.tmux_active:
            self.notify("Cannot kill: no active tmux session for this entry.", severity="warning")
            return
        self._confirm(ConfirmScreen("Kill session", f"Kill the session '{row.name}'?", "Kill"), lambda: self.service.kill_session(row.name))

    def action_rerun(self) -> None:
        row = self.selected_row()
        if not row:
            return
        if row.tmux_active:
            self.notify(f"'{row.name}' is still running.", severity="warning")
            return
        self.service.rerun_session(row.name, row.command)
        self.refresh_sessions()

    def action_clear_session(self) -> None:
        row = self.selected_row()
        if row:
            message = f"Clear the session '{row.name}'? This deletes its log file and removes it from the table."
            self._confirm(ConfirmScreen("Clear session", message, "Clear"), lambda: self.service.clear_session(row.name))

    def action_cancel_job(self) -> None:
        job_id = _selected_key(self.query_one("#scheduled-table", DataTable))
        if job_id is None:
            self.notify("No scheduled job selected.", severity="warning")
            return
        message = f"Cancel scheduled job {job_id}?"
        recurrence = self.service.get_recurring_info(job_id)
        if recurrence:
            message += f"\nIt is part of a recurring schedule ({recurrence[1]}); cancelling it stops all future runs."
        self._confirm(ConfirmScreen("Cancel scheduled job", message, "Cancel job"), lambda: self.service.cancel_scheduled_job(job_id))

    def action_kill_all(self) -> None:
        running = [row.name for row in self.snapshot.rows if row.tmux_active]
        jobs = len(self.snapshot.scheduled)
        if not running and not jobs:
            self.notify("No active sessions or scheduled jobs to clear.")
            return
        parts = []
        if running:
            parts.append(f"{len(running)} running session(s): {', '.join(running[:5])}{' …' if len(running) > 5 else ''}")
        if jobs:
            parts.append(f"{jobs} scheduled job(s)")
        message = "This kills:\n• " + "\n• ".join(parts) + ("\n\nThis interrupts running processes!" if running else "")
        self._confirm(ConfirmScreen("Kill everything", message, "Kill all"), self.service.kill_all_and_notify)

    def action_clear_history(self) -> None:
        message = "Remove every session record from Redis? Running sessions keep running, and log files are kept."
        self._confirm(ConfirmScreen("Clear history", message, "Clear history"), self.service.clear_session_history)

    def action_clear_logs(self) -> None:
        message = f"Delete every log file in {self.service.LOG_DIR}? This cannot be undone."
        self._confirm(ConfirmScreen("Clear logs", message, "Delete logs"), self.service.clear_log_files)

    def _confirm(self, screen: ConfirmScreen, action) -> None:
        def done(confirmed: bool | None) -> None:
            if confirmed:
                action()
                self.refresh_sessions()

        self.app.push_screen(screen, done)


def _selected_key(table: DataTable):
    """Key of the row under the table's cursor, or None for an empty table."""
    if table.row_count == 0:
        return None
    try:
        return table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
    except Exception:
        return None
