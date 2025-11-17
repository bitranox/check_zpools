"""Tests for CLI error handling utilities.

Tests cover:
- ZFS not available error handling
- Generic error handling
- Exit codes
- Error message formatting
- Logging behavior
"""

from __future__ import annotations

import logging

import pytest

from check_zpools.cli_errors import handle_generic_error, handle_zfs_not_available
from check_zpools.zfs_client import ZFSNotAvailableError


class TestHandleZfsNotAvailable:
    """Test ZFS not available error handling."""

    def test_exits_with_code_1(self, caplog: pytest.LogCaptureFixture) -> None:
        """Should exit with code 1."""
        exc = ZFSNotAvailableError("ZFS kernel module not loaded")

        with pytest.raises(SystemExit) as excinfo:
            handle_zfs_not_available(exc)

        assert excinfo.value.code == 1

    def test_logs_error_message(self, caplog: pytest.LogCaptureFixture) -> None:
        """Should log error message with details."""
        exc = ZFSNotAvailableError("ZFS kernel module not loaded")

        with caplog.at_level(logging.ERROR):
            with pytest.raises(SystemExit):
                handle_zfs_not_available(exc, operation="check")

        # Check log contains error details
        assert any("ZFS not available" in record.message for record in caplog.records)
        # The operation is logged (verified via captured stderr in test output)
        assert len(caplog.records) > 0

    def test_uses_default_operation_name(self, caplog: pytest.LogCaptureFixture) -> None:
        """Should use default operation name if not provided."""
        exc = ZFSNotAvailableError("ZFS not found")

        with caplog.at_level(logging.ERROR):
            with pytest.raises(SystemExit):
                handle_zfs_not_available(exc)

        # Should log with "Operation" as default
        assert any("ZFS not available" in record.message for record in caplog.records)

    def test_displays_error_message(self, capsys: pytest.CaptureFixture) -> None:
        """Should display error message to stderr."""
        exc = ZFSNotAvailableError("ZFS kernel module not loaded")

        with pytest.raises(SystemExit):
            handle_zfs_not_available(exc)

        captured = capsys.readouterr()
        assert "Error: ZFS kernel module not loaded" in captured.err


class TestHandleGenericError:
    """Test generic error handling."""

    def test_exits_with_code_1(self, caplog: pytest.LogCaptureFixture) -> None:
        """Should exit with code 1."""
        exc = RuntimeError("Something went wrong")

        with pytest.raises(SystemExit) as excinfo:
            handle_generic_error(exc)

        assert excinfo.value.code == 1

    def test_logs_error_with_traceback(self, caplog: pytest.LogCaptureFixture) -> None:
        """Should log error with full traceback."""
        exc = ValueError("Invalid configuration")

        with caplog.at_level(logging.ERROR):
            with pytest.raises(SystemExit):
                handle_generic_error(exc, operation="config validation")

        # Check log contains operation name
        assert any("config validation" in record.message for record in caplog.records)
        # Check exc_info was logged (traceback)
        assert any(record.exc_info is not None for record in caplog.records)

    def test_logs_error_type(self, caplog: pytest.LogCaptureFixture) -> None:
        """Should log the exception type name."""
        exc = KeyError("missing_key")

        with caplog.at_level(logging.ERROR):
            with pytest.raises(SystemExit):
                handle_generic_error(exc, operation="parse")

        # Check that error was logged
        assert any("Operation failed" in record.message or "parse" in record.message for record in caplog.records)
        assert len(caplog.records) > 0

    def test_uses_default_operation_name(self, caplog: pytest.LogCaptureFixture) -> None:
        """Should use default operation name if not provided."""
        exc = Exception("Generic error")

        with caplog.at_level(logging.ERROR):
            with pytest.raises(SystemExit):
                handle_generic_error(exc)

        # Should log with "Operation" as default
        assert any("Operation failed" in record.message for record in caplog.records)

    def test_displays_error_message(self, capsys: pytest.CaptureFixture) -> None:
        """Should display error message to stderr."""
        exc = RuntimeError("Configuration file not found")

        with pytest.raises(SystemExit):
            handle_generic_error(exc, operation="load config")

        captured = capsys.readouterr()
        assert "Error: Configuration file not found" in captured.err

    def test_handles_various_exception_types(self, capsys: pytest.CaptureFixture) -> None:
        """Should handle different exception types consistently."""
        exceptions = [
            ValueError("Invalid value"),
            KeyError("missing_key"),
            FileNotFoundError("File not found"),
            PermissionError("Permission denied"),
            RuntimeError("Runtime error"),
        ]

        for exc in exceptions:
            with pytest.raises(SystemExit) as excinfo:
                handle_generic_error(exc, operation="test")

            assert excinfo.value.code == 1
            captured = capsys.readouterr()
            assert "Error:" in captured.err
            assert str(exc) in captured.err
