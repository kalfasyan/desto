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
                self.cpu_cores_container.visible = e.value
                if e.value and not self.cpu_core_labels:
                    self._initialize_cpu_cores()

            self.show_cpu_cores.on("update:model-value", toggle_cpu_cores_visibility)
            self.cpu_cores_container.visible = self.show_cpu_cores.value

            ui.label("Memory Usage").style(f"font-weight: {self.ui_settings['labels']['subtitle_font_weight']}; margin-top: 10px;")
            with ui.row().style("align-items: center"):
                ui.icon("memory", size="1.2rem")
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
                with ui.row().style("gap: 8px; margin-bottom: 4px;"):
                    for j in range(i, min(i + max_cols, cpu_count)):
                        core_column = ui.column().style("align-items: center; min-width: 60px;")
                        with core_column:
                            ui.label(f"Core {j}").style("font-size: 0.8em; margin-bottom: 2px;")
                            core_percent = ui.label("0%").style("font-size: 0.75em; font-weight: bold;")
                            core_bar = ui.linear_progress(value=0, size="sm", show_value=False).style("width: 50px; height: 4px;")

                        self.cpu_core_labels.append(core_percent)
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
            self.log_display = (
                ui.textarea("")
                .style("width: 600px; height: 100%; background-color: #fff; color: #000; border: 1px solid #ccc; font-family: monospace;")
                .props("readonly")
            )

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


class HistoryTab:
    def __init__(self, tmux_manager):
        self.tmux_manager = tmux_manager
        self.history_container = None

    def get_session_history(self, days=7):
        """Get session history from Redis"""
        if not self.tmux_manager.use_redis:
            return []

        history = []
        try:
            # Debug: print all keys to see what's in Redis
            all_keys = list(self.tmux_manager.redis_client.redis.scan_iter(match="desto:session:*"))
            logger.debug(f"Found {len(all_keys)} session keys in Redis")

            # Get SessionStatusTracker for duration calculations
            from desto.redis.status_tracker import SessionStatusTracker

            status_tracker = SessionStatusTracker(self.tmux_manager.redis_client)

            for key in all_keys:
                try:
                    # Extract session name from key (remove "desto:session:" prefix)
                    session_name = key.replace("desto:session:", "")
                    session_data = self.tmux_manager.redis_client.redis.hgetall(key)

                    if session_data:
                        # Convert bytes to strings for Redis data
                        session_info = {
                            k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v for k, v in session_data.items()
                        }

                        # Calculate duration using SessionStatusTracker
                        duration_str = status_tracker.get_session_duration(session_name)

                        session_info.update(
                            {
                                "session_name": session_name,
                                "duration": duration_str,
                            }
                        )
                        history.append(session_info)
                        logger.debug(f"Added session: {session_name} with data: {session_info}")
                except Exception as e:
                    logger.error(f"Error processing session key {key}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error getting session history: {e}")
            return []

        # Sort by start time (newest first)
        history.sort(key=lambda x: x.get("start_time", ""), reverse=True)
        logger.debug(f"Returning {len(history)} sessions")
        return history

    def build(self):
        """Build session history tab with Redis availability check"""
        with ui.card().style(
            "background-color: #fff; color: #000; padding: 20px; border-radius: 8px; width: 100%; max-width: 1200px; margin: 0 auto;"
        ):
            # Header with refresh button
            with ui.row().style("width: 100%; justify-content: space-between; align-items: center; margin-bottom: 20px;"):
                ui.label("Session History").style("font-size: 1.5em; font-weight: bold;")
                ui.button("Refresh", icon="refresh", on_click=self.refresh_history_display).props("flat")

            # Check Redis availability first
            if not self.tmux_manager.use_redis:
                ui.label("Session history requires Redis to be enabled.").style("color: #666; font-style: italic; text-align: center; padding: 40px;")
                return

            # Get history data (Redis is available)
            history = self.get_session_history()

            if not history:
                ui.label("No session history found.").style("color: #666; font-style: italic; text-align: center; padding: 40px;")
                return

            # Summary stats - based on job status, not session status
            total_sessions = len(history)
            finished_jobs = len(
                [s for s in history if s.get("job_status") == "finished" or (s.get("status") == "finished" and not s.get("job_status"))]
            )
            failed_jobs = len([s for s in history if s.get("job_status") == "failed" or (s.get("status") == "failed" and not s.get("job_status"))])
            running_jobs = len([s for s in history if s.get("status") == "running" and not s.get("job_status")])

            with ui.row().style("gap: 30px; margin-bottom: 20px; flex-wrap: wrap;"):
                with ui.card().style("padding: 15px; min-width: 120px; text-align: center;"):
                    ui.label(str(total_sessions)).style("font-size: 2em; font-weight: bold; color: #2196F3;")
                    ui.label("Total Sessions").style("color: #666; font-size: 0.9em;")

                with ui.card().style("padding: 15px; min-width: 120px; text-align: center;"):
                    ui.label(str(finished_jobs)).style("font-size: 2em; font-weight: bold; color: #4CAF50;")
                    ui.label("Finished").style("color: #666; font-size: 0.9em;")

                with ui.card().style("padding: 15px; min-width: 120px; text-align: center;"):
                    ui.label(str(failed_jobs)).style("font-size: 2em; font-weight: bold; color: #F44336;")
                    ui.label("Failed").style("color: #666; font-size: 0.9em;")

                with ui.card().style("padding: 15px; min-width: 120px; text-align: center;"):
                    ui.label(str(running_jobs)).style("font-size: 2em; font-weight: bold; color: #FF9800;")
                    ui.label("Running").style("color: #666; font-size: 0.9em;")

            # History table container
            self.history_container = ui.column().style("width: 100%; overflow-x: auto;")

            # Initial display
            self.display_history_table(history)

    def display_history_table(self, history):
        """Display the history table with better spacing"""
        from datetime import datetime

        # Check if history_container exists, if not create it
        if not hasattr(self, "history_container") or self.history_container is None:
            logger.debug("history_container not found, creating new one")
            self.history_container = ui.column().style("width: 100%; overflow-x: auto;")

        # Clear existing content
        self.history_container.clear()

        with self.history_container:
            if not history:
                ui.label("No sessions found.").style("color: #666; font-style: italic; text-align: center; padding: 20px;")
                return

            # Simple table header - updated to include Elapsed
            with ui.row().style(
                "width: 100%; min-width: 900px; background-color: #f5f5f5; padding: 12px; border-radius: 4px; margin-bottom: 10px; font-weight: bold;"
            ):
                ui.label("Session").style("flex: 2; min-width: 150px;")
                ui.label("Command").style("flex: 3; min-width: 200px;")
                ui.label("Status").style("flex: 1; min-width: 80px;")
                ui.label("Started").style("flex: 2; min-width: 120px;")
                ui.label("Elapsed").style("flex: 1; min-width: 100px;")

            # Table rows (show last 20 sessions)
            for session in history[:20]:
                status = session.get("status", "unknown")
                job_status = session.get("job_status", "")

                # Determine display status and color
                if job_status == "finished":
                    display_status = "✅ Finished"
                    status_color = "#4CAF50"
                elif job_status == "failed":
                    display_status = "❌ Failed"
                    status_color = "#F44336"
                elif status == "running":
                    display_status = "🟡 Running"
                    status_color = "#FF9800"
                elif status == "finished":
                    display_status = "✅ Done"
                    status_color = "#4CAF50"
                elif status == "failed":
                    display_status = "❌ Error"
                    status_color = "#F44336"
                else:
                    display_status = "❓ Unknown"
                    status_color = "#9E9E9E"

                # Format start time
                start_time = session.get("start_time", "")
                if start_time:
                    try:
                        dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                        formatted_time = dt.strftime("%m/%d %H:%M")
                    except Exception:
                        formatted_time = start_time[:16] if len(start_time) > 16 else start_time
                else:
                    formatted_time = "Unknown"

                # Get duration
                duration = session.get("duration", "N/A")

                # Truncate command for display
                command = session.get("command", "N/A")
                if len(command) > 50:
                    command = command[:47] + "..."

                with ui.row().style(
                    "width: 100%; min-width: 900px; padding: 10px 12px; border-bottom: 1px solid #eee; "
                    "align-items: center; hover:background-color: #f9f9f9;"
                ):
                    # Session name
                    ui.label(session.get("session_name", "Unknown")).style("flex: 2; min-width: 150px; font-weight: 500;")

                    # Command (truncated)
                    ui.label(command).style("flex: 3; min-width: 200px; font-family: monospace; font-size: 0.9em; color: #555;")

                    # Status with color
                    ui.label(display_status).style(f"flex: 1; min-width: 80px; color: {status_color}; font-weight: 500;")

                    # Start time
                    ui.label(formatted_time).style("flex: 2; min-width: 120px; color: #666;")

                    # Duration
                    ui.label(duration).style("flex: 1; min-width: 100px; color: #666;")

    def refresh_history_display(self):
        """Refresh the history display"""
        if self.tmux_manager.use_redis:
            logger.debug("Refreshing history display")
            history = self.get_session_history()
            logger.debug(f"Got {len(history)} sessions")
            self.display_history_table(history)
        else:
            ui.notification("Redis not available", type="warning")


