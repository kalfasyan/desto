"""Tests for CLI utility functions."""

from datetime import datetime
from unittest.mock import patch

from desto.cli.utils import (
    format_duration,
    format_timestamp,
    setup_logging,
)


class TestFormatDuration:
    """Test duration formatting."""

    def test_format_seconds_only(self):
        """Test formatting durations under 1 minute."""
        assert format_duration(0) == "0s"
        assert format_duration(30) == "30s"
        assert format_duration(59) == "59s"

    def test_format_minutes_only(self):
        """Test formatting durations in minutes."""
        assert format_duration(60) == "1m"
        assert format_duration(120) == "2m"
        assert format_duration(3540) == "59m"

    def test_format_minutes_with_seconds(self):
        """Test formatting minutes with remaining seconds."""
        assert format_duration(90) == "1m 30s"
        assert format_duration(125) == "2m 5s"
        assert format_duration(3599) == "59m 59s"

    def test_format_hours_only(self):
        """Test formatting durations in hours."""
        assert format_duration(3600) == "1h"
        assert format_duration(7200) == "2h"
        assert format_duration(82800) == "23h"

    def test_format_hours_with_minutes(self):
        """Test formatting hours with remaining minutes."""
        assert format_duration(3660) == "1h 1m"
        assert format_duration(7380) == "2h 3m"
        assert format_duration(86100) == "23h 55m"

    def test_format_days_only(self):
        """Test formatting durations in days."""
        assert format_duration(86400) == "1d"
        assert format_duration(172800) == "2d"
        assert format_duration(604800) == "7d"

    def test_format_days_with_hours(self):
        """Test formatting days with remaining hours."""
        assert format_duration(90000) == "1d 1h"
        assert format_duration(176400) == "2d 1h"
        assert format_duration(608400) == "7d 1h"


class TestFormatTimestamp:
    """Test timestamp formatting."""

    def test_format_today_timestamp(self):
        """Test formatting timestamp from today."""
        now = datetime.now()
        timestamp = now.timestamp()

        result = format_timestamp(timestamp)

        # Should show only time for today
        assert ":" in result
        assert len(result.split(":")) == 3  # HH:MM:SS

    def test_format_this_year_timestamp(self):
        """Test formatting timestamp from this year but not today."""
        # Create a date from this year but not today
        this_year = datetime.now().year
        test_date = datetime(this_year, 1, 1, 12, 30, 45)
        timestamp = test_date.timestamp()

        result = format_timestamp(timestamp)

        # Should show month, day, and time (no year)
        assert "Jan" in result
        assert "01" in result
        assert "12:30" in result
        assert str(this_year) not in result

    def test_format_previous_year_timestamp(self):
        """Test formatting timestamp from previous year."""
        # Create a date from previous year
        prev_year = datetime.now().year - 1
        test_date = datetime(prev_year, 6, 15, 14, 20, 30)
        timestamp = test_date.timestamp()

        result = format_timestamp(timestamp)

        # Should show full date including year
        assert str(prev_year) in result
        assert "06-15" in result or "6-15" in result
        assert "14:20" in result


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
