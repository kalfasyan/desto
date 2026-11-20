"""TmuxManager: the web dashboard's DestoService.

Session, scheduling and clean-up logic lives in desto.core.service.DestoService, shared with
the terminal UI. This class adds what only the web dashboard needs, mixed in by concern:

- sessions_dashboard.SessionsDashboardMixin: stats cards and sessions/scheduled tables
- session_dialogs.SessionDialogsMixin: confirmation dialogs and the live log viewer
"""

from desto.app.session_dialogs import SessionDialogsMixin
from desto.app.sessions_dashboard import SessionsDashboardMixin
from desto.core.service import DestoService


class TmuxManager(SessionsDashboardMixin, SessionDialogsMixin, DestoService):
    def __init__(self, ui_instance, instance_logger, log_dir=None, scripts_dir=None):
        if not ui_instance or not instance_logger:
            raise ValueError("ui_instance and instance_logger are required")
        self.ui = ui_instance
        self.sessions_container = ui_instance.column().classes("w-full mt-5 gap-4")
        self.pause_updates = None  # Function to pause updates
        self.resume_updates = None  # Function to resume updates
        self.status_filter = None  # None, "running", "finished" or "failed"
        self._last_render_signature = None  # Skip re-rendering when nothing changed
        self._live_duration_labels = []  # (label, start datetime) for running sessions
        self._atd_cache = (0.0, True)  # (checked_at, is_running)
        self.sessions = {}  # For backward compatibility with tests
        super().__init__(log_dir=log_dir, scripts_dir=scripts_dir, notifier=self._notify_in_browser, instance_logger=instance_logger)

    def _notify_in_browser(self, message: str, level: str) -> None:
        self.ui.notification(message, type=level)

    def on_sessions_changed(self) -> None:
        self.update_sessions_status(force=True)

    def clear_sessions_container(self):
        """Clears the sessions container."""
        self.sessions_container.clear()

    def add_to_sessions_container(self, content):
        """Adds content to the sessions container."""
        with self.sessions_container:
            content()
