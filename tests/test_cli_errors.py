"""Tests for CLI error handling utilities.

Tests cover:
- ZFS not available error handling
- Generic error handling
- Exit codes
- Error message formatting
- Logging behavior

All tests are OS-agnostic (pure Python error handling and logging).
"""

from __future__ import annotations

import logging

import pytest

from check_zpools.cli_errors import handle_generic_error, handle_zfs_not_available
from check_zpools.zfs_client import ZFSNotAvailableError


# ============================================================================
# Tests: ZFS Not Available Error Handling
# ============================================================================


class TestZfsNotAvailableExitBehavior:
    """When ZFS is not available, the handler exits with code 1."""

    @pytest.mark.os_agnostic
    def test_handler_exits_with_code_one(self) -> None:
        """When handling a ZFS not available error,
        the process exits with code 1."""
        exc = ZFSNotAvailableError("ZFS kernel module not loaded")

        with pytest.raises(SystemExit) as excinfo:
            handle_zfs_not_available(exc)

        assert excinfo.value.code == 1


class TestZfsNotAvailableLogging:
    """When ZFS is not available, the handler logs appropriate error messages."""

    @pytest.mark.os_agnostic
    def test_handler_logs_error_message_with_details(self, caplog: pytest.LogCaptureFixture) -> None:
        """When handling a ZFS not available error,
        an ERROR level log message is written."""
        exc = ZFSNotAvailableError("ZFS kernel module not loaded")

        with caplog.at_level(logging.ERROR):
            with pytest.raises(SystemExit):
                handle_zfs_not_available(exc, operation="check")

        assert any("ZFS not available" in record.message for record in caplog.records)
        assert len(caplog.records) > 0

    @pytest.mark.os_agnostic
    def test_handler_uses_default_operation_name_when_not_provided(self, caplog: pytest.LogCaptureFixture) -> None:
        """When no operation name is provided,
        the handler uses a default operation name in logs."""
        exc = ZFSNotAvailableError("ZFS not found")

        with caplog.at_level(logging.ERROR):
            with pytest.raises(SystemExit):
                handle_zfs_not_available(exc)

        assert any("ZFS not available" in record.message for record in caplog.records)


class TestZfsNotAvailableStderrOutput:
    """When ZFS is not available, the handler displays error to stderr."""

    @pytest.mark.os_agnostic
    def test_handler_displays_error_message_to_stderr(self, capsys: pytest.CaptureFixture) -> None:
        """When handling a ZFS not available error,
        the error message appears on stderr."""
        exc = ZFSNotAvailableError("ZFS kernel module not loaded")

        with pytest.raises(SystemExit):
            handle_zfs_not_available(exc)

        captured = capsys.readouterr()
        assert "Error: ZFS kernel module not loaded" in captured.err


# ============================================================================
# Tests: Generic Error Handling
# ============================================================================


class TestGenericErrorExitBehavior:
    """When handling generic errors, the handler exits with code 1."""

    @pytest.mark.os_agnostic
    def test_handler_exits_with_code_one(self) -> None:
        """When handling a generic error,
        the process exits with code 1."""
        exc = RuntimeError("Something went wrong")

        with pytest.raises(SystemExit) as excinfo:
            handle_generic_error(exc)

        assert excinfo.value.code == 1


