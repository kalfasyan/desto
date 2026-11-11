import getpass
import os
import re
import socket
import time
from pathlib import Path

import psutil
from loguru import logger
from nicegui import ui

from .auth import logout
from .favorites_ui import FavoritesTab
from .schedule_ui import ScheduleLaunchMixin
from .sqlite_ui import SQLiteHistoryTab
from .ui_elements import LogSection, NewScriptTab, ScriptManagerTab, SettingsPanel, SystemStatsPanel


class UserInterfaceManager(ScheduleLaunchMixin):
    def __init__(self, ui, ui_settings, tmux_manager, desto_manager=None):
        from nicegui import ui as nicegui_ui

        self.nicegui_ui = nicegui_ui
        self._dark_mode = self.nicegui_ui.dark_mode()  # Create ONCE
        self.ui_settings = ui_settings
        self.ui = ui
        self.desto_manager = desto_manager
        self.tmux_manager = tmux_manager
        self.stats_panel = SystemStatsPanel(ui_settings)
        self.new_script_tab = NewScriptTab(tmux_manager, self)
        self.log_section = LogSection()
        self.script_manager_tab = ScriptManagerTab(self)
        self.favorites_tab = FavoritesTab(self, desto_manager) if desto_manager else None
        self.sqlite_history_tab = SQLiteHistoryTab(self, desto_manager) if desto_manager and getattr(desto_manager, "sqlite_store", None) and getattr(desto_manager.sqlite_store, "enabled", False) else None
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

    def build_ui(self, show_logout: bool = False):
        # Listener to update CodeMirror themes and body class for Tailwind
        def update_dark_mode_ui(v):
            if v:
                ui.query("body").classes(add="dark")
            else:
                ui.query("body").classes(remove="dark")
            if hasattr(self, "new_script_tab") and hasattr(self.new_script_tab, "code_editor") and self.new_script_tab.code_editor:
                self.new_script_tab.code_editor.theme = "vscodeDark" if v else "vscodeLight"
            if hasattr(self, "script_manager_tab") and hasattr(self.script_manager_tab, "script_preview_editor") and self.script_manager_tab.script_preview_editor:
                self.script_manager_tab.script_preview_editor.theme = "vscodeDark" if v else "vscodeLight"

        self._dark_mode.on_value_change(lambda e: update_dark_mode_ui(e.value))
        update_dark_mode_ui(self._dark_mode.value)

        # Header
        with ui.header(elevated=False).props("flat").classes("bg-white dark:!bg-slate-900 text-slate-900 dark:text-white border-b border-slate-200 dark:border-slate-800 px-6 py-4 items-center justify-between"):
            with ui.row().classes("items-center gap-4"):
                ui.button(on_click=lambda: left_drawer.toggle(), icon="menu").props("flat round color=primary")
                ui.label("desto").classes("text-2xl font-black tracking-tighter text-primary italic uppercase")

            with ui.row().classes("items-center gap-2"):
                ui.button(icon="dark_mode", on_click=lambda: self._dark_mode.toggle()).props("flat round color=primary")
                ui.button(on_click=lambda: right_drawer.toggle(), icon="settings").props("flat round color=primary")
                if show_logout:
                    ui.button(icon="logout", on_click=logout).props("flat round color=primary").tooltip("Log out")

        # Drawers
        with ui.left_drawer(value=True).classes("bg-slate-50 dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800 p-6") as left_drawer:
            self.stats_panel.build()

        with ui.right_drawer(value=False).classes("bg-slate-50 dark:bg-slate-900 border-l border-slate-200 dark:border-slate-800 p-6") as right_drawer:
            self.settings_panel = SettingsPanel(self.tmux_manager, self, right_drawer)
            self.settings_panel.build()

        # Main content area
        with ui.column().classes("w-full max-w-6xl mx-auto p-8 gap-8"):
            # Horizontal Tabs
            with ui.tabs().classes("w-full justify-start border-b border-slate-200 dark:border-slate-800") as tabs:
                scripts_tab = ui.tab("Scripts", icon="terminal")
                new_script_tab = ui.tab("New Script", icon="add")
                favorites_tab = ui.tab("Favorites", icon="star") if self.favorites_tab else None
                history_tab = ui.tab("Session History", icon="storage") if self.sqlite_history_tab else None

            with ui.tab_panels(tabs, value=scripts_tab).classes("w-full bg-transparent"):
                with ui.tab_panel(scripts_tab):
                    self.script_manager_tab.build()

                with ui.tab_panel(new_script_tab):
                    self.new_script_tab.build()

                if favorites_tab and self.favorites_tab:
                    with ui.tab_panel(favorites_tab):
                        self.favorites_tab.build()

                if history_tab and self.sqlite_history_tab:
                    with ui.tab_panel(history_tab):
                        self.sqlite_history_tab.build()

            # Chain Queue Section
            with ui.column().classes("w-full gap-4 mt-4"):
                with ui.row().classes("w-full justify-between items-end"):
                    ui.label("Chain Queue").classes("text-sm font-bold uppercase tracking-wider text-slate-500")
                    with ui.row().classes("gap-2"):
                        ui.button("Clear Chain", icon="clear_all", on_click=self.clear_chain_queue).props("flat color=warning dense")
                        ui.button("Kill All Sessions", icon="delete_forever", on_click=self.tmux_manager.confirm_kill_all_sessions).props("flat color=negative dense")

                self.chain_queue_display = ui.column().classes("modern-card w-full p-4 dark:!bg-slate-900 rounded-xl min-h-[60px] gap-2 border border-slate-100 dark:border-slate-800")
                self.refresh_chain_queue_display()

            self.log_section.build()

    def update_log_messages(self, message, number_of_lines=20):
        self.log_section.update_log_messages(message, number_of_lines)

    def refresh_log_display(self):
        self.log_section.refresh_log_display()

    def update_ui_system_info(self):
        """Update system stats in the UI."""
        cpu_percent = psutil.cpu_percent(interval=None)
        if self.stats_panel.cpu_percent is not None:
            self.stats_panel.cpu_percent.text = f"{cpu_percent:.1f}%"
        if self.stats_panel.cpu_bar is not None:
            self.stats_panel.cpu_bar.value = cpu_percent / 100

        # Update CPU cores if they're visible and initialized
        show_cores = getattr(self.stats_panel.show_cpu_cores, "value", False)
        if show_cores and self.stats_panel.cpu_core_labels and self.stats_panel.cpu_core_bars:
            try:
                core_percentages = psutil.cpu_percent(percpu=True, interval=None)
                for i, core_percent in enumerate(core_percentages):
                    if i < len(self.stats_panel.cpu_core_labels) and i < len(self.stats_panel.cpu_core_bars):
                        if self.stats_panel.cpu_core_labels[i] is not None:
                            self.stats_panel.cpu_core_labels[i].text = f"{core_percent:.1f}%"
                        if self.stats_panel.cpu_core_bars[i] is not None:
                            self.stats_panel.cpu_core_bars[i].value = core_percent / 100
            except Exception as e:
                logger.debug(f"Error updating CPU core data: {e}")

        memory = psutil.virtual_memory()
        if self.stats_panel.memory_percent is not None:
            self.stats_panel.memory_percent.text = f"{memory.percent}%"
        if self.stats_panel.memory_bar is not None:
            self.stats_panel.memory_bar.value = memory.percent / 100
        if self.stats_panel.memory_available is not None:
            self.stats_panel.memory_available.text = f"{round(memory.available / (1024**3), 2)} GB Available"
        if self.stats_panel.memory_used is not None:
            self.stats_panel.memory_used.text = f"{round(memory.used / (1024**3), 2)} GB Used"
        disk = psutil.disk_usage("/")
        if self.stats_panel.disk_percent is not None:
            self.stats_panel.disk_percent.text = f"{disk.percent}%"
        if self.stats_panel.disk_bar is not None:
            self.stats_panel.disk_bar.value = disk.percent / 100
        if self.stats_panel.disk_free is not None:
            self.stats_panel.disk_free.text = f"{round(disk.free / (1024**3), 2)} GB Free"
        if self.stats_panel.disk_used is not None:
            self.stats_panel.disk_used.text = f"{round(disk.used / (1024**3), 2)} GB Used"
        # --- tmux server stats ---
        # Reuse one psutil.Process so cpu_percent() is non-blocking (interval=None measures
        # since the previous call) instead of sleeping 100ms on every tick.
        tmux_cpu = "N/A"
        tmux_mem = "N/A"
        try:
            proc = self._get_tmux_server_proc()
            if proc is not None:
                tmux_cpu = f"{proc.cpu_percent(interval=None):.1f}%"
                tmux_mem = f"{proc.memory_info().rss / (1024 * 1024):.1f} MB"
        except Exception:
            self._tmux_server_proc = None
        if self.stats_panel.tmux_cpu is not None:
            self.stats_panel.tmux_cpu.text = f"tmux CPU: {tmux_cpu}"
        if self.stats_panel.tmux_mem is not None:
            self.stats_panel.tmux_mem.text = f"tmux MEM: {tmux_mem}"

    def _get_tmux_server_proc(self, rescan_interval: float = 10.0):
        """Return the cached tmux server process, re-scanning the process list at most every 10s."""
        proc = getattr(self, "_tmux_server_proc", None)
        if proc is not None and proc.is_running():
            return proc
        now = time.monotonic()
        if now - getattr(self, "_tmux_last_scan", 0.0) < rescan_interval:
            return None
        self._tmux_last_scan = now
        candidates = [p for p in psutil.process_iter(["name", "ppid"]) if "tmux" in (p.info["name"] or "")]
        if not candidates:
            self._tmux_server_proc = None
            return None
        proc = next((p for p in candidates if p.info["ppid"] == 1), None) or min(candidates, key=lambda p: p.info["ppid"])
        proc.cpu_percent(interval=None)  # prime the counter
        self._tmux_server_proc = proc
        return proc

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
        if self.script_preview_editor is not None:
            if script_path.is_file():
                with open(script_path, "r") as f:
                    content = f.read()
                    self.ignore_next_edit = True  # Ignore the next edit event
                    self.script_preview_editor.value = content

                    # Update syntax highlighting based on script type
                    script_type = self.get_script_type(actual_filename)
                    if hasattr(self.script_preview_editor, "language"):
                        if script_type == "python":
                            self.script_preview_editor.language = "python"
                        elif script_type == "bash":
                            self.script_preview_editor.language = "bash"
            else:
                self.ignore_next_edit = True
                self.script_preview_editor.value = "# Script not found."

    def confirm_delete_script(self):
        """Show a confirmation dialog and delete the selected script if confirmed."""
        selected_script = self.script_path_select.value if self.script_path_select is not None and hasattr(self.script_path_select, "value") else None
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
                if self.script_path_select is not None and hasattr(self.script_path_select, "value"):
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
        selected_script = self.script_path_select.value if self.script_path_select is not None and hasattr(self.script_path_select, "value") else None
        if not selected_script or selected_script == "No scripts found":
            ui.notification("No script selected to save.", type="warning")
            return
        actual_filename = self.extract_script_filename(selected_script)
        script_path = self.tmux_manager.SCRIPTS_DIR / actual_filename
        try:
            with script_path.open("w") as f:
                if self.script_preview_editor is not None and hasattr(self.script_preview_editor, "value"):
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
                        if self.script_preview_editor is not None and hasattr(self.script_preview_editor, "value"):
                            f.write(self.script_preview_editor.value)
                    os.chmod(new_script_path, 0o755)
                    self.refresh_script_list()
                    if self.script_path_select is not None:
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
        script_name = self.script_path_select.value if self.script_path_select is not None and hasattr(self.script_path_select, "value") else None
        arguments = self.arguments_input.value if self.arguments_input is not None and hasattr(self.arguments_input, "value") else ""
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

    def refresh_chain_queue_display(self):
        """Update the chain queue display in the UI."""
        if not hasattr(self, "chain_queue_display") or not self.chain_queue_display:
            logger.warning("chain_queue_display is not set.")
            return
        self.chain_queue_display.clear()
        with self.chain_queue_display:
            if not self.chain_queue:
                ui.label("Chain queue is empty.").classes("text-slate-400 italic text-sm")
            else:
                for idx, (script, args) in enumerate(self.chain_queue, 1):
                    with ui.row().classes("w-full items-center gap-2 p-2 rounded-lg bg-slate-50 dark:bg-slate-800"):
                        ui.label(str(idx)).classes("bg-primary text-white rounded-full w-5 h-5 text-[10px] flex items-center justify-center font-bold")
                        ui.label(Path(script).name).classes("font-semibold text-sm")
                        ui.label(args).classes("text-xs text-slate-500 truncate flex-grow")

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
