"""The dashboard's "schedule launch" dialog: one-off 'at' jobs and recurring schedules."""

from datetime import datetime

from nicegui import ui

from desto.core import scripts
from desto.core.scheduled_jobs import ScheduleError
from desto.redis.recurring import REPEAT_UNITS

REPEAT_OPTIONS = {"never": "Does not repeat", "minutes": "minute(s)", "hours": "hour(s)", "days": "day(s)", "weeks": "week(s)"}


class ScheduleLaunchMixin:
    """Scheduling for UserInterfaceManager.

    Expects the host class to provide tmux_manager, chain_queue, the launch inputs
    (session_name_input, arguments_input, script_path_select), python_executable,
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
        """Schedule the selected script (or the chain queue) at the picked date and time."""
        session_name = self.session_name_input.value.strip() if self.session_name_input is not None and hasattr(self.session_name_input, "value") else ""
        arguments = self.arguments_input.value if self.arguments_input is not None and hasattr(self.arguments_input, "value") else "."
        if not date_input.value or not time_input.value or not session_name:
            error_label.text = "Please select date, time, and enter a session name in the Launch Script section."
            return
        try:
            when = datetime.strptime(f"{date_input.value} {time_input.value}", "%Y-%m-%d %H:%M")
        except ValueError as e:
            error_label.text = f"Invalid date/time: {e}"
            return

        interval_minutes = None
        if repeat_select is not None and repeat_select.value != "never":
            repeat_count = int(repeat_count_input.value or 0) if repeat_count_input is not None else 1
            interval_minutes = repeat_count * REPEAT_UNITS[repeat_select.value]

        if self.chain_queue:
            command = scripts.chain_command(self.chain_queue, self.python_executable)
            script_paths = [script for script, _ in self.chain_queue]
        else:
            script_path = self._selected_script_path()
            command = scripts.launch_command(script_path, arguments, self.python_executable)
            script_paths = [script_path]

        try:
            self.tmux_manager.schedule_launch(session_name, command, script_paths, arguments, when, interval_minutes)
        except ScheduleError as e:
            error_label.text = str(e)
            return
        if self.chain_queue:
            self.chain_queue.clear()
            self.refresh_chain_queue_display()
        schedule_dialog.close()
