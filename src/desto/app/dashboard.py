from loguru import logger
from nicegui import ui

from desto.app.config import config as ui_settings
from desto.app.sessions import TmuxManager
from desto.app.ui import UserInterfaceManager

# Global variable to store the timer instance
global_timer = None


def run_updates(um: UserInterfaceManager, tm: TmuxManager) -> None:
    """Function to update the UI and session status."""
    um.update_ui_system_info()
    tm.update_sessions_status()
    tm.check_and_run_scheduled_jobs()
    um.refresh_log_display()


def pause_global_timer():
    """Pauses the global timer."""
    global global_timer
    if global_timer:
        global_timer.deactivate()


def resume_global_timer(um: UserInterfaceManager, tm: TmuxManager):
    """Resumes the global timer."""
    global global_timer
    if global_timer:
        global_timer.activate()
    else:
        global_timer = ui.timer(0.5, lambda: run_updates(um, tm))


def handle_instant_update(um: UserInterfaceManager, update_data):
    """Handle instant updates from Redis - happens immediately, not on timer."""
    session_name = update_data.get("session_name")
    status = update_data.get("status")

    # Instant notifications
    if status == "finished":
        ui.notification(f"Session '{session_name}' finished!", type="positive")
    elif status == "failed":
        ui.notification(f"Session '{session_name}' failed!", type="negative")

    # Force immediate UI refresh (don't wait for 1-second timer)
    um.tmux_manager.update_sessions_status()


def main():
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
        </style>
    """
    )

    tm = TmuxManager(ui, logger)
    um = UserInterfaceManager(ui, ui_settings, tm, desto_manager=tm.desto_manager)

    logger.add(
        lambda msg: um.log_section.update_log_messages(msg.strip()),
        format="{message}",
        level="INFO",
    )

    # Set up real-time updates using TmuxManager's Redis client
    if tm.pubsub:
        tm.pubsub.subscribe_to_session_updates(lambda update: handle_instant_update(um, update))
        logger.info("Redis pub/sub enabled for real-time updates")
    else:
        logger.warning("Redis pub/sub not available")

    um.build_ui()

    # Create the global timer
    global global_timer
    global_timer = ui.timer(0.5, lambda: run_updates(um, tm))

    # Pass pause and resume functions to TmuxManager
    tm.pause_updates = pause_global_timer
    tm.resume_updates = lambda: resume_global_timer(um, tm)

    ui.run(
        title="desto dashboard",
        port=8809,
        reload=False,
        show=False,
        binding_refresh_interval=0.1,
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
