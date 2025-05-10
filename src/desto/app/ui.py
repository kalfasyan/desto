from datetime import datetime
from loguru import logger
import psutil
from nicegui import ui
import subprocess
from desto.app.sessions import TmuxManager  # Import the TmuxManager class

logger.add(
    lambda msg: update_log_messages(msg.strip(), log_messages),
    format="{message}",
    level="INFO",
)

tmux_manager = TmuxManager()  # Initialize the TmuxManager instance

# Global variables for timers and log messages
update_system_info_timer = None
update_sessions_status_timer = None
log_messages = []

# Define a settings dictionary for UI customization
ui_settings = {
    "header": {"background_color": "#2196F3", "color": "#FFFFFF", "font_size": "1.8em"},
    "sidebar": {
        "width": "280px",
        "padding": "10px",
        "background_color": "#F0F0F0",
        "border_radius": "6px",
        "gap": "8px",
    },
    "labels": {
        "title_font_size": "1.3em",
        "title_font_weight": "bold",
        "subtitle_font_size": "1em",
        "subtitle_font_weight": "500",
        "info_font_size": "0.9em",
        "info_color": "#666",
        "margin_top": "8px",
        "margin_bottom": "4px",
    },
    "progress_bar": {"size": "sm"},
    "separator": {"margin_top": "12px", "margin_bottom": "8px"},
    "main_content": {
        "font_size": "1.8em",
        "font_weight": "600",
        "subtitle_font_size": "1em",
        "subtitle_color": "#444",
        "margin_top": "16px",
        "margin_bottom": "12px",
    },
}


# --- Utility Functions ---
def update_log_messages(message, log_messages, number_of_lines=20):
    """
    Updates the provided log_messages list with the latest log message.
    Keeps only the last 'number_of_lines' messages.
    """
    log_messages.append(message)
    if len(log_messages) > number_of_lines:
        log_messages.pop(0)  # Keep only the last 'number_of_lines' messages


def refresh_log_display(log_display, log_messages):
    """
    Refreshes the log display with the latest log messages.
    """
    log_display.value = "\n".join(log_messages)


