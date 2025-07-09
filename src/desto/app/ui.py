import getpass
import os
import re
import shlex
import socket
from pathlib import Path

import psutil
from loguru import logger
from nicegui import ui


class SystemStatsPanel:
    def __init__(self, ui_settings):
        self.ui_settings = ui_settings
        self.cpu_percent = None
        self.cpu_bar = None
        self.show_cpu_cores = None
        self.cpu_cores_container = None
        self.cpu_core_labels = []
        self.cpu_core_bars = []
        self.memory_percent = None
        self.memory_bar = None
        self.memory_available = None
        self.memory_used = None
        self.disk_percent = None
        self.disk_bar = None
        self.disk_free = None
        self.disk_used = None
        self.tmux_cpu = None
        self.tmux_mem = None

    def build(self):
        with ui.column():
            ui.label("System Stats").style(
                f"font-size: {self.ui_settings['labels']['title_font_size']}; "
                f"font-weight: {self.ui_settings['labels']['title_font_weight']}; "
                "margin-bottom: 10px;"
            )
            ui.label("CPU Usage (Average)").style(f"font-weight: {self.ui_settings['labels']['subtitle_font_weight']}; margin-top: 10px;")
            with ui.row().style("align-items: center"):
                ui.icon("memory", size="1.2rem")
                self.cpu_percent = ui.label("0%").style(f"font-size: {self.ui_settings['labels']['subtitle_font_size']}; margin-left: 5px;")
            self.cpu_bar = ui.linear_progress(value=0, size=self.ui_settings["progress_bar"]["size"], show_value=False)

            # CPU Cores toggle and container
            self.show_cpu_cores = ui.switch("Show CPU Cores", value=False).style("margin-top: 8px;")
            self.cpu_cores_container = ui.column().style("margin-top: 8px;")

            def toggle_cpu_cores_visibility(e):
                self.cpu_cores_container.visible = e.args[0]
                if e.args[0] and not self.cpu_core_labels:
                    # Initialize CPU cores display if not already done
                    self._initialize_cpu_cores()

            self.show_cpu_cores.on("update:model-value", toggle_cpu_cores_visibility)
            self.cpu_cores_container.visible = self.show_cpu_cores.value

            ui.label("Memory Usage").style(f"font-weight: {self.ui_settings['labels']['subtitle_font_weight']}; margin-top: 10px;")
            with ui.row().style("align-items: center"):
                ui.icon("developer_board", size="1.2rem")
                self.memory_percent = ui.label("0%").style(f"font-size: {self.ui_settings['labels']['subtitle_font_size']}; margin-left: 5px;")
            self.memory_bar = ui.linear_progress(value=0, size=self.ui_settings["progress_bar"]["size"], show_value=False)
            self.memory_used = ui.label("0 GB Used").style(
                f"font-size: {self.ui_settings['labels']['info_font_size']}; color: {self.ui_settings['labels']['info_color']};"
            )
            self.memory_available = ui.label("0 GB Available").style(
                f"font-size: {self.ui_settings['labels']['info_font_size']}; color: {self.ui_settings['labels']['info_color']};"
            )
            ui.label("Disk Usage").style(f"font-weight: {self.ui_settings['labels']['subtitle_font_weight']}; margin-top: 10px;")
            with ui.row().style("align-items: center"):
                ui.icon("storage", size="1.2rem")
                self.disk_percent = ui.label("0%").style(f"font-size: {self.ui_settings['labels']['subtitle_font_size']}; margin-left: 5px;")
            self.disk_bar = ui.linear_progress(value=0, size=self.ui_settings["progress_bar"]["size"], show_value=False)
            self.disk_used = ui.label("0 GB Used").style(
                f"font-size: {self.ui_settings['labels']['info_font_size']}; color: {self.ui_settings['labels']['info_color']};"
            )
            self.disk_free = ui.label("0 GB Free").style(
                f"font-size: {self.ui_settings['labels']['info_font_size']}; color: {self.ui_settings['labels']['info_color']};"
            )
            self.tmux_cpu = ui.label("tmux CPU: N/A").style(
                f"font-size: {self.ui_settings['labels']['info_font_size']}; color: #888; margin-top: 20px;"
            )
            self.tmux_mem = ui.label("tmux MEM: N/A").style(f"font-size: {self.ui_settings['labels']['info_font_size']}; color: #888;")

    def _initialize_cpu_cores(self):
        """Initialize the CPU cores display."""
        cpu_count = psutil.cpu_count()
        max_cols = self.ui_settings.get("cpu_cores", {}).get("max_columns", 4)

        with self.cpu_cores_container:
            ui.label("CPU Cores").style(f"font-weight: {self.ui_settings['labels']['subtitle_font_weight']}; margin-bottom: 8px;")

            # Create cores in rows based on max_columns
            for i in range(0, cpu_count, max_cols):
                with ui.row().style("gap: 12px; margin-bottom: 4px;"):
                    for core_idx in range(i, min(i + max_cols, cpu_count)):
                        with ui.column().style("align-items: center; min-width: 60px;"):
                            core_label = ui.label(f"Core {core_idx}").style(
                                f"font-size: {self.ui_settings.get('cpu_cores', {}).get('core_label_size', '0.9em')}; "
                                "text-align: center; margin-bottom: 2px;"
                            )
                            core_percent = ui.label("0%").style(
                                f"font-size: {self.ui_settings.get('cpu_cores', {}).get('core_label_size', '0.9em')}; "
                                "text-align: center; margin-bottom: 2px;"
                            )
                            core_bar = ui.linear_progress(value=0, size="xs", show_value=False).style(
                                f"height: {self.ui_settings.get('cpu_cores', {}).get('bar_height', '6px')};"
                            )

                            self.cpu_core_labels.append((core_label, core_percent))
                            self.cpu_core_bars.append(core_bar)


