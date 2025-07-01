"""Tests for CLI utility functions."""

from datetime import datetime
from unittest.mock import patch

from desto.cli.utils import (
    format_duration,
    format_timestamp,
    setup_logging,
    truncate_text,
    validate_session_name,
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


class TestValidateSessionName:
    """Test session name validation."""

    def test_validate_empty_name(self):
        """Test validation of empty session name."""
        assert validate_session_name("") is False
        assert validate_session_name(None) is False

    def test_validate_valid_names(self):
        """Test validation of valid session names."""
        assert validate_session_name("simple") is True
        assert validate_session_name("with-dashes") is True
        assert validate_session_name("with_underscores") is True
        assert validate_session_name("with123numbers") is True
        assert validate_session_name("session.name") is True

    def test_validate_invalid_names(self):
        """Test validation of invalid session names."""
        assert validate_session_name('with"quotes') is False
        assert validate_session_name("with'quotes") is False
        assert validate_session_name("with\\backslash") is False
        assert validate_session_name("with\nnewline") is False
        assert validate_session_name("with\rcarriage") is False
        assert validate_session_name("with\ttab") is False


class TestTruncateText:
    """Test text truncation."""

    def test_truncate_short_text(self):
        """Test truncating text shorter than max length."""
        text = "short"
        result = truncate_text(text, 10)
        assert result == "short"

    def test_truncate_exact_length(self):
        """Test truncating text at exact max length."""
        text = "exactly10!"
        result = truncate_text(text, 10)
        assert result == "exactly10!"

    def test_truncate_long_text(self):
        """Test truncating text longer than max length."""
        text = "this is a very long text that needs truncation"
        result = truncate_text(text, 20)
        assert result == "this is a very lo..."
        assert len(result) == 20

    def test_truncate_very_short_max_length(self):
        """Test truncating with very short max length."""
        text = "longtext"
        result = truncate_text(text, 3)
        assert result == "..."

    def test_truncate_max_length_less_than_ellipsis(self):
        """Test truncating with max length less than ellipsis."""
        text = "longtext"
        result = truncate_text(text, 2)
        assert result == ".."
        assert len(result) == 2

    def test_truncate_max_length_zero(self):
        """Test truncating with max length of zero."""
        text = "anytext"
        result = truncate_text(text, 0)
        assert result == ""

    def test_truncate_unicode_text(self):
        """Test truncating text with unicode characters."""
        text = "Hello 世界 🌍"
        result = truncate_text(text, 8)
        assert result == "Hello..."
        assert len(result) == 8
