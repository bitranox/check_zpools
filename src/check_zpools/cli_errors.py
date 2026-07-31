"""Shared error handling utilities for CLI commands.

Purpose
-------
Provides centralized error handling functions to eliminate duplication across
CLI commands. All commands use these shared handlers to ensure consistent
error messaging and exit codes.

Contents
--------
* :func:`handle_zfs_not_available` - Handle ZFSNotAvailableError exceptions
* :func:`handle_generic_error` - Handle unexpected exceptions with logging
* :func:`emit_json_error` - Emit a parseable error object for --format json
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, NoReturn

from pydantic import BaseModel

from . import safe_console
from .models import OutputFormat

if TYPE_CHECKING:
    from .zfs_client import ZFSNotAvailableError

logger = logging.getLogger(__name__)


class CliError(BaseModel):
    """The error object a structured caller receives instead of data.

    Why
        A caller parsing stdout must be able to tell "the command could not
        run" from "the command produced nothing". An empty stream cannot say
        which, so the JSON modes emit this instead. The type field carries the
        exception CLASS, so a caller branches on it rather than matching prose.
    """

    error: dict[str, str]

    @classmethod
    def of(cls, exc: Exception) -> CliError:
        """Build the error object from an exception."""
        return cls(error={"type": type(exc).__name__, "message": str(exc)})


def emit_json_error(exc: Exception, *, output_format: OutputFormat) -> None:
    """Print a parseable error object when the caller asked for JSON.

    Why
        Diagnostics belong on stderr, but the DATA stream must stay valid for
        the format the caller requested; otherwise a pipeline sees an empty
        stdout and cannot distinguish failure from an empty result.
    """
    if output_format is OutputFormat.JSON:
        safe_console.echo(CliError.of(exc).model_dump_json(indent=2))


def handle_zfs_not_available(exc: ZFSNotAvailableError, *, operation: str = "Operation") -> NoReturn:
    """Handle ZFS not available errors with consistent logging and messaging.

    Why
    ---
    All CLI commands need identical handling for ZFS unavailability. This
    centralizes the logging and user messaging to maintain consistency.

    Parameters
    ----------
    exc:
        The ZFSNotAvailableError exception that was raised.
    operation:
        Name of the operation that failed (for logging context).

    Raises
    ------
    SystemExit:
        Always exits with code 1 after logging and displaying error.

    Side Effects
    ------------
    Logs error message and displays user-friendly message to stderr.
    """
    logger.error("ZFS not available", extra={"error": str(exc), "operation": operation})
    safe_console.echo(f"\nError: {exc}", err=True)
    raise SystemExit(1)


def handle_generic_error(exc: Exception, *, operation: str = "Operation") -> NoReturn:
    """Handle unexpected errors with logging and user-friendly messaging.

    Why
    ---
    All CLI commands need identical handling for unexpected exceptions. This
    centralizes the logging, traceback capture, and user messaging.

    Parameters
    ----------
    exc:
        The exception that was raised.
    operation:
        Name of the operation that failed (displayed in error message).

    Raises
    ------
    SystemExit:
        Always exits with code 1 after logging and displaying error.

    Side Effects
    ------------
    Logs error with full traceback and displays user-friendly message to stderr.
    """
    logger.error(
        "%s failed",
        operation,
        extra={"error": str(exc), "error_type": type(exc).__name__},
        exc_info=True,
    )
    safe_console.echo(f"\nError: {exc}", err=True)
    raise SystemExit(1)


__all__ = [
    "CliError",
    "emit_json_error",
    "handle_generic_error",
    "handle_zfs_not_available",
]
