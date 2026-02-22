import json
import os
from datetime import datetime
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
        with ui.column().classes("w-full gap-6"):
            ui.label("System Stats").classes("text-xl font-bold text-slate-900 dark:text-white mb-2")

            # CPU Section
            with ui.column().classes("w-full gap-2"):
                with ui.row().classes("w-full justify-between items-center"):
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("memory", color="primary", size="1.2rem")
                        ui.label("CPU").classes("font-semibold text-slate-700 dark:text-slate-300")
                    self.cpu_percent = ui.label("0%").classes("font-bold text-primary")
                self.cpu_bar = ui.linear_progress(value=0, size="8px", show_value=False).props("rounded color=primary")

                # CPU Details toggle
                self.show_cpu_cores = ui.switch("Show Details", value=False).props("dense size=sm")
                self.cpu_cores_container = ui.column().classes("w-full bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 p-4 transition-all overflow-hidden")

                def toggle_cpu_cores_visibility(e):
                    new_value = self.show_cpu_cores.value
                    self.cpu_cores_container.visible = new_value
                    if new_value and not self.cpu_core_labels:
                        self._initialize_cpu_cores()

                self.show_cpu_cores.on_value_change(toggle_cpu_cores_visibility)
                self.cpu_cores_container.visible = False

            # Memory Section
            with ui.column().classes("w-full gap-2"):
                with ui.row().classes("w-full justify-between items-center"):
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("analytics", color="accent", size="1.2rem")
                        ui.label("Memory").classes("font-semibold text-slate-700 dark:text-slate-300")
                    self.memory_percent = ui.label("0%").classes("font-bold text-accent")
                self.memory_bar = ui.linear_progress(value=0, size="8px", show_value=False).props("rounded color=accent")

                with ui.row().classes("w-full justify-between text-xs text-slate-500 dark:text-slate-400 mt-1"):
                    self.memory_used = ui.label("0 GB Used")
                    self.memory_available = ui.label("0 GB Available")

            # Disk Section
            with ui.column().classes("w-full gap-2"):
                with ui.row().classes("w-full justify-between items-center"):
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("storage", color="info", size="1.2rem")
                        ui.label("Disk").classes("font-semibold text-slate-700 dark:text-slate-300")
                    self.disk_percent = ui.label("0%").classes("font-bold text-info")
                self.disk_bar = ui.linear_progress(value=0, size="8px", show_value=False).props("rounded color=info")

                with ui.row().classes("w-full justify-between text-xs text-slate-500 dark:text-slate-400 mt-1"):
                    self.disk_used = ui.label("0 GB Used")
                    self.disk_free = ui.label("0 GB Free")

            # Tmux Section
            with ui.column().classes("w-full mt-4 p-4 bg-primary/10 dark:bg-primary/5 rounded-lg border border-primary/20"):
                ui.label("Tmux Environment").classes("text-xs font-bold uppercase tracking-wider text-primary mb-2")
                self.tmux_cpu = ui.label("tmux CPU: N/A").classes("text-sm text-slate-700 dark:text-slate-300")
                self.tmux_mem = ui.label("tmux MEM: N/A").classes("text-sm text-slate-700 dark:text-slate-300")

    def _initialize_cpu_cores(self):
        """Initialize the CPU cores display."""
        logger.debug("Initializing CPU cores display")
        logical_cores = psutil.cpu_count(logical=True)
        physical_cores = psutil.cpu_count(logical=False)
        max_cols = self.ui_settings.get("cpu_cores", {}).get("max_columns", 4)

        logger.debug(f"CPU cores: {logical_cores} logical, {physical_cores} physical, max_cols: {max_cols}")

        with self.cpu_cores_container:
            ui.label(f"CPU Details ({logical_cores} threads on {physical_cores} cores)").classes("text-sm font-bold mb-4")

            # Create a grid for CPU cores for better alignment
            with ui.grid(columns=max_cols).classes("w-full gap-x-2 gap-y-4 mb-2"):
                for j in range(logical_cores):
                    with ui.column().classes("items-center gap-0 w-full"):
                        ui.label(f"T{j}").classes("text-[10px] text-slate-400 uppercase")
                        core_percent = ui.label("0%").classes("text-xs font-bold text-slate-700 dark:text-slate-300")
                        core_bar = ui.linear_progress(value=0, size="4px", show_value=False).props("rounded color=primary").classes("w-full")

                    self.cpu_core_labels.append(core_percent)
                    self.cpu_core_bars.append(core_bar)


