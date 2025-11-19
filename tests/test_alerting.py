"""Tests for email alerting module.

Tests cover:
- Email formatting (subject, body)
- Alert sending with SMTP mocking
- Recovery email generation
- Error handling for failed sends
- Configuration handling

All tests are OS-agnostic (email logic works everywhere).
SMTP functionality is tested with mocks (no real email sending in unit tests).
"""

from __future__ import annotations

import tomllib
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from check_zpools.alerting import EmailAlerter
from check_zpools.mail import EmailConfig
from check_zpools.models import PoolHealth, PoolIssue, PoolStatus, Severity


# ============================================================================
# Test Data Builders
# ============================================================================


def a_pool_for_alerting(
    name: str = "rpool",
    capacity: float = 50.0,
    scrub_in_progress: bool = False,
    last_scrub: datetime | None = None,
) -> PoolStatus:
    """Create a pool for alerting tests."""
    if last_scrub is None:
        last_scrub = datetime.now(UTC)

    return PoolStatus(
        name=name,
        health=PoolHealth.ONLINE,
        capacity_percent=capacity,
        size_bytes=1024**4,
        allocated_bytes=int((capacity / 100.0) * 1024**4),
        free_bytes=int(((100.0 - capacity) / 100.0) * 1024**4),
        read_errors=0,
        write_errors=0,
        checksum_errors=0,
        last_scrub=last_scrub,
        scrub_errors=0,
        scrub_in_progress=scrub_in_progress,
    )


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
class TestEmailAlerterInitialization:
    """When creating an email alerter, configuration is applied correctly."""

    def test_alerter_stores_email_config(self, email_config: EmailConfig, alert_config: dict) -> None:
        """When initializing with email config,
        the alerter stores the configuration."""
        alerter = EmailAlerter(email_config, alert_config)

        assert alerter.email_config == email_config

    def test_alerter_applies_custom_subject_prefix(self, email_config: EmailConfig, alert_config: dict) -> None:
        """When config specifies subject_prefix,
        the alerter uses that prefix."""
        alerter = EmailAlerter(email_config, alert_config)

        assert alerter.subject_prefix == "[ZFS Test]"

    def test_alerter_stores_alert_recipients(self, email_config: EmailConfig, alert_config: dict) -> None:
        """When config specifies alert_recipients,
        the alerter stores the recipient list."""
        alerter = EmailAlerter(email_config, alert_config)

        assert alerter.recipients == ["admin@example.com"]

    def test_alerter_uses_default_subject_prefix_when_not_configured(self, email_config: EmailConfig) -> None:
        """When config omits subject_prefix,
        the alerter uses '[ZFS Alert]' as default."""
        alerter = EmailAlerter(email_config, {})

        assert alerter.subject_prefix == "[ZFS Alert]"


