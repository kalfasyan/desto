"""Core data models for session and job management."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


class SessionStatus(Enum):
    STARTING = "starting"
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"
    SCHEDULED = "scheduled"


class JobStatus(Enum):
    QUEUED = "queued"
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"
    SCHEDULED = "scheduled"


@dataclass
class DestoJob:
    """Represents a single script execution within a session."""

    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    command: str = ""
    script_path: str = ""
    status: JobStatus = JobStatus.QUEUED
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    exit_code: Optional[int] = None
    error_message: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for Redis storage."""
        return {
            "job_id": self.job_id,
            "session_id": self.session_id,
            "command": self.command,
            "script_path": self.script_path,
            "status": self.status.value,
            "start_time": self.start_time.isoformat() if self.start_time else "",
            "end_time": self.end_time.isoformat() if self.end_time else "",
            "exit_code": str(self.exit_code) if self.exit_code is not None else "",
            "error_message": self.error_message or "",
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DestoJob":
        """Create from dictionary (Redis data)."""
        return cls(
            job_id=data.get("job_id", ""),
            session_id=data.get("session_id", ""),
            command=data.get("command", ""),
            script_path=data.get("script_path", ""),
            status=JobStatus(data.get("status", "queued")),
            start_time=datetime.fromisoformat(data["start_time"]) if data.get("start_time") else None,
            end_time=datetime.fromisoformat(data["end_time"]) if data.get("end_time") else None,
            exit_code=int(data["exit_code"]) if data.get("exit_code") else None,
            error_message=data.get("error_message") or None,
        )


@dataclass
class DestoSession:
    """Represents a tmux session that can run multiple jobs."""

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_name: str = ""
    tmux_session_name: str = ""
    status: SessionStatus = SessionStatus.STARTING
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    last_heartbeat: Optional[datetime] = None
    job_ids: List[str] = field(default_factory=list)
    tmux_active: bool = False  # New field: is the tmux session active?
    at_job_id: Optional[str] = None  # System 'at' job ID if scheduled

    def to_dict(self) -> dict:
        """Convert to dictionary for Redis storage."""
        return {
            "session_id": self.session_id,
            "session_name": self.session_name,
            "tmux_session_name": self.tmux_session_name,
            "status": self.status.value,
            "start_time": self.start_time.isoformat() if self.start_time else "",
            "end_time": self.end_time.isoformat() if self.end_time else "",
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else "",
            "job_ids": ",".join(self.job_ids),
            "tmux_active": str(self.tmux_active),
            "at_job_id": self.at_job_id or "",
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DestoSession":
        """Create from dictionary (Redis data)."""
        # Handle bytes from Redis
        if data and isinstance(list(data.values())[0], bytes):
            data = {k.decode("utf-8") if isinstance(k, bytes) else k: v.decode("utf-8") if isinstance(v, bytes) else v for k, v in data.items()}
        return cls(
            session_id=data.get("session_id", ""),
            session_name=data.get("session_name", ""),
            tmux_session_name=data.get("tmux_session_name", ""),
            status=SessionStatus(data.get("status", "starting")),
            start_time=datetime.fromisoformat(data["start_time"]) if data.get("start_time") else None,
            end_time=datetime.fromisoformat(data["end_time"]) if data.get("end_time") else None,
            last_heartbeat=datetime.fromisoformat(data["last_heartbeat"]) if data.get("last_heartbeat") else None,
            job_ids=data.get("job_ids", "").split(",") if data.get("job_ids") else [],
            tmux_active=(str(data.get("tmux_active", "False")).lower() == "true"),
            at_job_id=data.get("at_job_id") or None,
        )


@dataclass
class FavoriteCommand:
    """Represents a favorite command saved by the user."""

    favorite_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    command: str = ""
    created_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    use_count: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary for Redis storage."""
        return {
            "favorite_id": self.favorite_id,
            "name": self.name,
            "command": self.command,
            "created_at": self.created_at.isoformat() if self.created_at else "",
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else "",
            "use_count": str(self.use_count),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FavoriteCommand":
        """Create from dictionary (Redis data)."""
        # Handle bytes from Redis
        if data and isinstance(list(data.values())[0], bytes):
            data = {k.decode("utf-8") if isinstance(k, bytes) else k: v.decode("utf-8") if isinstance(v, bytes) else v for k, v in data.items()}
        return cls(
            favorite_id=data.get("favorite_id", ""),
            name=data.get("name", ""),
            command=data.get("command", ""),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
            last_used_at=datetime.fromisoformat(data["last_used_at"]) if data.get("last_used_at") else None,
            use_count=int(data.get("use_count", 0)),
        )