class TestGenericErrorLogging:
    """When handling generic errors, the handler logs errors with tracebacks."""

    @pytest.mark.os_agnostic
    def test_handler_logs_error_with_full_traceback(self, caplog: pytest.LogCaptureFixture) -> None:
        """When handling a generic error,
        an ERROR log is written with full traceback information."""
        exc = ValueError("Invalid configuration")

        with caplog.at_level(logging.ERROR):
            with pytest.raises(SystemExit):
                handle_generic_error(exc, operation="config validation")

        assert any("config validation" in record.message for record in caplog.records)
        assert any(record.exc_info is not None for record in caplog.records)

    @pytest.mark.os_agnostic
    def test_handler_logs_exception_type_name(self, caplog: pytest.LogCaptureFixture) -> None:
        """When handling a generic error,
        the log includes information about the exception type."""
        exc = KeyError("missing_key")

        with caplog.at_level(logging.ERROR):
            with pytest.raises(SystemExit):
                handle_generic_error(exc, operation="parse")

        assert any("Operation failed" in record.message or "parse" in record.message for record in caplog.records)
        assert len(caplog.records) > 0

    @pytest.mark.os_agnostic
    def test_handler_uses_default_operation_name_when_not_provided(self, caplog: pytest.LogCaptureFixture) -> None:
        """When no operation name is provided,
        the handler uses a default operation name in logs."""
        exc = Exception("Generic error")

        with caplog.at_level(logging.ERROR):
            with pytest.raises(SystemExit):
                handle_generic_error(exc)

        assert any("Operation failed" in record.message for record in caplog.records)


class TestGenericErrorStderrOutput:
    """When handling generic errors, the handler displays error to stderr."""

    @pytest.mark.os_agnostic
    def test_handler_displays_error_message_to_stderr(self, capsys: pytest.CaptureFixture) -> None:
        """When handling a generic error,
        the error message appears on stderr."""
        exc = RuntimeError("Configuration file not found")

        with pytest.raises(SystemExit):
            handle_generic_error(exc, operation="load config")

        captured = capsys.readouterr()
        assert "Error: Configuration file not found" in captured.err


class TestGenericErrorHandlesVariousExceptionTypes:
    """The generic error handler works consistently with all exception types."""

    @pytest.mark.os_agnostic
    def test_value_error_exits_with_code_one(self, capsys: pytest.CaptureFixture) -> None:
        """When handling a ValueError,
        the process exits with code 1 and displays the message."""
        exc = ValueError("Invalid value")

        with pytest.raises(SystemExit) as excinfo:
            handle_generic_error(exc, operation="test")

        assert excinfo.value.code == 1
        captured = capsys.readouterr()
        assert "Error:" in captured.err
        assert "Invalid value" in captured.err

    @pytest.mark.os_agnostic
    def test_key_error_exits_with_code_one(self, capsys: pytest.CaptureFixture) -> None:
        """When handling a KeyError,
        the process exits with code 1 and displays the message."""
        exc = KeyError("missing_key")

        with pytest.raises(SystemExit) as excinfo:
            handle_generic_error(exc, operation="test")

        assert excinfo.value.code == 1
        captured = capsys.readouterr()
        assert "Error:" in captured.err
        assert "missing_key" in captured.err

    @pytest.mark.os_agnostic
    def test_file_not_found_error_exits_with_code_one(self, capsys: pytest.CaptureFixture) -> None:
        """When handling a FileNotFoundError,
        the process exits with code 1 and displays the message."""
        exc = FileNotFoundError("File not found")

        with pytest.raises(SystemExit) as excinfo:
            handle_generic_error(exc, operation="test")

        assert excinfo.value.code == 1
        captured = capsys.readouterr()
        assert "Error:" in captured.err
        assert "File not found" in captured.err

    @pytest.mark.os_agnostic
    def test_permission_error_exits_with_code_one(self, capsys: pytest.CaptureFixture) -> None:
        """When handling a PermissionError,
        the process exits with code 1 and displays the message."""
        exc = PermissionError("Permission denied")

        with pytest.raises(SystemExit) as excinfo:
            handle_generic_error(exc, operation="test")

        assert excinfo.value.code == 1
        captured = capsys.readouterr()
        assert "Error:" in captured.err
        assert "Permission denied" in captured.err

    @pytest.mark.os_agnostic
    def test_runtime_error_exits_with_code_one(self, capsys: pytest.CaptureFixture) -> None:
        """When handling a RuntimeError,
        the process exits with code 1 and displays the message."""
        exc = RuntimeError("Runtime error")

        with pytest.raises(SystemExit) as excinfo:
            handle_generic_error(exc, operation="test")

        assert excinfo.value.code == 1
        captured = capsys.readouterr()
        assert "Error:" in captured.err
        assert "Runtime error" in captured.err
