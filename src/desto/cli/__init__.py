"""Desto CLI package for command-line interface functionality."""

from .main import app
from .session_manager import CLISessionManager

__version__ = "0.1.0"
__all__ = ["app", "CLISessionManager"]
