"""Modal screens of the terminal UI: confirmations, small forms, scheduling and the live log viewer."""

from datetime import datetime
from typing import Callable, Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Log, Select, Sparkline, Static

from desto.core.formatting import format_bytes, format_seconds
from desto.core.log_tailer import LogTailer
from desto.core.scheduled_jobs import ScheduleError
from desto.redis.recurring import REPEAT_UNITS

REPEAT_OPTIONS = [("Does not repeat", "never"), ("minute(s)", "minutes"), ("hour(s)", "hours"), ("day(s)", "days"), ("week(s)", "weeks")]


class ConfirmScreen(ModalScreen[bool]):
    """Ask a yes/no question. Dismisses with True when confirmed."""

    BINDINGS = [Binding("escape", "dismiss(False)", "Cancel"), Binding("y", "dismiss(True)", "Yes", show=False)]

    def __init__(self, title: str, message: str, confirm_label: str = "Confirm") -> None:
        super().__init__()
        self.title_text, self.message, self.confirm_label = title, message, confirm_label

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label(self.title_text, classes="dialog-title")
            yield Static(self.message, classes="dialog-body")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel", id="cancel")
                yield Button(self.confirm_label, id="confirm", variant="error")

    def on_mount(self) -> None:
        self.query_one("#cancel", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm")


class FormScreen(ModalScreen[Optional[dict]]):
    """A few labelled text inputs. Dismisses with {key: value}, or None when cancelled.

    validate(values) may return an error message, which keeps the form open.
    """

    BINDINGS = [Binding("escape", "dismiss(None)", "Cancel")]

    def __init__(self, title: str, fields: list[tuple[str, str, str]], submit_label: str = "Save", validate: Optional[Callable[[dict], Optional[str]]] = None) -> None:
        super().__init__()
        self.title_text, self.fields, self.submit_label, self.validate = title, fields, submit_label, validate

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label(self.title_text, classes="dialog-title")
            for key, label, value in self.fields:
                yield Label(label, classes="field-label")
                yield Input(value=value, id=f"field-{key}")
            yield Label("", id="form-error", classes="error")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel", id="cancel")
                yield Button(self.submit_label, id="submit", variant="primary")

    def values(self) -> dict:
        return {key: self.query_one(f"#field-{key}", Input).value.strip() for key, _, _ in self.fields}

    def _submit(self) -> None:
        values = self.values()
        error = self.validate(values) if self.validate else None
        if error:
            self.query_one("#form-error", Label).update(error)
            return
        self.dismiss(values)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "submit":
            self._submit()
        else:
            self.dismiss(None)


class ScheduleScreen(ModalScreen[bool]):
    """Pick a date, time and optional repetition, then hand them to schedule(when, interval_minutes).

    schedule raises ScheduleError for invalid input, which is shown and keeps the dialog open.
    Dismisses with True once scheduled.
    """

    BINDINGS = [Binding("escape", "dismiss(False)", "Cancel")]

    def __init__(self, what: str, schedule: Callable[[datetime, Optional[int]], object]) -> None:
        super().__init__()
        self.what, self.schedule = what, schedule

    def compose(self) -> ComposeResult:
        now = datetime.now()
        with Vertical(classes="dialog"):
            yield Label(f"Schedule {self.what}", classes="dialog-title")
            with Horizontal(classes="form-row"):
                with Vertical():
                    yield Label("Date (YYYY-MM-DD)", classes="field-label")
                    yield Input(now.strftime("%Y-%m-%d"), id="date")
                with Vertical():
                    yield Label("Time (HH:MM)", classes="field-label")
                    yield Input(now.strftime("%H:%M"), id="time")
            with Horizontal(classes="form-row"):
                with Vertical():
                    yield Label("Repeat every", classes="field-label")
                    yield Input("1", id="count", type="integer", disabled=True)
                with Vertical():
                    yield Label("Unit", classes="field-label")
                    yield Select(REPEAT_OPTIONS, value="never", allow_blank=False, id="unit")
            yield Label("", id="form-error", classes="error")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Schedule", id="submit", variant="primary")

    def on_select_changed(self, event: Select.Changed) -> None:
        self.query_one("#count", Input).disabled = event.value == "never"

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "submit":
            self._submit()
        else:
            self.dismiss(False)

    def _submit(self) -> None:
        error = self.query_one("#form-error", Label)
        date, time = self.query_one("#date", Input).value.strip(), self.query_one("#time", Input).value.strip()
        try:
            when = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
        except ValueError:
            error.update("Enter the date as YYYY-MM-DD and the time as HH:MM.")
            return
        unit = self.query_one("#unit", Select).value
        interval = None
        if unit != "never":
            count = self.query_one("#count", Input).value
            interval = int(count or 0) * REPEAT_UNITS[unit]
        try:
            self.schedule(when, interval)
        except ScheduleError as e:
            error.update(str(e))
            return
        self.dismiss(True)


class LogScreen(ModalScreen[None]):
    """Show the last lines of a session's log and follow it while the session runs."""

    BINDINGS = [
        Binding("escape,q", "dismiss(None)", "Close"),
        Binding("f", "toggle_follow", "Follow on/off"),
        Binding("end", "scroll_end", "Bottom", show=False),
    ]

    POLL_SECONDS = 1.0

    def __init__(self, session_name: str, log_file, session_alive: Callable[[str], bool]) -> None:
        super().__init__()
        self.session_name, self.session_alive = session_name, session_alive
        self.tailer = LogTailer(log_file)
        self.log_file = log_file
        self.follow = True

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog log-dialog"):
            with Horizontal(classes="log-header"):
                yield Label(f"Log · {self.session_name}", classes="dialog-title")
                yield Label("", id="live-badge")
            yield Log(max_lines=5000, id="log-view")
            yield Static("[b]f[/] follow on/off   [b]esc[/] close", classes="hint")

    def on_mount(self) -> None:
        log_view = self.query_one(Log)
        lines = self.tailer.initial_lines(200)
        if lines:
            log_view.write_lines(lines)
        elif not self.log_file.exists():
            log_view.write_line(f"Log file for session '{self.session_name}' not found.")
        self._set_live(self.session_alive(self.session_name))
        self.timer = self.set_interval(self.POLL_SECONDS, self.poll)

    def poll(self) -> None:
        if not self.follow:
            return
        self.query_one(Log).write_lines(self.tailer.poll())
        if not self.session_alive(self.session_name):
            self.query_one(Log).write_lines(self.tailer.poll())  # One final read after the session ended
            self._set_live(False)
            self.timer.stop()

    def _set_live(self, active: bool) -> None:
        badge = self.query_one("#live-badge", Label)
        badge.update(" LIVE " if active else " ENDED ")
        badge.set_class(active, "live")

    def action_toggle_follow(self) -> None:
        self.follow = not self.follow
        self.notify("Following the log" if self.follow else "Paused following")

    def action_scroll_end(self) -> None:
        self.query_one(Log).scroll_end(animate=False)


class UsageScreen(ModalScreen[None]):
    """A session's CPU and memory over its run, with its totals."""

    BINDINGS = [Binding("escape", "dismiss(None)", "Close"), Binding("u", "dismiss(None)", "Close", show=False)]

    def __init__(self, session_name: str, summary: dict, points: list[dict]) -> None:
        super().__init__()
        self.session_name, self.summary, self.points = session_name, summary or {}, points

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog usage-dialog"):
            yield Label(f"Resource usage: {self.session_name}", classes="dialog-title")
            if not self.points:
                yield Static("No usage recorded for this session yet. It is recorded while the dashboard, the TUI or `desto-cli monitor` runs.", classes="dialog-body")
            else:
                first, last = self.points[0]["t"], self.points[-1]["t"]
                span = format_seconds(int(last - first))
                yield Label(f"CPU % over the last {span} (peak {max(p.get('cpu_max', 0) for p in self.points):.0f}%)", classes="field-label")
                yield Sparkline([p.get("cpu", 0) for p in self.points], id="usage-cpu")
                yield Label(f"Memory over the last {span} (peak {format_bytes(max(p.get('rss_max', 0) for p in self.points))})", classes="field-label")
                yield Sparkline([p.get("rss", 0) for p in self.points], id="usage-mem")
            s = self.summary
            if s:
                totals = (
                    f"Peak memory {format_bytes(s.get('peak_rss', 0))} · CPU time {format_seconds(int(float(s.get('cpu_seconds', 0))))} · "
                    f"up to {s.get('max_procs', 0)} processes, {s.get('max_threads', 0)} threads · "
                    f"read {format_bytes(s.get('read_bytes', 0))}, written {format_bytes(s.get('write_bytes', 0))}"
                )
                yield Static(totals, classes="dialog-body")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Close", id="close", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)
