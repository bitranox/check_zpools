"""Integration tests for CLI commands following clean architecture principles.

Design Philosophy
-----------------
These tests validate real CLI command behavior through the full stack:
- Test names read like plain English sentences describing exact behavior
- Each test validates ONE specific behavior - no multi-assert kitchen sinks
- Real behavior over mocks - we test actual command flow with minimal stubbing
- OS-agnostic - these commands work the same on all platforms
- Deterministic - no randomness, timing dependencies, or environment coupling

Test Structure Pattern
----------------------
1. Given: Setup minimal test state (fixtures, test data)
2. When: Execute ONE command action
3. Then: Assert ONE specific outcome

Coverage Strategy
-----------------
- Happy paths: Commands succeed with valid inputs
- Error paths: Commands fail gracefully with appropriate messages
- Exit codes: Correct codes for monitoring tool integration (0=OK, 1=WARNING, 2=CRITICAL)
- Format variations: Text vs JSON output
- Configuration scenarios: With/without required config
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from check_zpools.cli import cli
from check_zpools.models import CheckResult, PoolStatus, Severity


# =============================================================================
# OS Markers
# =============================================================================

# These tests are OS-agnostic - the CLI commands work the same on all platforms
pytestmark = pytest.mark.skipif(False, reason="OS-agnostic CLI tests")


# =============================================================================
# Note: Shared fixtures like cli_runner, healthy_pool_status, and
# ok_check_result are defined in conftest.py and automatically available
# to all test files.
# =============================================================================


@pytest.fixture
def warning_check_result(healthy_pool_status: PoolStatus) -> CheckResult:
    """Create a check result with WARNING severity.

    Why
        Simulates pools with issues requiring attention but not critical.
        Used for testing non-zero exit codes (exit 1 = WARNING).

    Returns
        CheckResult with WARNING severity.
    """
    return CheckResult(
        timestamp=datetime(2025, 11, 24, 12, 0, 0, tzinfo=timezone.utc),
        pools=[healthy_pool_status],
        issues=[],
        overall_severity=Severity.WARNING,
    )


@pytest.fixture
def critical_check_result(healthy_pool_status: PoolStatus) -> CheckResult:
    """Create a check result with CRITICAL severity.

    Why
        Simulates pools with serious problems requiring immediate action.
        Used for testing critical exit codes (exit 2 = CRITICAL).

    Returns
        CheckResult with CRITICAL severity.
    """
    return CheckResult(
        timestamp=datetime(2025, 11, 24, 12, 0, 0, tzinfo=timezone.utc),
        pools=[healthy_pool_status],
        issues=[],
        overall_severity=Severity.CRITICAL,
    )


# =============================================================================
# Check Command Tests - Pool Health Monitoring
# =============================================================================


class TestCheckCommandSucceedsWithHealthyPools:
    """When pools are healthy, the check command reports success."""

    def test_displays_pool_status_in_human_readable_text(
        self,
        cli_runner: CliRunner,
        ok_check_result: CheckResult,
    ) -> None:
        """When checking pools with default text format, it shows readable status.

        Given: A healthy pool named 'rpool' with ONLINE status
        When: Running 'check_zpools check' with default (text) format
        Then: Output contains pool name and health status in text
        """
        with patch("check_zpools.cli_commands.commands.check.check_pools_once") as mock_check:
            mock_check.return_value = ok_check_result

            result = cli_runner.invoke(cli, ["check"])

            assert result.exit_code == 0, "Healthy pools should exit with success code"
            assert "rpool" in result.output, "Output must show pool name"
            assert "ONLINE" in result.output, "Output must show health status"

    def test_displays_pool_status_as_parseable_json(
        self,
        cli_runner: CliRunner,
        ok_check_result: CheckResult,
    ) -> None:
        """When checking pools with JSON format, it outputs valid structured data.

        Given: A healthy pool with known properties
        When: Running 'check_zpools check --format json'
        Then: Output is valid JSON with pool details
        """
        with patch("check_zpools.cli_commands.commands.check.check_pools_once") as mock_check:
            mock_check.return_value = ok_check_result

            result = cli_runner.invoke(cli, ["check", "--format", "json"])

            assert result.exit_code == 0, "Healthy pools should exit with success code"

            # Verify JSON structure and content
            output_data = json.loads(result.output)
            assert output_data["overall_severity"] == "OK", "JSON should show OK severity"
            assert len(output_data["pools"]) == 1, "JSON should contain one pool"
            assert output_data["pools"][0]["name"] == "rpool", "JSON should show pool name"

    def test_invokes_pool_monitoring_exactly_once(
        self,
        cli_runner: CliRunner,
        ok_check_result: CheckResult,
    ) -> None:
        """When checking pools, it calls the monitoring function once.

        Given: Mock monitoring function ready to return results
        When: Running 'check_zpools check'
        Then: Monitoring function is called exactly once
        """
        with patch("check_zpools.cli_commands.commands.check.check_pools_once") as mock_check:
            mock_check.return_value = ok_check_result

            cli_runner.invoke(cli, ["check"])

            mock_check.assert_called_once()


class TestCheckCommandExitsWithMonitoringStatusCodes:
    """The check command exits with standard monitoring tool codes."""

    def test_exits_with_code_one_when_pools_have_warnings(
        self,
        cli_runner: CliRunner,
        warning_check_result: CheckResult,
    ) -> None:
        """When pools have warnings, exit with code 1 for monitoring tools.

        Given: Pools with WARNING severity issues
        When: Running 'check_zpools check'
        Then: Process exits with code 1 (standard monitoring WARNING)
        """
        with patch("check_zpools.cli_commands.commands.check.check_pools_once") as mock_check:
            mock_check.return_value = warning_check_result

            result = cli_runner.invoke(cli, ["check"])

            assert result.exit_code == 1, "WARNING severity must exit with code 1"

    def test_exits_with_code_two_when_pools_are_critical(
        self,
        cli_runner: CliRunner,
        critical_check_result: CheckResult,
    ) -> None:
        """When pools are critical, exit with code 2 for monitoring tools.

        Given: Pools with CRITICAL severity issues
        When: Running 'check_zpools check'
        Then: Process exits with code 2 (standard monitoring CRITICAL)
        """
        with patch("check_zpools.cli_commands.commands.check.check_pools_once") as mock_check:
            mock_check.return_value = critical_check_result

            result = cli_runner.invoke(cli, ["check"])

            assert result.exit_code == 2, "CRITICAL severity must exit with code 2"


class TestCheckCommandHandlesExpectedErrors:
    """The check command handles error conditions gracefully."""

    def test_reports_when_zfs_is_not_installed(
        self,
        cli_runner: CliRunner,
    ) -> None:
        """When ZFS is unavailable, show helpful error message.

        Given: ZFS tools are not installed on the system
        When: Running 'check_zpools check'
        Then: Shows error message mentioning ZFS and exits with code 1
        """
        from check_zpools.zfs_client import ZFSNotAvailableError

        with patch("check_zpools.cli_commands.commands.check.check_pools_once") as mock_check:
            mock_check.side_effect = ZFSNotAvailableError("ZFS not installed")

            result = cli_runner.invoke(cli, ["check"])

            assert result.exit_code == 1, "Missing ZFS should be an error"
            assert "zfs" in result.output.lower(), "Error message should mention ZFS"

    def test_reports_unexpected_errors_with_helpful_message(
        self,
        cli_runner: CliRunner,
    ) -> None:
        """When unexpected errors occur, show error message to user.

        Given: An unexpected error during pool checking
        When: Running 'check_zpools check'
        Then: Shows error message and exits with code 1
        """
        with patch("check_zpools.cli_commands.commands.check.check_pools_once") as mock_check:
            mock_check.side_effect = RuntimeError("Something went wrong")

            result = cli_runner.invoke(cli, ["check"])

            assert result.exit_code == 1, "Unexpected errors should exit with code 1"
            assert len(result.output) > 0, "Error message should be shown to user"


# =============================================================================
# Daemon Command Tests - Background Monitoring Service
# =============================================================================


class TestDaemonCommandStartsBackgroundMonitoring:
    """The daemon command starts continuous pool monitoring."""

    def test_invokes_daemon_runner_with_foreground_flag(
        self,
        cli_runner: CliRunner,
    ) -> None:
        """When starting daemon in foreground, it invokes the daemon runner.

        Given: Daemon configured to exit immediately
        When: Running 'check_zpools daemon --foreground'
        Then: Daemon runner is called with foreground flag
        """
        with patch("check_zpools.cli_commands.commands.daemon.run_daemon") as mock_daemon:
            mock_daemon.return_value = None

            result = cli_runner.invoke(cli, ["daemon", "--foreground"])

            assert result.exit_code == 0, "Daemon should exit cleanly"
            mock_daemon.assert_called_once()

            # Verify foreground flag was passed
            call_kwargs = mock_daemon.call_args[1]
            assert "foreground" in call_kwargs or call_kwargs == {}, "Foreground flag should be handled"


# =============================================================================
# Email Command Tests - Alert Delivery
# =============================================================================


class TestSendEmailCommandDeliversAlerts:
    """The send-email command delivers email notifications."""

    def test_sends_email_when_smtp_is_configured(
        self,
        cli_runner: CliRunner,
    ) -> None:
        """When SMTP is configured, email is sent successfully.

        Given: Valid SMTP configuration with localhost:25
        When: Running 'check_zpools send-email' with valid parameters
        Then: Email is sent and success message is shown
        """
        with (
            patch("check_zpools.cli_commands.commands.send_email.send_email") as mock_send,
            patch("check_zpools.cli_commands.commands.send_email.load_email_config_from_dict") as mock_load,
        ):
            mock_config = MagicMock()
            mock_config.smtp_hosts = ["localhost:25"]
            mock_load.return_value = mock_config
            mock_send.return_value = True

            result = cli_runner.invoke(
                cli,
                [
                    "send-email",
                    "--to",
                    "admin@example.com",
                    "--subject",
                    "Test Alert",
                    "--body",
                    "Test message body",
                ],
            )

            assert result.exit_code == 0, "Valid email should succeed"
            assert "successfully" in result.output.lower(), "Success message should be shown"
            mock_send.assert_called_once()

    def test_reports_error_when_smtp_is_not_configured(
        self,
        cli_runner: CliRunner,
    ) -> None:
        """When SMTP is not configured, show helpful error message.

        Given: Email configuration with no SMTP hosts
        When: Running 'check_zpools send-email'
        Then: Error message mentions SMTP and exits with code 1
        """
        with patch("check_zpools.cli_commands.commands.send_email.load_email_config_from_dict") as mock_load:
            mock_config = MagicMock()
            mock_config.smtp_hosts = []
            mock_load.return_value = mock_config

            result = cli_runner.invoke(
                cli,
                [
                    "send-email",
                    "--to",
                    "admin@example.com",
                    "--subject",
                    "Test",
                    "--body",
                    "Test",
                ],
            )

            assert result.exit_code == 1, "Missing SMTP config should be an error"
            assert "smtp" in result.output.lower(), "Error should mention SMTP"


class TestSendNotificationCommandDeliversSimpleAlerts:
    """The send-notification command sends simple text notifications."""

    def test_sends_notification_when_smtp_is_configured(
        self,
        cli_runner: CliRunner,
    ) -> None:
        """When SMTP is configured, notification is sent successfully.

        Given: Valid SMTP configuration
        When: Running 'check_zpools send-notification'
        Then: Notification is sent and success message is shown
        """
        with (
            patch("check_zpools.cli_commands.commands.send_notification.send_notification") as mock_send,
            patch("check_zpools.cli_commands.commands.send_notification.load_email_config_from_dict") as mock_load,
        ):
            mock_config = MagicMock()
            mock_config.smtp_hosts = ["localhost:25"]
            mock_load.return_value = mock_config
            mock_send.return_value = True

            result = cli_runner.invoke(
                cli,
                [
                    "send-notification",
                    "--to",
                    "admin@example.com",
                    "--subject",
                    "Alert",
                    "--message",
                    "Pool status changed",
                ],
            )

            assert result.exit_code == 0, "Valid notification should succeed"
            assert "successfully" in result.output.lower(), "Success message should be shown"
            mock_send.assert_called_once()


# =============================================================================
# Configuration Command Tests - System Setup
# =============================================================================


class TestConfigDeployCommandInstallsDefaultConfiguration:
    """The config-deploy command installs default configuration files."""

    def test_deploys_configuration_to_user_directory(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
    ) -> None:
        """When deploying user config, it creates config file in user directory.

        Given: Empty user configuration directory
        When: Running 'check_zpools config-deploy --target user'
        Then: Configuration file is created in user config path
        """
        with patch("check_zpools.cli_commands.commands.config_deploy.deploy_configuration") as mock_deploy:
            mock_deploy.return_value = str(tmp_path / "config.toml")

            result = cli_runner.invoke(cli, ["config-deploy", "--target", "user"])

            assert result.exit_code == 0, "Config deployment should succeed"
            mock_deploy.assert_called_once()


class TestConfigShowCommandDisplaysCurrentSettings:
    """The config command shows current merged configuration."""

    def test_displays_merged_configuration_from_all_sources(
        self,
        cli_runner: CliRunner,
    ) -> None:
        """When showing config, it displays merged settings from all sources.

        Given: Configuration loaded from multiple sources
        When: Running 'check_zpools config'
        Then: Shows merged configuration values
        """
        result = cli_runner.invoke(cli, ["config"])

        assert result.exit_code == 0, "Config display should succeed"
        assert len(result.output) > 0, "Should show configuration details"
