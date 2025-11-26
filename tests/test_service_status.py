"""Tests for enhanced service status functionality.

Tests cover:
- Duration formatting for service uptime display
- Alert state loading from JSON files
- Pool status summary generation
- Service start time parsing from systemctl output

All tests mock external dependencies (systemctl, ZFS commands, file I/O).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from check_zpools.service_install import (
    _format_duration,
    _get_pool_status_summary,
    _get_service_start_time,
    _load_alert_state,
)


# ============================================================================
# Tests for _format_duration
# ============================================================================


class TestFormatDurationWithSeconds:
    """Tests for duration formatting with various second values."""

    def test_zero_seconds_shows_zero_s(self) -> None:
        """Zero duration should display as '0s'."""
        result = _format_duration(timedelta(seconds=0))
        assert result == "0s"

    def test_thirty_seconds_shows_seconds_only(self) -> None:
        """Sub-minute duration should show only seconds."""
        result = _format_duration(timedelta(seconds=30))
        assert result == "30s"

    def test_negative_duration_shows_zero_s(self) -> None:
        """Negative duration should be treated as zero."""
        result = _format_duration(timedelta(seconds=-100))
        assert result == "0s"


class TestFormatDurationWithMinutes:
    """Tests for duration formatting with minutes."""

    def test_one_minute_shows_minutes_only(self) -> None:
        """Exactly one minute should show '1m'."""
        result = _format_duration(timedelta(minutes=1))
        assert result == "1m"

    def test_five_minutes_thirty_seconds_shows_both(self) -> None:
        """Minutes and seconds should both appear."""
        result = _format_duration(timedelta(minutes=5, seconds=30))
        assert result == "5m 30s"

    def test_forty_five_minutes_shows_minutes_only(self) -> None:
        """Large minute value without seconds should show only minutes."""
        result = _format_duration(timedelta(minutes=45))
        assert result == "45m"


class TestFormatDurationWithHours:
    """Tests for duration formatting with hours."""

    def test_one_hour_shows_hours_only(self) -> None:
        """Exactly one hour should show '1h'."""
        result = _format_duration(timedelta(hours=1))
        assert result == "1h"

    def test_two_hours_fifteen_minutes_shows_both(self) -> None:
        """Hours and minutes should both appear."""
        result = _format_duration(timedelta(hours=2, minutes=15))
        assert result == "2h 15m"

    def test_three_hours_fifteen_minutes_thirty_seconds_shows_three_components(self) -> None:
        """Should show at most three components."""
        result = _format_duration(timedelta(hours=3, minutes=15, seconds=30))
        assert result == "3h 15m 30s"


class TestFormatDurationWithDays:
    """Tests for duration formatting with days."""

    def test_one_day_shows_days_only(self) -> None:
        """Exactly one day should show '1d'."""
        result = _format_duration(timedelta(days=1))
        assert result == "1d"

    def test_two_days_three_hours_shows_both(self) -> None:
        """Days and hours should both appear."""
        result = _format_duration(timedelta(days=2, hours=3))
        assert result == "2d 3h"

    def test_five_days_six_hours_fifteen_minutes_shows_three_components(self) -> None:
        """Should show at most three components (days, hours, minutes)."""
        result = _format_duration(timedelta(days=5, hours=6, minutes=15, seconds=30))
        assert result == "5d 6h 15m"

    def test_large_duration_truncates_to_three_parts(self) -> None:
        """Very large durations should still only show three components."""
        result = _format_duration(timedelta(days=100, hours=12, minutes=30, seconds=45))
        assert result == "100d 12h 30m"


# ============================================================================
# Tests for _load_alert_state
# ============================================================================


class TestLoadAlertStateWithMissingFile:
    """Tests for alert state loading when file doesn't exist."""

    def test_missing_file_returns_empty_dict(self, tmp_path: Path) -> None:
        """Non-existent state file should return empty dict."""
        with patch("check_zpools.service_install.CACHE_DIR", tmp_path):
            result = _load_alert_state()
            assert result == {}


