"""Utility functions for the desto CLI."""

from datetime import datetime
from typing import Optional

from loguru import logger


def format_duration(seconds: int) -> str:
    """Format a duration in seconds to a human-readable string.

    Args:
        seconds: Duration in seconds

    Returns:
        Formatted duration string (e.g., "1h 23m", "45s", "2d 5h")
    """
    if seconds < 60:
        return f"{seconds}s"

    minutes = seconds // 60
    remaining_seconds = seconds % 60

    if minutes < 60:
        if remaining_seconds > 0:
            return f"{minutes}m {remaining_seconds}s"
        return f"{minutes}m"

    hours = minutes // 60
    remaining_minutes = minutes % 60

    if hours < 24:
        if remaining_minutes > 0:
            return f"{hours}h {remaining_minutes}m"
        return f"{hours}h"

    days = hours // 24
    remaining_hours = hours % 24

    if remaining_hours > 0:
        return f"{days}d {remaining_hours}h"
    return f"{days}d"


def format_timestamp(timestamp: float) -> str:
    """Format a Unix timestamp to a human-readable string.

    Args:
        timestamp: Unix timestamp

    Returns:
        Formatted timestamp string
    """
    dt = datetime.fromtimestamp(timestamp)
    now = datetime.now()

    # If it's today, just show the time
    if dt.date() == now.date():
        return dt.strftime("%H:%M:%S")

    # If it's this year, show date without year
    if dt.year == now.year:
        return dt.strftime("%b %d %H:%M")

    # Otherwise, show full date
    return dt.strftime("%Y-%m-%d %H:%M")


def setup_logging(level: str = "INFO", log_file: Optional[str] = None) -> None:
    """Setup logging configuration for the CLI.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional log file path
    """
    # Remove default logger
    logger.remove()

    # Add console handler with custom format
    logger.add(
        lambda msg: print(msg, end=""),
        level=level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
        colorize=True,
    )

    # Add file handler if specified
    if log_file:
        logger.add(
            log_file,
            level=level,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
            rotation="10 MB",
            retention="7 days",
        )


def validate_session_name(name: str) -> bool:
    """Validate a session name for tmux compatibility.

    Args:
        name: The session name to validate

    Returns:
        True if valid, False otherwise
    """
    if not name:
        return False

    # tmux session names cannot contain certain characters
    invalid_chars = ['"', "'", "\\", "\n", "\r", "\t"]
    for char in invalid_chars:
        if char in name:
            return False

    return True


def truncate_text(text: str, max_length: int) -> str:
    """Truncate text to a maximum length with ellipsis.

    Args:
        text: Text to truncate
        max_length: Maximum length including ellipsis

    Returns:
        Truncated text with ellipsis if needed
    """
    if len(text) <= max_length:
        return text

    if max_length <= 3:
        return "..."[:max_length]

    return text[: max_length - 3] + "..."
