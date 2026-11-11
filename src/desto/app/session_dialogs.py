"""Confirmation dialogs, the live log viewer and the clean-up actions behind them."""

from loguru import logger
from nicegui import ui

from desto.app.log_tailer import LogTailer
from desto.app.session_format import decode_hash


class SessionDialogsMixin:
    """Dialogs and clean-up actions of TmuxManager.

    Every dialog pauses the dashboard timers while it is open (pause_updates/resume_updates).
    Expects the host class to provide redis_client, desto_manager, LOG_DIR, ui and the
    session and scheduled-job methods the dialogs call.
    """

    def _resume(self):
        if self.resume_updates:
            self.resume_updates()

    # --- Confirmations -------------------------------------------------------------

    def confirm_cancel_scheduled_job_by_id(self, at_job_id):
        """Show a confirmation dialog before canceling a scheduled job by at_job_id.
        Pauses updates while dialog is open.
        """
        if self.pause_updates:
            self.pause_updates()

        def do_cancel():
            self.cancel_scheduled_job(at_job_id)
            dialog.close()
            self._resume()
            # Force UI refresh
            self.update_sessions_status()

        def cancel():
            dialog.close()
            self._resume()

        with ui.dialog() as dialog, ui.card().style("min-width: 400px;"):
            self.telemetry_event("confirm_cancel_scheduled_job.open", {"at_job_id": str(at_job_id)})
            ui.label(f"Are you sure you want to cancel scheduled job {at_job_id}?").style("font-size: 1.1em; font-weight: bold; color: #d32f2f; margin-bottom: 10px;")
            recurrence = self._get_recurring_info(at_job_id)
            if recurrence:
                ui.label(f"This job is part of a recurring schedule ({recurrence[1]}). Cancelling it stops all future runs.").classes("text-slate-600 dark:text-slate-400")

            def _cancel():
                cancel()
                self.telemetry_event("confirm_cancel_scheduled_job.cancel", {"at_job_id": str(at_job_id)})

            def _confirm():
                do_cancel()
                self.telemetry_event("confirm_cancel_scheduled_job.confirm", {"at_job_id": str(at_job_id)})

            with ui.row().style("gap: 10px; justify-content: flex-end; width: 100%; margin-top: 20px;"):
                ui.button("Cancel", on_click=_cancel).props("color=grey")
                ui.button("Confirm Cancel", color="red", on_click=_confirm).props("icon=delete_forever")
        dialog.open()

    def confirm_clear_history(self):
        """Show confirmation dialog before clearing session history. Pauses updates while dialog is open."""
        if self.pause_updates:
            self.pause_updates()

        def close_dialog():
            dialog.close()
            self._resume()

        with ui.dialog() as dialog, ui.card().style("min-width: 400px;").classes("dark:!bg-slate-900"):
            self.telemetry_event("confirm_clear_history.open", {})
            ui.label("⚠️ Clear Session History").style("font-size: 1.3em; font-weight: bold; color: #d32f2f; margin-bottom: 10px;")
            ui.label("This will permanently delete all session history from Redis.").style("margin-bottom: 15px;")
            ui.label("This action cannot be undone.").style("margin-bottom: 20px;").classes("text-slate-600 dark:text-slate-400")

            def _close_and_telemetry_cancel():
                close_dialog()
                self.telemetry_event("confirm_clear_history.cancel", {})

            def _clear_and_telemetry_confirm():
                self.clear_session_history()
                close_dialog()
                self.telemetry_event("confirm_clear_history.confirm", {})

            with ui.row().style("gap: 10px; justify-content: flex-end; width: 100%;"):
                ui.button("Cancel", on_click=_close_and_telemetry_cancel).props("color=grey")
                ui.button("Clear History", color="red", on_click=_clear_and_telemetry_confirm).props("icon=delete_forever")
        dialog.open()

    def confirm_clear_logs(self):
        """Show confirmation dialog before clearing log files. Pauses updates while dialog is open."""
        log_dir = self.LOG_DIR
        log_files = []
        if log_dir.exists():
            log_files = list(log_dir.glob("*.log"))
        if not log_files:
            ui.notification("No log files found to clear", type="info")
            return
        if self.pause_updates:
            self.pause_updates()

        def close_dialog():
            dialog.close()
            self._resume()

        with ui.dialog() as dialog, ui.card().style("min-width: 400px;").classes("dark:!bg-slate-900"):
            self.telemetry_event("confirm_clear_logs.open", {"num_files": len(log_files)})
            ui.label("🗂️ Clear Log Files").style("font-size: 1.3em; font-weight: bold; color: #ff9800; margin-bottom: 10px;")
            ui.label(f"This will permanently delete {len(log_files)} log file(s) from:").style("margin-bottom: 10px;")
            ui.label(str(log_dir)).style("font-family: monospace; padding: 5px; border-radius: 3px; margin-bottom: 15px;").classes("bg-slate-100 dark:!bg-slate-800")
            ui.label("Files to be deleted:").style("font-weight: bold; margin-bottom: 5px;")
            shown = log_files if len(log_files) <= 5 else log_files[:3]
            for log_file in shown:
                ui.label(f"• {log_file.name}").style("margin-left: 10px; font-family: monospace; font-size: 0.9em;")
            if len(log_files) > 5:
                ui.label(f"• ... and {len(log_files) - 3} more files").style("margin-left: 10px; font-size: 0.9em;").classes("text-slate-600")

            def _close_logs_cancel():
                close_dialog()
                self.telemetry_event("confirm_clear_logs.cancel", {})

            def _confirm_clear_logs():
                self.clear_log_files()
                close_dialog()
                self.telemetry_event("confirm_clear_logs.confirm", {})

            with ui.row().style("gap: 10px; justify-content: flex-end; width: 100%; margin-top: 20px;"):
                ui.button("Cancel", on_click=_close_logs_cancel).props("color=grey")
                ui.button("Clear Log Files", color="orange", on_click=_confirm_clear_logs).props("icon=folder_delete")
        dialog.open()

    def confirm_kill_session(self, session_name):
        """Displays a confirmation dialog before killing a tmux session and pauses updates."""
        logger.debug(f"User requested to kill session: {session_name}")
        if self.pause_updates:
            self.pause_updates()

        with self.ui.dialog() as dialog, self.ui.card():
            self.telemetry_event("confirm_kill_session.open", {"session": session_name})
            self.ui.label(f"Are you sure you want to kill the session '{session_name}'?")

            def _confirm_kill():
                logger.info(f"User confirmed killing session: {session_name}")
                self.telemetry_event("confirm_kill_session.confirm", {"session": session_name})
                self.kill_tmux_session(session_name)
                dialog.close()
                self.resume_updates()

            def _cancel_kill():
                logger.debug(f"User cancelled killing session: {session_name}")
                self.telemetry_event("confirm_kill_session.cancel", {"session": session_name})
                dialog.close()
                self.resume_updates()

            with self.ui.row():
                self.ui.button("Yes", on_click=_confirm_kill).props("color=red")
                self.ui.button("No", on_click=_cancel_kill)

        dialog.open()

    def confirm_clear_session(self, session_name, ui):
        """Show confirmation dialog before clearing a session (deletes log and removes from Redis)."""
        if self.pause_updates:
            self.pause_updates()

        def do_clear():
            self.clear_session(session_name, ui)
            dialog.close()
            self._resume()

        def cancel():
            dialog.close()
            self._resume()

        with ui.dialog() as dialog, ui.card().style("min-width: 400px;"):
            self.telemetry_event("confirm_clear_session.open", {"session": session_name})
            ui.label(f"Are you sure you want to clear session '{session_name}'?").style("font-size: 1.1em; font-weight: bold; color: #ff9800; margin-bottom: 10px;")
            ui.label("This will delete its log file and remove it from the sessions table.").style("margin-bottom: 15px;")

            def _cancel_clear_session():
                cancel()
                self.telemetry_event("confirm_clear_session.cancel", {"session": session_name})

            def _confirm_clear_session():
                do_clear()
                self.telemetry_event("confirm_clear_session.confirm", {"session": session_name})

            with ui.row().style("gap: 10px; justify-content: flex-end; width: 100%; margin-top: 20px;"):
                ui.button("Cancel", on_click=_cancel_clear_session).props("color=grey")
                ui.button("Clear Session", color="orange", on_click=_confirm_clear_session).props("icon=delete_forever")
        dialog.open()

    def confirm_kill_all_sessions(self):
        """Displays a confirmation dialog before killing all tmux sessions and scheduled jobs, and pauses updates."""
        if self.pause_updates:
            self.pause_updates()

        sessions_status = self.check_sessions()
        session_count = len(sessions_status)
        scheduled_jobs = self.get_scheduled_jobs()
        job_count = len(scheduled_jobs)

        if session_count == 0 and job_count == 0:
            msg = "No active sessions or scheduled jobs to clear."
            logger.info(msg)
            self.ui.notification(msg, type="info")
            self._resume()
            return

        running_sessions, finished_sessions = self._split_running_finished(sessions_status)
        running_count = len(running_sessions)
        finished_count = len(finished_sessions)

        def do_kill_all():
            self._notify_kill_all_result(*self.kill_all_sessions_and_jobs())
            dialog.close()
            self._resume()

        def cancel_kill_all():
            logger.debug("User cancelled kill all sessions operation")
            dialog.close()
            self._resume()

        with self.ui.dialog() as dialog, self.ui.card().style("min-width: 500px;"):
            self.ui.label("⚠️ Clear All Jobs").style("font-size: 1.3em; font-weight: bold; color: #d32f2f; margin-bottom: 10px;")

            warning_parts = []
            if session_count > 0:
                if running_count > 0 and finished_count > 0:
                    warning_parts.append(f"{session_count} sessions ({running_count} running, {finished_count} finished)")
                elif running_count > 0:
                    warning_parts.append(f"{running_count} RUNNING sessions")
                else:
                    warning_parts.append(f"{finished_count} finished sessions")
            if job_count > 0:
                warning_parts.append(f"{job_count} scheduled jobs")

            warning_text = "This will clear:\n• " + "\n• ".join(warning_parts)
            if running_count > 0:
                warning_text += "\n\n⚠️ This may interrupt active processes!"
            self.ui.label(warning_text).style("margin-bottom: 15px; white-space: pre-line;")

            if running_count > 0:
                self.ui.label("Running sessions:").style("font-weight: bold; margin-bottom: 5px;")
                for session in running_sessions[:5]:
                    self.ui.label(f"• {session}").style("margin-left: 10px; color: #d32f2f;")
                if len(running_sessions) > 5:
                    self.ui.label(f"• ... and {len(running_sessions) - 5} more").style("margin-left: 10px; color: #666;")

            if job_count > 0:
                self.ui.label("Scheduled jobs:").style("font-weight: bold; margin-bottom: 5px; margin-top: 10px;")
                for job in scheduled_jobs[:5]:
                    self.ui.label(f"• Job {job['id']}: {job['datetime']}").style("margin-left: 10px; color: #ff9800;")
                if len(scheduled_jobs) > 5:
                    self.ui.label(f"• ... and {len(scheduled_jobs) - 5} more").style("margin-left: 10px; color: #666;")

            with self.ui.row().style("margin-top: 20px; gap: 10px;"):
                self.ui.button("Cancel", on_click=cancel_kill_all).props("color=grey")
                self.ui.button("Clear All Jobs", color="red", on_click=do_kill_all).props("icon=delete_forever")

        dialog.open()

    def _split_running_finished(self, sessions_status):
        """Split session names by their Redis job status; unknown statuses count as running."""
        running, finished = [], []
        for session_name in sessions_status.keys():
            try:
                job_status = self.desto_manager.get_job_status(session_name)
                if job_status in ["finished", "failed"]:
                    finished.append(session_name)
                else:
                    running.append(session_name)
            except Exception as e:
                logger.warning(f"Could not get status for session {session_name}: {e}")
                running.append(session_name)
        return running, finished

    def _notify_kill_all_result(self, session_success, session_total, job_success, job_total, error_messages):
        results = []
        if session_total > 0:
            if session_success == session_total:
                results.append(f"Successfully cleared all {session_total} sessions")
            else:
                results.append(f"Cleared {session_success}/{session_total} sessions")
        if job_total > 0:
            if job_success == job_total:
                results.append(f"Successfully cancelled all {job_total} scheduled jobs")
            else:
                results.append(f"Cancelled {job_success}/{job_total} scheduled jobs")
        if not results:
            results.append("No items to clear")

        msg = ". ".join(results) + "."
        if error_messages:
            msg += f" Errors: {'; '.join(error_messages[:3])}"  # Show first 3 errors
            logger.warning(msg)
            self.ui.notification(msg, type="warning")
        else:
            logger.success(msg)
            self.ui.notification(msg, type="positive")

    # --- Live log viewer -------------------------------------------------------------

    def view_log(self, session_name, ui):
        """Pauses the app and opens a dialog that live-tails the session's log file (last 100 lines, then follows)."""
        logger.debug(f"User requested to view log for session: {session_name}")
        if self.pause_updates:
            self.pause_updates()

        log_file = self.get_log_file(session_name)
        tailer = LogTailer(log_file)
        closed = False

        def close_dialog():
            nonlocal closed
            if closed:
                return
            closed = True
            try:
                timer.cancel()
            except Exception:
                logger.debug(f"Failed to cancel log follow timer for session: {session_name}")
            try:
                dialog.close()
            except Exception:
                logger.debug(f"Failed to close log dialog for session: {session_name}")
            logger.debug(f"User closed log view for session: {session_name}")
            self._resume()

        def push_new_lines():
            for line in tailer.poll():
                log_view.push(line)

        def set_live_state(active):
            status_badge.text = "LIVE" if active else "ENDED"
            status_badge.props(f"color={'positive' if active else 'grey'}")

        def refresh():
            try:
                push_new_lines()
            except Exception as e:
                logger.error(f"Error refreshing log view for session {session_name}: {e}")
            set_live_state(self.is_tmux_session_active(session_name))

        def tick():
            if closed or not auto_refresh.value:
                return
            try:
                push_new_lines()
            except Exception as e:
                logger.error(f"Error following log for session {session_name}: {e}")
                log_view.push(f"[desto] log follow error: {e}")
                timer.cancel()
                return
            if not self.is_tmux_session_active(session_name):
                try:
                    push_new_lines()  # One final read after the session ended
                except Exception as e:
                    logger.error(f"Error during final log read for session {session_name}: {e}")
                    log_view.push(f"[desto] log follow error: {e}")
                set_live_state(False)
                timer.cancel()

        def download_log():
            if not log_file.exists():
                ui.notification(f"Log file for session '{session_name}' not found.", type="warning")
                return
            ui.download.file(log_file, filename=f"{session_name}.log", media_type="text/plain")

        initial_lines = tailer.initial_lines(100)
        is_active = self.is_tmux_session_active(session_name)

        with (
            ui.dialog() as dialog,
            ui.card().style("width: 100%; height: 80%;").classes("dark:!bg-slate-900"),
        ):
            with ui.row().style("align-items: center; gap: 10px;"):
                ui.label(f"Log for session '{session_name}'").style("font-weight: bold;").classes("flex-grow")
                status_badge = ui.badge("LIVE" if is_active else "ENDED", color="positive" if is_active else "grey")

            log_view = ui.log(max_lines=2000).style("width: 100%; height: 65vh;").classes("font-mono text-xs dark:text-slate-300")
            if initial_lines:
                logger.debug(f"Successfully read {len(initial_lines)} lines from log file for session: {session_name}")
                for line in initial_lines:
                    log_view.push(line)
            elif not log_file.exists():
                log_view.push(f"Log file for session '{session_name}' not found.")
                logger.warning(f"Log file not found for session: {session_name}")

            with ui.row().style("align-items: center; gap: 10px;"):
                auto_refresh = ui.switch("Auto-refresh", value=True)
                ui.button("Refresh now", on_click=refresh).props("color=primary flat")
                ui.button("Download log", on_click=download_log).props("color=secondary flat")
                ui.button("Close", on_click=close_dialog).props("color=primary")
            timer = ui.timer(1.0, tick)

        dialog.on("hide", lambda: close_dialog())
        dialog.on_value_change(lambda e: close_dialog() if not e.value else None)
        dialog.open()

    # --- Clean-up actions ------------------------------------------------------------

    def clear_session_history(self):
        """Clear all session history from Redis."""
        try:
            all_keys = list(self.redis_client.redis.scan_iter(match="desto:session:*"))
            if not all_keys:
                ui.notification("No session history to clear", type="info")
                return
            deleted_count = 0
            for key in all_keys:
                try:
                    self.redis_client.redis.delete(key)
                    deleted_count += 1
                except Exception as e:
                    logger.error(f"Error deleting session key {key}: {e}")
            if deleted_count > 0:
                msg = f"Successfully cleared {deleted_count} session record(s) from history"
                logger.info(msg)
                ui.notification(msg, type="positive")
                self.update_sessions_status()
            else:
                ui.notification("No sessions were cleared", type="warning")
        except Exception as e:
            error_msg = f"Error clearing session history: {e}"
            logger.error(error_msg)
            ui.notification(error_msg, type="negative")

    def clear_log_files(self):
        """Clear all log files from the logs directory."""
        log_dir = self.LOG_DIR
        if not log_dir.exists():
            ui.notification("Logs directory not found", type="warning")
            return
        try:
            all_files = list(log_dir.glob("*.log")) + list(log_dir.glob("*.finished"))
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
            if deleted_count > 0:
                msg = f"Successfully deleted {deleted_count} log file(s)"
                if errors:
                    msg += f" ({len(errors)} errors)"
                logger.info(msg)
                ui.notification(msg, type="positive")
                self.update_sessions_status()
            if errors:
                error_summary = "; ".join(errors[:3])
                if len(errors) > 3:
                    error_summary += f" (+{len(errors) - 3} more)"
                ui.notification(f"Errors: {error_summary}", type="warning")
        except Exception as e:
            error_msg = f"Error clearing log files: {e}"
            logger.error(error_msg)
            ui.notification(error_msg, type="negative")

    def clear_session(self, session_name, ui):
        """Deletes the session's log file and removes the session from Redis, then refreshes the UI."""
        log_file = self.get_log_file(session_name)
        log_deleted = False
        try:
            if log_file.exists():
                log_file.unlink()
                log_deleted = True
                logger.info(f"Deleted log file for session: {session_name}")
        except Exception as e:
            logger.warning(f"Failed to delete log file for session {session_name}: {e}")

        redis_deleted = False
        try:
            found_key = self._find_session_key(session_name)
            if found_key:
                if self.redis_client.redis.delete(found_key):
                    redis_deleted = True
                    logger.info(f"Deleted Redis session: {session_name} (key: {found_key})")
            else:
                logger.warning(f"Could not find Redis key for session '{session_name}'")
        except Exception as e:
            logger.warning(f"Failed to delete Redis session {session_name}: {e}")

        if log_deleted and redis_deleted:
            ui.notification(f"Session '{session_name}' cleared (log and Redis entry deleted)", type="positive")
        elif log_deleted:
            ui.notification(f"Session '{session_name}' log deleted, but failed to remove from Redis", type="warning")
        elif redis_deleted:
            ui.notification(f"Session '{session_name}' removed from Redis, but log file not found/deleted", type="warning")
        else:
            ui.notification(f"Failed to clear session '{session_name}' (see logs)", type="negative")

        self.update_sessions_status(force=True)

    def _find_session_key(self, session_name):
        """Return the Redis key of the session hash whose display name is session_name, or None."""
        for key in list(self.redis_client.redis.scan_iter(match="desto:session:*")):
            session_data = self.redis_client.redis.hgetall(key)
            if session_data:
                session_info = decode_hash(session_data)
                if session_info.get("session_name", key.replace("desto:session:", "")) == session_name:
                    return key
        return None