class SettingsPanel:
    def __init__(self, tmux_manager, ui_manager=None, right_drawer=None):
        self.tmux_manager = tmux_manager
        self.ui_manager = ui_manager
        self.right_drawer = right_drawer
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
        ui.label("Settings").classes("text-xl font-bold text-slate-900 dark:text-white mb-6 text-center w-full")

        with ui.column().classes("w-full gap-4"):
            self.scripts_dir_input = ui.input(
                label="Scripts Directory",
                value=str(self.tmux_manager.SCRIPTS_DIR),
            ).classes("w-full")

            self.logs_dir_input = ui.input(
                label="Logs Directory",
                value=str(self.tmux_manager.LOG_DIR),
            ).classes("w-full")

            # Pushbullet API key input
            existing_key = getattr(self.tmux_manager, "pushbullet_api_key", os.environ.get("DESTO_PUSHBULLET_API_KEY", ""))
            self.pushbullet_input = ui.input(
                label="Pushbullet API Key",
                value=existing_key,
                password=True,
                password_toggle_button=True,
                autocomplete=[],
            ).classes("w-full")

            ui.button("Save Configuration", icon="save", on_click=self.save_settings).props("unelevated color=primary").classes("w-full mt-2")

            # Send test push button
            def _send_test_push():
                try:
                    api_key = self.pushbullet_input.value.strip()
                    setattr(self.tmux_manager, "pushbullet_api_key", api_key)
                    from desto.notifications import PushbulletNotifier

                    notifier = PushbulletNotifier(api_key=api_key)
                    title = "Desto Test Push"
                    body = f"Test push from Desto at {datetime.utcnow().isoformat()}Z"
                    resp = notifier.notify_with_response(title=title, body=body)

                    if resp.get("ok"):
                        ui.notification("Test push sent successfully.", type="positive")
                    else:
                        ui.notification(f"Test push failed: {resp.get('status_code')}", type="negative")

                    with ui.dialog() as d, ui.card().classes("p-6"):
                        ui.label("Push Response").classes("text-lg font-bold mb-4")
                        ui.textarea(json.dumps(resp, indent=2)).props("readonly").classes("w-96 h-48")
                        ui.button("Close", on_click=lambda: d.close()).classes("mt-4 w-full")
                    d.open()
                except Exception as e:
                    logger.exception("Failed to send test push")
                    ui.notification(f"Error: {e}", type="negative")

            ui.button("Send Test Notification", icon="send", on_click=_send_test_push).props("outline color=secondary").classes("w-full")

        with ui.row().classes("w-full justify-center mt-8"):
            ui.button("Close Panel", icon="close", on_click=lambda: self.right_drawer.toggle()).props("flat color=slate-500")

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
            try:
                api_key = self.pushbullet_input.value.strip()
                setattr(self.tmux_manager, "pushbullet_api_key", api_key)
                cfg = {"pushbullet_api_key": api_key}
                self._config_path.write_text(json.dumps(cfg))
            except Exception:
                logger.debug("Failed to persist config", exc_info=True)
            ui.notification("Settings updated successfully.", type="positive")
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
        with ui.card().props("flat").classes("modern-card w-full p-6 dark:!bg-slate-900 rounded-xl shadow-sm"):
            ui.label("Create New Script").classes("text-lg font-bold text-slate-900 dark:text-white mb-4")

            with ui.row().classes("w-full gap-4 items-center mb-6"):
                ui.select(
                    ["bash", "python"],
                    label="Script Type",
                    value="bash",
                    on_change=self.on_script_type_change,
                ).classes("flex-grow")

                self.custom_template_name_input = ui.input(
                    label="Script Name",
                    placeholder="MyScript",
                    validation={"Too long!": lambda value: len(value) <= 15},
                ).classes("flex-grow")

            self.code_editor = ui.codemirror(
                self.custom_code["value"],
                language="bash",
                theme="vscodeDark" if self.ui_manager._dark_mode.value else "vscodeLight",
                on_change=lambda e: self.custom_code.update({"value": e.value}),
            ).classes("w-full h-64 rounded-lg overflow-hidden border border-slate-200 dark:border-slate-800 mb-6")

            with ui.row().classes("w-full justify-between items-center"):
                ui.select(self.code_editor.supported_themes, label="Editor Theme").classes("w-40").bind_value(self.code_editor, "theme")
                ui.button(
                    "Save Script",
                    icon="save",
                    on_click=self.save_custom_script,
                ).props("unelevated color=primary").classes("px-6")

    def on_script_type_change(self, e):
        script_type = e.value
        self.script_type["value"] = script_type
        if script_type == "python":
            self.custom_code["value"] = "#!/usr/bin/env python3\n\n# Your Python code here\nprint('Hello from desto!')\n"
            self.code_editor.language = "python"
        else:
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
        extension = ".py" if script_type == "python" else ".sh"
        default_shebang = "#!/usr/bin/env python3\n" if script_type == "python" else "#!/bin/bash\n"
        if not code.startswith("#!"):
            code = default_shebang + code
        script_path = self.tmux_manager.get_script_file(f"{safe_name}{extension}")
        try:
            with script_path.open("w") as f:
                f.write(code)
            os.chmod(script_path, 0o755)
            ui.notification(f"Script '{name}' saved successfully.", type="positive")
        except Exception as e:
            ui.notification(f"Failed to save script: {e}", type="warning")
        if self.ui_manager:
            self.ui_manager.refresh_script_list()
            if hasattr(self.ui_manager, "script_path_select"):
                self.ui_manager.script_path_select.value = f"{safe_name}{extension}"


