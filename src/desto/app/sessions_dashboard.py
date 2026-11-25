"""Rendering of the sessions dashboard: stats cards, sessions table and scheduled jobs table."""

import json
import sys
import time

from nicegui import ui

from desto.core.formatting import (
    format_bytes,
    format_seconds,
    metrics_key,
    parse_iso,
    scheduled_job_rows,
    seconds_since,
    session_row_times,
    session_rows,
    usage_cells,
)
from desto.core.session_metrics import read_history, read_summaries


class SessionsDashboard:
    """The sessions dashboard: stats cards, sessions table and scheduled jobs table.

    Reads sessions and scheduled jobs from the service, opens dialogs through SessionDialogs
    and renders into its own container.
    """

    def __init__(self, service, dialogs, container):
        self.service = service
        self.dialogs = dialogs
        self.sessions_container = container
        self.status_filter = None  # None, "running", "finished" or "failed"
        self._last_render_signature = None  # Skip re-rendering when nothing changed
        self._live_duration_labels = []  # (label, start datetime) for running sessions
        self._usage_labels = {}  # metrics key -> CPU / memory label of a shown session
        self._atd_cache = (0.0, True)  # (checked_at, is_running)

    @property
    def ui(self):
        return self.service.ui

    def clear_sessions_container(self):
        self.sessions_container.clear()

    def add_to_sessions_container(self, content):
        with self.sessions_container:
            content()

    def update_sessions_status(self, ui_manager=None, force=True):
        """Render the sessions dashboard (stats cards, sessions table, scheduled jobs).

        Data is gathered in a few cheap batched calls. With force=False (the periodic timer),
        the dashboard is only rebuilt when something actually changed, so the page does not
        flicker and scroll position or open menus are not reset. Live durations of running
        sessions are updated in place by tick_live_durations().
        """
        sessions_status = self.service.get_all_sessions_status()
        tmux_active = set(self.service.check_sessions().keys())
        job_info = self.service._job_info_by_session()
        scheduled_jobs = self.service._get_scheduled_jobs_with_metadata()
        self.tick_usage()

        signature = json.dumps(
            [sessions_status, sorted(tmux_active), job_info, scheduled_jobs, self.status_filter],
            sort_keys=True,
            default=str,
        )
        if not force and signature == self._last_render_signature:
            return
        self._last_render_signature = signature

        counts = self.service._count_by_category(sessions_status, tmux_active, job_info)
        self.clear_sessions_container()

        def render():
            self.render_sessions_controls_and_stats(sessions_status, ui_manager, counts=counts)
            self.add_sessions_table(
                sessions_status, self.ui, tmux_active=tmux_active, job_info=job_info, scheduled_jobs=scheduled_jobs
            )

        self.add_to_sessions_container(render)

    def tick_live_durations(self):
        """Update the duration labels of running sessions in place (no table rebuild)."""
        for label, start_dt in self._live_duration_labels:
            try:
                label.text = format_seconds(seconds_since(start_dt))
            except Exception:
                pass

    def tick_usage(self):
        """Update the CPU / memory labels of the shown sessions in place (no table rebuild)."""
        labels = self._usage_labels
        if not labels:
            return
        try:
            summaries = read_summaries(self.service.redis_client.redis, list(labels))
        except Exception:
            return
        for key, label in labels.items():
            text = _usage_text(summaries.get(key))
            if label.text != text:
                label.text = text

    def _is_atd_running_cached(self, at_job_manager_cls, ttl: float = 60.0) -> bool:
        """The atd check spawns processes, so only run it once a minute."""
        checked_at, running = self._atd_cache
        now = time.monotonic()
        if now - checked_at > ttl or checked_at == 0.0:
            running = at_job_manager_cls.is_atd_running()
            self._atd_cache = (now, running)
        return running

    # --- Header: controls, atd warning, stats cards ------------------------------------

    def render_sessions_controls_and_stats(self, sessions_status, ui_manager=None, counts=None):
        """Render the stats cards and control buttons (Refresh, Clear History, Clear Logs)."""
        with ui.row().style("width: 100%; justify-content: space-between; align-items: center; margin-bottom: 20px;"):
            ui.label("Sessions Dashboard").style("font-size: 1.5em; font-weight: bold; margin-left: 10px;")
            with ui.row().style("gap: 10px;"):
                ui.button("Refresh", icon="refresh", on_click=lambda: self.update_sessions_status(force=True)).props(
                    "flat"
                )
                ui.button(
                    "Clear History", icon="delete_sweep", color="red", on_click=self.dialogs.confirm_clear_history
                ).props("flat")
                ui.button(
                    "Clear Logs", icon="folder_delete", color="orange", on_click=self.dialogs.confirm_clear_logs
                ).props("flat")

        self._render_atd_warning()

        # Counts use the same classification as the table rows, and clicking a card filters the table.
        if counts is None:
            counts = self.service._count_by_category(sessions_status)
        self._render_stats_cards(counts)

    def _render_atd_warning(self):
        from desto.core.at_job_manager import AtJobManager

        if self._is_atd_running_cached(AtJobManager):
            return
        with (
            ui.row()
            .style("width: 100%; align-items: center; margin-bottom: 20px; padding: 15px; border-radius: 8px;")
            .classes("bg-orange-1 dark:bg-orange-9") as warning_row
        ):
            ui.icon("warning", color="orange").style("font-size: 2em; margin-right: 15px;")
            with ui.column().style("flex-grow: 1;"):
                ui.label("System 'at' daemon is not running").style("font-weight: bold; color: #ef6c00;")
                ui.label(
                    "Scheduled jobs will be managed by desto's internal scheduler while the dashboard is open. For background execution, please enable 'atd' on your system."
                ).style("font-size: 0.9em;")
                if sys.platform == "darwin":
                    ui.label(
                        "On macOS: sudo launchctl load -w /System/Library/LaunchDaemons/com.apple.atrun.plist"
                    ).style("font-family: monospace; font-size: 0.8em; margin-top: 5px;")
            ui.button(icon="close", on_click=lambda: warning_row.delete()).props("flat round color=orange")

    def _render_stats_cards(self, counts):
        cards = [
            (None, "Total Sessions", counts.get("total", 0), "#2196F3"),
            ("finished", "Finished", counts.get("finished", 0), "#4CAF50"),
            ("failed", "Failed", counts.get("failed", 0), "#F44336"),
            ("running", "Running", counts.get("running", 0), "#FF9800"),
        ]
        with ui.row().style("gap: 30px; margin-bottom: 20px; flex-wrap: wrap; margin-left: 10px;"):
            for category, title, value, color in cards:
                active = self.status_filter == category
                card = (
                    ui.card()
                    .style("padding: 15px; min-width: 120px; text-align: center; cursor: pointer;")
                    .classes("bg-white dark:!bg-slate-900")
                )
                if active and category is not None:
                    card.classes("ring-2 ring-blue-500")
                card.on("click", lambda c=category: self.set_status_filter(c))
                with card:
                    ui.label(str(value)).style(f"font-size: 2em; font-weight: bold; color: {color};")
                    ui.label(title).style("font-size: 0.9em;").classes("text-slate-600 dark:text-slate-400")
                    card.tooltip("Show all sessions" if category is None else f"Show only {title.lower()} sessions")

    def set_status_filter(self, category):
        """Filter the sessions table by category; clicking the active filter (or Total) clears it."""
        self.status_filter = None if category is None or category == self.status_filter else category
        self.update_sessions_status(force=True)

    # --- Sessions table -------------------------------------------------------------

    def add_sessions_table(self, sessions_status, ui, tmux_active=None, job_info=None, scheduled_jobs=None):
        """Adds the sessions table to the UI, using the history tab's columns plus an Actions column."""
        if tmux_active is None:
            tmux_active = set(self.service.check_sessions().keys())
        if job_info is None:
            job_info = self.service._job_info_by_session()
        self._live_duration_labels = []
        self._usage_labels = {}

        self._render_sessions_header(ui)

        rows = [
            row
            for row in session_rows(sessions_status, tmux_active, job_info)
            if not self.status_filter or row.category == self.status_filter
        ]
        if not rows and self.status_filter:
            ui.label(f"No {self.status_filter} sessions. Click the card again to show all.").style(
                "padding: 12px;"
            ).classes("text-slate-500")

        try:
            usage = read_summaries(
                self.service.redis_client.redis, [metrics_key(row.name, row.session) for row in rows]
            )
        except Exception:
            usage = {}
        for row in rows:
            self._render_session_row(
                ui, row.name, row.session, row.tmux_active, row.label, row.color, row.command, usage=usage
            )

        if scheduled_jobs is None:
            scheduled_jobs = self.service._get_scheduled_jobs_with_metadata()
        if scheduled_jobs:
            self._render_scheduled_jobs_table(ui, scheduled_jobs)

    @staticmethod
    def _render_sessions_header(ui):
        with (
            ui.row()
            .style(
                "width: 100%; min-width: 1100px; padding: 12px; border-radius: 4px; margin-bottom: 10px; font-weight: bold;"
            )
            .classes("bg-slate-100 dark:!bg-slate-800 text-slate-900 dark:text-slate-100")
        ):
            ui.label("Session Name").style("flex: 2; min-width: 150px;")
            ui.label("Status").style("flex: 1; min-width: 100px;")
            ui.label("CPU · Memory").style("flex: 1; min-width: 110px;").tooltip(
                "Running: current CPU and memory. Ended: CPU time used and peak memory."
            )
            ui.label("Job Duration").style("flex: 1; min-width: 100px;")
            ui.label("Session Duration").style("flex: 1; min-width: 120px;")
            ui.label("Started").style("flex: 2; min-width: 125px;")
            ui.label("Finished").style("flex: 2; min-width: 125px;")
            ui.label("Tmux Active").style("flex: 1; min-width: 80px;")
            ui.label("Actions").style("flex: 1; min-width: 120px;")

    def _render_session_row(
        self, ui, session_name, session, tmux_active_row, status, status_color, command, usage=None
    ):
        times = session_row_times(session)
        key = metrics_key(session_name, session)
        with (
            ui.row()
            .style(
                "width: 100%; min-width: 1100px; padding: 10px 12px; border-bottom: 1px solid #ddd; align-items: center;"
            )
            .classes("dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800")
        ):
            ui.label(session.get("session_name", session_name)).style("flex: 2; min-width: 150px; font-weight: 500;")
            ui.label(status).style(f"flex: 1; min-width: 100px; color: {status_color}; font-weight: 500;")
            usage_label = (
                ui.label(_usage_text((usage or {}).get(key)))
                .style("flex: 1; min-width: 110px; font-size: 0.9em; cursor: pointer;")
                .classes("text-slate-700 dark:text-slate-400")
            )
            if key:
                self._usage_labels[key] = usage_label
                usage_label.on("click", lambda k=key, n=session_name: self.show_usage_dialog(ui, n, k))
                usage_label.tooltip("Show CPU and memory over time")
            ui.label(times["job_duration"]).style("flex: 1; min-width: 100px;").classes(
                "text-slate-700 dark:text-slate-400"
            )
            duration_label = (
                ui.label(times["session_duration"])
                .style("flex: 1; min-width: 120px;")
                .classes("text-slate-700 dark:text-slate-400")
            )
            if times["start_time"] and not times["end_time"] and tmux_active_row:
                try:
                    self._live_duration_labels.append((duration_label, parse_iso(times["start_time"])))
                except Exception:
                    pass
            ui.label(times["started"]).style("flex: 2; min-width: 125px; font-size: 0.9em;").classes(
                "text-slate-600 dark:text-slate-500"
            )
            ui.label(times["finished"]).style("flex: 2; min-width: 125px; font-size: 0.9em;").classes(
                "text-slate-600 dark:text-slate-500"
            )
            icon = "check_circle" if tmux_active_row else "cancel"
            color = "#4CAF50" if tmux_active_row else "#F44336"
            ui.icon(icon).style(f"flex: 1; min-width: 80px; color: {color}; font-size: 1.5em; text-align: center;")
            with ui.row().style("flex: 1; min-width: 120px; gap: 8px;"):
                # Kill while running; once the tmux session is gone, the slot becomes Re-run.
                if tmux_active_row:
                    ui.button(
                        "Kill",
                        on_click=lambda s=session_name: self.dialogs.confirm_kill_session(s),
                    ).props("color=red flat")
                elif command:
                    ui.button(
                        "Re-run",
                        on_click=lambda s=session_name, c=command: self.service.rerun_session(s, c),
                    ).props("color=green flat").tooltip("Run the same command again in a new session")
                else:
                    ui.button(
                        "Kill",
                        on_click=lambda: ui.notification(
                            "Cannot kill: no active tmux session for this entry.", type="warning"
                        ),
                    ).props("color=red flat disabled")
                ui.button(
                    "View Log",
                    on_click=lambda s=session_name: self.dialogs.view_log(s, ui),
                ).props("color=blue flat")
                ui.button(
                    "Clear",
                    on_click=lambda s=session_name: self.dialogs.confirm_clear_session(s, ui),
                ).props("color=orange flat")

    def show_usage_dialog(self, ui, session_name, key):
        """CPU and memory of a session over its run, with its totals."""
        try:
            points = read_history(self.service.redis_client.redis, key)
            summary = read_summaries(self.service.redis_client.redis, [key]).get(key, {})
        except Exception:
            points, summary = [], {}
        self.service.pause()

        def close_dialog():
            dialog.close()
            self.service.resume()

        with ui.dialog() as dialog, ui.card().style("min-width: 720px; max-width: 95vw;").classes("dark:!bg-slate-900"):
            ui.label(f"Resource usage: {session_name}").style("font-weight: bold; font-size: 1.1em;")
            if not points:
                ui.label(
                    "No usage recorded for this session yet. It is recorded while the dashboard, the terminal UI or `desto-cli monitor` runs."
                )
            else:
                ui.echart(_usage_chart_options(points)).style("width: 680px; height: 320px;")
            if summary:
                with ui.row().style("gap: 24px; flex-wrap: wrap;"):
                    for title, value in (
                        ("Peak memory", format_bytes(summary.get("peak_rss", 0))),
                        ("CPU time", format_seconds(int(float(summary.get("cpu_seconds", 0))))),
                        ("Peak processes", summary.get("max_procs", "0")),
                        ("Peak threads", summary.get("max_threads", "0")),
                        ("Read", format_bytes(summary.get("read_bytes", 0))),
                        ("Written", format_bytes(summary.get("write_bytes", 0))),
                    ):
                        with ui.column().style("gap: 0;"):
                            ui.label(title).style("font-size: 0.8em;").classes("text-slate-500")
                            ui.label(str(value)).style("font-weight: 600;")
            ui.button("Close", on_click=close_dialog)
        dialog.open()

    # --- Scheduled jobs table (atq + Redis metadata) ---------------------------------

    def _render_scheduled_jobs_table(self, ui, scheduled_jobs):
        with ui.row().style("margin-top: 40px; margin-bottom: 10px;"):
            ui.label("Scheduled Jobs (with metadata)").style("font-size: 1.2em; font-weight: bold;")

        with (
            ui.row()
            .style("width: 100%; min-width: 700px; padding: 10px; border-radius: 4px; font-weight: bold;")
            .classes("bg-slate-100 dark:!bg-slate-800 text-slate-900 dark:text-slate-100")
        ):
            ui.label("Job ID").style("flex: 1; min-width: 80px;")
            ui.label("Scheduled Time").style("flex: 2; min-width: 180px;")
            ui.label("User").style("flex: 1; min-width: 100px;")
            ui.label("Status").style("flex: 1; min-width: 100px;")
            ui.label("Actions").style("flex: 1; min-width: 120px;")

        for row in scheduled_job_rows(scheduled_jobs):
            job_id, metadata, scheduled_time, user, status = (
                row.job_id,
                row.metadata,
                row.scheduled_time,
                row.user,
                row.status,
            )

            with (
                ui.row()
                .style(
                    "width: 100%; min-width: 700px; padding: 8px 10px; border-bottom: 1px solid #ddd; align-items: center;"
                )
                .classes("dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800")
            ):
                ui.button(
                    str(job_id),
                    on_click=lambda j=job_id, m=metadata: self._show_job_metadata_dialog(ui, j, m),
                    color="primary",
                    icon="info",
                ).style("flex: 1; min-width: 80px; font-weight: 500;")
                ui.label(str(scheduled_time)).style("flex: 2; min-width: 180px;").classes(
                    "text-slate-700 dark:text-slate-400"
                )
                ui.label(str(user)).style("flex: 1; min-width: 100px;").classes("text-slate-700 dark:text-slate-400")
                ui.label(str(status)).style("flex: 1; min-width: 100px;").classes("text-slate-700 dark:text-slate-400")
                with ui.row().style("flex: 1; min-width: 120px; gap: 8px;"):
                    ui.button(
                        "Cancel",
                        on_click=lambda j=job_id: self.dialogs.confirm_cancel_scheduled_job_by_id(j),
                    ).props("color=red flat")

    def _show_job_metadata_dialog(self, ui, job_id, metadata):
        self.service.pause()

        def close_dialog():
            dialog.close()
            self.service.resume()

        with ui.dialog() as dialog, ui.card().style("min-width: 400px;").classes("dark:!bg-slate-900"):
            ui.label(f"Job Metadata for ID: {job_id}").style("font-weight: bold; font-size: 1.1em;")
            if metadata:
                for k in sorted(metadata.keys()):
                    v = metadata[k]
                    if k == "script_path":
                        try:
                            v_list = json.loads(v) if isinstance(v, str) else v
                            v = ", ".join(str(item) for item in v_list)
                        except Exception:
                            pass
                    with ui.row():
                        ui.label(f"{k}:").style("font-weight: bold; width: 120px;")
                        ui.label(str(v)).style("flex: 1;")
            else:
                ui.label("No metadata found.")
            ui.button("Close", on_click=close_dialog)
        dialog.open()


def _usage_text(summary):
    cpu, memory = usage_cells(summary)
    return f"{cpu} · {memory}" if cpu or memory else "–"


def _usage_chart_options(points):
    """ECharts options: CPU % (left axis) and memory in MB (right axis) over time."""
    cpu = [[int(p["t"] * 1000), p.get("cpu", 0)] for p in points]
    memory = [[int(p["t"] * 1000), round(p.get("rss", 0) / 1024**2, 1)] for p in points]
    return {
        "tooltip": {"trigger": "axis"},
        "legend": {"data": ["CPU %", "Memory MB"], "bottom": 0},
        "grid": {"left": 50, "right": 60, "top": 40, "bottom": 60},
        "xAxis": {"type": "time"},
        "yAxis": [{"type": "value", "name": "CPU %", "min": 0}, {"type": "value", "name": "MB", "min": 0}],
        "series": [
            {"name": "CPU %", "type": "line", "showSymbol": False, "data": cpu},
            {"name": "Memory MB", "type": "line", "showSymbol": False, "yAxisIndex": 1, "data": memory},
        ],
    }
