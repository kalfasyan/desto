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

            # CPU Details toggle and container
            core_info = "Show CPU details"
            self.show_cpu_cores = ui.switch(core_info, value=False).style("margin-top: 8px;")
            self.cpu_cores_container = ui.column().style(
                "margin-top: 8px; min-height: 50px; border: 1px solid #ddd; padding: 8px; border-radius: 4px;"
            )

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
        logger.debug("Initializing CPU cores display")
        logical_cores = psutil.cpu_count(logical=True)
        physical_cores = psutil.cpu_count(logical=False)
        max_cols = self.ui_settings.get("cpu_cores", {}).get("max_columns", 4)

        logger.debug(f"CPU cores: {logical_cores} logical, {physical_cores} physical, max_cols: {max_cols}")

        with self.cpu_cores_container:
            ui.label(f"CPU Details ({logical_cores} threads on {physical_cores} cores)").style(
                f"font-weight: {self.ui_settings['labels']['subtitle_font_weight']}; margin-bottom: 8px;"
            )

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
        # Add references to the stats labels so we can update them
        self.total_sessions_label = None
        self.finished_jobs_label = None
        self.failed_jobs_label = None
        self.running_jobs_label = None

    def get_session_history(self, days=7):
        """Get session history from Redis, deduplicate scheduled/real sessions, and show correct status/durations."""
        history = []
        session_map = {}  # session_name -> session_info
        scheduled_map = {}  # session_name -> scheduled_info
        try:
            all_keys = list(self.tmux_manager.redis_client.redis.scan_iter(match="desto:session:*"))
            logger.debug(f"Found {len(all_keys)} session keys in Redis")

            for key in all_keys:
                try:
                    session_id = key.replace("desto:session:", "")
                    session_data = self.tmux_manager.redis_client.redis.hgetall(key)
                    if session_data:
                        session_info = {
                            k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v for k, v in session_data.items()
                        }
                        display_session_name = session_info.get("session_name", session_id)
                        status = session_info.get("status", "unknown").lower()
                        start_time_str = session_info.get("start_time")
                        end_time_str = session_info.get("end_time")

                        # If session is scheduled but not started, store in scheduled_map
                        if status == "scheduled" and not start_time_str:
                            scheduled_map[display_session_name] = {
                                **session_info,
                                "session_name": display_session_name,
                                "status": "Scheduled",
                                "job_status": "scheduled",
                                "duration": "N/A",
                                "job_elapsed": "N/A",
                                "start_time": "N/A",
                                "end_time": "N/A",
                            }
                            continue

                        # Calculate session duration
                        duration_str = session_info.get("duration")
                        if not duration_str or duration_str == "unknown":
                            if start_time_str:
                                try:
                                    from datetime import datetime

                                    start_time = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
                                    if end_time_str:
                                        end_time = datetime.fromisoformat(end_time_str.replace("Z", "+00:00"))
                                    else:
                                        end_time = datetime.now()
                                    duration = end_time - start_time
                                    total_seconds = int(duration.total_seconds())
                                    hours = total_seconds // 3600
                                    minutes = (total_seconds % 3600) // 60
                                    seconds = total_seconds % 60
                                    if hours > 0:
                                        duration_str = f"{hours}h {minutes}m {seconds}s"
                                    elif minutes > 0:
                                        duration_str = f"{minutes}m {seconds}s"
                                    else:
                                        duration_str = f"{seconds}s"
                                except Exception as e:
                                    logger.error(f"Error calculating duration for {display_session_name}: {e}")
                                    duration_str = "N/A"
                            else:
                                duration_str = "N/A"

                        # Use JobManager to get job duration for the latest job in this session
                        job_elapsed = "N/A"
                        job_ids_str = session_info.get("job_ids", "")
                        job_ids = [jid for jid in job_ids_str.split(",") if jid]
                        if job_ids:
                            latest_job_id = job_ids[-1]
                            job_manager = None
                            if hasattr(self.tmux_manager, "job_manager"):
                                job_manager = self.tmux_manager.job_manager
                            elif hasattr(self.tmux_manager, "redis_client") and hasattr(self.tmux_manager.redis_client, "job_manager"):
                                job_manager = self.tmux_manager.redis_client.job_manager
                            if job_manager:
                                try:
                                    job_elapsed = job_manager.get_job_duration(latest_job_id)
                                except Exception as e:
                                    logger.error(f"Error using JobManager.get_job_duration for {display_session_name}: {e}")
                                    job_elapsed = "N/A"
                            else:
                                job_elapsed = "N/A"

                        session_info.update(
                            {
                                "session_name": display_session_name,
                                "duration": duration_str,
                                "job_elapsed": job_elapsed,
                            }
                        )
                        session_map[display_session_name] = session_info
                        logger.debug(f"Added session: {display_session_name} with data: {session_info}")
                except Exception as e:
                    logger.error(f"Error processing session key {key}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error getting session history: {e}")
            return []

        # Only show scheduled entry if no real session exists for that name
        for sname, sched in scheduled_map.items():
            if sname not in session_map:
                history.append(sched)
        # Add all real sessions
        history.extend(session_map.values())

        # Sort by start time (newest first, scheduled entries with N/A at the end)
        def sort_key(x):
            st = x.get("start_time", "")
            if st == "N/A":
                return "0000-00-00T00:00:00"
            return st

        history.sort(key=sort_key, reverse=True)
        logger.debug(f"Returning {len(history)} sessions (deduplicated)")
        return history

    def build(self):
        """Build session history tab with Redis availability check"""
        with ui.card().style(
            "background-color: #fff; color: #000; padding: 20px; border-radius: 8px; width: 100%; max-width: 1200px; margin: 0 auto;"
        ):
            # Header with refresh and clear buttons
            with ui.row().style("width: 100%; justify-content: space-between; align-items: center; margin-bottom: 20px;"):
                ui.label("Session History").style("font-size: 1.5em; font-weight: bold;")
                with ui.row().style("gap: 10px;"):
                    ui.button("Refresh", icon="refresh", on_click=self.refresh_history_display).props("flat")
                    ui.button("Clear History", icon="delete_sweep", color="red", on_click=self.confirm_clear_history).props("flat")
                    ui.button("Clear Logs", icon="folder_delete", color="orange", on_click=self.confirm_clear_logs).props("flat")

            # Always create stats container with labels we can update
            with ui.row().style("gap: 30px; margin-bottom: 20px; flex-wrap: wrap;"):
                with ui.card().style("padding: 15px; min-width: 120px; text-align: center;"):
                    self.total_sessions_label = ui.label("0").style("font-size: 2em; font-weight: bold; color: #2196F3;")
                    ui.label("Total Sessions").style("color: #666; font-size: 0.9em;")

                with ui.card().style("padding: 15px; min-width: 120px; text-align: center;"):
                    self.finished_jobs_label = ui.label("0").style("font-size: 2em; font-weight: bold; color: #4CAF50;")
                    ui.label("Finished").style("color: #666; font-size: 0.9em;")

                with ui.card().style("padding: 15px; min-width: 120px; text-align: center;"):
                    self.failed_jobs_label = ui.label("0").style("font-size: 2em; font-weight: bold; color: #F44336;")
                    ui.label("Failed").style("color: #666; font-size: 0.9em;")

                with ui.card().style("padding: 15px; min-width: 120px; text-align: center;"):
                    self.running_jobs_label = ui.label("0").style("font-size: 2em; font-weight: bold; color: #FF9800;")
                    ui.label("Running").style("color: #666; font-size: 0.9em;")

            # History table container - always create it
            self.history_container = ui.column().style("width: 100%; overflow-x: auto;")

            # Get initial history data and display it
            history = self.get_session_history()
            self.update_stats_and_display(history)

    def update_stats_and_display(self, history):
        """Update the stats labels and display table with current data"""
        # Calculate stats
        total_sessions = len(history)
        finished_jobs = len([s for s in history if s.get("job_status") == "finished" or (s.get("status") == "finished" and not s.get("job_status"))])
        failed_jobs = len([s for s in history if s.get("job_status") == "failed" or (s.get("status") == "failed" and not s.get("job_status"))])

        # Count running jobs properly
        actually_running = []
        for s in history:
            job_status = s.get("job_status", "")
            session_status = s.get("status", "")

            # Count as running if:
            # 1. Session is running and no job status set (job still running)
            # 2. Session is running and job status is explicitly "running"
            if session_status == "running" and (not job_status or job_status == "running"):
                actually_running.append(s)

        running_jobs = len(actually_running)

        # Debug logging to understand the data
        logger.debug(f"Session summary stats: Total={total_sessions}, Finished={finished_jobs}, Failed={failed_jobs}, Running={running_jobs}")
        logger.debug("Session status breakdown:")
        for i, s in enumerate(history[:5]):  # Log first 5 sessions for debugging
            session_name = s.get("session_name", "unknown")
            status = s.get("status", "unknown")
            job_status = s.get("job_status", "none")
            logger.debug(f"  Session {i + 1}: name={session_name}, status={status}, job_status={job_status}")

        # Update the UI labels with new values
        if self.total_sessions_label:
            self.total_sessions_label.text = str(total_sessions)
        if self.finished_jobs_label:
            self.finished_jobs_label.text = str(finished_jobs)
        if self.failed_jobs_label:
            self.failed_jobs_label.text = str(failed_jobs)
        if self.running_jobs_label:
            self.running_jobs_label.text = str(running_jobs)

        # Update the history table
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

            # Table header with original column structure
            with ui.row().style(
                "width: 100%; min-width: 1000px; background-color: #f5f5f5; "
                "padding: 12px; border-radius: 4px; margin-bottom: 10px; font-weight: bold;"
            ):
                ui.label("Session Name").style("flex: 2; min-width: 150px;")
                ui.label("Status").style("flex: 1; min-width: 100px;")
                ui.label("Job Duration").style("flex: 1; min-width: 120px;")
                ui.label("Session Duration").style("flex: 1; min-width: 130px;")
                ui.label("Started").style("flex: 2; min-width: 140px;")
                ui.label("Finished").style("flex: 2; min-width: 140px;")

            # Table rows (show last 20 sessions)
            for session in history[:20]:
                status = session.get("status", "unknown")
                job_status = session.get("job_status", "")

                # FIXED: Prioritize job_status over session status for display
                # This handles Keep Alive scenarios properly
                if job_status == "finished":
                    display_status = "✅ Finished"
                    status_color = "#4CAF50"
                elif job_status == "failed":
                    display_status = "❌ Failed"
                    status_color = "#F44336"
                elif job_status == "running":
                    display_status = "🟡 Running"
                    status_color = "#FF9800"
                elif job_status == "scheduled" or status == "scheduled":
                    display_status = "📅 Scheduled"
                    status_color = "#9C27B0"
                elif status == "finished":
                    display_status = "✅ Done"
                    status_color = "#4CAF50"
                elif status == "failed":
                    display_status = "❌ Error"
                    status_color = "#F44336"
                elif status == "running":
                    # This is likely a keep-alive session or job still running
                    if job_status == "":
                        display_status = "🟡 Running"
                    else:
                        display_status = "🟡 Active"  # Keep-alive mode
                    status_color = "#FF9800"
                else:
                    display_status = "❓ Unknown"
                    status_color = "#9E9E9E"

                # Format start time
                start_time = session.get("start_time", "")
                if start_time:
                    try:
                        dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                        # For scheduled jobs, show "Scheduled for:" prefix
                        if job_status == "scheduled" or status == "scheduled":
                            formatted_start_time = f"Scheduled: {dt.strftime('%Y-%m-%d %H:%M:%S')}"
                        else:
                            formatted_start_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        formatted_start_time = start_time[:19] if len(start_time) > 19 else start_time
                else:
                    formatted_start_time = "Unknown"

                # Format end time - for keep-alive sessions, show "Keep Alive" instead of "Running"
                end_time = session.get("end_time", "")
                if end_time:
                    try:
                        dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
                        formatted_end_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        formatted_end_time = end_time[:19] if len(end_time) > 19 else end_time
                else:
                    # Smart end time display for different session types
                    if job_status == "scheduled" or status == "scheduled":
                        formatted_end_time = "Pending"
                    elif status == "running":
                        if job_status == "finished":
                            formatted_end_time = "Keep Alive"
                        elif job_status == "failed":
                            formatted_end_time = "Keep Alive"
                        else:
                            formatted_end_time = "Running"
                    else:
                        formatted_end_time = "N/A"

                # Get job duration (script execution time) - Redis stores this as "job_elapsed"
                job_duration = session.get("job_elapsed", "N/A")
                if job_duration == "N/A" or job_duration == "unknown":
                    # Fallback to "elapsed" field for compatibility
                    job_duration = session.get("elapsed", "N/A")

                # Get session duration (total session time) - Redis stores this as "duration"
                session_duration = session.get("duration", "N/A")

                # For keep-alive sessions, show ongoing duration only if session is actually still running
                if status == "running" and job_status in ["finished", "failed"]:
                    session_duration = "Ongoing"

                # Format both durations if they're raw timedelta strings
                def format_duration(duration_str):
                    if duration_str == "N/A" or duration_str == "unknown" or duration_str == "Ongoing":
                        return duration_str

                    # Parse format like "0:05:23.456789" or "1 day, 0:05:23.456789"
                    if ":" in duration_str:
                        try:
                            # Handle "X days, H:M:S" format
                            if "day" in duration_str:
                                parts = duration_str.split(", ")
                                days_part = parts[0]
                                time_part = parts[1] if len(parts) > 1 else "0:00:00"
                                days = int(days_part.split()[0])
                            else:
                                days = 0
                                time_part = duration_str

                            # Parse H:M:S part
                            time_components = time_part.split(":")
                            if len(time_components) >= 3:
                                hours = int(time_components[0]) + (days * 24)
                                minutes = int(time_components[1])
                                seconds = int(float(time_components[2]))

                                if hours > 0:
                                    return f"{hours}h {minutes}m {seconds}s"
                                elif minutes > 0:
                                    return f"{minutes}m {seconds}s"
                                else:
                                    return f"{seconds}s"
                        except Exception:
                            pass  # Keep original format if parsing fails

                    return duration_str

                job_duration = format_duration(job_duration)
                session_duration = format_duration(session_duration)

                with ui.row().style(
                    "width: 100%; min-width: 1000px; padding: 10px 12px; border-bottom: 1px solid #eee; "
                    "align-items: center; hover:background-color: #f9f9f9;"
                ):
                    # Session name
                    ui.label(session.get("session_name", "Unknown")).style("flex: 2; min-width: 150px; font-weight: 500;")

                    # Status with color (now properly shows job status)
                    ui.label(display_status).style(f"flex: 1; min-width: 100px; color: {status_color}; font-weight: 500;")

                    # Job Duration (script execution time)
                    ui.label(job_duration).style("flex: 1; min-width: 120px; color: #666;")

                    # Session Duration (total session time)
                    ui.label(session_duration).style("flex: 1; min-width: 130px; color: #666;")

                    # Start time
                    ui.label(formatted_start_time).style("flex: 2; min-width: 140px; color: #666; font-size: 0.9em;")

                    # End time
                    ui.label(formatted_end_time).style("flex: 2; min-width: 140px; color: #666; font-size: 0.9em;")

    def refresh_history_display(self):
        """Refresh the history display"""
        logger.debug("Refreshing history display")
        history = self.get_session_history()
        logger.debug(f"Got {len(history)} sessions")
        self.update_stats_and_display(history)

    def confirm_clear_history(self):
        """Show confirmation dialog before clearing history"""
        with ui.dialog() as dialog, ui.card().style("min-width: 400px;"):
            ui.label("⚠️ Clear Session History").style("font-size: 1.3em; font-weight: bold; color: #d32f2f; margin-bottom: 10px;")
            ui.label("This will permanently delete all session history from Redis.").style("margin-bottom: 15px;")
            ui.label("This action cannot be undone.").style("color: #666; margin-bottom: 20px;")

            with ui.row().style("gap: 10px; justify-content: flex-end; width: 100%;"):
                ui.button("Cancel", on_click=dialog.close).props("color=grey")
                ui.button("Clear History", color="red", on_click=lambda: [self.clear_session_history(), dialog.close()]).props("icon=delete_forever")

        dialog.open()

    def clear_session_history(self):
        """Clear all session history from Redis"""
        try:
            # Get all session keys
            all_keys = list(self.tmux_manager.redis_client.redis.scan_iter(match="desto:session:*"))

            if not all_keys:
                ui.notification("No session history to clear", type="info")
                return

            # Delete all session keys
            deleted_count = 0
            for key in all_keys:
                try:
                    self.tmux_manager.redis_client.redis.delete(key)
                    deleted_count += 1
                except Exception as e:
                    logger.error(f"Error deleting session key {key}: {e}")

            if deleted_count > 0:
                msg = f"Successfully cleared {deleted_count} session record(s) from history"
                logger.info(msg)
                ui.notification(msg, type="positive")

                # Refresh the display to show empty history
                self.refresh_history_display()
            else:
                ui.notification("No sessions were cleared", type="warning")

        except Exception as e:
            error_msg = f"Error clearing session history: {e}"
            logger.error(error_msg)
            ui.notification(error_msg, type="negative")

    def confirm_clear_logs(self):
        """Show confirmation dialog before clearing log files"""
        log_dir = self.tmux_manager.LOG_DIR

        # Count log files
        log_files = []
        if log_dir.exists():
            log_files = list(log_dir.glob("*.log"))

        if not log_files:
            ui.notification("No log files found to clear", type="info")
            return

        with ui.dialog() as dialog, ui.card().style("min-width: 400px;"):
            ui.label("🗂️ Clear Log Files").style("font-size: 1.3em; font-weight: bold; color: #ff9800; margin-bottom: 10px;")
            ui.label(f"This will permanently delete {len(log_files)} log file(s) from:").style("margin-bottom: 10px;")
            ui.label(str(log_dir)).style("font-family: monospace; background: #f5f5f5; padding: 5px; border-radius: 3px; margin-bottom: 15px;")
            ui.label("This action cannot be undone.").style("color: #666; margin-bottom: 20px;")

            # Show some log files as examples
            if len(log_files) <= 5:
                ui.label("Files to be deleted:").style("font-weight: bold; margin-bottom: 5px;")
                for log_file in log_files:
                    ui.label(f"• {log_file.name}").style("margin-left: 10px; font-family: monospace; font-size: 0.9em;")
            else:
                ui.label("Files to be deleted:").style("font-weight: bold; margin-bottom: 5px;")
                for log_file in log_files[:3]:
                    ui.label(f"• {log_file.name}").style("margin-left: 10px; font-family: monospace; font-size: 0.9em;")
                ui.label(f"• ... and {len(log_files) - 3} more files").style("margin-left: 10px; color: #666; font-size: 0.9em;")

            with ui.row().style("gap: 10px; justify-content: flex-end; width: 100%; margin-top: 20px;"):
                ui.button("Cancel", on_click=dialog.close).props("color=grey")
                ui.button("Clear Log Files", color="orange", on_click=lambda: [self.clear_log_files(), dialog.close()]).props("icon=folder_delete")

        dialog.open()

    def clear_log_files(self):
        """Clear all log files from the logs directory"""
        log_dir = self.tmux_manager.LOG_DIR

        if not log_dir.exists():
            ui.notification("Logs directory not found", type="warning")
            return

        try:
            # Get all log files and .finished marker files
            log_files = list(log_dir.glob("*.log"))
            finished_files = list(log_dir.glob("*.finished"))
            all_files = log_files + finished_files

            if not all_files:
                ui.notification("No log files found to clear", type="info")
                return

            deleted_count = 0
            errors = []

            for file_path in all_files:
                try:
                    file_path.unlink()
                    deleted_count += 1
                    logger.info(f"Deleted log file: {file_path}")
                except Exception as e:
                    error_msg = f"Failed to delete {file_path.name}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg)

            # Report results
            if deleted_count > 0:
                msg = f"Successfully deleted {deleted_count} log file(s)"
                if errors:
                    msg += f" ({len(errors)} errors)"
                logger.info(msg)
                ui.notification(msg, type="positive")

            if errors:
                # Show first few errors
                error_summary = "; ".join(errors[:3])
                if len(errors) > 3:
                    error_summary += f" (+{len(errors) - 3} more)"
                ui.notification(f"Errors: {error_summary}", type="warning")

        except Exception as e:
            error_msg = f"Error clearing log files: {e}"
            logger.error(error_msg)
            ui.notification(error_msg, type="negative")


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
                marker = f"echo '=== Running script {idx+1} of {total_scripts}: {script_name} ==='"
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
