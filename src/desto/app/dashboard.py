from collections import deque

from loguru import logger
from nicegui import ui

from desto.app.auth import get_auth_config, is_loopback, setup_auth
from desto.app.config import config as ui_settings
from desto.app.sessions import TmuxManager
from desto.app.ui import UserInterfaceManager

# Dashboard timers, each running only as often as its data changes:
#   - fast (1s): system stats, live durations, pending Redis events, system log panel
#   - sessions (2s): sessions table, rebuilt only when the data actually changed
#   - scheduler (5s): fallback runner for overdue scheduled jobs
FAST_INTERVAL = 1.0
SESSIONS_INTERVAL = 2.0
SCHEDULER_INTERVAL = 5.0


class DashboardState:
    """Timers and queued Redis events for one browser tab's dashboard."""

    def __init__(self) -> None:
        self.timers = []
        # Redis pub/sub events arrive on a background thread; they are queued here and handled
        # on the UI timer, where it is safe to touch UI elements.
        self.pending_updates = deque()


def run_fast_updates(um: UserInterfaceManager, tm: TmuxManager, state: DashboardState) -> None:
    um.update_ui_system_info()
    tm.tick_live_durations()
    process_pending_updates(um, state)
    um.refresh_log_display()


def run_updates(um: UserInterfaceManager, tm: TmuxManager, state: DashboardState) -> None:
    """Run every periodic update once (kept for callers and tests)."""
    run_fast_updates(um, tm, state)
    tm.update_sessions_status(force=False)
    tm.check_and_run_scheduled_jobs()


def _create_timers(um: UserInterfaceManager, tm: TmuxManager, state: DashboardState) -> None:
    state.timers.extend(
        [
            ui.timer(FAST_INTERVAL, lambda: run_fast_updates(um, tm, state)),
            ui.timer(SESSIONS_INTERVAL, lambda: tm.update_sessions_status(force=False)),
            ui.timer(SCHEDULER_INTERVAL, tm.check_and_run_scheduled_jobs),
        ]
    )


def pause_global_timer(state: DashboardState):
    """Pauses the periodic updates."""
    for timer in state.timers:
        timer.deactivate()


def resume_global_timer(um: UserInterfaceManager, tm: TmuxManager, state: DashboardState):
    """Resumes the periodic updates."""
    if state.timers:
        for timer in state.timers:
            timer.activate()
    else:
        _create_timers(um, tm, state)


def handle_instant_update(state: DashboardState, update_data):
    """Called from the Redis pub/sub thread: queue the event for the UI timer."""
    state.pending_updates.append(update_data)


def process_pending_updates(um: UserInterfaceManager, state: DashboardState) -> None:
    """Show notifications for queued Redis events and refresh the sessions table once."""
    if not state.pending_updates:
        return
    while state.pending_updates:
        update_data = state.pending_updates.popleft()
        session_name = update_data.get("session_name")
        status = update_data.get("status")
        if status == "finished":
            ui.notification(f"Session '{session_name}' finished!", type="positive")
        elif status == "failed":
            ui.notification(f"Session '{session_name}' failed!", type="negative")
    um.tmux_manager.update_sessions_status(force=False)


def build_dashboard(show_logout: bool) -> None:
    """Build the dashboard page for one browser tab."""
    # Configure modern colors for Quasar
    ui.colors(
        primary="#3b82f6",  # blue-500
        secondary="#64748b",  # slate-500
        accent="#8b5cf6",  # violet-500
        positive="#10b981",  # emerald-500
        negative="#ef4444",  # red-500
        info="#06b6d4",  # cyan-500
        warning="#f59e0b",  # amber-500
        dark="#1e293b",  # slate-800
        dark_page="#0f172a",  # slate-900
    )

    # Set body background with Tailwind dark mode support
    ui.query("body").classes("bg-slate-50 dark:bg-slate-950")

    # Add custom styles for a modern look
    ui.add_head_html(
        """
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
            body {
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                -webkit-font-smoothing: antialiased;
                -moz-osx-font-smoothing: grayscale;
            }
            .nicegui-content {
                padding: 0 !important;
            }
            .q-tab-panel {
                padding: 0 !important;
            }
            .modern-card {
                border: 1px solid rgba(0, 0, 0, 0.05);
                transition: all 0.2s ease-in-out;
            }
            .dark .modern-card {
                border: 1px solid rgba(255, 255, 255, 0.05);
            }
            .modern-card:hover {
                box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
            }
            /* Dark mode card backgrounds */
            body.dark .q-card {
                background-color: #0f172a !important;
            }
            body.dark .q-header {
                background-color: #0f172a !important;
            }
            body.dark .q-drawer {
                background-color: #0f172a !important;
            }
        </style>
    """
    )

    state = DashboardState()
    tm = TmuxManager(ui, logger)
    um = UserInterfaceManager(ui, ui_settings, tm, desto_manager=tm.desto_manager)

    log_sink_id = logger.add(
        lambda msg: um.log_section.update_log_messages(msg.strip()),
        format="{message}",
        level="INFO",
    )
    # Stop sending log lines to this tab's log panel once the tab is gone.
    ui.context.client.on_delete(lambda: logger.remove(log_sink_id))

    # Set up real-time updates using TmuxManager's Redis client
    if tm.pubsub:
        tm.pubsub.subscribe_to_session_updates(lambda update: handle_instant_update(state, update))
        logger.info("Redis pub/sub enabled for real-time updates")
    else:
        logger.warning("Redis pub/sub not available")

    um.build_ui(show_logout=show_logout)

    _create_timers(um, tm, state)

    # Pass pause and resume functions to TmuxManager
    tm.pause_updates = lambda: pause_global_timer(state)
    tm.resume_updates = lambda: resume_global_timer(um, tm, state)


def main():
    cfg = get_auth_config()

    setup_auth(cfg.password)
    if not is_loopback(cfg.host) and not cfg.password:
        logger.warning(
            f"desto dashboard is reachable on {cfg.host}:{cfg.port} without a password.\n"
            "Anyone who can reach this address can run commands on this machine.\n"
            "Set DESTO_PASSWORD to require a login, or set DESTO_HOST=127.0.0.1 to keep the dashboard local."
        )
    logger.info(f"Serving the desto dashboard at http://{cfg.host}:{cfg.port}")

    # The dashboard is built in a root function rather than at module level: NiceGUI 3 does not
    # allow global-scope UI next to ui.page routes, and the login page is one of those.
    ui.run(
        lambda: build_dashboard(show_logout=bool(cfg.password)),
        title="desto dashboard",
        host=cfg.host,
        port=cfg.port,
        reload=False,
        show=False,
        binding_refresh_interval=0.1,
        storage_secret=cfg.storage_secret,
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
