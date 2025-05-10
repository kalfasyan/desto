from nicegui import ui
import psutil
import time
from datetime import datetime
import humanize

# Global variable to store the current filter text
current_filter_text = ""
# Global variable to store the current sort column and order
current_sort_column = "cpu_percent"
current_sort_order = "desc"  # "asc" for ascending, "desc" for descending


# --- Utility Functions ---
def get_boot_time():
    boot_timestamp = psutil.boot_time()
    boot_datetime = datetime.fromtimestamp(boot_timestamp)
    return boot_datetime.strftime("%Y-%m-%d %H:%M:%S")


def get_network_stats():
    net_io = psutil.net_io_counters()
    return f"Sent: {round(net_io.bytes_sent / (1024**2), 2)} MB, Received: {round(net_io.bytes_recv / (1024**2), 2)} MB"


def get_temperatures():
    temps = psutil.sensors_temperatures()
    temp_list = []
    for name, entries in temps.items():
        for entry in entries:
            temp_list.append((f"{name} - {entry.label}", f"{entry.current}°C"))
    return temp_list


def get_process_info():
    """Get information about running processes"""
    processes = []
    for proc in psutil.process_iter(
        [
            "pid",
            "name",
            "username",
            "cpu_percent",
            "memory_percent",
            "create_time",
            "status",
            "cmdline",  # Include the command line
        ]
    ):
        try:
            # Get process info
            proc_info = proc.info

            # Calculate human-readable creation time
            create_time = datetime.fromtimestamp(proc_info["create_time"])
            age = humanize.naturaltime(datetime.now() - create_time)

            # Get memory usage in MB
            memory_mb = round(
                proc_info["memory_percent"] * psutil.virtual_memory().total / (1024**2),
                2,
            )

            # Get the full command line as a single string
            command = (
                " ".join(proc_info["cmdline"])
                if proc_info["cmdline"]
                else proc_info["name"]
            )

            processes.append(
                {
                    "pid": proc_info["pid"],
                    "name": proc_info["name"],
                    "username": proc_info["username"],
                    "cpu_percent": proc_info["cpu_percent"],
                    "memory_percent": proc_info["memory_percent"],
                    "memory_mb": memory_mb,
                    "create_time": create_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "age": age,
                    "status": proc_info["status"],
                    "command": command,  # Use the full command line
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

    # Sort processes by CPU usage (descending)
    return sorted(processes, key=lambda x: x["cpu_percent"], reverse=True)


# --- Sidebar Update Function ---
def update_system_info():
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
    disk_used.text = (
        f"{round(disk.used / (1024**3), 2)} GB Used"  # Fixed to use disk.used
    )

    boot_time.text = f"Boot Time: {get_boot_time()}"
    network_stats.text = f"Network I/O: {get_network_stats()}"

    temperatures_container.clear()
    temp_data = get_temperatures()
    for name, value in temp_data:
        with temperatures_container:
            with ui.row().style("justify-content: space-between;"):
                ui.label(name).style("font-size: 0.9em;")
                ui.label(value).style("font-size: 0.9em; font-weight: bold;")

    # Update processes table
    update_process_table()


def update_process_table():
    """Update the processes table with current data"""
    global current_sort_column, current_sort_order

    process_table.clear()
    processes = get_process_info()

    # Apply the current filter if it exists
    if current_filter_text:
        processes = [
            p for p in processes if current_filter_text.lower() in p["name"].lower()
        ]

    # Sort processes based on the current sort column and order
    reverse = current_sort_order == "desc"
    processes = sorted(processes, key=lambda x: x[current_sort_column], reverse=reverse)

    # Recreate table headers with clickable sorting
    with process_table:
        with (
            ui.row()
            .classes("w-full")
            .style("font-weight: bold; border-bottom: 1px solid #ddd; padding: 8px;")
        ):
            ui.label("PID").classes("w-1/12").on("click", lambda: sort_table("pid"))
            ui.label("Name").classes("w-2/12").on("click", lambda: sort_table("name"))
            ui.label("User").classes("w-1/12").on(
                "click", lambda: sort_table("username")
            )
            ui.label("CPU %").classes("w-1/12").on(
                "click", lambda: sort_table("cpu_percent")
            )
            ui.label("Memory").classes("w-2/12").on(
                "click", lambda: sort_table("memory_mb")
            )
            ui.label("Started").classes("w-2/12").on(
                "click", lambda: sort_table("create_time")
            )
            ui.label("Command").classes("w-3/12").on(
                "click", lambda: sort_table("command")
            )
            ui.label("Status").classes("w-1/12").on(
                "click", lambda: sort_table("status")
            )

        # Add process rows (limit to top 20 to avoid performance issues)
        for proc in processes[:20]:
            with (
                ui.row()
                .classes("w-full")
                .style("border-bottom: 1px solid #eee; padding: 4px;")
            ):
                ui.label(str(proc["pid"])).classes("w-1/12")
                ui.label(proc["name"]).classes("w-2/12")
                ui.label(proc["username"]).classes("w-1/12")
                ui.label(f"{proc['cpu_percent']:.1f}%").classes("w-1/12")
                ui.label(
                    f"{proc['memory_mb']:.1f} MB ({proc['memory_percent']:.1f}%)"
                ).classes("w-2/12")
                ui.label(proc["create_time"]).classes("w-2/12")
                ui.label(proc["command"]).classes("w-3/12")
                ui.label(proc["status"]).classes("w-1/12")


def sort_table(column):
    """Sort the process table by the given column"""
    global current_sort_column, current_sort_order

    if current_sort_column == column:
        # Toggle sort order if the same column is clicked
        current_sort_order = "asc" if current_sort_order == "desc" else "desc"
    else:
        # Set new column and default to descending order
        current_sort_column = column
        current_sort_order = "desc"

    # Refresh the table with the new sorting
    update_process_table()


# --- UI Definition ---
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
    "table": {"width": "100%", "font_size": "0.9em"},
    "main_content": {
        "font_size": "1.8em",
        "font_weight": "600",
        "subtitle_font_size": "1em",
        "subtitle_color": "#444",
        "margin_top": "16px",
        "margin_bottom": "12px",
    },
    "temperatures": {
        "margin_top": "8px",
        "margin_bottom": "4px",
    },
    "process_list": {
        "title_font_size": "1.5em",
        "padding": "16px",
        "background_color": "#FFFFFF",
        "border_radius": "8px",
        "box_shadow": "0 2px 10px rgba(0, 0, 0, 0.1)",
        "refresh_rate": 3,  # seconds
    },
}

# Use a ui.left_drawer for the sidebar
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
    ui.label("System Monitor").style(
        f"font-size: {ui_settings['header']['font_size']}; font-weight: bold;"
    )

with ui.left_drawer().style(
    f"width: {ui_settings['sidebar']['width']}; "
    f"padding: {ui_settings['sidebar']['padding']}; "
    f"background-color: {ui_settings['sidebar']['background_color']}; "
    f"border-radius: {ui_settings['sidebar']['border_radius']}; "
    "display: flex; flex-direction: column;"  # Enable flexbox for layout
) as left_drawer:
    # Container for the main System Stats
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

        ui.label("System Information").style(
            f"font-weight: {ui_settings['labels']['subtitle_font_weight']}; margin-top: 10px;"
        )
        boot_time = ui.label().style(
            f"font-size: {ui_settings['labels']['info_font_size']};"
        )
        network_stats = ui.label().style(
            f"font-size: {ui_settings['labels']['info_font_size']};"
        )

        ui.label("Temperatures").style(
            f"font-weight: {ui_settings['labels']['subtitle_font_weight']}; "
            f"margin-top: {ui_settings['temperatures']['margin_top']}; "
            f"margin-bottom: {ui_settings['temperatures']['margin_bottom']};"
        )
        temperatures_container = ui.column()

        ui.separator().style(
            f"margin-top: {ui_settings['separator']['margin_top']}; "
            f"margin-bottom: {ui_settings['separator']['margin_bottom']};"
        )

# Main Content Area with Process List
with ui.column().style("flex-grow: 1; padding: 20px; gap: 20px;"):
    # Welcome section
    with ui.card().style("width: 100%;"):
        ui.label("System Overview").style(
            f"font-size: {ui_settings['main_content']['font_size']}; "
            f"font-weight: {ui_settings['main_content']['font_weight']}; "
            f"margin: 16px 0;"
        )
        ui.label("Monitor your system resources and processes in real-time").style(
            f"font-size: {ui_settings['main_content']['subtitle_font_size']}; "
            f"color: {ui_settings['main_content']['subtitle_color']}; "
            f"margin-bottom: 16px;"
        )

        # Process List Section
        with ui.card().style(
            f"width: 100%; "
            f"padding: {ui_settings['process_list']['padding']}; "
            f"background-color: {ui_settings['process_list']['background_color']}; "
            f"border-radius: {ui_settings['process_list']['border_radius']}; "
            f"box-shadow: {ui_settings['process_list']['box_shadow']}; "
            f"overflow-x: auto;"  # Add horizontal scrolling if needed
        ):
            with ui.row().style(
                "justify-content: space-between; align-items: center; margin-bottom: 16px;"
            ):
                ui.label("Running Processes").style(
                    f"font-size: {ui_settings['process_list']['title_font_size']}; "
                    f"font-weight: {ui_settings['labels']['title_font_weight']};"
                )

                # Add refresh button with tooltip
                with ui.tooltip("Refresh Process List"):
                    refresh_btn = ui.button(
                        icon="refresh", on_click=update_process_table
                    ).props("flat")

            # Add a search input and a filter button
            search_input = ui.input(
                label="Filter processes", placeholder="Enter process name..."
            ).style("margin-bottom: 16px;")

            # Add a "Filter" button to trigger the filtering
            ui.button(
                "Filter", on_click=lambda: filter_processes(search_input.value)
            ).style("margin-bottom: 16px;")

            # Create process table container with a fixed width for columns
            process_table = ui.column().style(
                f"width: 1200px; font-size: {ui_settings['table']['font_size']};"
            )


# Global variable to store the current filter text
current_filter_text = ""


def filter_processes(search_text):
    """Filter the process table based on search text"""
    global current_filter_text
    current_filter_text = search_text  # Update the global filter text
    update_process_table()  # Refresh the table with the filter applied


def update_process_table():
    """Update the processes table with current data"""
    process_table.clear()
    processes = get_process_info()

    # Apply the current filter if it exists
    if current_filter_text:
        processes = [
            p for p in processes if current_filter_text.lower() in p["name"].lower()
        ]

    with process_table:
        with (
            ui.row()
            .classes("w-full")
            .style("font-weight: bold; border-bottom: 1px solid #ddd; padding: 8px;")
        ):
            ui.button("PID", on_click=lambda: sort_table("pid")).classes("w-1/12 flat")
            ui.button("Name", on_click=lambda: sort_table("name")).classes(
                "w-2/12 flat"
            )
            ui.button("User", on_click=lambda: sort_table("username")).classes(
                "w-1/12 flat"
            )
            ui.button("CPU %", on_click=lambda: sort_table("cpu_percent")).classes(
                "w-1/12 flat"
            )
            ui.button("Memory", on_click=lambda: sort_table("memory_mb")).classes(
                "w-2/12 flat"
            )
            ui.button("Started", on_click=lambda: sort_table("create_time")).classes(
                "w-2/12 flat"
            )
            ui.button("Command", on_click=lambda: sort_table("command")).classes(
                "w-3/12 flat"
            )
            ui.button("Status", on_click=lambda: sort_table("status")).classes(
                "w-1/12 flat"
            )

        # Add process rows (limit to top 20 to avoid performance issues)
        for proc in processes[:20]:
            with (
                ui.row()
                .classes("w-full")
                .style("border-bottom: 1px solid #eee; padding: 4px;")
            ):
                ui.label(str(proc["pid"])).classes("w-1/12")
                ui.label(proc["name"]).classes("w-2/12")
                ui.label(proc["username"]).classes("w-1/12")
                ui.label(f"{proc['cpu_percent']:.1f}%").classes("w-1/12")
                ui.label(
                    f"{proc['memory_mb']:.1f} MB ({proc['memory_percent']:.1f}%)"
                ).classes("w-2/12")
                ui.tooltip(f"Created: {proc['create_time']}")
                ui.label(proc["age"]).classes("w-3/12")
                ui.label(proc["status"]).classes("w-1/12")


# Initial updates
update_system_info()

# Set timer for regular updates (sidebar and processes)
ui.timer(1.0, update_system_info)
ui.timer(ui_settings["process_list"]["refresh_rate"], update_process_table)

ui.run()