class ScriptManagerTab:
    def __init__(self, ui_manager):
        self.ui_manager = ui_manager
        self.session_name_input = None
        self.script_path_select = None
        self.arguments_input = None
        self.script_preview_editor = None
        self.keep_alive_switch_new = None
        self.script_edited = {"changed": False}

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

            # Keep Alive switch
            self.keep_alive_switch_new = ui.switch("Keep Alive").style("margin-top: 10px;")
            self.ui_manager.keep_alive_switch_new = self.keep_alive_switch_new

            # Launch logic: warn if unsaved changes
            async def launch_with_save_check():
                if self.script_edited["changed"]:
                    ui.notification(
                        "You have unsaved changes. Please save before launching or use 'Save as New'.",
                        type="warning",
                    )
                    return
                # If there are scripts in the chain queue, launch the chain
                if self.ui_manager.chain_queue:
                    await self.ui_manager.run_chain_queue(
                        self.session_name_input.value,
                        self.arguments_input.value,
                        self.keep_alive_switch_new.value,
                    )
                    self.ui_manager.chain_queue.clear()
                else:
                    await self.ui_manager.run_session_with_keep_alive(
                        self.session_name_input.value,
                        str(self.ui_manager.tmux_manager.SCRIPTS_DIR / self.ui_manager.extract_script_filename(self.script_path_select.value)),
                        self.arguments_input.value,
                        self.keep_alive_switch_new.value,
                    )

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
