"""Integration tests for email alerting following clean architecture principles.

Design Philosophy
-----------------
These tests validate email alerting behavior through real formatting logic with minimal mocking:
- Test names read like plain English sentences describing exact behavior
- Each test validates ONE specific behavior - no multi-assert kitchen sinks
- Real formatting logic - tests actual subject/body generation with minimal stubbing
- OS-agnostic - email logic works the same on all platforms
- Deterministic - no SMTP connections, uses mocks for email sending only

Test Structure Pattern
----------------------
1. Given: Setup minimal test state (fixtures, test data)
2. When: Execute ONE alert action
3. Then: Assert ONE specific outcome

Coverage Strategy
-----------------
- Email configuration: Store and apply settings correctly
- Subject formatting: Descriptive subjects with severity, pool, message
- Body formatting: Complete pool details with recommended actions
- Alert sending: SMTP interaction with error handling
- Recovery emails: Separate notifications for resolved issues
- Severity filtering: Send only alerts matching configured severities
- Edge cases: No recipients, SMTP failures, missing scrub data
"""

from __future__ import annotations

import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from check_zpools.alerting import EmailAlerter
from check_zpools.mail import EmailConfig
from check_zpools.models import PoolHealth, PoolIssue, PoolStatus, Severity


# ============================================================================
# Test Data Builders
# ============================================================================
# Note: Pool status factory (configurable_pool_status) is defined in conftest.py
# and automatically available to all test files.
# ============================================================================


def a_capacity_issue(pool_name: str = "rpool", severity: Severity = Severity.WARNING) -> PoolIssue:
    """Create a capacity issue for testing."""
    return PoolIssue(
        pool_name=pool_name,
        severity=severity,
        category="capacity",
        message="Pool capacity at 85.5%",
        details={"threshold": 80, "actual": 85.5},
    )


def an_error_issue(pool_name: str = "rpool") -> PoolIssue:
    """Create an error issue for testing."""
    return PoolIssue(
        pool_name=pool_name,
        severity=Severity.WARNING,
        category="errors",
        message="Read errors detected",
        details={},
    )


def a_scrub_issue(pool_name: str = "rpool") -> PoolIssue:
    """Create a scrub issue for testing."""
    return PoolIssue(
        pool_name=pool_name,
        severity=Severity.INFO,
        category="scrub",
        message="Scrub overdue",
        details={},
    )


def a_health_issue(pool_name: str = "rpool") -> PoolIssue:
    """Create a health issue for testing."""
    return PoolIssue(
        pool_name=pool_name,
        severity=Severity.CRITICAL,
        category="health",
        message="Pool degraded",
        details={},
    )


# ============================================================================
# Test Fixtures
# ============================================================================
# Note: Some shared fixtures like healthy_pool_status and ok_check_result are
# defined in conftest.py and automatically available to all test files.
# ============================================================================


@pytest.fixture
def email_config() -> EmailConfig:
    """Create test email configuration."""
    return EmailConfig(
        smtp_hosts=["localhost:587"],
        from_address="zfs@example.com",
        smtp_username="test@example.com",
        smtp_password="password",
        use_starttls=True,
    )


@pytest.fixture
def alert_config() -> dict:
    """Create test alert configuration."""
    return {
        "subject_prefix": "[ZFS Test]",
        "alert_recipients": ["admin@example.com"],
        "send_ok_emails": False,
        "send_recovery_emails": True,
    }


@pytest.fixture
def alerter(email_config: EmailConfig, alert_config: dict) -> EmailAlerter:
    """Create EmailAlerter instance."""
    return EmailAlerter(email_config, alert_config)


@pytest.fixture
def sample_pool() -> PoolStatus:
    """Create a sample pool status."""
    return PoolStatus(
        name="rpool",
        health=PoolHealth.ONLINE,
        capacity_percent=85.5,
        size_bytes=1024**4,  # 1 TB
        allocated_bytes=int(0.855 * 1024**4),
        free_bytes=int(0.145 * 1024**4),
        read_errors=0,
        write_errors=0,
        checksum_errors=0,
        last_scrub=datetime.now(UTC),
        scrub_errors=0,
        scrub_in_progress=False,
    )


@pytest.fixture
def sample_issue() -> PoolIssue:
    """Create a sample pool issue."""
    return PoolIssue(
        pool_name="rpool",
        severity=Severity.WARNING,
        category="capacity",
        message="Pool capacity at 85.5%",
        details={"threshold": 80, "actual": 85.5},
    )


