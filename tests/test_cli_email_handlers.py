"""Tests for CLI email error handling utilities.

Design Philosophy
-----------------
These tests validate email-related error handling extracted from CLI commands:
- Test names read like plain English sentences describing exact behavior
- Each test validates ONE specific behavior
- OS-agnostic — pure Python error handling and logging

Coverage Strategy
-----------------
- SMTP configuration validation (empty hosts, configured hosts)
- Email send error handling (known types, unknown types)
- Exit codes (always 1)
- Stderr output (user-facing error messages)
- Logging behavior (error messages with context)
"""

from __future__ import annotations

import logging

import pytest

from check_zpools.cli_email_handlers import handle_send_email_error, validate_smtp_configuration
from check_zpools.mail import EmailConfig


# ============================================================================
# Tests: SMTP Configuration Validation — Exit Behavior
# ============================================================================


class TestSmtpValidationExitsBehavior:
    """When SMTP hosts are not configured, the validator exits with code 1."""

    @pytest.mark.os_agnostic
    def test_exits_with_code_one_when_smtp_hosts_empty(self) -> None:
        """When smtp_hosts is an empty list,
        the validator exits with code 1."""
        config = EmailConfig(smtp_hosts=[])

        with pytest.raises(SystemExit) as excinfo:
            validate_smtp_configuration(config)

        assert excinfo.value.code == 1

    @pytest.mark.os_agnostic
    def test_passes_silently_when_smtp_hosts_configured(self) -> None:
        """When smtp_hosts contains at least one host,
        the validator returns without error."""
        config = EmailConfig(smtp_hosts=["smtp.example.com:587"])

        validate_smtp_configuration(config)


# ============================================================================
# Tests: SMTP Configuration Validation — Stderr Output
# ============================================================================


class TestSmtpValidationStderrOutput:
    """When SMTP hosts are missing, the validator displays helpful guidance."""

    @pytest.mark.os_agnostic
    def test_displays_missing_config_message(self, capsys: pytest.CaptureFixture[str]) -> None:
        """When smtp_hosts is empty,
        an error message mentioning SMTP configuration appears on stderr."""
        config = EmailConfig(smtp_hosts=[])

        with pytest.raises(SystemExit):
            validate_smtp_configuration(config)

        captured = capsys.readouterr()
        assert "No SMTP hosts configured" in captured.err

    @pytest.mark.os_agnostic
    def test_displays_config_deploy_hint(self, capsys: pytest.CaptureFixture[str]) -> None:
        """When smtp_hosts is empty,
        stderr includes a hint about config-deploy."""
        config = EmailConfig(smtp_hosts=[])

        with pytest.raises(SystemExit):
            validate_smtp_configuration(config)

        captured = capsys.readouterr()
        assert "config-deploy" in captured.err


# ============================================================================
# Tests: SMTP Configuration Validation — Logging
# ============================================================================


class TestSmtpValidationLogging:
    """When SMTP hosts are missing, the validator logs an error."""

    @pytest.mark.os_agnostic
    def test_logs_error_when_hosts_empty(self, caplog: pytest.LogCaptureFixture) -> None:
        """When smtp_hosts is empty,
        an ERROR level log message is written."""
        config = EmailConfig(smtp_hosts=[])

        with caplog.at_level(logging.ERROR):
            with pytest.raises(SystemExit):
                validate_smtp_configuration(config)

        assert any("No SMTP hosts configured" in record.message for record in caplog.records)


# ============================================================================
# Tests: Email Send Error Handling — Exit Behavior
# ============================================================================


class TestSendEmailErrorExitBehavior:
    """When an email send error occurs, the handler always exits with code 1."""

    @pytest.mark.os_agnostic
    def test_exits_with_code_one_for_value_error(self) -> None:
        """When handling a ValueError,
        the process exits with code 1."""
        exc = ValueError("Invalid recipient")

        with pytest.raises(SystemExit) as excinfo:
            handle_send_email_error(exc, "ValueError")

        assert excinfo.value.code == 1

    @pytest.mark.os_agnostic
    def test_exits_with_code_one_for_file_not_found_error(self) -> None:
        """When handling a FileNotFoundError,
        the process exits with code 1."""
        exc = FileNotFoundError("/tmp/attachment.pdf")

        with pytest.raises(SystemExit) as excinfo:
            handle_send_email_error(exc, "FileNotFoundError")

        assert excinfo.value.code == 1

    @pytest.mark.os_agnostic
    def test_exits_with_code_one_for_runtime_error(self) -> None:
        """When handling a RuntimeError,
        the process exits with code 1."""
        exc = RuntimeError("SMTP connection refused")

        with pytest.raises(SystemExit) as excinfo:
            handle_send_email_error(exc, "RuntimeError")

        assert excinfo.value.code == 1

    @pytest.mark.os_agnostic
    def test_exits_with_code_one_for_unknown_error_type(self) -> None:
        """When handling an unknown error type,
        the process exits with code 1."""
        exc = OSError("Network unreachable")

        with pytest.raises(SystemExit) as excinfo:
            handle_send_email_error(exc, "OSError")

        assert excinfo.value.code == 1


