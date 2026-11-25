"""TmuxManager: the web dashboard's DestoService.

Session, scheduling and clean-up logic lives in desto.core.service.DestoService, shared with
the terminal UI. The web-only parts are separate objects that hold this service, the way the
terminal UI's panes do:

- dashboard (sessions_dashboard.SessionsDashboard): stats cards and sessions/scheduled tables
- dialogs (session_dialogs.SessionDialogs): confirmation dialogs and the live log viewer
"""

from desto.app.session_dialogs import SessionDialogs
from desto.app.sessions_dashboard import SessionsDashboard
from desto.core.service import DestoService


class TmuxManager(DestoService):
    def __init__(self, ui_instance, instance_logger, log_dir=None, scripts_dir=None):
        if not ui_instance or not instance_logger:
            raise ValueError("ui_instance and instance_logger are required")
        self.ui = ui_instance
        sessions_container = ui_instance.column().classes("w-full mt-5 gap-4")
        self.pause_updates = None  # Function to pause updates, set by the dashboard page
        self.resume_updates = None  # Function to resume updates, set by the dashboard page
        self.sessions = {}  # For backward compatibility with tests
        super().__init__(
            log_dir=log_dir, scripts_dir=scripts_dir, notifier=self._notify_in_browser, instance_logger=instance_logger
        )
        self.dialogs = SessionDialogs(self)
        self.dashboard = SessionsDashboard(self, self.dialogs, sessions_container)

    def _notify_in_browser(self, message: str, level: str) -> None:
        self.ui.notification(message, type=level)

    def on_sessions_changed(self) -> None:
        self.dashboard.update_sessions_status(force=True)

    def pause(self) -> None:
        """Pause the dashboard's periodic updates (while a dialog is open)."""
        if self.pause_updates:
            self.pause_updates()

    def resume(self) -> None:
        """Resume the dashboard's periodic updates."""
        if self.resume_updates:
            self.resume_updates()