class SettingsPanel:
    def __init__(self, tmux_manager, ui_manager=None):
        self.tmux_manager = tmux_manager
        self.ui_manager = ui_manager
        self.scripts_dir_input = None
        self.logs_dir_input = None

    def build(self):
        ui.label("Settings").style("font-size: 1.5em; font-weight: bold; margin-bottom: 20px; text-align: center;")
        self.scripts_dir_input = ui.input(
            label="Scripts Directory",
            value=str(self.tmux_manager.SCRIPTS_DIR),
        ).style("width: 100%; margin-bottom: 10px;")
        self.logs_dir_input = ui.input(
            label="Logs Directory",
            value=str(self.tmux_manager.LOG_DIR),
        ).style("width: 100%; margin-bottom: 10px;")
        ui.button("Save", on_click=self.save_settings).style("width: 100%; margin-top: 10px;")

    def save_settings(self):
        scripts_dir = Path(self.scripts_dir_input.value).expanduser()
        logs_dir = Path(self.logs_dir_input.value).expanduser()
        valid = True
        if not scripts_dir.is_dir():
            ui.notification("Invalid scripts directory.", type="warning")
            self.scripts_dir_input.value = str(self.tmux_manager.SCRIPTS_DIR)
            valid = False
        if not logs_dir.is_dir():
            ui.notification("Invalid logs directory.", type="warning")
            self.logs_dir_input.value = str(self.tmux_manager.LOG_DIR)
            valid = False
        if valid:
            self.tmux_manager.SCRIPTS_DIR = scripts_dir
            self.tmux_manager.LOG_DIR = logs_dir
            ui.notification("Directories updated.", type="positive")
            if self.ui_manager:
                self.ui_manager.refresh_script_list()