# ============================================================================
# Tests: Email Send Error Handling — Stderr Output
# ============================================================================


class TestSendEmailErrorStderrOutput:
    """Error messages are displayed to stderr with context-specific phrasing."""

    @pytest.mark.os_agnostic
    def test_value_error_shows_invalid_parameters_message(self, capsys: pytest.CaptureFixture[str]) -> None:
        """When handling a ValueError,
        stderr shows 'Invalid email parameters' with the exception detail."""
        exc = ValueError("Bad recipient address")

        with pytest.raises(SystemExit):
            handle_send_email_error(exc, "ValueError")

        captured = capsys.readouterr()
        assert "Invalid email parameters" in captured.err
        assert "Bad recipient address" in captured.err

    @pytest.mark.os_agnostic
    def test_file_not_found_error_shows_attachment_message(self, capsys: pytest.CaptureFixture[str]) -> None:
        """When handling a FileNotFoundError,
        stderr shows 'Attachment file not found' with the exception detail."""
        exc = FileNotFoundError("/tmp/missing.pdf")

        with pytest.raises(SystemExit):
            handle_send_email_error(exc, "FileNotFoundError")

        captured = capsys.readouterr()
        assert "Attachment file not found" in captured.err
        assert "/tmp/missing.pdf" in captured.err

    @pytest.mark.os_agnostic
    def test_runtime_error_shows_delivery_failure_message(self, capsys: pytest.CaptureFixture[str]) -> None:
        """When handling a RuntimeError,
        stderr shows 'Failed to send email' with the exception detail."""
        exc = RuntimeError("Connection refused")

        with pytest.raises(SystemExit):
            handle_send_email_error(exc, "RuntimeError")

        captured = capsys.readouterr()
        assert "Failed to send email" in captured.err
        assert "Connection refused" in captured.err

    @pytest.mark.os_agnostic
    def test_unknown_error_type_shows_unexpected_error_message(self, capsys: pytest.CaptureFixture[str]) -> None:
        """When handling an unrecognized error type,
        stderr shows 'Unexpected error' with the exception detail."""
        exc = OSError("Network unreachable")

        with pytest.raises(SystemExit):
            handle_send_email_error(exc, "OSError")

        captured = capsys.readouterr()
        assert "Unexpected error" in captured.err
        assert "Network unreachable" in captured.err


# ============================================================================
# Tests: Email Send Error Handling — Logging
# ============================================================================


class TestSendEmailErrorLogging:
    """Error messages are logged with appropriate context."""

    @pytest.mark.os_agnostic
    def test_value_error_logs_invalid_parameters(self, caplog: pytest.LogCaptureFixture) -> None:
        """When handling a ValueError,
        an ERROR log with 'Invalid email parameters' is written."""
        exc = ValueError("Bad address")

        with caplog.at_level(logging.ERROR):
            with pytest.raises(SystemExit):
                handle_send_email_error(exc, "ValueError")

        assert any("Invalid email parameters" in record.message for record in caplog.records)

    @pytest.mark.os_agnostic
    def test_unknown_error_type_logs_unexpected_error(self, caplog: pytest.LogCaptureFixture) -> None:
        """When handling an unknown error type,
        an ERROR log with 'Unexpected error sending email' is written."""
        exc = OSError("Disk full")

        with caplog.at_level(logging.ERROR):
            with pytest.raises(SystemExit):
                handle_send_email_error(exc, "OSError")

        assert any("Unexpected error sending email" in record.message for record in caplog.records)

    @pytest.mark.os_agnostic
    def test_known_error_type_does_not_include_traceback(self, caplog: pytest.LogCaptureFixture) -> None:
        """When handling a known error type like ValueError,
        the log does not include exc_info traceback."""
        exc = ValueError("Bad address")

        with caplog.at_level(logging.ERROR):
            with pytest.raises(SystemExit):
                handle_send_email_error(exc, "ValueError")

        error_records = [r for r in caplog.records if "Invalid email parameters" in r.message]
        assert len(error_records) > 0
        exc_info = error_records[0].exc_info
        assert not exc_info or (isinstance(exc_info, tuple) and exc_info[0] is None)

    @pytest.mark.os_agnostic
    def test_unknown_error_type_includes_traceback(self, caplog: pytest.LogCaptureFixture) -> None:
        """When handling an unknown error type,
        the log includes exc_info for debugging."""
        exc = OSError("Disk full")

        with caplog.at_level(logging.ERROR):
            with pytest.raises(SystemExit):
                handle_send_email_error(exc, "OSError")

        error_records = [r for r in caplog.records if "Unexpected error" in r.message]
        assert len(error_records) > 0
        assert error_records[0].exc_info is not None