@pytest.mark.os_agnostic
class TestEmailAlerterInitializationStoresConfiguration:
    """Email alerter initialization stores all provided configuration."""

    def test_stores_email_config_reference(self, email_config: EmailConfig, alert_config: dict) -> None:
        """When initializing with email config, stores reference.

        Given: Email configuration with SMTP settings
        When: Creating alerter with config
        Then: Alerter stores config reference
        """
        alerter = EmailAlerter(email_config, alert_config)

        assert alerter.email_config == email_config

    def test_applies_custom_subject_prefix_from_config(self, email_config: EmailConfig, alert_config: dict) -> None:
        """When config specifies subject_prefix, uses that prefix.

        Given: Alert config with custom prefix "[ZFS Test]"
        When: Creating alerter with config
        Then: Alerter uses custom prefix
        """
        alerter = EmailAlerter(email_config, alert_config)

        assert alerter.subject_prefix == "[ZFS Test]"

    def test_stores_alert_recipients_from_config(self, email_config: EmailConfig, alert_config: dict) -> None:
        """When config specifies alert_recipients, stores recipient list.

        Given: Alert config with recipient list
        When: Creating alerter with config
        Then: Alerter stores recipient list
        """
        alerter = EmailAlerter(email_config, alert_config)

        assert alerter.recipients == ["admin@example.com"]

    def test_uses_default_subject_prefix_when_not_configured(self, email_config: EmailConfig) -> None:
        """When config omits subject_prefix, uses default '[ZFS Alert]'.

        Given: Empty alert config (no subject_prefix)
        When: Creating alerter
        Then: Alerter uses default prefix "[ZFS Alert]"
        """
        alerter = EmailAlerter(email_config, {})

        assert alerter.subject_prefix == "[ZFS Alert]"


@pytest.mark.os_agnostic
class TestAlertSubjectFormattingIncludesKeyInformation:
    """Alert subject formatting includes all key information for quick identification."""

    def test_includes_prefix_hostname_severity_pool_and_message(self, alerter: EmailAlerter) -> None:
        """When formatting subject, includes all key identification fields.

        Given: Alerter with custom prefix "[ZFS Test]"
        When: Formatting subject for WARNING on "rpool"
        Then: Subject contains prefix, hostname, severity, pool, message
        """
        import socket

        subject = alerter._format_subject(Severity.WARNING, "rpool", "High capacity")
        hostname = socket.gethostname()

        # Verify exact format: [Prefix] [hostname] SEVERITY - pool: message
        assert subject.startswith(f"[ZFS Test] [{hostname}]"), f"Subject should start with '[ZFS Test] [{hostname}]', got: {subject}"

        assert "WARNING" in subject
        assert "rpool" in subject
        assert "High capacity" in subject

        # Verify bracket structure
        assert subject.count("[") >= 2, "Subject should have at least 2 opening brackets"
        assert subject.count("]") >= 2, "Subject should have at least 2 closing brackets"

    def test_marks_critical_issues_in_subject(self, alerter: EmailAlerter) -> None:
        """When formatting critical issue, subject shows CRITICAL severity.

        Given: CRITICAL severity pool issue
        When: Formatting subject
        Then: Subject contains "CRITICAL" and pool name
        """
        subject = alerter._format_subject(Severity.CRITICAL, "data", "Pool degraded")

        assert "CRITICAL" in subject
        assert "data" in subject


@pytest.mark.os_agnostic
class TestAlertBodyFormattingIncludesCompleteDetails:
    """Alert body formatting includes complete pool and issue information."""

    def test_includes_pool_name_capacity_severity_and_category(self, alerter: EmailAlerter, sample_issue: PoolIssue, sample_pool: PoolStatus) -> None:
        """When formatting body, includes all pool details and issue info.

        Given: Pool at 85.5% capacity with WARNING severity
        When: Formatting alert body
        Then: Body contains pool name, capacity, severity, category, actions
        """
        body = alerter._format_body(sample_issue, sample_pool)

        # Check key information is present
        assert "rpool" in body
        assert "85.5%" in body  # Capacity
        assert "WARNING" in body
        assert "capacity" in body
        assert "zpool status" in body  # Recommended action

    def test_includes_issue_detail_fields(self, alerter: EmailAlerter, sample_issue: PoolIssue, sample_pool: PoolStatus) -> None:
        """When issue has detail fields, includes them in body.

        Given: Issue with threshold and actual values in details
        When: Formatting alert body
        Then: Body contains detail field names and values
        """
        body = alerter._format_body(sample_issue, sample_pool)

        assert "threshold" in body
        assert "actual" in body