class TestLoadAlertStateWithValidFile:
    """Tests for alert state loading with valid JSON files."""

    def test_valid_json_returns_parsed_data(self, tmp_path: Path) -> None:
        """Valid JSON state file should be parsed correctly."""
        state_file = tmp_path / "alert_state.json"
        state_data = {
            "version": 1,
            "alerts": {
                "rpool:device": {
                    "pool_name": "rpool",
                    "issue_category": "device",
                    "first_seen": "2025-11-26T08:00:00+00:00",
                    "last_alerted": "2025-11-26T10:00:00+00:00",
                    "alert_count": 3,
                    "last_severity": "CRITICAL",
                }
            },
        }
        state_file.write_text(json.dumps(state_data))

        with patch("check_zpools.service_install.CACHE_DIR", tmp_path):
            result = _load_alert_state()

        assert result["version"] == 1
        assert "alerts" in result
        assert "rpool:device" in result["alerts"]
        assert result["alerts"]["rpool:device"]["alert_count"] == 3

    def test_empty_alerts_returns_empty_alerts_dict(self, tmp_path: Path) -> None:
        """State file with empty alerts should return structure with empty alerts."""
        state_file = tmp_path / "alert_state.json"
        state_data = {"version": 1, "alerts": {}}
        state_file.write_text(json.dumps(state_data))

        with patch("check_zpools.service_install.CACHE_DIR", tmp_path):
            result = _load_alert_state()

        assert result["alerts"] == {}


class TestLoadAlertStateWithInvalidFile:
    """Tests for alert state loading with corrupt or invalid files."""

    def test_invalid_json_returns_empty_dict(self, tmp_path: Path) -> None:
        """Corrupt JSON should return empty dict."""
        state_file = tmp_path / "alert_state.json"
        state_file.write_text("not valid json {{{")

        with patch("check_zpools.service_install.CACHE_DIR", tmp_path):
            result = _load_alert_state()

        assert result == {}

    def test_empty_file_returns_empty_dict(self, tmp_path: Path) -> None:
        """Empty file should return empty dict."""
        state_file = tmp_path / "alert_state.json"
        state_file.write_text("")

        with patch("check_zpools.service_install.CACHE_DIR", tmp_path):
            result = _load_alert_state()

        assert result == {}


# ============================================================================
# Tests for _get_service_start_time
# ============================================================================


class TestGetServiceStartTimeWithRunningService:
    """Tests for service start time parsing when service is running."""

    def test_valid_timestamp_with_utc_returns_datetime(self) -> None:
        """Valid systemctl timestamp with UTC should be parsed to datetime."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "ActiveEnterTimestamp=Wed 2025-11-26 10:30:00 UTC"

        with patch("check_zpools.service_install._run_systemctl", return_value=mock_result):
            result = _get_service_start_time()

        assert result is not None
        assert result.year == 2025
        assert result.month == 11
        assert result.day == 26
        assert result.hour == 10
        assert result.minute == 30

    def test_valid_timestamp_with_cet_returns_datetime(self) -> None:
        """Valid systemctl timestamp with CET timezone should be parsed."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "ActiveEnterTimestamp=Wed 2025-11-26 12:14:25 CET"

        with patch("check_zpools.service_install._run_systemctl", return_value=mock_result):
            result = _get_service_start_time()

        assert result is not None
        assert result.year == 2025
        assert result.month == 11
        assert result.day == 26
        assert result.hour == 12
        assert result.minute == 14
        assert result.second == 25

    def test_na_timestamp_returns_none(self) -> None:
        """'n/a' timestamp (service never started) should return None."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "ActiveEnterTimestamp=n/a"

        with patch("check_zpools.service_install._run_systemctl", return_value=mock_result):
            result = _get_service_start_time()

        assert result is None


class TestGetServiceStartTimeWithErrors:
    """Tests for service start time parsing with error conditions."""

    def test_systemctl_failure_returns_none(self) -> None:
        """Failed systemctl command should return None."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with patch("check_zpools.service_install._run_systemctl", return_value=mock_result):
            result = _get_service_start_time()

        assert result is None

    def test_empty_output_returns_none(self) -> None:
        """Empty systemctl output should return None."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""

        with patch("check_zpools.service_install._run_systemctl", return_value=mock_result):
            result = _get_service_start_time()

        assert result is None

    def test_exception_returns_none(self) -> None:
        """Exception during systemctl call should return None."""
        with patch("check_zpools.service_install._run_systemctl", side_effect=RuntimeError("test")):
            result = _get_service_start_time()

        assert result is None

    def test_malformed_timestamp_returns_none(self) -> None:
        """Unparseable timestamp format should return None."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "ActiveEnterTimestamp=invalid-format-here"

        with patch("check_zpools.service_install._run_systemctl", return_value=mock_result):
            result = _get_service_start_time()

        assert result is None


