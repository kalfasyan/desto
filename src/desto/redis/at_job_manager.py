import re
import subprocess
from typing import Dict, List, Optional


class AtJobManager:
    """
    Wrapper for scheduling, listing, and canceling jobs with 'at',
    and for extracting the system 'at' job ID.
    """

    @staticmethod
    def schedule(command: str, time_spec: str) -> Optional[str]:
        """
        Schedule a command with 'at'. Returns the at job ID as a string, or None on failure.
        """
        try:
            proc = subprocess.run(
                ["at", time_spec],
                input=command.encode(),
                capture_output=True,
                text=True,
                check=True,
            )
            # Output: job 123 at Sat Jul 20 12:00:00 2025
            match = re.search(r"job (\d+)", proc.stdout)
            if match:
                return match.group(1)
        except Exception as e:
            print(f"Failed to schedule job with 'at': {e}")
        return None

    @staticmethod
    def list_jobs() -> List[Dict[str, str]]:
        """
        List all jobs scheduled with 'atq'. Returns a list of dicts with job info.
        """
        jobs = []
        try:
            proc = subprocess.run(["atq"], capture_output=True, text=True, check=False)
            for line in proc.stdout.splitlines():
                # Example: 123	Sat Jul 20 12:00:00 2025 a user
                parts = line.split()
                if len(parts) >= 7:
                    job_id = parts[0]
                    date_str = " ".join(parts[1:6])
                    queue = parts[6]
                    user = parts[7] if len(parts) > 7 else ""
                    jobs.append(
                        {
                            "id": job_id,
                            "datetime": date_str,
                            "queue": queue,
                            "user": user,
                        }
                    )
        except Exception as e:
            print(f"Failed to list jobs with 'atq': {e}")
        return jobs

    @staticmethod
    def get_job_command(job_id: str) -> str:
        """
        Get the command for a scheduled job by job ID.
        """
        try:
            proc = subprocess.run(["at", "-c", str(job_id)], capture_output=True, text=True, check=True)
            return proc.stdout
        except Exception as e:
            return f"Unknown command (error: {e})"

    @staticmethod
    def cancel(job_id: str) -> bool:
        """
        Cancel a scheduled job by job ID. Returns True if successful.
        """
        try:
            subprocess.run(["atrm", str(job_id)], check=True)
            return True
        except Exception as e:
            print(f"Failed to cancel job {job_id} with 'atrm': {e}")
            return False