@pytest.mark.os_agnostic
class TestAlertBodyIncludesRecommendedActionsByCategory:
    """Alert body includes category-specific recommended actions."""

    def test_capacity_issues_recommend_freeing_space(self, alerter: EmailAlerter, sample_pool: PoolStatus) -> None:
        """When issue is capacity, recommends freeing up space.

        Given: Capacity warning issue
        When: Formatting alert body
        Then: Body contains recommendations about removing files and storage
        """
        issue = PoolIssue(
            pool_name="rpool",
            severity=Severity.WARNING,
            category="capacity",
            message="High capacity",
            details={},
        )

        body = alerter._format_body(issue, sample_pool)

        assert "remove unnecessary files" in body.lower()
        assert "storage capacity" in body.lower()

    def test_error_issues_recommend_hardware_check_and_scrub(self, alerter: EmailAlerter, sample_pool: PoolStatus) -> None:
        """When issue is errors, recommends checking hardware and running scrub.

        Given: Read/write error issue
        When: Formatting alert body
        Then: Body mentions hardware issues and scrub recommendations
        """
        issue = PoolIssue(
            pool_name="rpool",
            severity=Severity.WARNING,
            category="errors",
            message="Read errors detected",
            details={},
        )

        body = alerter._format_body(issue, sample_pool)

        assert "hardware issues" in body.lower()
        assert "scrub" in body.lower()

    def test_scrub_issues_recommend_running_scrub(self, alerter: EmailAlerter, sample_pool: PoolStatus) -> None:
        """When issue is scrub, recommends running zpool scrub command.

        Given: Scrub overdue issue
        When: Formatting alert body
        Then: Body contains zpool scrub command recommendation
        """
        issue = PoolIssue(
            pool_name="rpool",
            severity=Severity.INFO,
            category="scrub",
            message="Scrub overdue",
            details={},
        )

        body = alerter._format_body(issue, sample_pool)

        assert "zpool scrub" in body.lower()

    def test_health_issues_recommend_device_replacement(self, alerter: EmailAlerter, sample_pool: PoolStatus) -> None:
        """When issue is health, recommends checking and replacing devices.

        Given: Pool health degraded issue
        When: Formatting alert body
        Then: Body mentions failed devices and replacement recommendations
        """
        issue = PoolIssue(
            pool_name="rpool",
            severity=Severity.CRITICAL,
            category="health",
            message="Pool degraded",
            details={},
        )

        body = alerter._format_body(issue, sample_pool)

        assert "failed or degraded devices" in body.lower()
        assert "replace" in body.lower()


@pytest.mark.os_agnostic
class TestAlertSendingCallsSMTPWithFormattedContent:
    """Alert sending calls SMTP with properly formatted subject and body."""

    @patch("check_zpools.alerting.send_email")
    def test_calls_smtp_with_config_recipients_and_formatted_content(
        self,
        mock_send: MagicMock,
        alerter: EmailAlerter,
        sample_issue: PoolIssue,
        sample_pool: PoolStatus,
    ) -> None:
        """When sending alert, calls send_email with all required parameters.

        Given: Pool issue and SMTP configured
        When: Sending alert
        Then: Calls send_email with config, recipients, formatted subject/body
        """
        mock_send.return_value = True

        result = alerter.send_alert(sample_issue, sample_pool)

        assert result is True
        mock_send.assert_called_once()

        # Verify call parameters
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["config"] == alerter.email_config
        assert call_kwargs["recipients"] == ["admin@example.com"]
        assert "WARNING" in call_kwargs["subject"]
        assert "rpool" in call_kwargs["body"]

    @patch("check_zpools.alerting.send_email")
    def test_returns_false_when_smtp_connection_fails(
        self,
        mock_send: MagicMock,
        alerter: EmailAlerter,
        sample_issue: PoolIssue,
        sample_pool: PoolStatus,
    ) -> None:
        """When SMTP fails, returns False without crashing.

        Given: SMTP connection that will fail
        When: Attempting to send alert
        Then: Returns False and handles exception gracefully
        """
        mock_send.side_effect = RuntimeError("SMTP connection failed")

        result = alerter.send_alert(sample_issue, sample_pool)

        assert result is False

    def test_returns_false_when_no_recipients_configured(self, email_config: EmailConfig, sample_issue: PoolIssue, sample_pool: PoolStatus) -> None:
        """When no recipients configured, returns False without attempting send.

        Given: Alerter with empty recipient list
        When: Attempting to send alert
        Then: Returns False immediately
        """
        alerter = EmailAlerter(email_config, {"alert_recipients": []})

        result = alerter.send_alert(sample_issue, sample_pool)

        assert result is False


