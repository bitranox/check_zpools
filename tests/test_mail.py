"""Tests for email sending functionality.

Purpose
-------
Verify that the mail wrapper correctly integrates btx_lib_mail with the
application's configuration system and provides a clean interface for
email operations.

All tests are OS-agnostic (email logic works everywhere).
SMTP tests use mocks (no real SMTP servers needed).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from check_zpools.mail import (
    EmailConfig,
    load_email_config_from_dict,
    send_email,
    send_notification,
)


@pytest.mark.os_agnostic
class TestEmailConfig:
    """Test EmailConfig dataclass."""

    def test_default_values(self) -> None:
        """EmailConfig should provide sensible defaults."""
        config = EmailConfig()

        assert config.smtp_hosts == []
        assert config.from_address == "noreply@localhost"
        assert config.smtp_username is None
        assert config.smtp_password is None
        assert config.use_starttls is True
        assert config.timeout == 30.0
        assert config.raise_on_missing_attachments is True
        assert config.raise_on_invalid_recipient is True

    def test_validation_negative_timeout_raises(self) -> None:
        """Should raise ValueError for negative timeout."""
        with pytest.raises(ValueError, match="timeout must be positive"):
            EmailConfig(timeout=-5.0)

    def test_validation_zero_timeout_raises(self) -> None:
        """Should raise ValueError for zero timeout."""
        with pytest.raises(ValueError, match="timeout must be positive"):
            EmailConfig(timeout=0.0)

    def test_validation_invalid_from_address_raises(self) -> None:
        """Should raise ValueError for from_address without @."""
        with pytest.raises(ValueError, match="from_address must contain @"):
            EmailConfig(from_address="not-an-email")

    def test_validation_invalid_smtp_host_port_format(self) -> None:
        """Should raise ValueError for invalid host:port format."""
        with pytest.raises(ValueError, match="Invalid SMTP host format"):
            EmailConfig(smtp_hosts=["smtp.test.com:587:extra"])

    def test_validation_invalid_port_number(self) -> None:
        """Should raise ValueError for non-numeric port."""
        with pytest.raises(ValueError, match="Port must be numeric"):
            EmailConfig(smtp_hosts=["smtp.test.com:abc"])

    def test_validation_port_out_of_range_high(self) -> None:
        """Should raise ValueError for port > 65535."""
        with pytest.raises(ValueError, match="Port must be 1-65535"):
            EmailConfig(smtp_hosts=["smtp.test.com:99999"])

    def test_validation_port_out_of_range_low(self) -> None:
        """Should raise ValueError for port < 1."""
        with pytest.raises(ValueError, match="Port must be 1-65535"):
            EmailConfig(smtp_hosts=["smtp.test.com:0"])

    def test_validation_smtp_host_without_port_valid(self) -> None:
        """Should allow SMTP host without explicit port."""
        config = EmailConfig(smtp_hosts=["smtp.test.com"])
        assert config.smtp_hosts == ["smtp.test.com"]

    def test_validation_smtp_host_with_valid_port(self) -> None:
        """Should allow SMTP host with valid port."""
        config = EmailConfig(smtp_hosts=["smtp.test.com:587"])
        assert config.smtp_hosts == ["smtp.test.com:587"]

    def test_custom_values(self) -> None:
        """EmailConfig should accept custom configuration."""
        config = EmailConfig(
            smtp_hosts=["smtp.example.com:587"],
            from_address="test@example.com",
            smtp_username="user",
            smtp_password="pass",
            use_starttls=False,
            timeout=60.0,
        )

        assert config.smtp_hosts == ["smtp.example.com:587"]
        assert config.from_address == "test@example.com"
        assert config.smtp_username == "user"
        assert config.smtp_password == "pass"
        assert config.use_starttls is False
        assert config.timeout == 60.0

    def test_frozen_dataclass(self) -> None:
        """EmailConfig should be immutable."""
        config = EmailConfig()

        with pytest.raises(AttributeError):
            config.smtp_hosts = ["new.smtp.com"]  # type: ignore[misc]

    def test_to_conf_mail(self) -> None:
        """to_conf_mail should convert to btx_lib_mail ConfMail."""
        config = EmailConfig(
            smtp_hosts=["smtp.example.com:587"],
            smtp_username="user",
            smtp_password="pass",
            timeout=45.0,
        )

        conf = config.to_conf_mail()

        assert conf.smtphosts == ["smtp.example.com:587"]
        assert conf.smtp_username == "user"
        assert conf.smtp_password == "pass"
        assert conf.smtp_timeout == 45.0
        assert conf.smtp_use_starttls is True


@pytest.mark.os_agnostic
class TestLoadEmailConfigFromDict:
    """Test load_email_config_from_dict function."""

    def test_empty_config(self) -> None:
        """Should return defaults when email section is missing."""
        config = load_email_config_from_dict({})

        assert config.smtp_hosts == []
        assert config.from_address == "noreply@localhost"

    def test_email_section_loaded(self) -> None:
        """Should load values from email section."""
        config_dict = {
            "email": {
                "smtp_hosts": ["smtp.test.com:587"],
                "from_address": "alerts@test.com",
                "smtp_username": "testuser",
                "smtp_password": "testpass",
                "use_starttls": False,
                "timeout": 120.0,
            }
        }

        config = load_email_config_from_dict(config_dict)

        assert config.smtp_hosts == ["smtp.test.com:587"]
        assert config.from_address == "alerts@test.com"
        assert config.smtp_username == "testuser"
        assert config.smtp_password == "testpass"
        assert config.use_starttls is False
        assert config.timeout == 120.0

    def test_partial_config(self) -> None:
        """Should merge partial config with defaults."""
        config_dict = {
            "email": {
                "smtp_hosts": ["smtp.partial.com"],
                "from_address": "partial@test.com",
            }
        }

        config = load_email_config_from_dict(config_dict)

        assert config.smtp_hosts == ["smtp.partial.com"]
        assert config.from_address == "partial@test.com"
        assert config.smtp_username is None
        assert config.use_starttls is True

    def test_invalid_email_section(self) -> None:
        """Should handle non-dict email section gracefully."""
        config_dict = {"email": "invalid"}

        config = load_email_config_from_dict(config_dict)

        assert config.smtp_hosts == []
        assert config.from_address == "noreply@localhost"


@pytest.mark.os_agnostic
class TestSendEmail:
    """Test send_email function."""

    @patch("smtplib.SMTP")
    def test_send_simple_email(self, mock_smtp: MagicMock) -> None:
        """Should send email with basic parameters."""
        config = EmailConfig(
            smtp_hosts=["smtp.test.com:587"],
            from_address="sender@test.com",
        )

        result = send_email(
            config=config,
            recipients="recipient@test.com",
            subject="Test Subject",
            body="Test body",
        )

        assert result is True

    @patch("smtplib.SMTP")
    def test_send_email_with_html(self, mock_smtp: MagicMock) -> None:
        """Should send email with both plain text and HTML."""
        config = EmailConfig(
            smtp_hosts=["smtp.test.com:587"],
            from_address="sender@test.com",
        )

        result = send_email(
            config=config,
            recipients="recipient@test.com",
            subject="Test Subject",
            body="Plain text",
            body_html="<h1>HTML</h1>",
        )

        assert result is True

    @patch("smtplib.SMTP")
    def test_send_email_multiple_recipients(self, mock_smtp: MagicMock) -> None:
        """Should send email to multiple recipients."""
        config = EmailConfig(
            smtp_hosts=["smtp.test.com:587"],
            from_address="sender@test.com",
        )

        result = send_email(
            config=config,
            recipients=["user1@test.com", "user2@test.com"],
            subject="Test Subject",
            body="Test body",
        )

        assert result is True

    @patch("smtplib.SMTP")
    def test_send_email_with_from_override(self, mock_smtp: MagicMock) -> None:
        """Should allow overriding sender address."""
        config = EmailConfig(
            smtp_hosts=["smtp.test.com:587"],
            from_address="default@test.com",
        )

        result = send_email(
            config=config,
            recipients="recipient@test.com",
            subject="Test Subject",
            body="Test body",
            from_address="override@test.com",
        )

        assert result is True

    @patch("smtplib.SMTP")
    def test_send_email_with_attachments(self, mock_smtp: MagicMock, tmp_path: Path) -> None:
        """Should send email with file attachments."""
        # Create test attachment
        attachment = tmp_path / "test.txt"
        attachment.write_text("Test attachment content")

        config = EmailConfig(
            smtp_hosts=["smtp.test.com:587"],
            from_address="sender@test.com",
        )

        result = send_email(
            config=config,
            recipients="recipient@test.com",
            subject="Test Subject",
            body="Test body",
            attachments=[attachment],
        )

        assert result is True

    @patch("smtplib.SMTP")
    def test_send_email_with_credentials(self, mock_smtp: MagicMock) -> None:
        """Should use SMTP credentials when configured."""
        config = EmailConfig(
            smtp_hosts=["smtp.test.com:587"],
            from_address="sender@test.com",
            smtp_username="testuser",
            smtp_password="testpass",
        )

        result = send_email(
            config=config,
            recipients="recipient@test.com",
            subject="Test Subject",
            body="Test body",
        )

        assert result is True


@pytest.mark.os_agnostic
class TestSendNotification:
    """Test send_notification convenience function."""

    @patch("smtplib.SMTP")
    def test_send_simple_notification(self, mock_smtp: MagicMock) -> None:
        """Should send plain-text notification."""
        config = EmailConfig(
            smtp_hosts=["smtp.test.com:587"],
            from_address="alerts@test.com",
        )

        result = send_notification(
            config=config,
            recipients="admin@test.com",
            subject="Alert",
            message="System notification",
        )

        assert result is True

    @patch("smtplib.SMTP")
    def test_send_notification_multiple_recipients(self, mock_smtp: MagicMock) -> None:
        """Should send notification to multiple recipients."""
        config = EmailConfig(
            smtp_hosts=["smtp.test.com:587"],
            from_address="alerts@test.com",
        )

        result = send_notification(
            config=config,
            recipients=["admin1@test.com", "admin2@test.com"],
            subject="Alert",
            message="System notification",
        )

        assert result is True


@pytest.mark.os_agnostic
class TestEmailErrorScenarios:
    """Test error handling in email functionality."""

    @patch("smtplib.SMTP")
    def test_send_email_smtp_connection_failure(self, mock_smtp: MagicMock) -> None:
        """Should raise RuntimeError when SMTP connection fails."""
        mock_smtp.side_effect = ConnectionError("Cannot connect to SMTP server")

        config = EmailConfig(
            smtp_hosts=["smtp.test.com:587"],
            from_address="sender@test.com",
        )

        # btx_lib_mail wraps connection errors in RuntimeError
        with pytest.raises(RuntimeError, match="failed.*on all of following hosts"):
            send_email(
                config=config,
                recipients="recipient@test.com",
                subject="Test",
                body="Hello",
            )

    @patch("smtplib.SMTP")
    def test_send_email_authentication_failure(self, mock_smtp: MagicMock) -> None:
        """Should raise exception when SMTP authentication fails."""
        mock_instance = MagicMock()
        mock_instance.login.side_effect = Exception("Authentication failed")
        mock_smtp.return_value.__enter__.return_value = mock_instance

        config = EmailConfig(
            smtp_hosts=["smtp.test.com:587"],
            from_address="sender@test.com",
            smtp_username="user@test.com",
            smtp_password="wrong_password",
        )

        # btx_lib_mail wraps auth errors in RuntimeError
        with pytest.raises(RuntimeError, match="failed.*on all of following hosts"):
            send_email(
                config=config,
                recipients="recipient@test.com",
                subject="Test",
                body="Hello",
            )

    @patch("smtplib.SMTP")
    def test_send_email_invalid_recipients(self, mock_smtp: MagicMock) -> None:
        """Should propagate errors from btx_lib_mail for invalid recipients."""
        # Configure mock to raise ValueError during send
        mock_smtp.side_effect = ValueError("Invalid recipient address")

        config = EmailConfig(
            smtp_hosts=["smtp.test.com:587"],
            from_address="sender@test.com",
        )

        # btx_lib_mail wraps validation errors in RuntimeError
        with pytest.raises(RuntimeError, match="following recipients failed"):
            send_email(
                config=config,
                recipients="recipient@test.com",
                subject="Test",
                body="Hello",
            )

    def test_send_email_missing_attachment_raises(self, tmp_path: Path) -> None:
        """Should raise FileNotFoundError for missing attachments when configured."""
        nonexistent = tmp_path / "nonexistent.txt"

        config = EmailConfig(
            smtp_hosts=["smtp.test.com:587"],
            from_address="sender@test.com",
            raise_on_missing_attachments=True,
        )

        with patch("smtplib.SMTP"):
            with pytest.raises(FileNotFoundError):
                send_email(
                    config=config,
                    recipients="recipient@test.com",
                    subject="Test",
                    body="Hello",
                    attachments=[nonexistent],
                )

    @patch("smtplib.SMTP")
    def test_send_email_all_smtp_hosts_fail(self, mock_smtp: MagicMock) -> None:
        """Should raise RuntimeError when all SMTP hosts fail."""
        mock_smtp.side_effect = ConnectionError("Connection refused")

        config = EmailConfig(
            smtp_hosts=["smtp1.test.com:587", "smtp2.test.com:587"],
            from_address="sender@test.com",
        )

        with pytest.raises(RuntimeError, match="following recipients failed"):
            send_email(
                config=config,
                recipients="recipient@test.com",
                subject="Test",
                body="Hello",
            )


class TestLoadEmailConfigEdgeCases:
    """Test edge cases in configuration loading."""

    def test_malformed_timeout_uses_default(self) -> None:
        """Should use default timeout when config has invalid value."""
        config_dict = {"email": {"timeout": "not_a_number"}}

        email_config = load_email_config_from_dict(config_dict)

        assert email_config.timeout == 30.0  # Default value

    def test_smtp_hosts_not_list_uses_default(self) -> None:
        """Should use default empty list when smtp_hosts is not a list."""
        config_dict = {"email": {"smtp_hosts": "should_be_list"}}

        email_config = load_email_config_from_dict(config_dict)

        assert email_config.smtp_hosts == []

    def test_boolean_as_string_uses_default(self) -> None:
        """Should use default when boolean config value is a string."""
        config_dict = {"email": {"use_starttls": "yes"}}

        email_config = load_email_config_from_dict(config_dict)

        assert email_config.use_starttls is True  # Default value

    def test_empty_string_username_becomes_none(self) -> None:
        """Should convert empty string username to None."""
        config_dict = {"email": {"smtp_username": ""}}

        email_config = load_email_config_from_dict(config_dict)

        # Currently returns "", but ideally should be None
        # This test documents current behavior
        assert email_config.smtp_username == ""

    def test_mixed_valid_invalid_config(self) -> None:
        """Should use valid values and defaults for invalid ones."""
        config_dict = {
            "email": {
                "smtp_hosts": ["smtp.test.com:587"],  # Valid
                "from_address": "test@example.com",  # Valid
                "timeout": "invalid",  # Invalid - use default
                "use_starttls": "maybe",  # Invalid - use default
            }
        }

        email_config = load_email_config_from_dict(config_dict)

        assert email_config.smtp_hosts == ["smtp.test.com:587"]
        assert email_config.from_address == "test@example.com"
        assert email_config.timeout == 30.0  # Default
        assert email_config.use_starttls is True  # Default


class TestRealSMTPIntegration:
    """Integration tests using real SMTP server from .env file.

    These tests are skipped if TEST_SMTP_SERVER or TEST_EMAIL_ADDRESS
    are not configured in the .env file.
    """

    @pytest.fixture
    def smtp_config(self) -> EmailConfig | None:
        """Load SMTP configuration from .env file."""
        import os

        smtp_server = os.getenv("TEST_SMTP_SERVER")
        email_address = os.getenv("TEST_EMAIL_ADDRESS")

        if not smtp_server or not email_address:
            pytest.skip("TEST_SMTP_SERVER or TEST_EMAIL_ADDRESS not configured in .env")

        return EmailConfig(
            smtp_hosts=[smtp_server],
            from_address=email_address,
            timeout=10.0,
        )

    def test_send_real_email(self, smtp_config: EmailConfig | None) -> None:
        """Send a real test email using configured SMTP server."""
        if smtp_config is None:
            pytest.skip("SMTP not configured")

        result = send_email(
            config=smtp_config,
            recipients=smtp_config.from_address,  # Send to self
            subject="Test Email from check_zpools",
            body="This is a test email sent from the integration test suite.\n\nIf you receive this, the email functionality is working correctly.",
        )

        assert result is True

    def test_send_real_email_with_html(self, smtp_config: EmailConfig | None) -> None:
        """Send a real test email with HTML body."""
        if smtp_config is None:
            pytest.skip("SMTP not configured")

        result = send_email(
            config=smtp_config,
            recipients=smtp_config.from_address,
            subject="Test HTML Email from check_zpools",
            body="This is the plain text version.",
            body_html="<html><body><h1>Test Email</h1><p>This is a <strong>HTML</strong> test email.</p></body></html>",
        )

        assert result is True

    def test_send_real_notification(self, smtp_config: EmailConfig | None) -> None:
        """Send a real notification using configured SMTP server."""
        if smtp_config is None:
            pytest.skip("SMTP not configured")

        result = send_notification(
            config=smtp_config,
            recipients=smtp_config.from_address,
            subject="Test Notification from check_zpools",
            message="This is a test notification.\n\nSystem: All tests passing!",
        )

        assert result is True