class LogSection:
    def __init__(self):
        self.log_display = None
        self.log_messages = []

    def build(self):
        with ui.column().classes("w-full gap-4 mt-8"):
            with ui.row().classes("w-full justify-between items-center"):
                ui.label("System Logs").classes("text-lg font-bold text-slate-900 dark:text-white")
                show_logs = ui.switch("Show Logs", value=True).props("dense")

            log_card = ui.card().classes("modern-card w-full p-0 bg-slate-100 dark:bg-slate-900 rounded-xl shadow-lg overflow-hidden transition-all")
            with log_card:
                self.log_display = ui.textarea("").classes("w-full h-64 font-mono text-xs p-4 bg-transparent text-slate-700 dark:text-emerald-400 border-none").props("readonly borderless fill-viewport")

            def toggle_log_card_visibility(value):
                log_card.set_visibility(value)

            show_logs.on_value_change(lambda e: toggle_log_card_visibility(e.value))
            log_card.set_visibility(show_logs.value)

    def update_log_messages(self, message, number_of_lines=20):
        self.log_messages.append(message)
        if len(self.log_messages) > number_of_lines:
            self.log_messages.pop(0)

    def refresh_log_display(self):
        if self.log_display:
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
        script_marker = f"echo '=== Running script: {script_path.name} ==='"
        try:
            full_cmd = f"{script_marker} && ({exec_cmd})"
            self.ui_manager.tmux_manager.start_tmux_session(session_name, full_cmd, logger)
            ui.notification(f"Launched session '{session_name}'", type="positive")
        except Exception as e:
            logger.error(f"Failed to launch session: {e}")
            ui.notification(f"Error: {e}", type="negative")

    async def _launch_chained_scripts(self, session_name):
        if not session_name:
            ui.notification("Please enter a session name for the chain.", type="warning")
            return
        chain = self.ui_manager.chain_queue
        if not chain:
            ui.notification("Chain queue is empty.", type="warning")
            return
        commands = []
        try:
            total_scripts = len(chain)
            for idx, (script_path, arguments) in enumerate(chain):
                script_path_obj = Path(script_path)
                if not script_path_obj.is_file():
                    ui.notification(f"Script not found: {script_path_obj.name}", type="warning")
                    return
                marker = f"echo '=== Running script {idx + 1} of {total_scripts}: {script_path_obj.name} ==='"
                exec_cmd = self.ui_manager.build_execution_command(script_path_obj, arguments)
                commands.append(f"{marker} && ({exec_cmd})")
            full_cmd = " && ".join(commands)
            self.ui_manager.tmux_manager.start_tmux_session(session_name, full_cmd, logger)
            ui.notification(f"Launched chain '{session_name}' ({total_scripts} scripts)", type="positive")
        except Exception as e:
            logger.error(f"Failed to launch chain: {e}")
            ui.notification(f"Error: {e}", type="negative")

    def build(self):
        with ui.card().props("flat").classes("modern-card w-full p-6 dark:!bg-slate-900 rounded-xl shadow-sm"):
            ui.label("Script Execution").classes("text-lg font-bold text-slate-900 dark:text-white mb-4")

            with ui.grid(columns=3).classes("w-full gap-4 mb-6"):
                self.session_name_input = ui.input(label="Session Name", placeholder="e.g. build-task").classes("w-full")
                script_files = self.ui_manager.get_script_files()
                self.script_path_select = ui.select(
                    options=script_files if script_files else ["No scripts found"],
                    label="Target Script",
                    value=script_files[0] if script_files else "No scripts found",
                ).classes("w-full")
                self.script_path_select.on("update:model-value", self.ui_manager.update_script_preview)
                self.arguments_input = ui.input(
                    label="Arguments",
                    value=".",
                ).classes("w-full")

            self.ui_manager.script_path_select = self.script_path_select
            self.ui_manager.session_name_input = self.session_name_input
            self.ui_manager.arguments_input = self.arguments_input

            script_preview_content = ""
            if script_files and (self.ui_manager.tmux_manager.SCRIPTS_DIR / script_files[0]).is_file():
                with open(self.ui_manager.tmux_manager.SCRIPTS_DIR / script_files[0], "r") as f:
                    script_preview_content = f.read()

            def on_script_edit(e):
                if not self.ui_manager.ignore_next_edit:
                    self.script_edited["changed"] = True
                else:
                    self.ui_manager.ignore_next_edit = False

            with ui.column().classes("w-full gap-2 mb-6"):
                with ui.row().classes("w-full justify-between items-center"):
                    ui.label("Script Preview").classes("text-sm font-semibold text-slate-500 uppercase tracking-wider")

                self.script_preview_editor = ui.codemirror(
                    script_preview_content,
                    language="bash",
                    theme="vscodeDark" if self.ui_manager._dark_mode.value else "vscodeLight",
                    line_wrapping=True,
                    highlight_whitespace=True,
                    indent="    ",
                    on_change=on_script_edit,
                ).classes("w-full h-64 rounded-lg overflow-hidden border border-slate-200 dark:border-slate-800")

            self.ui_manager.script_preview_editor = self.script_preview_editor

            with ui.row().classes("w-full justify-between items-center mt-4 pt-6 border-t border-slate-100 dark:border-slate-800"):
                with ui.row().classes("gap-2"):
                    ui.button("Save", icon="save", on_click=lambda: self.ui_manager.save_current_script(self.script_edited)).props("unelevated color=primary")
                    ui.button("Save As", icon="save_as", on_click=self.ui_manager.save_as_new_dialog).props("outline color=primary")
                    ui.button("Delete", icon="delete", on_click=self.ui_manager.confirm_delete_script).props("flat color=negative")

                with ui.row().classes("gap-2"):

                    async def launch_with_save_check():
                        if self.script_edited["changed"]:
                            ui.notification("Please save changes before launching.", type="warning")
                            return
                        session_name = self.session_name_input.value.strip()
                        arguments = self.arguments_input.value
                        if self.ui_manager.chain_queue:
                            await self._launch_chained_scripts(session_name)
                            self.ui_manager.chain_queue.clear()
                            self.ui_manager.refresh_chain_queue_display()
                        else:
                            selected_script = self.script_path_select.value
                            await self._launch_single_script(session_name, selected_script, arguments)

                    ui.button("Launch Now", icon="rocket_launch", on_click=launch_with_save_check).props("unelevated color=positive").classes("px-6")
                    ui.button(icon="history", on_click=self.ui_manager.schedule_launch).props("outline color=secondary round")
                    ui.button(icon="add_link", on_click=self.ui_manager.chain_current_script).props("outline color=secondary round")

                    if self.ui_manager.favorites_tab:

                        def save_script_as_favorite():
                            selected_script = self.script_path_select.value
                            arguments = self.arguments_input.value
                            actual_filename = self.ui_manager.extract_script_filename(selected_script)
                            script_path = self.ui_manager.tmux_manager.SCRIPTS_DIR / actual_filename
                            if script_path.is_file():
                                command = self.ui_manager.build_execution_command(script_path, arguments)

                                class CommandWrapper:
                                    def __init__(self, val):
                                        self.value = val

                                self.ui_manager.favorites_tab._save_as_favorite(self.session_name_input, CommandWrapper(command))
                            else:
                                ui.notification("Select a valid script first", type="warning")

                        ui.button(icon="star", on_click=save_script_as_favorite).props("outline color=warning round")
