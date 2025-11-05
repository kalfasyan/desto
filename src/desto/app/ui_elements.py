import json
import os
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
            ui.label("System Stats").style(f"font-size: {self.ui_settings['labels']['title_font_size']}; font-weight: {self.ui_settings['labels']['title_font_weight']}; margin-bottom: 10px;")
            ui.label("CPU Usage (Average)").style(f"font-weight: {self.ui_settings['labels']['subtitle_font_weight']}; margin-top: 10px;")
            with ui.row().style("align-items: center"):
                ui.icon("memory", size="1.2rem")
                self.cpu_percent = ui.label("0%").style(f"font-size: {self.ui_settings['labels']['subtitle_font_size']}; margin-left: 5px;")
            self.cpu_bar = ui.linear_progress(value=0, size=self.ui_settings["progress_bar"]["size"], show_value=False)

            # CPU Details toggle and container
            core_info = "Show CPU details"
            self.show_cpu_cores = ui.switch(core_info, value=False).style("margin-top: 8px;")
            self.cpu_cores_container = ui.column().style("margin-top: 8px; min-height: 50px; border: 1px solid #ddd; padding: 8px; border-radius: 4px;")

            def toggle_cpu_cores_visibility(e):
                # Access the switch value directly after the event
                new_value = self.show_cpu_cores.value
                logger.debug(f"CPU cores toggle: new_value={new_value}")
                logger.debug(f"Container visible before: {self.cpu_cores_container.visible}")
                self.cpu_cores_container.visible = new_value
                logger.debug(f"Container visible after: {self.cpu_cores_container.visible}")
                if new_value and not self.cpu_core_labels:
                    logger.debug("Calling _initialize_cpu_cores because new_value=True and cpu_core_labels is empty")
                    self._initialize_cpu_cores()
                elif new_value and self.cpu_core_labels:
                    logger.debug(f"CPU cores already initialized, have {len(self.cpu_core_labels)} labels")

            self.show_cpu_cores.on("update:model-value", toggle_cpu_cores_visibility)
            # Set initial visibility to match switch value
            self.cpu_cores_container.visible = False

            ui.label("Memory Usage").style(f"font-weight: {self.ui_settings['labels']['subtitle_font_weight']}; margin-top: 10px;")
            with ui.row().style("align-items: center"):
                ui.icon("memory", size="1.2rem")
                self.memory_percent = ui.label("0%").style(f"font-size: {self.ui_settings['labels']['subtitle_font_size']}; margin-left: 5px;")
            self.memory_bar = ui.linear_progress(value=0, size=self.ui_settings["progress_bar"]["size"], show_value=False)
            self.memory_used = ui.label("0 GB Used").style(f"font-size: {self.ui_settings['labels']['info_font_size']}; color: {self.ui_settings['labels']['info_color']};")
            self.memory_available = ui.label("0 GB Available").style(f"font-size: {self.ui_settings['labels']['info_font_size']}; color: {self.ui_settings['labels']['info_color']};")
            ui.label("Disk Usage").style(f"font-weight: {self.ui_settings['labels']['subtitle_font_weight']}; margin-top: 10px;")
            with ui.row().style("align-items: center"):
                ui.icon("storage", size="1.2rem")
                self.disk_percent = ui.label("0%").style(f"font-size: {self.ui_settings['labels']['subtitle_font_size']}; margin-left: 5px;")
            self.disk_bar = ui.linear_progress(value=0, size=self.ui_settings["progress_bar"]["size"], show_value=False)
            self.disk_used = ui.label("0 GB Used").style(f"font-size: {self.ui_settings['labels']['info_font_size']}; color: {self.ui_settings['labels']['info_color']};")
            self.disk_free = ui.label("0 GB Free").style(f"font-size: {self.ui_settings['labels']['info_font_size']}; color: {self.ui_settings['labels']['info_color']};")
            self.tmux_cpu = ui.label("tmux CPU: N/A").style(f"font-size: {self.ui_settings['labels']['info_font_size']}; color: #888; margin-top: 20px;")
            self.tmux_mem = ui.label("tmux MEM: N/A").style(f"font-size: {self.ui_settings['labels']['info_font_size']}; color: #888;")

    def _initialize_cpu_cores(self):
        """Initialize the CPU cores display."""
        logger.debug("Initializing CPU cores display")
        logical_cores = psutil.cpu_count(logical=True)
        physical_cores = psutil.cpu_count(logical=False)
        max_cols = self.ui_settings.get("cpu_cores", {}).get("max_columns", 4)

        logger.debug(f"CPU cores: {logical_cores} logical, {physical_cores} physical, max_cols: {max_cols}")

        with self.cpu_cores_container:
            ui.label(f"CPU Details ({logical_cores} threads on {physical_cores} cores)").style(f"font-weight: {self.ui_settings['labels']['subtitle_font_weight']}; margin-bottom: 8px;")

            # Create cores in rows based on max_columns
            for i in range(0, logical_cores, max_cols):
                with ui.row().style("gap: 8px; margin-bottom: 4px;"):
                    for j in range(i, min(i + max_cols, logical_cores)):
                        core_column = ui.column().style("align-items: center; min-width: 60px;")
                        with core_column:
                            # Label each thread as T0, T1, etc.
                            ui.label(f"T{j}").style("font-size: 0.8em; margin-bottom: 2px;")
                            core_percent = ui.label("0%").style("font-size: 0.75em; font-weight: bold;")
                            core_bar = ui.linear_progress(value=0, size="sm", show_value=False).style("width: 50px; height: 4px;")

                        self.cpu_core_labels.append(core_percent)
                        self.cpu_core_bars.append(core_bar)

        logger.debug(f"Created {len(self.cpu_core_labels)} CPU core labels and {len(self.cpu_core_bars)} progress bars")


