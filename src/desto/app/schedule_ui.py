"""The dashboard's "schedule launch" dialog: one-off 'at' jobs and recurring schedules."""

import shlex
import shutil
import sys
from datetime import datetime

from nicegui import ui

from desto.redis.at_job_manager import AtJobManager
from desto.redis.recurring import REPEAT_UNITS, RecurringScheduleManager, describe_interval

REPEAT_OPTIONS = {"never": "Does not repeat", "minutes": "minute(s)", "hours": "hour(s)", "days": "day(s)", "weeks": "week(s)"}


class ScheduleLaunchMixin:
    """Scheduling for UserInterfaceManager.

    Expects the host class to provide tmux_manager, chain_queue, the launch inputs
    (session_name_input, arguments_input, script_path_select), build_execution_command,
    extract_script_filename and refresh_chain_queue_display.
    """

    def _selected_script_path(self):
        """Path of the script currently picked in the launch section's select."""
        select_value = self.script_path_select.value if self.script_path_select is not None and hasattr(self.script_path_select, "value") else None
        return self.tmux_manager.SCRIPTS_DIR / self.extract_script_filename(select_value)

    def schedule_launch(self):
        """Open a dialog to schedule the script launch at a specific date and time."""
        with ui.dialog() as schedule_dialog, ui.card():
            ui.label("Schedule Script Launch").style("font-size: 1.2em; font-weight: bold;")

            # Date and time inputs side by side
            with ui.row().style("gap: 16px; margin-bottom: 16px; align-items: flex-start;"):
                date_input = ui.date(value=datetime.now().strftime("%Y-%m-%d")).style("flex: 1; min-width: 150px;")
                time_input = ui.time(value=datetime.now().strftime("%H:%M")).style("flex: 1; min-width: 120px;")

            # Optional repetition: the date/time above is the first run
            with ui.row().style("gap: 8px; align-items: center; margin-bottom: 8px;"):
                ui.label("Repeat:")
                repeat_count_input = ui.number(value=1, min=1, step=1, format="%d").props("dense outlined").style("width: 80px;")
                repeat_select = ui.select(REPEAT_OPTIONS, value="never").props("dense outlined").style("min-width: 160px;")
                repeat_count_input.bind_visibility_from(repeat_select, "value", backward=lambda v: v != "never")

            error_label = ui.label("").style("color: red;")

            # Buttons below the date/time inputs
            with ui.row().style("gap: 8px; justify-content: flex-end;"):
                ui.button("Cancel", on_click=schedule_dialog.close)
                ui.button(
                    "Schedule",
                    on_click=lambda: self.confirm_schedule(date_input, time_input, error_label, schedule_dialog, repeat_select, repeat_count_input),
                )
        schedule_dialog.open()

    def confirm_schedule(self, date_input, time_input, error_label, schedule_dialog, repeat_select=None, repeat_count_input=None):
        # Imported here so tests can patch them on their defining modules
        from desto.redis.client import DestoRedisClient
        from desto.redis.desto_manager import DestoManager
        from desto.redis.models import SessionStatus

        date_val = date_input.value
        time_val = time_input.value
        session_name = self.session_name_input.value.strip() if self.session_name_input is not None and hasattr(self.session_name_input, "value") else ""
        arguments = self.arguments_input.value if self.arguments_input is not None and hasattr(self.arguments_input, "value") else "."

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

            interval_minutes = None
            if repeat_select is not None and repeat_select.value != "never":
                repeat_count = int(repeat_count_input.value or 0) if repeat_count_input is not None else 1
                if repeat_count < 1:
                    error_label.text = "Repeat interval must be at least 1."
                    return
                interval_minutes = repeat_count * REPEAT_UNITS[repeat_select.value]

            # Add Redis session with SCHEDULED status for one-off scheduled scripts.
            # Recurring runs each get their own session when they fire.
            redis_client = DestoRedisClient()
            if interval_minutes is None and redis_client.is_connected():
                manager = DestoManager(redis_client)
                if self.chain_queue:
                    manager.start_session_with_job(
                        session_name=session_name,
                        command=f"Chain: {len(self.chain_queue)} scripts",
                        script_path=f"Chain: {len(self.chain_queue)} scripts",
                        status=SessionStatus.SCHEDULED,
                    )
                else:
                    script_file_path = self._selected_script_path()
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
                tmux_cmd = " && ".join(self.build_execution_command(script, args) for script, args in self.chain_queue)
                script_paths = [script for script, _ in self.chain_queue]
            else:
                script_file_path = self._selected_script_path()
                tmux_cmd = self.build_execution_command(script_file_path, arguments)
                script_paths = [str(script_file_path)]

            if interval_minutes is not None:
                self.create_recurring_schedule(redis_client, session_name, tmux_cmd, interval_minutes, scheduled_dt, script_paths, arguments, error_label, schedule_dialog)
                return

            # Use the bundled wrapper for proper Redis tracking of scheduled jobs, with the
            # current interpreter and logs directory so it matches this dashboard's environment
            scheduled_cmd = f"DESTO_LOGS_DIR={shlex.quote(str(self.tmux_manager.LOG_DIR))} {shlex.quote(sys.executable)} -m desto.hooks.start_scheduled_session {shlex.quote(session_name)} {shlex.quote(tmux_cmd)}"

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

    def create_recurring_schedule(self, redis_client, session_name, command, interval_minutes, first_run, script_paths, arguments, error_label, schedule_dialog):
        """Create a recurring schedule whose runs launch as '<session_name>-YYYYMMDD-HHMM' sessions."""
        if not redis_client.is_connected():
            error_label.text = "Recurring schedules need Redis, which is not available."
            return
        schedule_id = RecurringScheduleManager(redis_client).create(
            session_name=session_name,
            command=command,
            interval_minutes=interval_minutes,
            first_run=first_run,
            log_dir=str(self.tmux_manager.LOG_DIR),
            script_paths=[str(p) for p in script_paths],
            arguments=arguments,
        )
        if not schedule_id:
            error_label.text = "Failed to schedule the first run with 'at'."
            return

        what = f"Chain of {len(self.chain_queue)} scripts" if self.chain_queue else "Script"
        ui.notification(
            f"{what} will run {describe_interval(interval_minutes)} starting {first_run:%Y-%m-%d %H:%M}, as sessions named '{session_name}-<date>-<time>'",
            type="info",
        )
        if self.chain_queue:
            self.chain_queue.clear()
            self.refresh_chain_queue_display()
        schedule_dialog.close()
