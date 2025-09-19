import json
import os
import re
import subprocess
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger

# Import DestoRedisClient from sibling module
from .client import DestoRedisClient


class AtJobManager:
    """Wrapper for scheduling, listing, and canceling jobs with 'at', and for extracting the system 'at' job ID. Now supports storing job metadata in Redis."""

    def __init__(self, redis_client: Optional[DestoRedisClient] = None):
        """Optionally pass a DestoRedisClient to enable Redis metadata tracking."""
        self.redis_client = redis_client

    def schedule(
        self,
        command: str,
        time_spec: str,
        session_name: str = "",
        script_path: list = None,  # Accept a list
        arguments: str = "",
    ) -> Optional[str]:
        """Schedule a command with 'at'. Returns the at job ID as a string, or None on failure. Also stores job metadata in Redis if enabled."""
        try:
            request_time = datetime.now()
            # Convert time_spec if needed
            parts = time_spec.split()
            if len(parts) == 2 and "-" in parts[1]:
                # Convert "2025-07-21" to "Jul 21 2025"
                date_obj = datetime.strptime(parts[1], "%Y-%m-%d")
                date_str = date_obj.strftime("%b %d %Y")
                at_args = [parts[0], date_str]
            else:
                at_args = [time_spec]

            proc = subprocess.run(
                ["at"] + at_args,
                input=command,
                capture_output=True,
                text=True,
                check=False,  # Don't raise on error, handle manually
            )
            output = proc.stdout + proc.stderr  # Combine both outputs

            if proc.returncode != 0:
                logger.error(f"Failed to schedule job with 'at': {proc.stderr.strip()}")
                return None

            match = re.search(r"job (\d+)", output)
            if not match:
                logger.error(f"No job ID found in at output. Output: {output.strip()}")
                return None

            job_id = match.group(1)
            scheduled_time_match = re.search(r"at (.+)", output)
            scheduled_time_str = scheduled_time_match.group(1) if scheduled_time_match else ""
            try:
                scheduled_time = datetime.strptime(scheduled_time_str, "%a %b %d %H:%M:%S %Y")
            except Exception:
                scheduled_time = None

            metadata = {
                "job_id": job_id,
                "command": command,
                "request_time": request_time.isoformat(),
                "scheduled_time": scheduled_time.isoformat() if scheduled_time else scheduled_time_str,
                "user": os.getenv("USER", "unknown"),
                "status": "scheduled",
                "creation_time": request_time.isoformat(),
                "queue": "a",
                "session_name": session_name,
                "script_path": json.dumps(script_path if script_path else []),  # Serialize as JSON string
                "arguments": arguments,
                "error_message": "",
                "execution_result": "",
            }
            if self.redis_client and self.redis_client.is_connected():
                key = f"desto:atjob:{job_id}"
                self.redis_client.redis.hmset(key, metadata)
                # If a session_name was provided, try to link this at job id back to the session record.
                # First attempt a direct lookup using client's helper; if that fails, fall back to scanning.
                try:
                    if session_name:
                        # Try direct key lookup (some deployments may store sessions keyed by name)
                        try_key = None
                        try:
                            try_key = self.redis_client.get_session_key(session_name)
                        except Exception:
                            try_key = None

                        linked = False
                        if try_key:
                            try:
                                sdata = self.redis_client.redis.hgetall(try_key)
                                if sdata and sdata.get("session_name") == session_name:
                                    self.redis_client.redis.hset(try_key, "at_job_id", job_id)
                                    linked = True
                            except Exception:
                                linked = False

                        if not linked:
                            # Fallback: scan all sessions and match by session_name field
                            for s_key in self.redis_client.redis.scan_iter(match="desto:session:*"):
                                try:
                                    sdata = self.redis_client.redis.hgetall(s_key)
                                    if not sdata:
                                        continue
                                    if sdata.get("session_name") == session_name:
                                        self.redis_client.redis.hset(s_key, "at_job_id", job_id)
                                        linked = True
                                        break
                                except Exception:
                                    # Non-fatal: continue scanning other keys
                                    continue
                except Exception as e:
                    logger.debug(f"Failed to link at_job_id to session '{session_name}': {e}")
            return job_id
        except Exception as e:
            logger.error(f"Exception during scheduling: {e}")
            return None

    def list_jobs(self) -> List[Dict[str, Any]]:
        """List all jobs scheduled with 'atq'. Returns a list of dicts with job info and metadata from Redis if available."""
        jobs = []
        try:
            proc = subprocess.run(["atq"], capture_output=True, text=True, check=False)
            for line in proc.stdout.splitlines():
                # Example: 123\tSat Jul 20 12:00:00 2025 a user
                parts = line.split()
                if len(parts) >= 7:
                    job_id = parts[0]
                    date_str = " ".join(parts[1:6])
                    queue = parts[6]
                    user = parts[7] if len(parts) > 7 else ""
                    job_info = {
                        "id": job_id,
                        "datetime": date_str,
                        "queue": queue,
                        "user": user,
                    }
                    # Add metadata from Redis if available
                    if self.redis_client and self.redis_client.is_connected():
                        key = f"desto:atjob:{job_id}"
                        metadata = self.redis_client.redis.hgetall(key)
                        if metadata:
                            job_info["metadata"] = metadata
                    jobs.append(job_info)
        except Exception as e:
            logger.debug(f"Failed to list jobs with 'atq': {e}")
        return jobs

    def get_job_command(self, job_id: str) -> str:
        """Get the command for a scheduled job by job ID."""
        try:
            proc = subprocess.run(["at", "-c", str(job_id)], capture_output=True, text=True, check=True)
            return proc.stdout
        except Exception as e:
            return f"Unknown command (error: {e})"

    def get_job_metadata(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve job metadata from Redis for a given job_id."""
        if self.redis_client and self.redis_client.is_connected():
            key = f"desto:atjob:{job_id}"
            metadata = self.redis_client.redis.hgetall(key)
            return metadata if metadata else None
        return None

    def cancel(self, job_id: str) -> bool:
        """Cancel a scheduled job by job ID. Returns True if successful. Updates status in Redis if enabled."""
        try:
            subprocess.run(["atrm", str(job_id)], check=True)
            # Update status in Redis
            if self.redis_client and self.redis_client.is_connected():
                key = f"desto:atjob:{job_id}"
                if self.redis_client.redis.exists(key):
                    self.redis_client.redis.hset(key, "status", "cancelled")
            return True
        except Exception as e:
            logger.debug(f"Failed to cancel job {job_id} with 'atrm': {e}")
            return False
