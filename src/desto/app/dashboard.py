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
        global_timer = ui.timer(1.0, lambda: run_updates(um, tm))


def main():
    tm = TmuxManager(ui, logger)  # Initialize the TmuxManager instance

    um = UserInterfaceManager(ui, ui_settings, tm)  # Initialize the UI instance
    logger.add(
        lambda msg: um.log_panel.update_log_messages(msg.strip()),
        format="{message}",
        level="INFO",
    )

    um.build_ui()  # Build the UI

    # Create the global timer
    global global_timer
    global_timer = ui.timer(1.0, lambda: run_updates(um, tm))

    # Pass pause and resume functions to TmuxManager
    tm.pause_updates = pause_global_timer
    tm.resume_updates = lambda: resume_global_timer(um, tm)

    # Start the NiceGUI app on a custom port
    ui.run(title="desto dashboard", port=8809, reload=False)


if __name__ in {"__main__", "__mp_main__"}:
    main()
