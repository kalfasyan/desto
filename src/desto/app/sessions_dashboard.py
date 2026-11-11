"""Rendering of the sessions dashboard: stats cards, sessions table and scheduled jobs table."""

import json
import sys
import time

from loguru import logger
from nicegui import ui

from desto.app.session_format import (
    classify_session,
    decode_hash,
    format_seconds,
    parse_iso,
    seconds_since,
    session_row_times,
    session_sort_key,
    summarize_jobs,
)


class SessionsDashboardMixin:
    """Dashboard rendering for TmuxManager.

    Expects the host class to provide sessions_container, redis_client, status_filter,
    pause_updates/resume_updates and the session/scheduled-job/dialog methods it calls.
    """

    # Kept as attributes for callers that use the old private names.
    _decode_hash = staticmethod(decode_hash)
    _classify_session = staticmethod(classify_session)
    _format_seconds = staticmethod(format_seconds)

    def update_sessions_status(self, ui_manager=None, force=True):
        """Render the sessions dashboard (stats cards, sessions table, scheduled jobs).

        Data is gathered in a few cheap batched calls. With force=False (the periodic timer),
        the dashboard is only rebuilt when something actually changed, so the page does not
        flicker and scroll position or open menus are not reset. Live durations of running
        sessions are updated in place by tick_live_durations().
        """
        sessions_status = self.get_all_sessions_status()
        tmux_active = set(self.check_sessions().keys())
        job_info = self._job_info_by_session()
        scheduled_jobs = self._get_scheduled_jobs_with_metadata()

        signature = json.dumps([sessions_status, sorted(tmux_active), job_info, scheduled_jobs, self.status_filter], sort_keys=True, default=str)
        if not force and signature == self._last_render_signature:
            return
        self._last_render_signature = signature

        counts = self._count_by_category(sessions_status, tmux_active, job_info)
        self.clear_sessions_container()

        def render():
            self.render_sessions_controls_and_stats(sessions_status, ui_manager, counts=counts)
            self.add_sessions_table(sessions_status, self.ui, tmux_active=tmux_active, job_info=job_info, scheduled_jobs=scheduled_jobs)

        self.add_to_sessions_container(render)

    def tick_live_durations(self):
        """Update the duration labels of running sessions in place (no table rebuild)."""
        for label, start_dt in self._live_duration_labels:
            try:
                label.text = format_seconds(seconds_since(start_dt))
            except Exception:
                pass

    # --- Data gathering -------------------------------------------------------------

    def _job_info_by_session(self):
        """Read every job once and summarise it per session id.

        Returns {session_id: {"status", "exit_code", "command"}}. This replaces the per-row
        get_job_status() lookups, which scanned all sessions and all jobs for every row.
        """
        result = {}
        try:
            r = self.redis_client.redis
            keys = list(r.scan_iter(match="desto:job:*", count=500))
            if not keys:
                return result
            pipe = r.pipeline(transaction=False)
            for key in keys:
                pipe.hgetall(key)
            jobs_by_session = {}
            for data in pipe.execute():
                if data:
                    job = decode_hash(data)
                    jobs_by_session.setdefault(job.get("session_id", ""), []).append(job)
        except Exception as e:
            logger.debug(f"Could not read jobs from Redis: {e}")
            return result

        for session_id, jobs in jobs_by_session.items():
            result[session_id] = summarize_jobs(jobs)
        return result

    def _count_by_category(self, sessions_status, tmux_active=None, job_info=None):
        if tmux_active is None:
            tmux_active = set(self.check_sessions().keys())
        job_info = job_info or {}
        counts = {"total": 0, "running": 0, "finished": 0, "failed": 0}
        for name, session in sessions_status.items():
            category, _, _ = classify_session(name, session, name in tmux_active, job_info)
            if category == "scheduled":
                continue
            counts["total"] += 1
            counts[category] += 1
        return counts

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
                ui.button("Refresh", icon="refresh", on_click=lambda: self.update_sessions_status(force=True)).props("flat")
                ui.button("Clear History", icon="delete_sweep", color="red", on_click=self.confirm_clear_history).props("flat")
                ui.button("Clear Logs", icon="folder_delete", color="orange", on_click=self.confirm_clear_logs).props("flat")

        self._render_atd_warning()

        # Counts use the same classification as the table rows, and clicking a card filters the table.
        if counts is None:
            counts = self._count_by_category(sessions_status)
        self._render_stats_cards(counts)

    def _render_atd_warning(self):
        from desto.redis.at_job_manager import AtJobManager

        if self._is_atd_running_cached(AtJobManager):
            return
        with ui.row().style("width: 100%; align-items: center; margin-bottom: 20px; padding: 15px; border-radius: 8px;").classes("bg-orange-1 dark:bg-orange-9") as warning_row:
            ui.icon("warning", color="orange").style("font-size: 2em; margin-right: 15px;")
            with ui.column().style("flex-grow: 1;"):
                ui.label("System 'at' daemon is not running").style("font-weight: bold; color: #ef6c00;")
                ui.label("Scheduled jobs will be managed by desto's internal scheduler while the dashboard is open. For background execution, please enable 'atd' on your system.").style("font-size: 0.9em;")
                if sys.platform == "darwin":
                    ui.label("On macOS: sudo launchctl load -w /System/Library/LaunchDaemons/com.apple.atrun.plist").style("font-family: monospace; font-size: 0.8em; margin-top: 5px;")
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
                card = ui.card().style("padding: 15px; min-width: 120px; text-align: center; cursor: pointer;").classes("bg-white dark:!bg-slate-900")
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
            tmux_active = set(self.check_sessions().keys())
        if job_info is None:
            job_info = self._job_info_by_session()
        self._live_duration_labels = []

        self._render_sessions_header(ui)

        rows = self._session_rows(sessions_status, tmux_active, job_info)
        if not rows and self.status_filter:
            ui.label(f"No {self.status_filter} sessions. Click the card again to show all.").style("padding: 12px;").classes("text-slate-500")

        for session_name, session, is_active, status, status_color in rows:
            command = job_info.get(session.get("session_id", ""), {}).get("command", "")
            self._render_session_row(ui, session_name, session, is_active, status, status_color, command)

        if scheduled_jobs is None:
            scheduled_jobs = self._get_scheduled_jobs_with_metadata()
        if scheduled_jobs:
            self._render_scheduled_jobs_table(ui, scheduled_jobs)

    def _session_rows(self, sessions_status, tmux_active, job_info):
        """Return the non-scheduled sessions matching the status filter, newest first.

        Each row is a (session_name, session, tmux_active, status_label, status_color) tuple.
        """
        rows = []
        for session_name, session in sessions_status.items():
            is_active = session_name in tmux_active
            category, status, status_color = classify_session(session_name, session, is_active, job_info)
            if category == "scheduled":
                continue
            if self.status_filter and category != self.status_filter:
                continue
            rows.append((session_sort_key(session), session_name, session, is_active, status, status_color))
        rows.sort(key=lambda r: r[0], reverse=True)
        return [row[1:] for row in rows]

    @staticmethod
    def _render_sessions_header(ui):
        with ui.row().style("width: 100%; min-width: 1100px; padding: 12px; border-radius: 4px; margin-bottom: 10px; font-weight: bold;").classes("bg-slate-100 dark:!bg-slate-800 text-slate-900 dark:text-slate-100"):
            ui.label("Session Name").style("flex: 2; min-width: 150px;")
            ui.label("Status").style("flex: 1; min-width: 100px;")
            ui.label("Job Duration").style("flex: 1; min-width: 120px;")
            ui.label("Session Duration").style("flex: 1; min-width: 130px;")
            ui.label("Started").style("flex: 2; min-width: 140px;")
            ui.label("Finished").style("flex: 2; min-width: 140px;")
            ui.label("Tmux Active").style("flex: 1; min-width: 100px;")
            ui.label("Actions").style("flex: 1; min-width: 120px;")

    def _render_session_row(self, ui, session_name, session, tmux_active_row, status, status_color, command):
        times = session_row_times(session)
        with ui.row().style("width: 100%; min-width: 1100px; padding: 10px 12px; border-bottom: 1px solid #ddd; align-items: center;").classes("dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800"):
            ui.label(session.get("session_name", session_name)).style("flex: 2; min-width: 150px; font-weight: 500;")
            ui.label(status).style(f"flex: 1; min-width: 100px; color: {status_color}; font-weight: 500;")
            ui.label(times["job_duration"]).style("flex: 1; min-width: 120px;").classes("text-slate-700 dark:text-slate-400")
            duration_label = ui.label(times["session_duration"]).style("flex: 1; min-width: 130px;").classes("text-slate-700 dark:text-slate-400")
            if times["start_time"] and not times["end_time"] and tmux_active_row:
                try:
                    self._live_duration_labels.append((duration_label, parse_iso(times["start_time"])))
                except Exception:
                    pass
            ui.label(times["started"]).style("flex: 2; min-width: 140px; font-size: 0.9em;").classes("text-slate-600 dark:text-slate-500")
            ui.label(times["finished"]).style("flex: 2; min-width: 140px; font-size: 0.9em;").classes("text-slate-600 dark:text-slate-500")
            icon = "check_circle" if tmux_active_row else "cancel"
            color = "#4CAF50" if tmux_active_row else "#F44336"
            ui.icon(icon).style(f"flex: 1; min-width: 100px; color: {color}; font-size: 1.5em; text-align: center;")
            with ui.row().style("flex: 1; min-width: 120px; gap: 8px;"):
                # Kill while running; once the tmux session is gone, the slot becomes Re-run.
                if tmux_active_row:
                    ui.button(
                        "Kill",
                        on_click=lambda s=session_name: self.confirm_kill_session(s),
                    ).props("color=red flat")
                elif command:
                    ui.button(
                        "Re-run",
                        on_click=lambda s=session_name, c=command: self.rerun_session(s, c),
                    ).props("color=green flat").tooltip("Run the same command again in a new session")
                else:
                    ui.button(
                        "Kill",
                        on_click=lambda: ui.notification("Cannot kill: no active tmux session for this entry.", type="warning"),
                    ).props("color=red flat disabled")
                ui.button(
                    "View Log",
                    on_click=lambda s=session_name: self.view_log(s, ui),
                ).props("color=blue flat")
                ui.button(
                    "Clear",
                    on_click=lambda s=session_name: self.confirm_clear_session(s, ui),
                ).props("color=orange flat")

    # --- Scheduled jobs table (atq + Redis metadata) ---------------------------------

    def _render_scheduled_jobs_table(self, ui, scheduled_jobs):
        with ui.row().style("margin-top: 40px; margin-bottom: 10px;"):
            ui.label("Scheduled Jobs (with metadata)").style("font-size: 1.2em; font-weight: bold;")

        with ui.row().style("width: 100%; min-width: 700px; padding: 10px; border-radius: 4px; font-weight: bold;").classes("bg-slate-100 dark:!bg-slate-800 text-slate-900 dark:text-slate-100"):
            ui.label("Job ID").style("flex: 1; min-width: 80px;")
            ui.label("Scheduled Time").style("flex: 2; min-width: 180px;")
            ui.label("User").style("flex: 1; min-width: 100px;")
            ui.label("Status").style("flex: 1; min-width: 100px;")
            ui.label("Actions").style("flex: 1; min-width: 120px;")

        for job in scheduled_jobs:
            job_id = job.get("id", "?")
            metadata = job.get("metadata")
            status = metadata.get("status", "scheduled") if metadata else "scheduled"

            # Hide jobs the internal scheduler has already handled
            if status in ["finished_internal", "running_internal"]:
                continue

            if metadata and metadata.get("recurring_id"):
                status = f"{status} · {metadata.get('recurrence', 'recurring')}"

            scheduled_time = metadata.get("scheduled_time", job.get("datetime", "?")) if metadata else job.get("datetime", "?")
            user = metadata.get("user", job.get("user", "?")) if metadata else job.get("user", "?")

            with ui.row().style("width: 100%; min-width: 700px; padding: 8px 10px; border-bottom: 1px solid #ddd; align-items: center;").classes("dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800"):
                ui.button(
                    str(job_id),
                    on_click=lambda j=job_id, m=metadata: self._show_job_metadata_dialog(ui, j, m),
                    color="primary",
                    icon="info",
                ).style("flex: 1; min-width: 80px; font-weight: 500;")
                ui.label(str(scheduled_time)).style("flex: 2; min-width: 180px;").classes("text-slate-700 dark:text-slate-400")
                ui.label(str(user)).style("flex: 1; min-width: 100px;").classes("text-slate-700 dark:text-slate-400")
                ui.label(str(status)).style("flex: 1; min-width: 100px;").classes("text-slate-700 dark:text-slate-400")
                with ui.row().style("flex: 1; min-width: 120px; gap: 8px;"):
                    ui.button(
                        "Cancel",
                        on_click=lambda j=job_id: self.confirm_cancel_scheduled_job_by_id(j),
                    ).props("color=red flat")

    def _show_job_metadata_dialog(self, ui, job_id, metadata):
        if self.pause_updates:
            self.pause_updates()

        def close_dialog():
            dialog.close()
            if self.resume_updates:
                self.resume_updates()

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