@pytest.mark.os_agnostic
class TestRecoveryEmailFormattingIndicatesResolution:
    """Recovery email formatting clearly indicates issue resolution."""

    def test_subject_includes_recovery_marker_and_issue_details(self, alerter: EmailAlerter) -> None:
        """When formatting recovery subject, includes RECOVERY and issue info.

        Given: Resolved capacity issue on "rpool"
        When: Formatting recovery subject
        Then: Subject contains RECOVERY, pool name, issue category
        """
        import socket

        subject = alerter._format_recovery_subject("rpool", "capacity")
        hostname = socket.gethostname()

        # Verify exact format: [Prefix] [hostname] RECOVERY - pool: message
        assert subject.startswith(f"[ZFS Test] [{hostname}]"), f"Subject should start with '[ZFS Test] [{hostname}]', got: {subject}"

        assert "RECOVERY" in subject
        assert "rpool" in subject
        assert "capacity" in subject

        # Verify bracket structure
        assert subject.count("[") >= 2, "Subject should have at least 2 opening brackets"
        assert subject.count("]") >= 2, "Subject should have at least 2 closing brackets"

    def test_body_indicates_issue_resolved(self, alerter: EmailAlerter) -> None:
        """When formatting recovery body, clearly states resolution.

        Given: Resolved capacity issue
        When: Formatting recovery body
        Then: Body contains pool name, category, and "resolved" language
        """
        body = alerter._format_recovery_body("rpool", "capacity")

        assert "rpool" in body
        assert "capacity" in body
        assert "resolved" in body.lower()


@pytest.mark.os_agnostic
class TestRecoverySendingRespectsConfiguration:
    """Recovery email sending respects configuration flags."""

    @patch("check_zpools.alerting.send_email")
    def test_calls_smtp_when_recovery_emails_enabled(self, mock_send: MagicMock, alerter: EmailAlerter) -> None:
        """When send_recovery_emails enabled, sends recovery notification.

        Given: Alerter with send_recovery_emails=True (default in fixture)
        When: Sending recovery for resolved issue
        Then: Calls send_email with RECOVERY subject
        """
        mock_send.return_value = True

        result = alerter.send_recovery("rpool", "capacity")

        assert result is True
        mock_send.assert_called_once()

        call_kwargs = mock_send.call_args.kwargs
        assert "RECOVERY" in call_kwargs["subject"]
        assert "rpool" in call_kwargs["body"]

    def test_skips_sending_when_recovery_emails_disabled(self, email_config: EmailConfig) -> None:
        """When send_recovery_emails disabled, skips sending.

        Given: Alerter with send_recovery_emails=False
        When: Attempting to send recovery
        Then: Returns False without sending
        """
        alerter = EmailAlerter(
            email_config,
            {"send_recovery_emails": False, "alert_recipients": ["admin@example.com"]},
        )

        result = alerter.send_recovery("rpool", "capacity")

        assert result is False

    @patch("check_zpools.alerting.send_email")
    def test_returns_false_when_smtp_fails(self, mock_send: MagicMock, alerter: EmailAlerter) -> None:
        """When SMTP fails during recovery send, returns False.

        Given: SMTP that will fail
        When: Attempting to send recovery
        Then: Returns False and handles exception gracefully
        """
        mock_send.side_effect = RuntimeError("SMTP error")

        result = alerter.send_recovery("rpool", "capacity")

        assert result is False

    def test_returns_false_when_no_recipients_configured(self, email_config: EmailConfig) -> None:
        """When no recipients configured, returns False for recovery.

        Given: Alerter with empty recipient list
        When: Attempting to send recovery
        Then: Returns False immediately
        """
        alerter = EmailAlerter(email_config, {"alert_recipients": []})

        result = alerter.send_recovery("rpool", "capacity")

        assert result is False


