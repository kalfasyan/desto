"""desto-tui: the desto dashboard in the terminal, built with Textual on top of DestoService."""

import sys
import threading
from collections import deque
from pathlib import Path

from loguru import logger
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, Log, TabbedContent, TabPane

from desto.core.formatting import session_event_message
from desto.core.service import DestoService
from desto.core.system_stats import SystemMonitor
from desto.tui.favorites import FavoritesPane
from desto.tui.messages import FavoritesChanged, SessionsChanged
from desto.tui.scripts import ScriptsPane
from desto.tui.sessions import SessionsPane
from desto.tui.stats import StatsBar

# The same refresh rhythm as the web dashboard
FAST_INTERVAL = 1.0  # system stats, desto log panel, Redis session events
SESSIONS_INTERVAL = 2.0  # sessions and scheduled jobs tables
SCHEDULER_INTERVAL = 5.0  # fallback runner for overdue scheduled jobs

# The widget that gets focus when a tab is shown
MAIN_WIDGETS = {"sessions": "#sessions-table", "scripts": "#script-list", "favorites": "#favorites-table"}

SEVERITY = {"positive": "information", "info": "information", "warning": "warning", "negative": "error"}


class DestoApp(App):
    TITLE = "desto"
    CSS_PATH = "desto.tcss"
    BINDINGS = [
        Binding("1", "show_tab('sessions')", "Sessions"),
        Binding("2", "show_tab('scripts')", "Scripts"),
        Binding("3", "show_tab('favorites')", "Favorites"),
        Binding("g", "toggle_log", "desto log"),
        Binding("question_mark", "show_help_panel", "All keys"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, service: DestoService, monitor: SystemMonitor | None = None, log_lines: deque | None = None) -> None:
        super().__init__()
        self.service = service
        self.monitor = monitor or SystemMonitor()
        # Filled from other threads (loguru, Redis pub/sub) and drained on the UI timer
        self.pending_log_lines = log_lines if log_lines is not None else deque(maxlen=1000)
        self.pending_events: deque[dict] = deque()
        self._ui_thread = threading.get_ident()
        service.notifier = self.show_message

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield StatsBar(id="stats")
        with TabbedContent(initial="sessions"):
            with TabPane("Sessions", id="sessions"):
                yield SessionsPane(self.service, id="sessions-pane")
            with TabPane("Scripts", id="scripts"):
                yield ScriptsPane(self.service, id="scripts-pane")
            with TabPane("Favorites", id="favorites"):
                yield FavoritesPane(self.service, id="favorites-pane")
        yield Log(id="desto-log", max_lines=500)
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = f"scripts {_short(self.service.SCRIPTS_DIR)} · logs {_short(self.service.LOG_DIR)}"
        self.focus_tab("sessions")
        self.tick()
        self.set_interval(FAST_INTERVAL, self.tick)
        self.set_interval(SESSIONS_INTERVAL, self.refresh_sessions)
        self.set_interval(SCHEDULER_INTERVAL, self.run_overdue_jobs)
        if self.service.pubsub:
            self.service.pubsub.subscribe_to_session_updates(self.pending_events.append)
        self.warn_if_atd_stopped()

    # --- Periodic work --------------------------------------------------------------

    def tick(self) -> None:
        self.query_one(StatsBar).show(self.monitor.read())
        log_view = self.query_one("#desto-log", Log)
        while self.pending_log_lines:
            log_view.write_line(self.pending_log_lines.popleft())
        if self.pending_events:
            while self.pending_events:
                event = session_event_message(self.pending_events.popleft())
                if event:
                    self.show_message(*event)
            self.refresh_sessions()

    def refresh_sessions(self) -> None:
        self.query_one(SessionsPane).refresh_sessions()

    @work(thread=True, exclusive=True, group="scheduler")
    def run_overdue_jobs(self) -> None:
        self.service.check_and_run_scheduled_jobs()

    @work(thread=True)
    def warn_if_atd_stopped(self) -> None:
        from desto.redis.at_job_manager import AtJobManager

        if not AtJobManager.is_atd_running():
            self.call_from_thread(
                self.show_message,
                "The 'at' daemon is not running: scheduled jobs only run while desto is open. Enable 'atd' for background scheduling.",
                "warning",
            )

    # --- Messages -------------------------------------------------------------------

    def show_message(self, message: str, level: str = "info") -> None:
        """Service notifier: a toast, from whichever thread the message came."""
        if threading.get_ident() == self._ui_thread:
            self.notify(message, severity=SEVERITY.get(level, "information"), markup=False)
        else:
            self.call_from_thread(self.show_message, message, level)

    def on_sessions_changed(self, message: SessionsChanged) -> None:
        self.refresh_sessions()

    def on_favorites_changed(self, message: FavoritesChanged) -> None:
        self.query_one(FavoritesPane).reload()

    # --- Actions --------------------------------------------------------------------

    def action_show_tab(self, tab: str) -> None:
        # Drop focus first: a focused widget in the old tab would otherwise pull the old tab back
        self.set_focus(None)
        self.query_one(TabbedContent).active = tab
        if tab == "favorites":
            self.query_one(FavoritesPane).reload()
        self.call_after_refresh(self.focus_tab, tab)

    def focus_tab(self, tab: str) -> None:
        """Focus the main widget of a tab, so its key bindings work straight away."""
        self.set_focus(self.query_one(MAIN_WIDGETS[tab]))

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        if self.focused is None:
            self.call_after_refresh(self.focus_tab, event.pane.id)

    def action_toggle_log(self) -> None:
        log_view = self.query_one("#desto-log")
        log_view.display = not log_view.display


def _short(path) -> str:
    """Path with the home directory shown as ~."""
    home = str(Path.home())
    return "~" + str(path)[len(home) :] if str(path).startswith(home) else str(path)


def main() -> None:
    """Entry point of desto-tui."""
    pending_log_lines: deque[str] = deque(maxlen=1000)
    # Log lines would scribble over the terminal UI, so they go to the in-app log panel instead
    logger.remove()
    logger.add(lambda msg: pending_log_lines.append(msg.strip()), format="{time:HH:mm:ss} {level: <7} {message}", level="INFO")
    try:
        service = DestoService()
    except RuntimeError as e:
        print(f"desto-tui: {e}\nStart Redis (for example `docker compose up -d redis`) and try again.", file=sys.stderr)
        sys.exit(1)
    DestoApp(service, log_lines=pending_log_lines).run()


if __name__ == "__main__":
    main()