# ============================================================================
# Tests for _get_pool_status_summary
# ============================================================================


class TestGetPoolStatusSummaryWithHealthyPools:
    """Tests for pool status summary with healthy pools."""

    def test_healthy_pools_returns_correct_counts(self) -> None:
        """Healthy pools should return correct pool count and zero faulted."""
        from check_zpools.models import CheckResult, PoolHealth, PoolStatus, Severity

        mock_pool = PoolStatus(
            name="rpool",
            health=PoolHealth.ONLINE,
            capacity_percent=50.0,
            size_bytes=1024**4,
            allocated_bytes=int(0.5 * 1024**4),
            free_bytes=int(0.5 * 1024**4),
            read_errors=0,
            write_errors=0,
            checksum_errors=0,
            last_scrub=datetime.now(UTC),
            scrub_errors=0,
            scrub_in_progress=False,
            faulted_devices=(),
        )
        mock_result = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[mock_pool],
            issues=[],
            overall_severity=Severity.OK,
        )

        with patch("check_zpools.behaviors.check_pools_once", return_value=mock_result):
            pool_count, faulted_count, issues = _get_pool_status_summary()

        assert pool_count == 1
        assert faulted_count == 0
        assert issues == []


class TestGetPoolStatusSummaryWithFaultedDevices:
    """Tests for pool status summary with faulted devices."""

    def test_faulted_devices_returns_correct_counts(self) -> None:
        """Pools with faulted devices should return correct faulted count."""
        from check_zpools.models import (
            CheckResult,
            DeviceStatus,
            PoolHealth,
            PoolIssue,
            PoolStatus,
            Severity,
        )

        faulted_device = DeviceStatus(
            name="wwn-0x5002538f55117008-part3",
            state="FAULTED",
            read_errors=3,
            write_errors=220,
            checksum_errors=0,
            vdev_type="disk",
        )
        mock_pool = PoolStatus(
            name="rpool",
            health=PoolHealth.ONLINE,
            capacity_percent=50.0,
            size_bytes=1024**4,
            allocated_bytes=int(0.5 * 1024**4),
            free_bytes=int(0.5 * 1024**4),
            read_errors=0,
            write_errors=0,
            checksum_errors=0,
            last_scrub=datetime.now(UTC),
            scrub_errors=0,
            scrub_in_progress=False,
            faulted_devices=(faulted_device,),
        )
        mock_issue = PoolIssue(
            pool_name="rpool",
            severity=Severity.CRITICAL,
            category="device",
            message="Device wwn-0x5002538f55117008-part3 is FAULTED",
            details={},
        )
        mock_result = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[mock_pool],
            issues=[mock_issue],
            overall_severity=Severity.CRITICAL,
        )

        with patch("check_zpools.behaviors.check_pools_once", return_value=mock_result):
            pool_count, faulted_count, issues = _get_pool_status_summary()

        assert pool_count == 1
        assert faulted_count == 1
        assert len(issues) == 1
        assert "FAULTED" in issues[0]


class TestGetPoolStatusSummaryWithErrors:
    """Tests for pool status summary with error conditions."""

    def test_check_failure_returns_error_message(self) -> None:
        """Failed pool check should return error message."""
        with patch(
            "check_zpools.behaviors.check_pools_once",
            side_effect=RuntimeError("ZFS not available"),
        ):
            pool_count, faulted_count, issues = _get_pool_status_summary()

        assert pool_count == 0
        assert faulted_count == 0
        assert len(issues) == 1
        assert "Error" in issues[0]


# ============================================================================
# Tests for show_service_status output
# ============================================================================


class TestShowServiceStatusNotInstalled:
    """Tests for service status display when service is not installed."""

    def test_not_installed_shows_install_instructions(self, capsys: pytest.CaptureFixture[str]) -> None:
        """When service not installed, should show installation instructions."""
        from check_zpools.service_install import show_service_status

        with patch("check_zpools.service_install.get_service_status", return_value={"installed": False}):
            show_service_status()

        captured = capsys.readouterr()
        assert "not installed" in captured.out
        assert "sudo check_zpools install-service" in captured.out


