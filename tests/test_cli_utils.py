"""Tests for CLI utility functions."""

from unittest.mock import patch

from desto.cli.utils import setup_logging


class TestSetupLogging:
    """Test logging setup."""

    @patch("desto.cli.utils.logger")
    def test_setup_logging_default(self, mock_logger):
        """Test logging setup with default parameters."""
        setup_logging()

        mock_logger.remove.assert_called_once()
        assert mock_logger.add.call_count == 1

    @patch("desto.cli.utils.logger")
    def test_setup_logging_with_file(self, mock_logger):
        """Test logging setup with log file."""
        setup_logging(level="DEBUG", log_file="/tmp/test.log")

        mock_logger.remove.assert_called_once()
        assert mock_logger.add.call_count == 2  # Console + file

    @patch("desto.cli.utils.logger")
    def test_setup_logging_different_levels(self, mock_logger):
        """Test logging setup with different levels."""
        setup_logging(level="WARNING")

        mock_logger.remove.assert_called_once()
        mock_logger.add.assert_called()