class NewScriptPanel:
    def __init__(self, tmux_manager, ui_manager=None):
        self.tmux_manager = tmux_manager
        self.ui_manager = ui_manager
        self.script_type = {"value": "bash"}
        self.custom_code = {"value": "#!/bin/bash\n\n# Your bash script here\necho 'Hello from desto!'\n"}
        self.custom_template_name_input = None
        self.code_editor = None

    def build(self):
        # Script type selector
        ui.select(
            ["bash", "python"],
            label="Script Type",
            value="bash",
            on_change=self.on_script_type_change,
        ).style("width: 100%; margin-bottom: 10px;")

        self.code_editor = (
            ui.codemirror(
                self.custom_code["value"],
                language="bash",
                theme="vscodeLight",
                on_change=lambda e: self.custom_code.update({"value": e.value}),
            )
            .style("width: 100%; font-family: monospace; background: #f5f5f5; color: #222; border-radius: 6px;")
            .classes("h-48")
        )
        ui.select(self.code_editor.supported_themes, label="Theme").classes("w-32").bind_value(self.code_editor, "theme")
        self.custom_template_name_input = ui.input(
            label="Save Script As... (max 15 chars)",
            placeholder="MyScript",
            validation={"Too long!": lambda value: len(value) <= 15},
        ).style("width: 100%; margin-bottom: 8px;")
        ui.button(
            "Save",
            on_click=self.save_custom_script,
        ).style("width: 28%; margin-bottom: 8px;")

    def on_script_type_change(self, e):
        """Handle script type selection change."""
        script_type = e.value
        self.script_type["value"] = script_type

        if script_type == "python":
            self.custom_code["value"] = "#!/usr/bin/env python3\n\n# Your Python code here\nprint('Hello from desto!')\n"
            self.code_editor.language = "python"
        else:  # bash
            self.custom_code["value"] = "#!/bin/bash\n\n# Your bash script here\necho 'Hello from desto!'\n"
            self.code_editor.language = "bash"

        self.code_editor.value = self.custom_code["value"]

    def save_custom_script(self):
        name = self.custom_template_name_input.value.strip()
        if not name or len(name) > 15:
            ui.notification("Please enter a name up to 15 characters.", type="info")
            return
        safe_name = name.strip().replace(" ", "_")[:15]
        code = self.custom_code["value"]
        script_type = self.script_type["value"]

        # Determine file extension and default shebang
        if script_type == "python":
            extension = ".py"
            default_shebang = "#!/usr/bin/env python3\n"
        else:  # bash
            extension = ".sh"
            default_shebang = "#!/bin/bash\n"

        # Add shebang if missing
        if not code.startswith("#!"):
            code = default_shebang + code

        script_path = self.tmux_manager.get_script_file(f"{safe_name}{extension}")
        try:
            with script_path.open("w") as f:
                f.write(code)
            os.chmod(script_path, 0o755)
            msg = f"Script '{name}' saved to {script_path}."
            logger.info(msg)
            ui.notification(msg, type="positive")
        except Exception as e:
            msg = f"Failed to save script: {e}"
            logger.error(msg)
            ui.notification(msg, type="warning")

        if self.ui_manager:
            self.ui_manager.refresh_script_list()
            # Select the new script in the scripts tab and update the preview
            script_filename = f"{safe_name}{extension}"
            if hasattr(self.ui_manager, "script_path_select"):
                self.ui_manager.script_path_select.value = script_filename
                self.ui_manager.update_script_preview(type("E", (), {"args": script_filename})())

        ui.notification(f"Script '{name}' saved and available in Scripts.", type="positive")


class LogPanel:
    def __init__(self):
        self.log_display = None
        self.log_messages = []

    def build(self):
        show_logs = ui.switch("Show Logs", value=True).style("margin-bottom: 10px;")
        log_card = ui.card().style("background-color: #fff; color: #000; padding: 20px; border-radius: 8px; width: 100%;")
        with log_card:
            ui.label("Log Messages").style("font-size: 1.5em; font-weight: bold; margin-bottom: 20px; text-align: center;")
            self.log_display = (
                ui.textarea("")
                .style("width: 600px; height: 100%; background-color: #fff; color: #000; border: 1px solid #ccc; font-family: monospace;")
                .props("readonly")
            )

        def toggle_log_card_visibility(value):
            if value:
                log_card.style("opacity: 1; pointer-events: auto;")
            else:
                log_card.style("opacity: 0; pointer-events: none;")

        show_logs.on("update:model-value", lambda e: toggle_log_card_visibility(e.args[0]))
        log_card.visible = show_logs.value

    def update_log_messages(self, message, number_of_lines=20):
        self.log_messages.append(message)

        if len(self.log_messages) > number_of_lines:
            self.log_messages.pop(0)

    def refresh_log_display(self):
        self.log_display.value = "\n".join(self.log_messages)


