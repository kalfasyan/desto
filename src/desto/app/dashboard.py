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
    # Use the single TmuxManager class
    tm = TmuxManager(ui, logger)

    # Pass the desto_manager from TmuxManager to UserInterfaceManager
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

    ui.run(title="desto dashboard", port=8809, reload=False)


if __name__ in {"__main__", "__mp_main__"}:
    main()
