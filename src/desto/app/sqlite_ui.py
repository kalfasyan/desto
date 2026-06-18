"""SQLite Session History UI tab for the dashboard."""

from datetime import datetime

from loguru import logger
from nicegui import ui


# Status → (color, icon) mapping for badges
_STATUS_STYLE = {
    "finished": ("positive", "check_circle"),
    "failed": ("negative", "error"),
    "running": ("warning", "play_circle"),
    "starting": ("info", "hourglass_top"),
    "scheduled": ("accent", "schedule"),
}

_PAGE_SIZE = 20


class SQLiteHistoryTab:
    """Tab for inspecting the SQLite database and restarting cached sessions."""

    def __init__(self, ui_manager, desto_manager):
        self.ui_manager = ui_manager
        self.desto_manager = desto_manager
        self.sqlite_store = desto_manager.sqlite_store
        self.sessions_container = None
        self.stats_container = None
        self.search_input = None
        self.status_filter = None
        self._current_offset = 0

    # ─── Public ────────────────────────────────────────────────────────

    def build(self):
        """Build the Session History tab UI."""
        with ui.card().props("flat").classes(
            "modern-card w-full p-6 dark:!bg-slate-900 rounded-xl shadow-sm"
        ):
            # Header row
            with ui.row().classes("w-full justify-between items-center mb-6"):
                ui.label("Session History").classes(
                    "text-lg font-bold text-slate-900 dark:text-white"
                )
                with ui.row().classes("items-center gap-3"):
                    self.status_filter = (
                        ui.select(
                            options=["All", "running", "finished", "failed", "scheduled"],
                            value="All",
                            on_change=lambda _: self._on_filter_change(),
                        )
                        .props("dense outlined rounded")
                        .classes("w-36")
                    )
                    self.search_input = (
                        ui.input(placeholder="Search by name...")
                        .on("keyup", lambda _: self._on_filter_change())
                        .props("dense outlined rounded")
                        .classes("w-64")
                    )
                    ui.button(icon="refresh", on_click=self._on_filter_change).props(
                        "flat round color=primary dense"
                    )
                    ui.button(
                        "Clear History",
                        icon="delete_sweep",
                        on_click=self._confirm_clear_history,
                    ).props("flat color=negative dense")

            # Stats row
            self.stats_container = ui.row().classes("w-full gap-4 mb-6")
            self._render_stats()

            # Session cards
            self.sessions_container = ui.column().classes("w-full")
            self.refresh_sessions_list()

    # ─── Stats ─────────────────────────────────────────────────────────

    def _render_stats(self):
        """Render summary stat chips."""
        self.stats_container.clear()
        with self.stats_container:
            total = self.sqlite_store.get_session_count()
            finished = self.sqlite_store.get_session_count(status="finished")
            failed = self.sqlite_store.get_session_count(status="failed")
            running = self.sqlite_store.get_session_count(status="running")

            for label, value, color in [
                ("Total", total, "primary"),
                ("Finished", finished, "positive"),
                ("Failed", failed, "negative"),
                ("Running", running, "warning"),
            ]:
                with ui.row().classes(
                    "items-center gap-2 px-4 py-2 rounded-lg bg-slate-50 dark:bg-slate-800"
                ):
                    ui.label(str(value)).classes(f"text-xl font-bold text-{color}")
                    ui.label(label).classes(
                        "text-xs uppercase tracking-wider text-slate-500"
                    )

    # ─── Session list ──────────────────────────────────────────────────

    def refresh_sessions_list(self):
        """Refresh the session list from SQLite."""
        self.sessions_container.clear()
        self._current_offset = 0
        self._load_sessions_page()

    def _on_filter_change(self):
        """Handle status filter or search changes."""
        self._render_stats()
        self.refresh_sessions_list()

    def _get_status_filter(self):
        """Return the current status filter value or None for 'All'."""
        val = self.status_filter.value if self.status_filter else "All"
        return None if val == "All" else val

    def _load_sessions_page(self):
        """Load the next page of sessions into the container."""
        search_query = (
            self.search_input.value.strip() if self.search_input and self.search_input.value else ""
        )
        status = self._get_status_filter()

        if search_query:
            sessions = self.sqlite_store.search_sessions(
                name_query=search_query,
                limit=_PAGE_SIZE,
                offset=self._current_offset,
                status=status,
            )
        else:
            sessions = self.sqlite_store.get_all_sessions(
                limit=_PAGE_SIZE,
                offset=self._current_offset,
                status=status,
            )

        if not sessions and self._current_offset == 0:
            with self.sessions_container:
                ui.label("No sessions found").classes(
                    "text-slate-400 italic py-8 text-center w-full"
                )
            return

        with self.sessions_container:
            with ui.grid(columns="repeat(auto-fill, minmax(340px, 1fr))").classes(
                "w-full gap-4"
            ):
                for session in sessions:
                    self._render_session_card(session)

            # "Load More" button when a full page was returned
            if len(sessions) == _PAGE_SIZE:
                self._current_offset += _PAGE_SIZE
                ui.button(
                    "Load More",
                    icon="expand_more",
                    on_click=lambda: self._load_more(),
                ).props("flat color=primary").classes("w-full mt-4")

    def _load_more(self):
        """Load the next page appending to the existing list."""
        # Remove the current "Load More" button before appending
        children = list(self.sessions_container)
        if children:
            last = children[-1]
            last.delete()
        self._load_sessions_page()

    # ─── Single session card ──────────────────────────────────────────

    def _render_session_card(self, session):
        """Render a card for a single session."""
        status_str = session.status.value if hasattr(session.status, "value") else str(session.status)
        color, icon = _STATUS_STYLE.get(status_str, ("grey", "help"))

        # Pre-fetch jobs to show command preview
        jobs = self.sqlite_store.get_jobs_for_session(session.session_id)
        has_command = jobs and jobs[0].command

        with ui.card().props("flat").classes(
            "modern-card p-5 dark:!bg-slate-900 rounded-xl shadow-sm "
            "border border-slate-100 dark:border-slate-800"
        ):
            with ui.column().classes("w-full gap-3"):
                # Top row: name + status badge
                with ui.row().classes("w-full justify-between items-start"):
                    with ui.column().classes("gap-1"):
                        ui.label(session.session_name).classes(
                            "text-base font-bold text-slate-900 dark:text-white"
                        )
                        ui.badge(status_str.upper(), color=color).props("dense outline")

                    ui.button(
                        icon="info",
                        on_click=lambda s=session: self._show_session_details(s.session_id),
                    ).props("flat round color=primary dense")

                # Command preview (from first job)
                if has_command:
                    cmd_display = jobs[0].command
                    if len(cmd_display) > 80:
                        cmd_display = cmd_display[:77] + "…"
                    ui.label(cmd_display).classes(
                        "font-mono text-xs p-3 rounded-lg bg-slate-50 dark:bg-slate-800 "
                        "text-slate-600 dark:text-slate-400 break-all w-full"
                    )

                # Timestamps
                with ui.column().classes("gap-1 text-xs text-slate-500 dark:text-slate-400"):
                    if session.start_time:
                        ui.label(f"Started: {_fmt_dt(session.start_time)}")
                    if session.end_time:
                        ui.label(f"Ended:   {_fmt_dt(session.end_time)}")
                    if session.start_time and session.end_time:
                        duration = session.end_time - session.start_time
                        ui.label(f"Duration: {_fmt_duration(duration)}").classes("font-semibold")

                # Job count
                if jobs:
                    with ui.row().classes("items-center gap-1 text-[10px] text-slate-400 uppercase tracking-wider"):
                        ui.icon("work", size="12px")
                        ui.label(f"{len(jobs)} job{'s' if len(jobs) != 1 else ''}")

                # Action buttons row at bottom
                with ui.row().classes("w-full justify-between items-center mt-1"):
                    # Restart button — prominent, only for finished/failed with a command
                    if status_str in ("finished", "failed") and has_command:
                        ui.button(
                            "Restart",
                            icon="replay",
                            on_click=lambda s=session: self._restart_session(s.session_id),
                        ).props("unelevated color=positive dense").classes("text-xs")
                    else:
                        ui.label("")  # spacer

                    ui.button(
                        icon="delete",
                        on_click=lambda s=session: self._delete_session(
                            s.session_id, s.session_name
                        ),
                    ).props("flat round color=negative dense")

    # ─── Session detail dialog ────────────────────────────────────────

    def _show_session_details(self, session_id: str):
        """Open a dialog showing full session details and its jobs."""
        session = self.sqlite_store.get_session(session_id)
        if not session:
            ui.notification("Session not found in database", type="warning")
            return

        status_str = session.status.value if hasattr(session.status, "value") else str(session.status)
        color, icon = _STATUS_STYLE.get(status_str, ("grey", "help"))

        with ui.dialog() as dialog:
            with ui.card().classes("p-6 w-[700px] max-h-[80vh] overflow-auto dark:!bg-slate-900"):
                # Header
                with ui.row().classes("w-full justify-between items-center mb-4"):
                    ui.label("Session Details").classes("text-xl font-bold")
                    ui.badge(status_str.upper(), color=color).props("outline")

                # Session info grid
                with ui.grid(columns=2).classes("w-full gap-x-6 gap-y-2 mb-6"):
                    for label, value in [
                        ("Session Name", session.session_name),
                        ("Session ID", session.session_id),
                        ("Tmux Session", session.tmux_session_name or "—"),
                        ("Tmux Active", "Yes" if session.tmux_active else "No"),
                        ("Start Time", _fmt_dt(session.start_time) if session.start_time else "—"),
                        ("End Time", _fmt_dt(session.end_time) if session.end_time else "—"),
                        ("Last Heartbeat", _fmt_dt(session.last_heartbeat) if session.last_heartbeat else "—"),
                        ("At Job ID", session.at_job_id or "—"),
                    ]:
                        ui.label(label).classes(
                            "text-xs uppercase tracking-wider text-slate-500 font-semibold"
                        )
                        ui.label(str(value)).classes(
                            "text-sm text-slate-800 dark:text-slate-200 font-mono break-all"
                        )

                    if session.start_time and session.end_time:
                        duration = session.end_time - session.start_time
                        ui.label("Duration").classes(
                            "text-xs uppercase tracking-wider text-slate-500 font-semibold"
                        )
                        ui.label(_fmt_duration(duration)).classes(
                            "text-sm text-slate-800 dark:text-slate-200 font-mono"
                        )

                # Jobs table
                jobs = self.sqlite_store.get_jobs_for_session(session_id)
                if jobs:
                    ui.separator().classes("my-4")
                    ui.label(f"Jobs ({len(jobs)})").classes("text-sm font-bold mb-2")

                    columns = [
                        {"name": "command", "label": "Command", "field": "command", "align": "left"},
                        {"name": "script", "label": "Script", "field": "script_path", "align": "left"},
                        {"name": "status", "label": "Status", "field": "status", "align": "center"},
                        {"name": "exit_code", "label": "Exit", "field": "exit_code", "align": "center"},
                        {"name": "start_time", "label": "Started", "field": "start_time", "align": "left"},
                        {"name": "end_time", "label": "Ended", "field": "end_time", "align": "left"},
                    ]
                    rows = []
                    for job in jobs:
                        job_status = job.status.value if hasattr(job.status, "value") else str(job.status)
                        rows.append({
                            "command": job.command or "—",
                            "script_path": job.script_path or "—",
                            "status": job_status,
                            "exit_code": str(job.exit_code) if job.exit_code is not None else "—",
                            "start_time": _fmt_dt(job.start_time) if job.start_time else "—",
                            "end_time": _fmt_dt(job.end_time) if job.end_time else "—",
                        })

                    ui.table(columns=columns, rows=rows).props(
                        "flat dense bordered separator=cell"
                    ).classes("w-full text-xs")

                    # Show error messages if any
                    for job in jobs:
                        if job.error_message:
                            with ui.card().classes("w-full p-3 mt-2 bg-red-50 dark:bg-red-900/20 rounded-lg"):
                                ui.label(f"Error (job {job.job_id[:8]}…):").classes(
                                    "text-xs font-bold text-red-600 dark:text-red-400"
                                )
                                ui.label(job.error_message).classes(
                                    "text-xs font-mono text-red-500 dark:text-red-300 break-all"
                                )
                else:
                    ui.label("No jobs recorded for this session.").classes(
                        "text-slate-400 italic text-sm mt-2"
                    )

                # Action buttons
                with ui.row().classes("w-full justify-between items-center mt-6"):
                    # Restart button in detail dialog
                    if status_str in ("finished", "failed") and jobs and jobs[0].command:
                        ui.button(
                            "Restart Session",
                            icon="replay",
                            on_click=lambda: (dialog.close(), self._restart_session(session_id)),
                        ).props("unelevated color=positive")
                    else:
                        ui.label("")  # spacer
                    ui.button("Close", on_click=dialog.close).props("flat color=primary")

        dialog.open()

    # ─── Restart session ──────────────────────────────────────────────

    def _restart_session(self, session_id: str):
        """Restart a finished/failed session by re-running its command(s)."""
        session = self.sqlite_store.get_session(session_id)
        if not session:
            ui.notification("Session not found", type="warning")
            return

        jobs = self.sqlite_store.get_jobs_for_session(session_id)
        if not jobs:
            ui.notification("No jobs found for this session — cannot restart", type="warning")
            return

        # Use the first job's command (most sessions are single-job)
        command = jobs[0].command
        if not command:
            ui.notification("No command found in session jobs", type="warning")
            return

        base_name = f"retry-{session.session_name}"
        session_name = self.ui_manager.tmux_manager.get_unique_session_name(base_name)

        try:
            self.ui_manager.tmux_manager.start_tmux_session(session_name, command, logger)
            ui.notification(f"Restarted session: {session_name}", type="positive")
        except Exception as e:
            logger.error(f"Failed to restart session: {e}")
            ui.notification(f"Failed to restart: {e}", type="negative")

    # ─── Delete session ───────────────────────────────────────────────

    def _delete_session(self, session_id: str, session_name: str):
        """Delete a session from SQLite with confirmation."""
        with ui.dialog() as confirm_dialog:
            with ui.card().classes("p-6 dark:!bg-slate-900"):
                ui.label(f"Delete '{session_name}' from history?").classes(
                    "text-lg font-bold mb-2"
                )
                ui.label(
                    "This will permanently remove the session and its jobs from the database."
                ).classes("text-slate-500 mb-6")
                with ui.row().classes("w-full justify-end gap-2"):
                    ui.button("Cancel", on_click=confirm_dialog.close).props(
                        "flat color=slate-500"
                    )
                    ui.button(
                        "Delete",
                        on_click=lambda: self._confirm_delete(
                            session_id, session_name, confirm_dialog
                        ),
                    ).props("unelevated color=negative")
        confirm_dialog.open()

    def _confirm_delete(self, session_id: str, session_name: str, dialog):
        """Execute session deletion after confirmation."""
        result = self.sqlite_store.delete_session(session_id)
        if result:
            ui.notification(f"Deleted: {session_name}", type="positive")
            dialog.close()
            self._render_stats()
            self.refresh_sessions_list()
        else:
            ui.notification("Failed to delete session", type="negative")

    # ─── Clear all history ────────────────────────────────────────────

    def _confirm_clear_history(self):
        """Show confirmation dialog before clearing all session history."""
        count = self.sqlite_store.get_session_count()
        if count == 0:
            ui.notification("No session history to clear", type="info")
            return

        with ui.dialog() as dialog:
            with ui.card().classes("p-6 dark:!bg-slate-900"):
                ui.label("Clear Session History").classes(
                    "text-lg font-bold text-red-600 mb-2"
                )
                ui.label(
                    f"This will permanently delete all {count} session(s) "
                    "and their associated jobs from the database."
                ).classes("text-slate-500 mb-2")
                ui.label("This action cannot be undone.").classes(
                    "text-slate-500 mb-6 font-semibold"
                )
                with ui.row().classes("w-full justify-end gap-2"):
                    ui.button("Cancel", on_click=dialog.close).props(
                        "flat color=slate-500"
                    )
                    ui.button(
                        "Clear All History",
                        icon="delete_sweep",
                        on_click=lambda: self._execute_clear_history(dialog),
                    ).props("unelevated color=negative")
        dialog.open()

    def _execute_clear_history(self, dialog):
        """Execute the history clear."""
        result = self.sqlite_store.clear_sessions_and_jobs()
        if result:
            ui.notification("Session history cleared", type="positive")
            dialog.close()
            self._render_stats()
            self.refresh_sessions_list()
        else:
            ui.notification("Failed to clear history", type="negative")


# ─── Helpers ──────────────────────────────────────────────────────────


def _fmt_dt(dt) -> str:
    """Format a datetime for display."""
    if not dt:
        return "—"
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except (ValueError, TypeError):
            return dt
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _fmt_duration(td) -> str:
    """Format a timedelta for display."""
    total_seconds = int(td.total_seconds())
    if total_seconds < 0:
        return "—"
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"