class UserInterfaceManager:
    def __init__(self, ui, ui_settings, tmux_manager):
        self.ui_settings = ui_settings
        self.ui = ui
        self.tmux_manager = tmux_manager
        self.stats_panel = SystemStatsPanel(ui_settings)
        self.new_script_panel = NewScriptPanel(tmux_manager, self)
        self.log_panel = LogPanel()
        self.script_path_select = None  # Reference to the script select component
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
        with (
            ui.header(elevated=True)
            .style(f"background-color: {self.ui_settings['header']['background_color']}; color: {self.ui_settings['header']['color']};")
            .classes(replace="row items-center justify-between")
        ):
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
                with splitter.after:
                    with ui.tab_panels(tabs, value=scripts_tab).props("vertical").classes("w-full"):
                        with ui.tab_panel(scripts_tab):
                            with ui.card().style(
                                "background-color: #fff; color: #000; padding: 20px; "
                                "border-radius: 8px; width: 100%; margin-left: 0; margin-right: 0;"
                            ):
                                # Place Session Name, Script, and Arguments side by side
                                with ui.row().style("width: 100%; gap: 10px; margin-bottom: 10px;"):
                                    self.session_name_input = ui.input(label="Session Name").style("width: 30%; color: #75a8db;")
                                    script_files = self.get_script_files()
                                    self.script_path_select = ui.select(
                                        options=script_files if script_files else ["No scripts found"],
                                        label="Script",
                                        value=script_files[0] if script_files else "No scripts found",
                                    ).style("width: 35%;")
                                    self.script_path_select.on("update:model-value", self.update_script_preview)
                                    self.arguments_input = ui.input(
                                        label="Arguments",
                                        value=".",
                                    ).style("width: 35%;")

                                script_preview_content = ""
                                if script_files and (self.tmux_manager.SCRIPTS_DIR / script_files[0]).is_file():
                                    with open(
                                        self.tmux_manager.SCRIPTS_DIR / script_files[0],
                                        "r",
                                    ) as f:
                                        script_preview_content = f.read()

                                # Track if the script was edited
                                script_edited = {"changed": False}

                                def on_script_edit(e):
                                    if not self.ignore_next_edit:
                                        script_edited["changed"] = True
                                    else:
                                        self.ignore_next_edit = False  # Reset after ignoring

                                # Place code editor and theme selection side by side
                                with ui.row().style("width: 100%; gap: 10px; margin-bottom: 10px;"):
                                    self.script_preview_editor = (
                                        ui.codemirror(
                                            script_preview_content,
                                            language="bash",
                                            theme="vscodeLight",
                                            line_wrapping=True,
                                            highlight_whitespace=True,
                                            indent="    ",
                                            on_change=on_script_edit,
                                        )
                                        .style("width: 80%; min-width: 300px; margin-top: 0px;")
                                        .classes("h-48")
                                    )
                                    ui.select(
                                        self.script_preview_editor.supported_themes,
                                        label="Theme",
                                    ).classes("w-32").bind_value(self.script_preview_editor, "theme")

                                # Save/Save as/Delete Buttons
                                with ui.row().style("gap: 10px; margin-top: 10px;"):
                                    ui.button(
                                        "Save",
                                        on_click=lambda: self.save_current_script(script_edited),
                                        color="primary",
                                        icon="save",
                                    )
                                    ui.button(
                                        "Save as",
                                        on_click=self.save_as_new_dialog,
                                        color="secondary",
                                        icon="save",
                                    )
                                    ui.button(
                                        "DELETE",
                                        color="red",
                                        on_click=lambda: self.confirm_delete_script(),
                                        icon="delete",
                                    )

                                # Keep Alive switch
                                self.keep_alive_switch_new = ui.switch("Keep Alive").style("margin-top: 10px;")

                                # Launch logic: warn if unsaved changes
                                async def launch_with_save_check():
                                    if script_edited["changed"]:
                                        ui.notification(
                                            "You have unsaved changes. Please save before launching or use 'Save as New'.",
                                            type="warning",
                                        )
                                        return
                                    # If there are scripts in the chain queue, launch the chain
                                    if self.chain_queue:
                                        await self.run_chain_queue(
                                            self.session_name_input.value,
                                            self.arguments_input.value,
                                            self.keep_alive_switch_new.value,
                                        )
                                        self.chain_queue.clear()
                                    else:
                                        await self.run_session_with_keep_alive(
                                            self.session_name_input.value,
                                            str(self.tmux_manager.SCRIPTS_DIR / self.extract_script_filename(self.script_path_select.value)),
                                            self.arguments_input.value,
                                            self.keep_alive_switch_new.value,
                                        )

                                with ui.row().style("width: 100%; gap: 10px; margin-top: 10px;"):
                                    ui.button(
                                        "Launch",
                                        on_click=launch_with_save_check,  # Pass the async function directly
                                        icon="rocket_launch",
                                    )
                                    ui.button(
                                        "Schedule",
                                        color="secondary",
                                        icon="history",
                                        on_click=lambda: self.schedule_launch(),
                                    )
                                    ui.button(
                                        "Chain Script",
                                        color="secondary",
                                        on_click=self.chain_current_script,
                                        icon="add_link",
                                    )

                        with ui.tab_panel(new_script_tab):
                            with ui.card().style(
                                "background-color: #fff; color: #000; padding: 20px; border-radius: 8px; width: 100%; margin-left: 0;"
                            ):
                                self.new_script_panel.build()
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

            self.log_panel.build()

    def update_log_messages(self, message, number_of_lines=20):
        self.log_panel.update_log_messages(message, number_of_lines)

    def refresh_log_display(self):
        self.log_panel.refresh_log_display()

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
                for i, (core_percent, core_bar) in enumerate(zip(core_percentages, self.stats_panel.cpu_core_bars)):
                    if i < len(self.stats_panel.cpu_core_labels):
                        _, percent_label = self.stats_panel.cpu_core_labels[i]
                        percent_label.text = f"{core_percent:.1f}%"
                        core_bar.value = core_percent / 100
            except Exception:
                # If there's an error getting per-core data, just skip the update
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
            tmux_procs = [
                p
                for p in psutil.process_iter(["name", "ppid", "cpu_percent", "memory_info", "cmdline"])
                if p.info["name"] == "tmux" or "tmux" in p.info["name"]
            ]
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

    async def run_session_with_keep_alive(self, session_name, script_path, arguments, keep_alive):
        # Build the basic execution command - TmuxManager will handle all logging
        exec_cmd = self.build_execution_command(script_path, arguments)

        self.tmux_manager.start_tmux_session(session_name, exec_cmd, logger, keep_alive)
        ui.notification(f"Started session '{session_name}'.", type="positive")

    async def run_chain_queue(self, session_name, arguments, keep_alive):
        if not self.chain_queue:
            ui.notification("Chain queue is empty.", type="warning")
            return

        session_name = session_name.strip() or f"chain_{os.getpid()}"

        # Build a single command that runs all scripts in sequence
        chain_commands = []
        for script, args in self.chain_queue:
            script_name = Path(script).name
            exec_cmd = self.build_execution_command(script, args)
            # Add a separator echo before each script
            chain_commands.append(f"echo '---- Running {script_name} ----'")
            chain_commands.append(exec_cmd)

        # Join all commands with &&
        full_chain_cmd = " && ".join(chain_commands)

        self.tmux_manager.start_tmux_session(session_name, full_chain_cmd, logger, keep_alive)
        ui.notification(f"Started chained session '{session_name}'.", type="positive")
        self.chain_queue.clear()
        self.refresh_chain_queue_display()

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
        return "\\n".join(info_lines)

    def build_logging_command(self, log_file_path, info_block, exec_cmd, finished_marker_cmd, keep_alive=False):
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

        # Add post-script logging
        post_script_log = f"printf '\\n=== SCRIPT FINISHED at %s ===\\n' \"$(date)\" >> '{log_file_path}'"

        # Build the full command
        cmd_parts = []

        # Add separator if needed
        if separator_cmd:
            cmd_parts.append(separator_cmd)

        # Add info block
        cmd_parts.append(info_cmd)

        # Add pre-script logging
        cmd_parts.append(pre_script_log)

        # Add the actual script execution with output redirection
        # FIXED: Group the execution command in parentheses to ensure ALL output gets redirected
        # This fixes the issue where only the last command in a chain gets logged
        cmd_parts.append(f"({exec_cmd}) >> '{log_file_path}' 2>&1")

        # Add post-script logging
        cmd_parts.append(post_script_log)

        # Add finished marker
        cmd_parts.append(finished_marker_cmd)

        # Add keep-alive if requested
        if keep_alive:
            cmd_parts.append(f"tail -f /dev/null >> '{log_file_path}' 2>&1")

        return " && ".join(cmd_parts)

    async def run_session_with_save_check(self, session_name, script_path, arguments, keep_alive):
        # Build the basic execution command - TmuxManager will handle all logging
        exec_cmd = self.build_execution_command(script_path, arguments)

        self.tmux_manager.start_tmux_session(session_name, exec_cmd, logger, keep_alive)
        ui.notification(f"Scheduled session '{session_name}' started.", type="positive")

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

        date_val = date_input.value
        time_val = time_input.value
        session_name = self.session_name_input.value.strip() if hasattr(self, "session_name_input") else ""
        arguments = self.arguments_input.value if hasattr(self, "arguments_input") else "."
        keep_alive = self.keep_alive_switch_new.value if hasattr(self, "keep_alive_switch_new") else False

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

            # If chain queue is not empty, schedule the chain
            if self.chain_queue:
                log_file_path = self.tmux_manager.LOG_DIR / f"{session_name}.log"
                info_block = self.get_log_info_block(self.chain_queue[0][0], session_name, scheduled_dt)
                finished_marker_cmd = f"touch '{self.tmux_manager.LOG_DIR}/{session_name}.finished'"

                # Build the chain command with proper logging
                cmd_parts = []

                # Check if log file exists to determine if we should append or create new
                append_mode = Path(log_file_path).exists()

                # Add initial info block using printf for better compatibility
                if append_mode:
                    cmd_parts.append(f"printf '\\n---- NEW SESSION (%s) -----\\n' \"$(date '+%Y-%m-%d %H:%M:%S')\" >> '{log_file_path}'")
                    cmd_parts.append(f"printf '%s\\n' {repr(info_block)} >> '{log_file_path}'")
                else:
                    cmd_parts.append(f"printf '%s\\n' {repr(info_block)} > '{log_file_path}'")

                # Add each script in the chain with proper logging
                for idx, (script, args) in enumerate(self.chain_queue):
                    script_name = Path(script).name
                    # Add separator for each script
                    separator = f"printf '\\n---- NEW SCRIPT (%s) -----\\n' '{script_name}' >> '{log_file_path}'"
                    # Add pre-script logging
                    pre_script_log = f"printf '\\n=== SCRIPT STARTING at %s ===\\n' \"$(date)\" >> '{log_file_path}'"
                    # Build execution command
                    exec_cmd = self.build_execution_command(script, args)
                    # FIXED: Group execution command to ensure proper logging
                    run_script = f"({exec_cmd}) >> '{log_file_path}' 2>&1"
                    # Add post-script logging using printf for consistency
                    post_script_log = f"printf '\\n=== SCRIPT FINISHED at %s ===\\n' \"$(date)\" >> '{log_file_path}'"

                    cmd_parts.extend([separator, pre_script_log, run_script, post_script_log])

                # Add finished marker
                cmd_parts.append(finished_marker_cmd)

                # Add keep-alive if requested
                if keep_alive:
                    cmd_parts.append(f"tail -f /dev/null >> '{log_file_path}' 2>&1")

                # Join all parts with &&
                tmux_cmd = " && ".join(cmd_parts)
                tmux_new_session_cmd = f"tmux new-session -d -s {shlex.quote(session_name)} bash -c {shlex.quote(tmux_cmd)}"
                # Schedule with 'at'
                at_shell_cmd = f"echo {shlex.quote(tmux_new_session_cmd)} | at {shlex.quote(at_time_str)}"
                import subprocess

                result = subprocess.run(
                    at_shell_cmd,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                if result.returncode == 0:
                    ui.notification(
                        f"Chain scheduled for {scheduled_dt} as session '{session_name}'",
                        type="info",
                    )
                    self.chain_queue.clear()
                    self.refresh_chain_queue_display()
                    schedule_dialog.close()
                else:
                    error_label.text = f"Failed to schedule: {result.stderr}"
                return

            # Otherwise, schedule a single script as before
            actual_filename = self.extract_script_filename(self.script_path_select.value)
            script_file_path = self.tmux_manager.SCRIPTS_DIR / actual_filename
            log_file_path = self.tmux_manager.LOG_DIR / f"{session_name}.log"
            info_block = self.get_log_info_block(script_file_path, session_name, scheduled_dt)
            finished_marker_cmd = f"touch '{self.tmux_manager.LOG_DIR}/{session_name}.finished'"
            exec_cmd = self.build_execution_command(script_file_path, arguments)

            # Use the new logging command builder
            tmux_cmd = self.build_logging_command(log_file_path, info_block, exec_cmd, finished_marker_cmd, keep_alive=True)
            tmux_new_session_cmd = f"tmux new-session -d -s {shlex.quote(session_name)} bash -c {shlex.quote(tmux_cmd)}"
            at_shell_cmd = f"echo {shlex.quote(tmux_new_session_cmd)} | at {shlex.quote(at_time_str)}"
            import subprocess

            result = subprocess.run(
                at_shell_cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if result.returncode == 0:
                ui.notification(
                    f"Script scheduled for {scheduled_dt} as session '{session_name}'",
                    type="info",
                )
                schedule_dialog.close()
            else:
                error_label.text = f"Failed to schedule: {result.stderr}"
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
