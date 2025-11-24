"""Email error handling for CLI commands.

Purpose
-------
Centralize email-related error handling that was duplicated across
multiple email commands in cli.py. Provides consistent error messages
and exit codes for email configuration and sending failures.

Why
    Extracted from cli.py to eliminate code duplication and follow DRY
    principle. Error handling patterns were repeated 3+ times across
    email commands.

Contents
--------
* :func:`validate_smtp_configuration` - validate SMTP hosts are configured
* :func:`handle_send_email_error` - handle errors during email sending operations
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import rich_click as click

if TYPE_CHECKING:
    from .mail import EmailConfig

logger = logging.getLogger(__name__)


def validate_smtp_configuration(email_config: "EmailConfig") -> None:
    """Validate SMTP configuration is present.

    Why
        Eliminates duplicated SMTP validation code across CLI email commands
        (send-email and send-notification). Provides consistent error messages
        and logging.

    Parameters
    ----------
    email_config:
        Email configuration to validate.

    Raises
    ------
    SystemExit:
        If SMTP hosts not configured (exits with code 1).

    Examples
    --------
    >>> from check_zpools.mail import EmailConfig
    >>> config = EmailConfig(smtp_hosts=[])
    >>> validate_smtp_configuration(config)  # doctest: +SKIP
    Traceback (most recent call last):
    ...
    SystemExit: 1
    """
    if not email_config.smtp_hosts:
        logger.error("No SMTP hosts configured")
        click.echo(
            "\nError: No SMTP hosts configured. Please configure email.smtp_hosts in your config file.",
            err=True,
        )
        click.echo(
            "See: check_zpools config-deploy --target user",
            err=True,
        )
        raise SystemExit(1)


def handle_send_email_error(exc: Exception, error_type: str) -> None:
    """Handle and log email sending errors.

    Why
        Eliminates duplicated error handling across CLI email commands.
        Maintains compatibility with existing CLI tests by using click.echo
        for error output.

    Parameters
    ----------
    exc:
        The exception that was caught during email operations.
    error_type:
        The type name of the exception (e.g., "ValueError", "RuntimeError").

    Side Effects
    ------------
    Logs the error and exits with code 1 after displaying error message.

    Examples
    --------
    >>> exc = ValueError("Invalid recipient email")
    >>> handle_send_email_error(exc, "ValueError")  # doctest: +SKIP
    # Logs error and exits with code 1
    """
    error_messages = {
        "ValueError": ("Invalid email parameters", f"Invalid email parameters - {exc}"),
        "FileNotFoundError": ("Attachment file not found", f"Attachment file not found - {exc}"),
        "RuntimeError": ("SMTP delivery failed", f"Failed to send email - {exc}"),
    }

    log_msg, cli_msg = error_messages.get(
        error_type,
        ("Unexpected error sending email", f"Unexpected error - {exc}"),
    )

    logger.error(log_msg, extra={"error": str(exc)}, exc_info=(error_type not in error_messages))
    click.echo(f"\nError: {cli_msg}", err=True)
    raise SystemExit(1)


__all__ = [
    "validate_smtp_configuration",
    "handle_send_email_error",
]
