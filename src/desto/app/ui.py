import getpass
import os
import re
import shlex
import socket
from pathlib import Path

import psutil
from loguru import logger
from nicegui import ui

from desto.redis.at_job_manager import AtJobManager

from .favorites_ui import FavoritesTab
from .ui_elements import LogSection, NewScriptTab, ScriptManagerTab, SettingsPanel, SystemStatsPanel


class UserInterfaceManager:
    def __init__(self, ui, ui_settings, tmux_manager, desto_manager=None):
        self.ui_settings = ui_settings
        self.ui = ui
        self.desto_manager = desto_manager
        self.tmux_manager = tmux_manager
        self.stats_panel = SystemStatsPanel(ui_settings)
        self.new_script_tab = NewScriptTab(tmux_manager, self)
        self.log_section = LogSection()
        self.script_manager_tab = ScriptManagerTab(self)
        self.favorites_tab = FavoritesTab(self, desto_manager) if desto_manager else None
        self.script_path_select = None  # Reference to the script select component
        self.session_name_input = None  # Reference to session name input
        self.arguments_input = None  # Reference to arguments input
        self.script_preview_editor = None  # Reference to script preview editor
        self.ignore_next_edit = False
        self.chain_queue = []  # List of (script_path, arguments)

    def get_script_files(self):
        """Return a list of script filenames in the scripts directory."""
        script_extensions = self.ui_settings.get("script_settings", {}).get("supported_extensions", [".sh", ".py"])
        scripts = []
        for ext in script_extensions:
            pattern = f"*{ext}"
            scripts.extend([f.name for f in self.tmux_manager.SCRIPTS_DIR.glob(pattern) if f.is_file()])
        return sorted(scripts)

    def get_script_type(self, script_name):
        """Determine script type from extension."""
        if script_name.endswith(".py"):
            return "python"
        elif script_name.endswith(".sh"):
            return "bash"
        return "unknown"

    def get_script_icon(self, script_type):
        """Get icon for script type."""
        icons = {"python": "🐍", "bash": "🐚", "unknown": "📄"}
        return icons.get(script_type, "📄")

    def build_execution_command(self, script_path, arguments):
        """Build the appropriate execution command based on script type."""
        script_name = Path(script_path).name
        script_type = self.get_script_type(script_name)

        if script_type == "python":
            python_exec = self.ui_settings.get("script_settings", {}).get("python_executable", "python3")
            return f"{python_exec} '{script_path}' {arguments}"
        elif script_type == "bash":
            return f"bash '{script_path}' {arguments}"
        else:
            # Fallback: try to execute directly (relies on shebang)
            return f"'{script_path}' {arguments}"

    @staticmethod
    def is_valid_script_name(name):
        return re.match(r"^[\w\-]{1,15}$", name) is not None

    def refresh_script_list(self):
        script_files = self.get_script_files()
        if self.script_path_select:
            # Check if icons should be shown
            show_icons = self.ui_settings.get("script_settings", {}).get("show_script_type_icons", True)

            if show_icons and script_files:
                # Create options with icons
                script_options = []
                for script_file in script_files:
                    script_type = self.get_script_type(script_file)
                    icon = self.get_script_icon(script_type)
                    script_options.append(f"{icon} {script_file}")

                self.script_path_select.options = script_options
                self.script_path_select.value = script_options[0] if script_options else "No scripts found"
            else:
                # Use plain filenames
                self.script_path_select.options = script_files if script_files else ["No scripts found"]
                self.script_path_select.value = script_files[0] if script_files else "No scripts found"

            if not script_files:
                msg = f"No script files found in {self.tmux_manager.SCRIPTS_DIR}. Select a different directory or add scripts."
                logger.warning(msg)
                ui.notification(msg, type="warning")

    def extract_script_filename(self, display_value):
        """Extract the actual filename from the display value (which might include an icon)."""
        if not display_value or display_value == "No scripts found":
            return display_value

        # If the value starts with an emoji (icon), extract the filename part
        if display_value and len(display_value) > 2 and display_value[1] == " ":
            return display_value[2:]  # Skip the icon and space

        return display_value  # Return as-is if no icon

    def build_ui(self):
        with ui.header(elevated=True).style(f"background-color: {self.ui_settings['header']['background_color']}; color: {self.ui_settings['header']['color']};").classes(replace="row items-center justify-between"):
            ui.button(on_click=lambda: left_drawer.toggle(), icon="preview").props("flat color=white")
            ui.label("desto").style(f"font-size: {self.ui_settings['header']['font_size']}; font-weight: bold;")
            ui.button(on_click=lambda: right_drawer.toggle(), icon="settings").props("flat color=white").style("margin-left: auto;")
        with ui.left_drawer().style(
            f"width: {self.ui_settings['sidebar']['width']}; "
            f"min-width: {self.ui_settings['sidebar']['width']}; "
            f"max-width: {self.ui_settings['sidebar']['width']}; "
            f"padding: {self.ui_settings['sidebar']['padding']}; "
            f"background-color: {self.ui_settings['sidebar']['background_color']}; "
            f"border-radius: {self.ui_settings['sidebar']['border_radius']}; "
            "display: flex; flex-direction: column;"
        ) as left_drawer:
            self.stats_panel.build()

        with ui.right_drawer(top_corner=False, bottom_corner=True, value=False).style(
            f"width: {self.ui_settings['sidebar']['width']}; "
            f"padding: {self.ui_settings['sidebar']['padding']}; "
            f"background-color: {self.ui_settings['sidebar']['background_color']}; "
            f"border-radius: {self.ui_settings['sidebar']['border_radius']}; "
            "display: flex; flex-direction: column;"
        ) as right_drawer:
            self.settings_panel = SettingsPanel(self.tmux_manager, self)
            self.settings_panel.build()

        ui.button("Settings", on_click=lambda: right_drawer.toggle(), icon="settings").props("flat color=blue").style("margin-right: auto;")
        with ui.column().style("flex-grow: 1; padding: 20px; gap: 20px;"):
            with ui.splitter(value=25).classes("w-full").style("gap:0; padding:0; margin:0;") as splitter:
                with splitter.before:
                    with ui.tabs().props("vertical").classes("w-32 min-w-0") as tabs:
                        scripts_tab = ui.tab("Scripts", icon="terminal")
                        new_script_tab = ui.tab("New Script", icon="add")
                        favorites_tab = ui.tab("Favorites", icon="star") if self.favorites_tab else None
                with splitter.after:
                    with ui.tab_panels(tabs, value=scripts_tab).props("vertical").classes("w-full"):
                        with ui.tab_panel(scripts_tab):
                            self.script_manager_tab.build()

                        with ui.tab_panel(new_script_tab):
                            with ui.card().style("background-color: #fff; color: #000; padding: 20px; border-radius: 8px; width: 100%; margin-left: 0;"):
                                self.new_script_tab.build()

                        if favorites_tab and self.favorites_tab:
                            with ui.tab_panel(favorites_tab):
                                self.favorites_tab.build()

            ui.label("Chain Queue:").style("font-weight: bold; margin-top: 10px;")
            self.chain_queue_display = ui.column().style("margin-bottom: 10px;")
            self.refresh_chain_queue_display()

            # Clear Chain Queue button
            ui.button(
                "Clear Chain Queue",
                color="orange",
                icon="clear_all",
                on_click=self.clear_chain_queue,
            ).style("width: 200px; margin-top: 10px; margin-bottom: 5px;")

            # Clear All Jobs button
            ui.button(
                "Clear All Jobs",
                color="red",
                icon="delete_forever",
                on_click=self.tmux_manager.confirm_kill_all_sessions,
            ).style("width: 200px; margin-top: 15px; margin-bottom: 15px;")

            self.log_section.build()

    def update_log_messages(self, message, number_of_lines=20):
        self.log_section.update_log_messages(message, number_of_lines)

    def refresh_log_display(self):
        self.log_section.refresh_log_display()

    def update_ui_system_info(self):
        """Update system stats in the UI."""
        # Get CPU percentage once to avoid inconsistent readings
        cpu_percent = psutil.cpu_percent(interval=None)  # Non-blocking call
        self.stats_panel.cpu_percent.text = f"{cpu_percent:.1f}%"
        self.stats_panel.cpu_bar.value = cpu_percent / 100

        # Update CPU cores if they're visible and initialized
        if self.stats_panel.show_cpu_cores.value and self.stats_panel.cpu_core_labels and self.stats_panel.cpu_core_bars:
            try:
                core_percentages = psutil.cpu_percent(percpu=True, interval=None)
                for i, core_percent in enumerate(core_percentages):
                    if i < len(self.stats_panel.cpu_core_labels) and i < len(self.stats_panel.cpu_core_bars):
                        self.stats_panel.cpu_core_labels[i].text = f"{core_percent:.1f}%"
                        self.stats_panel.cpu_core_bars[i].value = core_percent / 100
            except Exception as e:
                # If there's an error getting per-core data, just skip the update
                logger.debug(f"Error updating CPU core data: {e}")
                pass

        memory = psutil.virtual_memory()
        self.stats_panel.memory_percent.text = f"{memory.percent}%"
        self.stats_panel.memory_bar.value = memory.percent / 100
        self.stats_panel.memory_available.text = f"{round(memory.available / (1024**3), 2)} GB Available"
        self.stats_panel.memory_used.text = f"{round(memory.used / (1024**3), 2)} GB Used"
        disk = psutil.disk_usage("/")
        self.stats_panel.disk_percent.text = f"{disk.percent}%"
        self.stats_panel.disk_bar.value = disk.percent / 100
        self.stats_panel.disk_free.text = f"{round(disk.free / (1024**3), 2)} GB Free"
        self.stats_panel.disk_used.text = f"{round(disk.used / (1024**3), 2)} GB Used"
        # --- tmux server stats ---
        tmux_cpu = "N/A"
        tmux_mem = "N/A"
        try:
            tmux_procs = [p for p in psutil.process_iter(["name", "ppid", "cpu_percent", "memory_info", "cmdline"]) if p.info["name"] == "tmux" or "tmux" in p.info["name"]]
            if tmux_procs:
                server_proc = next((p for p in tmux_procs if p.info["ppid"] == 1), None)
                if not server_proc:
                    server_proc = min(tmux_procs, key=lambda p: p.info["ppid"])
                tmux_cpu = f"{server_proc.cpu_percent(interval=0.1):.1f}%"
                mem_mb = server_proc.memory_info().rss / (1024 * 1024)
                tmux_mem = f"{mem_mb:.1f} MB"
            else:
                total_cpu = sum(p.cpu_percent(interval=0.1) for p in tmux_procs)
                total_mem = sum(p.memory_info().rss for p in tmux_procs)
                tmux_cpu = f"{total_cpu:.1f}%"
                tmux_mem = f"{total_mem / (1024 * 1024):.1f} MB"
        except Exception:
            tmux_cpu = "N/A"
            tmux_mem = "N/A"
        self.stats_panel.tmux_cpu.text = f"tmux CPU: {tmux_cpu}"
        self.stats_panel.tmux_mem.text = f"tmux MEM: {tmux_mem}"

    def update_script_preview(self, e):
        """Update the script preview editor when a new script is selected."""
        selected = e.args
        script_files = self.get_script_files()
        # If selected is a list/tuple, get the first element
        if isinstance(selected, (list, tuple)):
            selected = selected[0]
        # If selected is a dict (option object), get the value
        if isinstance(selected, dict):
            selected = selected.get("value", "")
        # If selected is an int, treat it as an index
        if isinstance(selected, int):
            if 0 <= selected < len(script_files):
                selected = script_files[selected]
            else:
                selected = ""
        # Now selected should be a string (filename or display text)
        actual_filename = self.extract_script_filename(selected)
        script_path = self.tmux_manager.SCRIPTS_DIR / actual_filename
        if script_path.is_file():
            with open(script_path, "r") as f:
                content = f.read()
                self.ignore_next_edit = True  # Ignore the next edit event
                self.script_preview_editor.value = content

                # Update syntax highlighting based on script type
                script_type = self.get_script_type(actual_filename)
                if script_type == "python":
                    self.script_preview_editor.language = "python"
                elif script_type == "bash":
                    self.script_preview_editor.language = "bash"
        else:
            self.ignore_next_edit = True
            self.script_preview_editor.value = "# Script not found."

    def confirm_delete_script(self):
        """Show a confirmation dialog and delete the selected script if confirmed."""
        selected_script = self.script_path_select.value
        if not selected_script or selected_script == "No scripts found":
            msg = "No script selected to delete."
            logger.warning(msg)
            ui.notification(msg, type="warning")
            return

        actual_filename = self.extract_script_filename(selected_script)

        def do_delete():
            script_path = self.tmux_manager.SCRIPTS_DIR / actual_filename
            try:
                logger.info(f"Attempting to delete script: {script_path}")
                script_path.unlink()
                msg = f"Deleted script: {actual_filename}"
                logger.info(msg)
                ui.notification(msg, type="positive")
                self.refresh_script_list()
                self.update_script_preview(type("E", (), {"args": self.script_path_select.value})())
            except Exception as e:
                msg = f"Failed to delete: {e}"
                logger.error(msg)
                ui.notification(msg, type="negative")
            confirm_dialog.close()

        with ui.dialog() as confirm_dialog, ui.card():
            ui.label(f"Are you sure you want to delete '{actual_filename}'?")
            with ui.row():
                ui.button("Cancel", on_click=confirm_dialog.close)
                ui.button("Delete", color="red", on_click=do_delete)
        msg = f"Opened delete confirmation dialog for: {actual_filename}"
        logger.debug(msg)
        confirm_dialog.open()

    def save_current_script(self, script_edited):
        """Save the current script in the editor to its file."""
        selected_script = self.script_path_select.value
        if not selected_script or selected_script == "No scripts found":
            ui.notification("No script selected to save.", type="warning")
            return
        actual_filename = self.extract_script_filename(selected_script)
        script_path = self.tmux_manager.SCRIPTS_DIR / actual_filename
        try:
            with script_path.open("w") as f:
                f.write(self.script_preview_editor.value)
            os.chmod(script_path, 0o755)
            script_edited["changed"] = False
            ui.notification(f"Saved changes to {actual_filename}", type="positive")
        except Exception as e:
            logger.exception("Failed to save current script")
            ui.notification(f"Failed to save: {e}", type="negative")

    def save_as_new_dialog(self):
        """Open a dialog to save the current script as a new file."""
        with ui.dialog() as name_dialog, ui.card():
            name_input = ui.input(label="New Script Name (max 15 chars)").style("width: 100%;")
            error_label = ui.label("").style("color: red;")

            def do_save_as_new():
                name = name_input.value.strip().replace(" ", "_")[:15]
                if not self.is_valid_script_name(name):
                    error_label.text = "Name must be 1-15 characters, letters, numbers, _ or -."
                    return
                new_script_path = self.tmux_manager.SCRIPTS_DIR / f"{name}.sh"
                if new_script_path.exists():
                    error_label.text = "A script with this name already exists."
                    return
                try:
                    with new_script_path.open("w") as f:
                        f.write(self.script_preview_editor.value)
                    os.chmod(new_script_path, 0o755)
                    self.refresh_script_list()
                    self.script_path_select.value = f"{name}.sh"
                    ui.notification(f"Script saved as {name}.sh", type="positive")
                    name_dialog.close()
                except Exception as e:
                    logger.exception("Failed to save as new script")
                    error_label.text = f"Failed to save: {e}"

            ui.button("Cancel", on_click=name_dialog.close)
            ui.button("Save", on_click=do_save_as_new)
        name_dialog.open()

    def chain_current_script(self):
        script_name = self.script_path_select.value
        arguments = self.arguments_input.value
        if not script_name or script_name == "No scripts found":
            ui.notification("No script selected to chain.", type="warning")
            return
        actual_filename = self.extract_script_filename(script_name)
        script_path = self.tmux_manager.SCRIPTS_DIR / actual_filename
        self.chain_queue.append((str(script_path), arguments))
        ui.notification(f"Added {actual_filename} to chain.", type="positive")
        self.refresh_chain_queue_display()

    def get_log_info_block(self, script_file_path, session_name, scheduled_dt=None):
        username = getpass.getuser()
        hostname = socket.gethostname()
        script_name = Path(script_file_path).name
        cwd = os.getcwd()
        now_str = scheduled_dt.strftime("%Y-%m-%d %H:%M") if scheduled_dt else ""
        info_lines = [
            f"# Script: {script_name}",
            f"# Session: {session_name}",
            f"# User: {username}@{hostname}",
            f"# Working Directory: {cwd}",
        ]
        if now_str:
            info_lines.append(f"# Scheduled for: {now_str}")
        info_lines.append("")  # Blank line
        return "\n".join(info_lines)

    def build_logging_command(self, log_file_path, info_block, exec_cmd, job_completion_cmd, session_start_cmd=None):
        """Build a properly formatted logging command that appends to existing logs."""
        # Check if log file exists to determine if we should append or create new
        append_mode = Path(log_file_path).exists()

        # Build the command components using printf for better shell compatibility
        if append_mode:
            # If log file exists, append a separator and the new info block
            separator_cmd = f"printf '\\n---- NEW SESSION (%s) -----\\n' \"$(date '+%Y-%m-%d %H:%M:%S')\" >> '{log_file_path}'"
            info_cmd = f"printf '%s\\n' {repr(info_block)} >> '{log_file_path}'"
        else:
            # If log file doesn't exist, create it with the info block
            separator_cmd = ""
            info_cmd = f"printf '%s\\n' {repr(info_block)} > '{log_file_path}'"

        # Add pre-script logging - use printf for better shell compatibility
        pre_script_log = f"printf '\\n=== SCRIPT STARTING at %s ===\\n' \"$(date)\" >> '{log_file_path}'"

        # Build the full command
        cmd_parts = []

        # Add Redis session start tracking first if provided
        if session_start_cmd:
            cmd_parts.append(session_start_cmd)

        # Add separator if needed
        if separator_cmd:
            cmd_parts.append(separator_cmd)

        # Add info block
        cmd_parts.append(info_cmd)

        # Add pre-script logging
        cmd_parts.append(pre_script_log)

        # Add the actual script execution with output redirection and proper error handling
        cmd_parts.append(f"({exec_cmd}) >> '{log_file_path}' 2>&1")
        cmd_parts.append("SCRIPT_EXIT_CODE=$?")

        # Add job completion marker (update to use variable)
        # Extract session name from log file path
        session_name = Path(log_file_path).stem
        if hasattr(self, "tmux_manager") and hasattr(self.tmux_manager, "get_job_completion_command"):
            completion_cmd = self.tmux_manager.get_job_completion_command(session_name, use_variable=True)
            cmd_parts.append(completion_cmd)
        else:
            # Fallback if tmux_manager not available
            cmd_parts.append(job_completion_cmd)

        # Join with semicolons after the main script execution to ensure subsequent commands run
        if len(cmd_parts) >= 3:
            # Everything up to and including script execution
            pre_execution = cmd_parts[:-4]  # Before script execution
            script_execution = cmd_parts[-4]  # The script execution
            post_execution = cmd_parts[-3:]  # Everything after script execution

            pre_cmd = " && ".join(pre_execution) if pre_execution else ""
            post_cmd = "; ".join(post_execution)  # Use semicolons so they run regardless

            if pre_cmd:
                return f"{pre_cmd} && {script_execution}; {post_cmd}"
            else:
                return f"{script_execution}; {post_cmd}"
        else:
            return " && ".join(cmd_parts)

    def schedule_launch(self):
        """Open a dialog to schedule the script launch at a specific date and time."""
        from datetime import datetime

        with ui.dialog() as schedule_dialog, ui.card():
            ui.label("Schedule Script Launch").style("font-size: 1.2em; font-weight: bold;")

            # Date and time inputs side by side
            with ui.row().style("gap: 16px; margin-bottom: 16px; align-items: flex-start;"):
                date_input = ui.date(value=datetime.now().strftime("%Y-%m-%d")).style("flex: 1; min-width: 150px;")
                time_input = ui.time(value=datetime.now().strftime("%H:%M")).style("flex: 1; min-width: 120px;")

            error_label = ui.label("").style("color: red;")

            # Buttons below the date/time inputs
            with ui.row().style("gap: 8px; justify-content: flex-end;"):
                ui.button("Cancel", on_click=schedule_dialog.close)
                ui.button(
                    "Schedule",
                    on_click=lambda: self.confirm_schedule(date_input, time_input, error_label, schedule_dialog),
                )
        schedule_dialog.open()

    def confirm_schedule(self, date_input, time_input, error_label, schedule_dialog):
        import shutil
        from datetime import datetime

        from desto.redis.client import DestoRedisClient  # noqa
        from desto.redis.desto_manager import DestoManager  # noqa
        from desto.redis.models import SessionStatus  # noqa

        date_val = date_input.value
        time_val = time_input.value
        session_name = self.session_name_input.value.strip() if hasattr(self, "session_name_input") else ""
        arguments = self.arguments_input.value if hasattr(self, "arguments_input") else "."

        if not date_val or not time_val or not session_name:
            error_label.text = "Please select date, time, and enter a session name in the Launch Script section."
            return
        try:
            scheduled_dt = datetime.strptime(f"{date_val} {time_val}", "%Y-%m-%d %H:%M")
            now = datetime.now()
            delta = (scheduled_dt - now).total_seconds()
            if delta < 0:
                error_label.text = "Scheduled time is in the past."
                return

            # Check if 'at' command is available
            if not shutil.which("at"):
                error_label.text = "'at' command is not available on this system. Please install 'at' to use scheduling."
                return

            # Format time for 'at' (e.g., 'HH:MM YYYY-MM-DD')
            at_time_str = scheduled_dt.strftime("%H:%M %Y-%m-%d")

            # Add Redis session with SCHEDULED status for scheduled scripts
            redis_client = DestoRedisClient()
            if redis_client.is_connected():
                manager = DestoManager(redis_client)
                if self.chain_queue:
                    manager.start_session_with_job(
                        session_name=session_name,
                        command=f"Chain: {len(self.chain_queue)} scripts",
                        script_path=f"Chain: {len(self.chain_queue)} scripts",
                        status=SessionStatus.SCHEDULED,
                    )
                else:
                    actual_filename = self.extract_script_filename(self.script_path_select.value)
                    script_file_path = self.tmux_manager.SCRIPTS_DIR / actual_filename
                    exec_cmd = self.build_execution_command(script_file_path, arguments)
                    manager.start_session_with_job(
                        session_name=session_name,
                        command=exec_cmd,
                        script_path=str(script_file_path),
                        status=SessionStatus.SCHEDULED,
                    )

            # Build the execution command(s) for the wrapper (no info block, no separator, no printf)
            if self.chain_queue:
                # Build a single shell command that runs all scripts in order, stopping on error
                commands = []
                script_paths = []
                for idx, (script, args) in enumerate(self.chain_queue):
                    exec_cmd = self.build_execution_command(script, args)
                    commands.append(exec_cmd)
                    script_paths.append(script)
                tmux_cmd = " && ".join(commands)
            else:
                actual_filename = self.extract_script_filename(self.script_path_select.value)
                script_file_path = self.tmux_manager.SCRIPTS_DIR / actual_filename
                exec_cmd = self.build_execution_command(script_file_path, arguments)
                tmux_cmd = exec_cmd
                script_paths = [str(script_file_path)]

            # Use the wrapper script for proper Redis tracking of scheduled jobs
            wrapper_script_path = Path(__file__).parent.parent.parent.parent / "scripts" / "start_scheduled_session.py"

            if wrapper_script_path.exists():
                scheduled_cmd = f"python3 '{wrapper_script_path}' {shlex.quote(session_name)} {shlex.quote(tmux_cmd)}"
            else:
                scheduled_cmd = f"tmux new-session -d -s {shlex.quote(session_name)} bash -c {shlex.quote(tmux_cmd)}"

            redis_client = DestoRedisClient()
            at_job_manager = AtJobManager(redis_client)

            # Call AtJobManager.schedule with all metadata fields
            job_id = at_job_manager.schedule(
                command=scheduled_cmd,
                time_spec=at_time_str,
                session_name=session_name,
                script_path=script_paths,  # Always a list
                arguments=arguments,
            )

            if job_id:
                if self.chain_queue:
                    ui.notification(
                        f"Chain scheduled for {scheduled_dt} as session '{session_name}' (Job ID: {job_id})",
                        type="info",
                    )
                    self.chain_queue.clear()
                    self.refresh_chain_queue_display()
                else:
                    ui.notification(
                        f"Script scheduled for {scheduled_dt} as session '{session_name}' (Job ID: {job_id})",
                        type="info",
                    )
                schedule_dialog.close()
            else:
                error_label.text = "Failed to schedule job via AtJobManager."

        except Exception as e:
            error_label.text = f"Invalid date/time: {e}"

    def refresh_chain_queue_display(self):
        """Update the chain queue display in the UI."""
        if not hasattr(self, "chain_queue_display") or not self.chain_queue_display:
            logger.warning("chain_queue_display is not set.")
            return
        self.chain_queue_display.clear()
        with self.chain_queue_display:
            if not self.chain_queue:
                ui.label("Chain queue is empty.")
            else:
                for idx, (script, args) in enumerate(self.chain_queue, 1):
                    ui.label(f"{idx}. {Path(script).name} {args}")

    def clear_chain_queue(self):
        """Clear all items from the chain queue."""
        if not self.chain_queue:
            ui.notification("Chain queue is already empty.", type="info")
            return

        queue_count = len(self.chain_queue)
        self.chain_queue.clear()
        self.refresh_chain_queue_display()
        ui.notification(f"Cleared {queue_count} item(s) from chain queue.", type="positive")
        logger.info(f"Chain queue cleared - removed {queue_count} items")
