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
"""

from __future__ import annotations

import logging
from typing import NoReturn

import rich_click as click

from .zfs_client import ZFSNotAvailableError

logger = logging.getLogger(__name__)


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
    click.echo(f"\nError: {exc}", err=True)
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
        f"{operation} failed",
        extra={"error": str(exc), "error_type": type(exc).__name__},
        exc_info=True,
    )
    click.echo(f"\nError: {exc}", err=True)
    raise SystemExit(1)


__all__ = [
    "handle_zfs_not_available",
    "handle_generic_error",
]