class SettingsPanel:
    def __init__(self, tmux_manager, ui_manager=None):
        self.tmux_manager = tmux_manager
        self.ui_manager = ui_manager
        self.scripts_dir_input = None
        self.logs_dir_input = None
        self.pushbullet_input = None
        # load persisted config
        self._config_path = Path.home() / ".desto_config.json"
        self._load_config()

    def _load_config(self):
        try:
            if self._config_path.exists():
                data = json.loads(self._config_path.read_text())
                api_key = data.get("pushbullet_api_key")
                if api_key:
                    # store on tmux_manager for runtime access
                    setattr(self.tmux_manager, "pushbullet_api_key", api_key)
        except Exception:
            logger.debug("Failed to load persisted config", exc_info=True)

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
        # Pushbullet API key input (masked by default)
        existing_key = getattr(self.tmux_manager, "pushbullet_api_key", os.environ.get("DESTO_PUSHBULLET_API_KEY", ""))
        # Use password=True to mask the input; allow toggle so user can reveal if needed; disable autocomplete
        self.pushbullet_input = ui.input(
            label="Pushbullet API Key",
            value=existing_key,
            password=True,
            password_toggle_button=True,
            autocomplete=[],
        ).style("width: 100%; margin-bottom: 10px;")
        ui.button("Save", on_click=self.save_settings).style("width: 100%; margin-top: 10px;")

        # Send test push button
        def _send_test_push():
            try:
                # persist current key temporarily to tmux_manager so notifier can pick it up
                api_key = self.pushbullet_input.value.strip()
                setattr(self.tmux_manager, "pushbullet_api_key", api_key)
                from desto.notifications import PushbulletNotifier

                notifier = PushbulletNotifier(api_key=api_key)
                # Send a small test push and show the response
                title = "Desto Test Push"
                body = f"Test push from Desto at {datetime.utcnow().isoformat()}Z"
                resp = notifier.notify_with_response(title=title, body=body)
                # Display the result in a notification and in a small dialog
                if resp.get("ok"):
                    ui.notification("Test push sent successfully.", type="positive")
                else:
                    ui.notification(f"Test push failed: {resp.get('status_code')} {resp.get('body')}", type="negative")
                # Show details in a dialog for easier copy/paste
                with ui.dialog() as d, ui.card():
                    ui.label("Push response details").style("font-weight: bold; margin-bottom: 8px;")
                    ui.textarea(json.dumps(resp, indent=2)).props("readonly").style("width: 600px; height: 200px;")
                    ui.button("Close", on_click=lambda: d.close()).style("margin-top: 8px;")
                d.open()
            except Exception as e:
                logger.exception("Failed to send test push", exc_info=True)
                ui.notification(f"Exception sending test push: {e}", type="negative")

        # import datetime locally to avoid top-level import
        from datetime import datetime

        ui.button("Send test push", on_click=_send_test_push).style("width: 100%; margin-top: 8px;")

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
            # persist pushbullet key
            try:
                api_key = self.pushbullet_input.value.strip()
                setattr(self.tmux_manager, "pushbullet_api_key", api_key)
                # write config
                cfg = {"pushbullet_api_key": api_key}
                self._config_path.write_text(json.dumps(cfg))
            except Exception:
                logger.debug("Failed to persist config", exc_info=True)
            ui.notification("Directories updated.", type="positive")
            if self.ui_manager:
                self.ui_manager.refresh_script_list()