def start_tmux_session(session_name, command, logger):
    """
    Starts a new tmux session with the given name and command, redirecting output to a log file.
    """
    log_file = f"{session_name}.log"  # Log file path
    try:
        # Start a detached tmux session
        subprocess.run(
            ["tmux", "new-session", "-d", "-s", session_name, command],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        logger.info(f"Tmux session '{session_name}' started with command: {command}")

        # Redirect output to the log file
        subprocess.run(
            ["tmux", "pipe-pane", "-t", session_name, f"cat > {log_file}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        logger.warning(f"Failed to start tmux session '{session_name}': {e}")


def confirm_kill_session(
    session_name,
    ui,
    kill_tmux_session,
    resume_updates,
    update_system_info_timer,
    update_sessions_status_timer,
):
    """
    Displays a confirmation dialog before killing a tmux session and pauses updates.
    """
    # Pause the timers by setting their active attribute to False
    if update_system_info_timer:
        update_system_info_timer.active = False
    if update_sessions_status_timer:
        update_sessions_status_timer.active = False

    with ui.dialog() as dialog, ui.card():
        ui.label(f"Are you sure you want to kill the session '{session_name}'?")
        with ui.row():
            ui.button(
                "Yes",
                on_click=lambda: [
                    kill_tmux_session(session_name, logger, update_sessions_status),
                    dialog.close(),
                    resume_updates(
                        update_system_info_timer, update_sessions_status_timer
                    ),  # Resume updates after killing
                ],
            ).props("color=red")
            ui.button(
                "No",
                on_click=lambda: [
                    dialog.close(),
                    resume_updates(
                        update_system_info_timer, update_sessions_status_timer
                    ),  # Resume updates if canceled
                ],
            )

    dialog.open()


def resume_updates(update_system_info_timer, update_sessions_status_timer):
    """
    Resumes the app's updates by reactivating the timers.
    """
    if update_system_info_timer:
        update_system_info_timer.active = True
    if update_sessions_status_timer:
        update_sessions_status_timer.active = True


def get_tmux_sessions_status(logger):
    """
    Retrieves the status of all active tmux sessions.
    Returns a list of dictionaries with session names and statuses.
    """
    try:
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}:#{session_attached}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        sessions = []
        for line in result.stdout.strip().split("\n"):
            if line:
                name, attached = line.split(":")
                sessions.append(
                    {
                        "name": name,
                        "status": "Attached" if attached == "1" else "Detached",
                    }
                )
        return sessions
    except subprocess.CalledProcessError as e:
        logger.warning(f"Failed to retrieve tmux sessions: {e}")
        return []


def update_sessions_status(
    tmux_manager, sessions_container, ui, confirm_kill_session, view_log
):
    """
    Updates the sessions table with detailed information and adds a kill button and a view log button for each session.
    """
    sessions_status = tmux_manager.check_sessions()

    sessions_container.clear()
    with sessions_container:
        # Add table headers
        with ui.row().style("font-weight: bold; margin-bottom: 10px;"):
            ui.label("Session ID").style("width: 100px;")
            ui.label("Name").style("width: 150px;")
            ui.label("Created").style("width: 200px;")
            ui.label("Attached").style("width: 100px;")
            ui.label("Windows").style("width: 100px;")
            ui.label("Group").style("width: 100px;")
            ui.label("Group Size").style("width: 100px;")
            ui.label("Actions").style("width: 200px;")

        # Add rows for each session
        for session_name, session in sessions_status.items():
            with ui.row().style("align-items: center; margin-bottom: 10px;"):
                ui.label(session["id"]).style("width: 100px;")
                ui.label(session_name).style("width: 150px;")
                ui.label(
                    datetime.fromtimestamp(session["created"]).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                ).style("width: 200px;")
                ui.label("Yes" if session["attached"] else "No").style("width: 100px;")
                ui.label(str(session["windows"])).style("width: 100px;")
                ui.label(session["group"] or "N/A").style("width: 100px;")
                ui.label(str(session["group_size"])).style("width: 100px;")
                ui.button(
                    "Kill",
                    on_click=lambda s=session_name: confirm_kill_session(
                        s,
                        ui,
                        kill_tmux_session,
                        resume_updates,
                        update_system_info_timer,
                        update_sessions_status_timer,
                    ),
                ).props("color=red flat")
                ui.button(
                    "View Log",
                    on_click=lambda s=session_name: view_log(
                        s,
                        ui,
                        resume_updates,
                        update_system_info_timer,
                        update_sessions_status_timer,
                    ),
                ).props("color=blue flat")


def view_log(
    session_name,
    ui,
    resume_updates,
    update_system_info_timer,
    update_sessions_status_timer,
):
    """
    Pauses the app and opens a dialog to display the last 100 lines of the session's log file.
    """
    # Pause the timers to stop updates
    if update_system_info_timer:
        update_system_info_timer.active = False
    if update_sessions_status_timer:
        update_sessions_status_timer.active = False

    log_file = f"{session_name}.log"  # Log file path
    try:
        with open(log_file, "r") as f:
            lines = f.readlines()[-100:]  # Get the last 100 lines
        log_content = "".join(lines)
    except FileNotFoundError:
        log_content = f"Log file for session '{session_name}' not found."

    with (
        ui.dialog() as dialog,
        ui.card().style("width: 100%; height: 80%;"),
    ):
        ui.label(f"Log for session '{session_name}'").style("font-weight: bold;")
        with ui.scroll_area().style("width: 100%; height: 100%;"):
            ui.label(log_content).style("white-space: pre-wrap;")
        ui.button(
            "Close",
            on_click=lambda: [
                dialog.close(),
                resume_updates(
                    update_system_info_timer, update_sessions_status_timer
                ),  # Resume updates when the dialog is closed
            ],
        ).props("color=primary")
    dialog.open()


def kill_tmux_session(session_name, logger, update_sessions_status):
    """
    Kills a tmux session by name.
    """
    try:
        subprocess.run(["tmux", "kill-session", "-t", session_name], check=True)
        logger.success(f"Tmux session '{session_name}' killed successfully.")
        update_sessions_status(
            tmux_manager, sessions_container, ui, confirm_kill_session, view_log
        )
    except subprocess.CalledProcessError as e:
        logger.warning(f"Failed to kill tmux session '{session_name}': {e}")


# --- Sidebar Update Function ---
def update_system_info(
    cpu_percent,
    cpu_bar,
    memory_percent,
    memory_bar,
    memory_available,
    memory_used,
    disk_percent,
    disk_bar,
    disk_free,
    disk_used,
):
    """
    Updates the system information displayed in the sidebar.
    """
    cpu_percent.text = f"{psutil.cpu_percent()}%"
    cpu_bar.value = psutil.cpu_percent() / 100

    memory = psutil.virtual_memory()
    memory_percent.text = f"{memory.percent}%"
    memory_bar.value = memory.percent / 100
    memory_available.text = f"{round(memory.available / (1024**3), 2)} GB Available"
    memory_used.text = f"{round(memory.used / (1024**3), 2)} GB Used"

    disk = psutil.disk_usage("/")
    disk_percent.text = f"{disk.percent}%"
    disk_bar.value = disk.percent / 100
    disk_free.text = f"{round(disk.free / (1024**3), 2)} GB Free"
    disk_used.text = f"{round(disk.used / (1024**3), 2)} GB Used"


# --- UI Definition ---
with (
    ui.header(elevated=True)
    .style(
        f"background-color: {ui_settings['header']['background_color']}; "
        f"color: {ui_settings['header']['color']};"
    )
    .classes(replace="row items-center")
):
    ui.button(on_click=lambda: left_drawer.toggle(), icon="menu").props(
        "flat color=white"
    )
    ui.label("desto").style(
        f"font-size: {ui_settings['header']['font_size']}; font-weight: bold;"
    )

with ui.left_drawer().style(
    f"width: {ui_settings['sidebar']['width']}; "
    f"padding: {ui_settings['sidebar']['padding']}; "
    f"background-color: {ui_settings['sidebar']['background_color']}; "
    f"border-radius: {ui_settings['sidebar']['border_radius']}; "
    "display: flex; flex-direction: column;"
) as left_drawer:
    with ui.column():
        ui.label("System Stats").style(
            f"font-size: {ui_settings['labels']['title_font_size']}; "
            f"font-weight: {ui_settings['labels']['title_font_weight']}; "
            "margin-bottom: 10px;"
        )

        ui.label("CPU Usage").style(
            f"font-weight: {ui_settings['labels']['subtitle_font_weight']}; margin-top: 10px;"
        )
        with ui.row().style("align-items: center"):
            ui.icon("memory", size="1.2rem")
            cpu_percent = ui.label("0%").style(
                f"font-size: {ui_settings['labels']['subtitle_font_size']}; margin-left: 5px;"
            )
        cpu_bar = ui.linear_progress(value=0, size=ui_settings["progress_bar"]["size"])

        ui.label("Memory Usage").style(
            f"font-weight: {ui_settings['labels']['subtitle_font_weight']}; margin-top: 10px;"
        )
        with ui.row().style("align-items: center"):
            ui.icon("memory", size="1.2rem")
            memory_percent = ui.label("0%").style(
                f"font-size: {ui_settings['labels']['subtitle_font_size']}; margin-left: 5px;"
            )
        memory_bar = ui.linear_progress(
            value=0, size=ui_settings["progress_bar"]["size"]
        )
        memory_used = ui.label("0 GB Used").style(
            f"font-size: {ui_settings['labels']['info_font_size']}; color: {ui_settings['labels']['info_color']};"
        )
        memory_available = ui.label("0 GB Available").style(
            f"font-size: {ui_settings['labels']['info_font_size']}; color: {ui_settings['labels']['info_color']};"
        )

        ui.label("Disk Usage (Root)").style(
            f"font-weight: {ui_settings['labels']['subtitle_font_weight']}; margin-top: 10px;"
        )
        with ui.row().style("align-items: center"):
            ui.icon("hard_drive", size="1.2rem")
            disk_percent = ui.label("0%").style(
                f"font-size: {ui_settings['labels']['subtitle_font_size']}; margin-left: 5px;"
            )
        disk_bar = ui.linear_progress(value=0, size=ui_settings["progress_bar"]["size"])
        disk_used = ui.label("0 GB Used").style(
            f"font-size: {ui_settings['labels']['info_font_size']}; color: {ui_settings['labels']['info_color']};"
        )
        disk_free = ui.label("0 GB Free").style(
            f"font-size: {ui_settings['labels']['info_font_size']}; color: {ui_settings['labels']['info_color']};"
        )

# Main Content Area with Process List
with ui.column().style("flex-grow: 1; padding: 20px; gap: 20px;"):
    ui.label("Dashboard").style("font-size: 2em; font-weight: bold;")

    session_name_input = ui.input(label="Session Name").style("width: 300px;")
    command_input = ui.input(
        label="Command",
        value='for i in {1..1000}; do echo -e "$i\\n"; sleep 0.1; done; echo',
    ).style("width: 300px;")

    ui.button(
        "Run in Session",
        on_click=lambda: start_tmux_session(
            session_name_input.value, command_input.value, logger
        ),
    )

    with ui.card().style(
        "background-color: #fff; color: #000; padding: 10px; border-radius: 8px; width: 100%;"
    ):
        ui.label("Active Sessions").style(
            "font-size: 1.5em; font-weight: bold; margin-bottom: 20px; text-align: center;"
        )
        sessions_container = ui.column().style("margin-top: 20px;")

    with ui.card().style(
        "background-color: #fff; color: #000; padding: 10px; border-radius: 8px; width: 100%;"
    ):
        ui.label("Log Messages").style(
            "font-size: 1.5em; font-weight: bold; margin-bottom: 20px; width: 100%; height: 100%;text-align: left;"
        )
        log_display = (
            ui.textarea("")
            .style(
                "width: 100%; height: 100%; background-color: #fff; color: #000; border: 1px solid #ccc; font-family: monospace;"
            )
            .props("readonly")
        )

# Initialize timers
update_system_info_timer = ui.timer(
    1.0,
    lambda: update_system_info(
        cpu_percent,
        cpu_bar,
        memory_percent,
        memory_bar,
        memory_available,
        memory_used,
        disk_percent,
        disk_bar,
        disk_free,
        disk_used,
    ),
)
update_sessions_status_timer = ui.timer(
    2.0,
    lambda: update_sessions_status(
        tmux_manager, sessions_container, ui, confirm_kill_session, view_log
    ),
)

# Initial updates
update_system_info(
    cpu_percent,
    cpu_bar,
    memory_percent,
    memory_bar,
    memory_available,
    memory_used,
    disk_percent,
    disk_bar,
    disk_free,
    disk_used,
)
update_sessions_status(
    tmux_manager, sessions_container, ui, confirm_kill_session, view_log
)
ui.timer(1.0, lambda: refresh_log_display(log_display, log_messages))

# Start the NiceGUI app
ui.run(title="Tmux Dashboard")
