"""Scheduled ('at') jobs for the dashboard: listing, cancelling and the internal fallback scheduler."""

import subprocess
import threading
from datetime import datetime

import redis
from loguru import logger
from nicegui import ui

from desto.app.session_format import decode_hash, extract_at_command, format_scheduled_datetime, parse_atq_output


class ScheduledJobsMixin:
    """Scheduled-job operations of TmuxManager.

    Expects the host class to provide redis_client, desto_manager and logger.
    """

    def get_scheduled_jobs(self, include_command=True):
        """Get a list of scheduled jobs from the 'at' command.
        Returns a list of dictionaries with job info. include_command=False skips the
        per-job `at -c` call (the dashboard table does not show the command).
        """
        try:
            result = subprocess.run(["atq"], capture_output=True, text=True)
            if result.returncode != 0:
                self.logger.debug("No scheduled jobs found or 'at' command failed")
                return []

            jobs = []
            for job_id, date_time, user in parse_atq_output(result.stdout):
                command = self._get_scheduled_job_command(job_id) if include_command else ""
                jobs.append({"id": job_id, "datetime": self._format_scheduled_datetime(date_time), "raw_datetime": date_time, "user": user, "command": command})
            return jobs
        except Exception as e:
            # Log once at warning level (e.g. `at` not installed), then quietly, since the dashboard polls this.
            if not getattr(self, "_scheduled_jobs_warned", False):
                self.logger.warning(f"Failed to get scheduled jobs: {e}")
                self._scheduled_jobs_warned = True
            else:
                self.logger.debug(f"Failed to get scheduled jobs: {e}")
            return []

    def _get_scheduled_job_command(self, job_id):
        """Get the actual command for a scheduled job."""
        try:
            result = subprocess.run(["at", "-c", job_id], capture_output=True, text=True)
            if result.returncode == 0:
                return extract_at_command(result.stdout)
            return "Unknown command"
        except Exception:
            return "Unknown command"

    def _format_scheduled_datetime(self, date_time):
        """Format datetime from atq output for better display."""
        return format_scheduled_datetime(date_time)

    def _get_scheduled_jobs_with_metadata(self):
        """Return atq jobs plus the Redis metadata for each, without spawning `at -c` per job."""
        jobs = self.get_scheduled_jobs(include_command=False)
        if not jobs:
            return []
        try:
            pipe = self.redis_client.redis.pipeline(transaction=False)
            for job in jobs:
                pipe.hgetall(f"desto:atjob:{job.get('id')}")
            for job, metadata in zip(jobs, pipe.execute()):
                job["metadata"] = decode_hash(metadata) if metadata else None
        except Exception as e:
            logger.debug(f"Could not read scheduled job metadata: {e}")
            for job in jobs:
                job.setdefault("metadata", None)
        return jobs

    def _get_recurring_info(self, at_job_id):
        """Return (schedule_id, description) if the at job is a queued run of a recurring schedule, else None."""
        try:
            metadata = self.redis_client.redis.hgetall(f"desto:atjob:{at_job_id}")
        except Exception:
            return None
        if metadata and metadata.get("recurring_id"):
            return metadata["recurring_id"], metadata.get("recurrence", "recurring")
        return None

    def cancel_scheduled_job(self, at_job_id, session_name=None):
        """Cancels a scheduled job using AtJobManager and optionally updates the session status in Redis.
        If session_name is not provided, attempts to find the session by at_job_id in Redis.
        """
        from desto.redis.at_job_manager import AtJobManager

        try:
            recurrence = self._get_recurring_info(at_job_id)
            if recurrence:
                from desto.redis.recurring import RecurringScheduleManager

                if RecurringScheduleManager(self.redis_client).cancel(recurrence[0]):
                    ui.notification(f"Cancelled recurring schedule ({recurrence[1]})", type="positive")
                else:
                    ui.notification(f"Failed to cancel recurring schedule for job {at_job_id}", type="negative")
                return

            at_job_manager = AtJobManager(self.redis_client)
            success = at_job_manager.cancel(str(at_job_id))
            if success:
                ui.notification(f"Cancelled scheduled job {at_job_id}", type="positive")
                self._mark_cancelled_session(at_job_id, session_name)
            else:
                ui.notification(f"Failed to cancel scheduled job {at_job_id}", type="negative")
        except Exception as e:
            ui.notification(f"Failed to cancel scheduled job {at_job_id}: {e}", type="negative")

    def _mark_cancelled_session(self, at_job_id, session_name=None):
        """Mark the session behind a cancelled at job as failed, looking it up by name or by at_job_id."""
        if not self.desto_manager:
            return
        session_manager = self.desto_manager.session_manager
        session_obj = None
        if session_name:
            session_obj = session_manager.get_session_by_name(session_name)
        else:
            for s in session_manager.list_all_sessions():
                if getattr(s, "at_job_id", None) == str(at_job_id):
                    session_obj = s
                    break
        if session_obj:
            session_obj.status = "failed"
            session_obj.at_job_id = None
            session_manager._update_session(session_obj)

    def kill_scheduled_jobs(self):
        """Kill all scheduled jobs and return summary.
        Returns a tuple: (success_count, total_count, error_messages).
        """
        if self.desto_manager:
            try:
                from desto.redis.recurring import RecurringScheduleManager

                RecurringScheduleManager(self.redis_client).cancel_all(remove_pending_jobs=False)
            except Exception as e:
                logger.warning(f"Failed to cancel recurring schedules: {e}")

        jobs = self.get_scheduled_jobs()
        total_count = len(jobs)
        success_count = 0
        error_messages = []

        if total_count == 0:
            logger.debug("No scheduled jobs found to kill")
            return (0, 0, [])

        logger.info(f"Attempting to cancel {total_count} scheduled jobs")

        for job in jobs:
            try:
                subprocess.run(["atrm", job["id"]], check=True)
                success_count += 1
                logger.info(f"Successfully removed scheduled job: {job['id']}")
            except subprocess.CalledProcessError as e:
                error_msg = f"Failed to remove job '{job['id']}': {e}"
                error_messages.append(error_msg)
                logger.warning(error_msg)
            except Exception as e:
                error_msg = f"Unexpected error removing job '{job['id']}': {str(e)}"
                error_messages.append(error_msg)
                logger.error(error_msg)

        logger.info(f"Cancelled {success_count}/{total_count} scheduled jobs")
        return (success_count, total_count, error_messages)

    def check_and_run_scheduled_jobs(self):
        """Check for overdue scheduled jobs in Redis and run them if 'at' hasn't."""
        if not self.desto_manager:
            return

        try:
            for key in self.redis_client.redis.scan_iter(match="desto:atjob:*"):
                try:
                    self._run_if_overdue(key)
                except Exception as e:
                    self.logger.error(f"Error processing scheduled job key {key}: {e}")
        except Exception as e:
            self.logger.error(f"Error scanning scheduled jobs: {e}")

    def _run_if_overdue(self, key):
        """Run the scheduled job stored at `key` if its time has passed and nobody else picked it up."""
        metadata = self.redis_client.redis.hgetall(key)
        if not metadata:
            return
        metadata = decode_hash(metadata)

        # Only jobs still waiting to run; ones the internal scheduler handled are skipped.
        if metadata.get("status") != "scheduled":
            return

        scheduled_time_str = metadata.get("scheduled_time")
        if not scheduled_time_str:
            return
        try:
            scheduled_time = datetime.fromisoformat(scheduled_time_str)
        except Exception:
            return

        if datetime.now() < scheduled_time:
            return

        job_id = metadata.get("job_id")
        self.logger.info(f"Internal scheduler detected overdue job {job_id} (scheduled for {scheduled_time_str}). Running now.")

        if self._claim_scheduled_job(key):
            # Run the command in a separate thread to not block the UI
            threading.Thread(target=self._run_overdue_job, args=(metadata.get("command"), job_id, key), daemon=True).start()

    def _claim_scheduled_job(self, key):
        """Atomically move a job from 'scheduled' to 'running_internal' so only one runner executes it."""
        with self.redis_client.redis.pipeline() as pipe:
            try:
                pipe.watch(key)
                # Read using the main client, not the pipeline
                current_status = self.redis_client.redis.hget(key, "status")
                if current_status and (current_status == "scheduled" or (hasattr(current_status, "decode") and current_status.decode() == "scheduled")):
                    pipe.multi()
                    pipe.hset(key, "status", "running_internal")
                    pipe.execute()
                    return True
                pipe.unwatch()
            except redis.WatchError:
                pass
        return False

    def _run_overdue_job(self, command, job_id, key):
        try:
            # shell=True because the command (built to call start_scheduled_session) contains quotes and arguments
            subprocess.run(command, shell=True, check=True)
            self.logger.info(f"Successfully started overdue job {job_id}")
            # Mark as finished so it is not picked up again and is hidden from the scheduled jobs view
            self.redis_client.redis.hset(key, "status", "finished_internal")
        except Exception as e:
            self.logger.error(f"Failed to run overdue job {job_id}: {e}")
            self.redis_client.redis.hset(key, "status", "failed_internal")