@pytest.mark.os_agnostic
class TestEmailSubjectFormatting:
    """When formatting email subjects, content is descriptive and clear."""

    def test_format_subject_includes_severity_and_pool(self, alerter: EmailAlerter) -> None:
        """Subject should include hostname, severity, pool name, and message."""
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

    def test_format_subject_for_critical_issue(self, alerter: EmailAlerter) -> None:
        """Critical issues should be marked in subject."""
        subject = alerter._format_subject(Severity.CRITICAL, "data", "Pool degraded")

        assert "CRITICAL" in subject
        assert "data" in subject

    def test_format_body_includes_pool_details(self, alerter: EmailAlerter, sample_issue: PoolIssue, sample_pool: PoolStatus) -> None:
        """Email body should include complete pool information."""
        body = alerter._format_body(sample_issue, sample_pool)

        # Check key information is present
        assert "rpool" in body
        assert "85.5%" in body  # Capacity
        assert "WARNING" in body
        assert "capacity" in body
        assert "zpool status" in body  # Recommended action

    def test_format_body_includes_issue_details(self, alerter: EmailAlerter, sample_issue: PoolIssue, sample_pool: PoolStatus) -> None:
        """Email body should include issue details."""
        body = alerter._format_body(sample_issue, sample_pool)

        assert "threshold" in body
        assert "actual" in body

    def test_format_body_includes_recommended_actions_for_capacity(self, alerter: EmailAlerter, sample_pool: PoolStatus) -> None:
        """Capacity issues should have specific recommendations."""
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

    def test_format_body_includes_recommended_actions_for_errors(self, alerter: EmailAlerter, sample_pool: PoolStatus) -> None:
        """Error issues should have specific recommendations."""
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

    def test_format_body_includes_recommended_actions_for_scrub(self, alerter: EmailAlerter, sample_pool: PoolStatus) -> None:
        """Scrub issues should have specific recommendations."""
        issue = PoolIssue(
            pool_name="rpool",
            severity=Severity.INFO,
            category="scrub",
            message="Scrub overdue",
            details={},
        )

        body = alerter._format_body(issue, sample_pool)

        assert "zpool scrub" in body.lower()

    def test_format_body_includes_recommended_actions_for_health(self, alerter: EmailAlerter, sample_pool: PoolStatus) -> None:
        """Health issues should have specific recommendations."""
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

    @patch("check_zpools.alerting.send_email")
    def test_send_alert_calls_smtp(
        self,
        mock_send: MagicMock,
        alerter: EmailAlerter,
        sample_issue: PoolIssue,
        sample_pool: PoolStatus,
    ) -> None:
        """Sending alert should call send_email with correct parameters."""
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
    def test_send_alert_handles_smtp_failure(
        self,
        mock_send: MagicMock,
        alerter: EmailAlerter,
        sample_issue: PoolIssue,
        sample_pool: PoolStatus,
    ) -> None:
        """Failed email send should return False without crashing."""
        mock_send.side_effect = RuntimeError("SMTP connection failed")

        result = alerter.send_alert(sample_issue, sample_pool)

        assert result is False

    def test_send_alert_returns_false_with_no_recipients(self, email_config: EmailConfig, sample_issue: PoolIssue, sample_pool: PoolStatus) -> None:
        """Sending alert with no recipients should return False."""
        alerter = EmailAlerter(email_config, {"alert_recipients": []})

        result = alerter.send_alert(sample_issue, sample_pool)

        assert result is False

    def test_format_recovery_subject(self, alerter: EmailAlerter) -> None:
        """Recovery subject should include hostname and indicate issue resolved."""
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

    def test_format_recovery_body(self, alerter: EmailAlerter) -> None:
        """Recovery body should indicate issue resolved."""
        body = alerter._format_recovery_body("rpool", "capacity")

        assert "rpool" in body
        assert "capacity" in body
        assert "resolved" in body.lower()

    @patch("check_zpools.alerting.send_email")
    def test_send_recovery_calls_smtp(self, mock_send: MagicMock, alerter: EmailAlerter) -> None:
        """Sending recovery should call send_email."""
        mock_send.return_value = True

        result = alerter.send_recovery("rpool", "capacity")

        assert result is True
        mock_send.assert_called_once()

        call_kwargs = mock_send.call_args.kwargs
        assert "RECOVERY" in call_kwargs["subject"]
        assert "rpool" in call_kwargs["body"]

    def test_send_recovery_respects_config_flag(self, email_config: EmailConfig) -> None:
        """Recovery emails should be skipped if disabled."""
        alerter = EmailAlerter(email_config, {"send_recovery_emails": False, "alert_recipients": ["admin@example.com"]})

        result = alerter.send_recovery("rpool", "capacity")

        assert result is False

    @patch("check_zpools.alerting.send_email")
    def test_send_recovery_handles_smtp_failure(self, mock_send: MagicMock, alerter: EmailAlerter) -> None:
        """Failed recovery email should return False."""
        mock_send.side_effect = RuntimeError("SMTP error")

        result = alerter.send_recovery("rpool", "capacity")

        assert result is False

    def test_send_recovery_returns_false_with_no_recipients(self, email_config: EmailConfig) -> None:
        """Recovery with no recipients should return False."""
        alerter = EmailAlerter(email_config, {"alert_recipients": []})

        result = alerter.send_recovery("rpool", "capacity")

        assert result is False

    def test_email_includes_hostname(self, alerter: EmailAlerter, sample_issue: PoolIssue, sample_pool: PoolStatus) -> None:
        """Email should include hostname for identification."""
        body = alerter._format_body(sample_issue, sample_pool)

        # Should contain hostname somewhere
        assert "Hostname:" in body or "Host:" in body

    def test_email_includes_version(self, alerter: EmailAlerter, sample_issue: PoolIssue, sample_pool: PoolStatus) -> None:
        """Email should include tool version from pyproject.toml."""
        body = alerter._format_body(sample_issue, sample_pool)

        # Read version from pyproject.toml
        pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
        with pyproject_path.open("rb") as f:
            pyproject = tomllib.load(f)
        expected_version = pyproject["project"]["version"]

        # Should contain version number (e.g., "v1.0.0")
        assert f"v{expected_version}" in body or "version" in body.lower()

    def test_pool_with_scrub_in_progress(self, alerter: EmailAlerter, sample_issue: PoolIssue) -> None:
        """Pool with scrub in progress should show in email."""
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

    def test_pool_never_scrubbed(self, alerter: EmailAlerter, sample_issue: PoolIssue) -> None:
        """Pool never scrubbed should show in email."""
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