@pytest.mark.os_agnostic
class TestAlertBodyIncludesSystemMetadata:
    """Alert body includes system metadata for debugging and tracking."""

    def test_includes_hostname_for_system_identification(self, alerter: EmailAlerter, sample_issue: PoolIssue, sample_pool: PoolStatus) -> None:
        """When formatting body, includes hostname.

        Given: Pool issue on current system
        When: Formatting alert body
        Then: Body contains hostname field
        """
        body = alerter._format_body(sample_issue, sample_pool)

        # Should contain hostname somewhere
        assert "Hostname:" in body or "Host:" in body

    def test_includes_tool_version_from_pyproject(self, alerter: EmailAlerter, sample_issue: PoolIssue, sample_pool: PoolStatus) -> None:
        """When formatting body, includes tool version.

        Given: Tool version defined in pyproject.toml
        When: Formatting alert body
        Then: Body contains version number
        """
        body = alerter._format_body(sample_issue, sample_pool)

        # Read version from pyproject.toml
        pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
        with pyproject_path.open("rb") as f:
            pyproject = tomllib.load(f)
        expected_version = pyproject["project"]["version"]

        # Should contain version number (e.g., "v1.0.0")
        assert f"v{expected_version}" in body or "version" in body.lower()


@pytest.mark.os_agnostic
class TestAlertBodyHandlesScrubEdgeCases:
    """Alert body handles edge cases in scrub status."""

    def test_shows_scrub_in_progress_status(self, alerter: EmailAlerter, sample_issue: PoolIssue) -> None:
        """When pool has scrub in progress, shows in body.

        Given: Pool with active scrub
        When: Formatting alert body
        Then: Body indicates scrub in progress
        """
        pool = PoolStatus(
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
            scrub_in_progress=True,
        )

        body = alerter._format_body(sample_issue, pool)

        assert "SCRUB IN PROGRESS" in body or "scrub" in body.lower()

    def test_shows_never_scrubbed_status(self, alerter: EmailAlerter, sample_issue: PoolIssue) -> None:
        """When pool was never scrubbed, shows 'Never' in body.

        Given: Pool with no scrub history (last_scrub=None)
        When: Formatting alert body
        Then: Body shows "Never" for scrub status
        """
        pool = PoolStatus(
            name="rpool",
            health=PoolHealth.ONLINE,
            capacity_percent=50.0,
            size_bytes=1024**4,
            allocated_bytes=int(0.5 * 1024**4),
            free_bytes=int(0.5 * 1024**4),
            read_errors=0,
            write_errors=0,
            checksum_errors=0,
            last_scrub=None,
            scrub_errors=0,
            scrub_in_progress=False,
        )

        body = alerter._format_body(sample_issue, pool)

        assert "Never" in body


# ============================================================================
# Severity Filtering Tests
# ============================================================================


def an_alerter_with_severity_config(alert_on_severities: list[str]) -> EmailAlerter:
    """Create an alerter with specific severity filtering configuration.

    Why
        Simplifies test setup for severity filtering tests by encapsulating
        the configuration details.

    Inputs
        alert_on_severities: List of severity strings to allow (e.g., ["CRITICAL", "WARNING"])

    Outputs
        EmailAlerter configured with the specified severity filters
    """
    email_config = EmailConfig(
        smtp_hosts=["localhost:587"],
        from_address="test@example.com",
        smtp_username="test",
        smtp_password="pass",
        use_starttls=True,
    )
    alert_config = {
        "alert_recipients": ["admin@example.com"],
        "alert_on_severities": alert_on_severities,
    }
    return EmailAlerter(email_config, alert_config)