class TestShowServiceStatusInstalled:
    """Tests for service status display when service is installed."""

    def test_installed_shows_service_file_path(self, capsys: pytest.CaptureFixture[str]) -> None:
        """When service installed, should show service file path."""
        from check_zpools.service_install import show_service_status

        status = {
            "installed": True,
            "running": False,
            "enabled": False,
            "status_text": "",
        }

        with (
            patch("check_zpools.service_install.get_service_status", return_value=status),
            patch("check_zpools.service_install._get_service_start_time", return_value=None),
            patch("check_zpools.service_install._get_daemon_config", return_value={}),
            patch("check_zpools.service_install._get_pool_status_summary", return_value=(0, 0, [])),
            patch("check_zpools.service_install._load_alert_state", return_value={}),
        ):
            show_service_status()

        captured = capsys.readouterr()
        assert "Service file installed" in captured.out

    def test_running_service_shows_uptime(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Running service should display uptime information."""
        from check_zpools.service_install import show_service_status

        status = {
            "installed": True,
            "running": True,
            "enabled": True,
            "status_text": "",
        }
        start_time = datetime.now(UTC) - timedelta(hours=3, minutes=15)

        with (
            patch("check_zpools.service_install.get_service_status", return_value=status),
            patch("check_zpools.service_install._get_service_start_time", return_value=start_time),
            patch("check_zpools.service_install._get_daemon_config", return_value={"check_interval_seconds": 300}),
            patch("check_zpools.service_install._get_pool_status_summary", return_value=(4, 0, [])),
            patch("check_zpools.service_install._load_alert_state", return_value={}),
        ):
            show_service_status()

        captured = capsys.readouterr()
        assert "Running:  ✓ Yes" in captured.out
        assert "uptime:" in captured.out
        assert "3h" in captured.out

    def test_displays_daemon_configuration(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should display daemon configuration section."""
        from check_zpools.service_install import show_service_status

        status = {
            "installed": True,
            "running": True,
            "enabled": True,
            "status_text": "",
        }
        daemon_config = {
            "check_interval_seconds": 300,
            "alert_resend_interval_hours": 2,
        }

        with (
            patch("check_zpools.service_install.get_service_status", return_value=status),
            patch("check_zpools.service_install._get_service_start_time", return_value=None),
            patch("check_zpools.service_install._get_daemon_config", return_value=daemon_config),
            patch("check_zpools.service_install._get_pool_status_summary", return_value=(4, 0, [])),
            patch("check_zpools.service_install._load_alert_state", return_value={}),
        ):
            show_service_status()

        captured = capsys.readouterr()
        assert "Daemon Configuration" in captured.out
        assert "300s" in captured.out
        assert "2h" in captured.out

    def test_displays_pool_status(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should display current pool status section."""
        from check_zpools.service_install import show_service_status

        status = {
            "installed": True,
            "running": True,
            "enabled": True,
            "status_text": "",
        }

        with (
            patch("check_zpools.service_install.get_service_status", return_value=status),
            patch("check_zpools.service_install._get_service_start_time", return_value=None),
            patch("check_zpools.service_install._get_daemon_config", return_value={}),
            patch("check_zpools.service_install._get_pool_status_summary", return_value=(4, 1, ["rpool: FAULTED device"])),
            patch("check_zpools.service_install._load_alert_state", return_value={}),
        ):
            show_service_status()

        captured = capsys.readouterr()
        assert "Pool Status" in captured.out
        assert "Pools monitored:    4" in captured.out
        assert "1 FAULTED" in captured.out

    def test_displays_active_alerts(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should display active alert states with time until next email."""
        from check_zpools.service_install import show_service_status

        status = {
            "installed": True,
            "running": True,
            "enabled": True,
            "status_text": "",
        }
        # Alert sent 30 minutes ago with 2 hour resend interval
        last_alerted = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
        alert_state = {
            "alerts": {
                "rpool:device": {
                    "pool_name": "rpool",
                    "issue_category": "device",
                    "last_alerted": last_alerted,
                    "alert_count": 3,
                    "last_severity": "CRITICAL",
                }
            }
        }

        with (
            patch("check_zpools.service_install.get_service_status", return_value=status),
            patch("check_zpools.service_install._get_service_start_time", return_value=None),
            patch("check_zpools.service_install._get_daemon_config", return_value={"alert_resend_interval_hours": 2}),
            patch("check_zpools.service_install._get_pool_status_summary", return_value=(4, 0, [])),
            patch("check_zpools.service_install._load_alert_state", return_value=alert_state),
        ):
            show_service_status()

        captured = capsys.readouterr()
        assert "Active Alert States" in captured.out
        assert "[CRITICAL] rpool:device" in captured.out
        assert "Alerts sent: 3" in captured.out
        assert "Next email in:" in captured.out