class NewScriptTab:
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

        ui.notification(f"Script '{name}' saved and available in Scripts.", type="positive")


class LogSection:
    def __init__(self):
        self.log_display = None
        self.log_messages = []

    def build(self):
        show_logs = ui.switch("Show Logs", value=True).style("margin-bottom: 10px;")
        log_card = ui.card().style("background-color: #fff; color: #000; padding: 20px; border-radius: 8px; width: 100%;")
        with log_card:
            ui.label("Log Messages").style("font-size: 1.5em; font-weight: bold; margin-bottom: 20px; text-align: center;")
            self.log_display = ui.textarea("").style("width: 600px; height: 100%; background-color: #fff; color: #000; border: 1px solid #ccc; font-family: monospace;").props("readonly")

        def toggle_log_card_visibility(value):
            if value:
                log_card.visible = True
            else:
                log_card.visible = False

        show_logs.on("update:model-value", lambda e: toggle_log_card_visibility(e.args[0]))
        log_card.visible = show_logs.value

    def update_log_messages(self, message, number_of_lines=20):
        self.log_messages.append(message)

        if len(self.log_messages) > number_of_lines:
            self.log_messages.pop(0)

    def refresh_log_display(self):
        self.log_display.value = "\n".join(self.log_messages)


class ScriptManagerTab:
    def __init__(self, ui_manager):
        self.ui_manager = ui_manager
        self.session_name_input = None
        self.script_path_select = None
        self.arguments_input = None
        self.script_preview_editor = None
        self.script_edited = {"changed": False}

    async def _launch_single_script(self, session_name, selected_script, arguments):
        if not session_name or not selected_script or selected_script == "No scripts found":
            ui.notification("Please enter a session name and select a script.", type="warning")
            return
        actual_filename = self.ui_manager.extract_script_filename(selected_script)
        script_path = self.ui_manager.tmux_manager.SCRIPTS_DIR / actual_filename
        if not script_path.is_file():
            ui.notification(f"Script file not found: {actual_filename}", type="warning")
            return
        exec_cmd = self.ui_manager.build_execution_command(script_path, arguments)

        # Only write a visible script start marker to the log for immediate launches
        script_marker = f"echo '=== Running script: {script_path.name} ==='"
        try:
            full_cmd = f"{script_marker} && ({exec_cmd})"
            self.ui_manager.tmux_manager.start_tmux_session(session_name, full_cmd, logger)
            ui.notification(f"Launched session '{session_name}' for script '{actual_filename}'", type="positive")
        except Exception as e:
            logger.error(f"Failed to launch session: {e}")
            ui.notification(f"Failed to launch session: {e}", type="negative")

    async def _launch_chained_scripts(self, session_name):
        if not session_name:
            ui.notification("Please enter a session name for the chain.", type="warning")
            return
        chain = self.ui_manager.chain_queue
        if not chain:
            ui.notification("Chain queue is empty.", type="warning")
            return
        # Build a single shell command that runs all scripts in order, stopping on error
        commands = []
        try:
            total_scripts = len(chain)
            for idx, (script_path, arguments) in enumerate(chain):
                script_path_obj = Path(script_path)
                if not script_path_obj.is_file():
                    ui.notification(f"Script file not found in chain: {script_path_obj.name}", type="warning")
                    return
                script_name = script_path_obj.name
                # Add a marker before each script
                marker = f"echo '=== Running script {idx + 1} of {total_scripts}: {script_name} ==='"
                exec_cmd = self.ui_manager.build_execution_command(script_path_obj, arguments)
                commands.append(f"{marker} && ({exec_cmd})")
            # Join with '&&' to stop on first failure
            full_cmd = " && ".join(commands)
            self.ui_manager.tmux_manager.start_tmux_session(session_name, full_cmd, logger)
            ui.notification(f"Launched chained session '{session_name}' with {len(chain)} scripts", type="positive")
        except Exception as e:
            logger.error(f"Failed to launch chained session: {e}")
            ui.notification(f"Failed to launch chained session: {e}", type="negative")

    def build(self):
        """Build the script manager tab UI."""
        with ui.card().style("background-color: #fff; color: #000; padding: 20px; border-radius: 8px; width: 100%; margin-left: 0; margin-right: 0;"):
            # Place Session Name, Script, and Arguments side by side
            with ui.row().style("width: 100%; gap: 10px; margin-bottom: 10px;"):
                self.session_name_input = ui.input(label="Session Name").style("width: 30%; color: #75a8db;")
                script_files = self.ui_manager.get_script_files()
                self.script_path_select = ui.select(
                    options=script_files if script_files else ["No scripts found"],
                    label="Script",
                    value=script_files[0] if script_files else "No scripts found",
                ).style("width: 35%;")
                self.script_path_select.on("update:model-value", self.ui_manager.update_script_preview)
                self.arguments_input = ui.input(
                    label="Arguments",
                    value=".",
                ).style("width: 35%;")

            # Set the reference in ui_manager so other methods can access it
            self.ui_manager.script_path_select = self.script_path_select
            self.ui_manager.session_name_input = self.session_name_input
            self.ui_manager.arguments_input = self.arguments_input

            script_preview_content = ""
            if script_files and (self.ui_manager.tmux_manager.SCRIPTS_DIR / script_files[0]).is_file():
                with open(
                    self.ui_manager.tmux_manager.SCRIPTS_DIR / script_files[0],
                    "r",
                ) as f:
                    script_preview_content = f.read()

            def on_script_edit(e):
                if not self.ui_manager.ignore_next_edit:
                    self.script_edited["changed"] = True
                else:
                    self.ui_manager.ignore_next_edit = False  # Reset after ignoring

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

            # Set the reference in ui_manager so other methods can access it
            self.ui_manager.script_preview_editor = self.script_preview_editor

            # Save/Save as/Delete Buttons
            with ui.row().style("gap: 10px; margin-top: 10px;"):
                ui.button(
                    "Save",
                    on_click=lambda: self.ui_manager.save_current_script(self.script_edited),
                    color="primary",
                    icon="save",
                )
                ui.button(
                    "Save as",
                    on_click=self.ui_manager.save_as_new_dialog,
                    color="secondary",
                    icon="save",
                )
                ui.button(
                    "DELETE",
                    color="red",
                    on_click=lambda: self.ui_manager.confirm_delete_script(),
                    icon="delete",
                )

            # Launch logic: warn if unsaved changes
            async def launch_with_save_check():
                if self.script_edited["changed"]:
                    ui.notification(
                        "You have unsaved changes. Please save before launching or use 'Save as New'.",
                        type="warning",
                    )
                    return
                session_name = self.session_name_input.value.strip() if self.session_name_input else ""
                arguments = self.arguments_input.value if self.arguments_input else ""
                # Launch chain if present, else single script
                if self.ui_manager.chain_queue:
                    await self._launch_chained_scripts(session_name)
                    self.ui_manager.chain_queue.clear()
                else:
                    selected_script = self.script_path_select.value if self.script_path_select else ""
                    await self._launch_single_script(session_name, selected_script, arguments)

            with ui.row().style("width: 100%; gap: 10px; margin-top: 10px;"):
                ui.button(
                    "Launch",
                    on_click=launch_with_save_check,
                    icon="rocket_launch",
                )
                ui.button(
                    "Schedule",
                    color="secondary",
                    icon="history",
                    on_click=lambda: self.ui_manager.schedule_launch(),
                )
                ui.button(
                    "Chain Script",
                    color="secondary",
                    on_click=self.ui_manager.chain_current_script,
                    icon="add_link",
                )
                if self.ui_manager.favorites_tab:

                    def save_script_as_favorite():
                        # Build the command from script and arguments
                        selected_script = self.script_path_select.value if self.script_path_select else ""
                        arguments = self.arguments_input.value if self.arguments_input else ""
                        actual_filename = self.ui_manager.extract_script_filename(selected_script)
                        script_path = self.ui_manager.tmux_manager.SCRIPTS_DIR / actual_filename
                        if script_path.is_file():
                            command = self.ui_manager.build_execution_command(script_path, arguments)

                            # Create a simple wrapper object with a value attribute
                            class CommandWrapper:
                                def __init__(self, val):
                                    self.value = val

                            command_obj = CommandWrapper(command)
                            self.ui_manager.favorites_tab._save_as_favorite(self.session_name_input, command_obj)
                        else:
                            ui.notification("Please select a valid script first", type="warning")

                    ui.button(
                        "Save as Favorite",
                        color="info",
                        icon="star",
                        on_click=save_script_as_favorite,
                    )