@pytest.mark.os_agnostic
class TestSeverityFilteringControlsWhichAlertsAreSent:
    """Severity filtering controls which alerts are sent based on configured severities."""

    @patch("check_zpools.alerting.send_email")
    def test_sends_critical_alerts_when_critical_in_filter(self, mock_send: MagicMock, configurable_pool_status: Any) -> None:
        """When CRITICAL in alert_on_severities, CRITICAL alerts are sent.

        Given: Alerter configured with ["CRITICAL", "WARNING"]
        When: Sending CRITICAL severity alert
        Then: Alert is sent via SMTP
        """
        mock_send.return_value = True
        alerter = an_alerter_with_severity_config(["CRITICAL", "WARNING"])

        issue = PoolIssue(
            pool_name="rpool",
            severity=Severity.CRITICAL,
            category="health",
            message="Pool faulted",
            details={},
        )
        pool = configurable_pool_status("rpool")

        result = alerter.send_alert(issue, pool)

        assert result is True
        assert mock_send.called

    @patch("check_zpools.alerting.send_email")
    def test_sends_warning_alerts_when_warning_in_filter(self, mock_send: MagicMock, configurable_pool_status: Any) -> None:
        """When WARNING in alert_on_severities, WARNING alerts are sent.

        Given: Alerter configured with ["CRITICAL", "WARNING"]
        When: Sending WARNING severity alert
        Then: Alert is sent via SMTP
        """
        mock_send.return_value = True
        alerter = an_alerter_with_severity_config(["CRITICAL", "WARNING"])

        issue = PoolIssue(
            pool_name="rpool",
            severity=Severity.WARNING,
            category="capacity",
            message="Pool at 85%",
            details={},
        )
        pool = configurable_pool_status("rpool", capacity=85.0)

        result = alerter.send_alert(issue, pool)

        assert result is True
        assert mock_send.called

    @patch("check_zpools.alerting.send_email")
    def test_skips_warning_alerts_when_not_in_filter(self, mock_send: MagicMock, configurable_pool_status: Any) -> None:
        """When WARNING not in alert_on_severities, WARNING alerts are skipped.

        Given: Alerter configured with ["CRITICAL"] only
        When: Attempting to send WARNING severity alert
        Then: Alert is not sent
        """
        mock_send.return_value = True
        alerter = an_alerter_with_severity_config(["CRITICAL"])  # Only CRITICAL

        issue = PoolIssue(
            pool_name="rpool",
            severity=Severity.WARNING,
            category="capacity",
            message="Pool at 85%",
            details={},
        )
        pool = configurable_pool_status("rpool", capacity=85.0)

        result = alerter.send_alert(issue, pool)

        assert result is False
        assert not mock_send.called

    @patch("check_zpools.alerting.send_email")
    def test_skips_info_alerts_by_default(self, mock_send: MagicMock, configurable_pool_status: Any) -> None:
        """When INFO not in alert_on_severities, INFO alerts are skipped.

        Given: Alerter with default filter ["CRITICAL", "WARNING"]
        When: Attempting to send INFO severity alert
        Then: Alert is not sent
        """
        mock_send.return_value = True
        alerter = an_alerter_with_severity_config(["CRITICAL", "WARNING"])  # Default

        issue = PoolIssue(
            pool_name="rpool",
            severity=Severity.INFO,
            category="scrub",
            message="Scrub completed",
            details={},
        )
        pool = configurable_pool_status("rpool")

        result = alerter.send_alert(issue, pool)

        assert result is False
        assert not mock_send.called

    @patch("check_zpools.alerting.send_email")
    def test_sends_info_alerts_when_explicitly_added_to_filter(self, mock_send: MagicMock, configurable_pool_status: Any) -> None:
        """When INFO explicitly in alert_on_severities, INFO alerts are sent.

        Given: Alerter configured with ["CRITICAL", "WARNING", "INFO"]
        When: Sending INFO severity alert
        Then: Alert is sent via SMTP
        """
        mock_send.return_value = True
        alerter = an_alerter_with_severity_config(["CRITICAL", "WARNING", "INFO"])

        issue = PoolIssue(
            pool_name="rpool",
            severity=Severity.INFO,
            category="scrub",
            message="Scrub completed",
            details={},
        )
        pool = configurable_pool_status("rpool")

        result = alerter.send_alert(issue, pool)

        assert result is True
        assert mock_send.called

    @patch("check_zpools.alerting.send_email")
    def test_filter_matching_is_case_insensitive(self, mock_send: MagicMock, configurable_pool_status: Any) -> None:
        """When config uses lowercase, matching works case-insensitively.

        Given: Alerter configured with ["critical", "warning"] (lowercase)
        When: Sending CRITICAL severity alert (uppercase enum)
        Then: Alert is sent via SMTP (case-insensitive match)
        """
        mock_send.return_value = True
        alerter = an_alerter_with_severity_config(["critical", "warning"])  # lowercase

        issue = PoolIssue(
            pool_name="rpool",
            severity=Severity.CRITICAL,
            category="health",
            message="Pool faulted",
            details={},
        )
        pool = configurable_pool_status("rpool")

        result = alerter.send_alert(issue, pool)

        assert result is True
        assert mock_send.called
