"""Send notification command implementation."""

from __future__ import annotations

import logging

import lib_log_rich.runtime
import rich_click as click

from ...cli_email_handlers import validate_smtp_configuration
from ...config import get_config
from ...mail import load_email_config_from_dict, send_notification

logger = logging.getLogger(__name__)


def _handle_notification_result(result: bool, recipients: tuple[str, ...]) -> None:
    """Handle notification send result.

    Parameters
    ----------
    result:
        Whether notification was sent successfully.
    recipients:
        Notification recipients.

    Raises
    ------
    SystemExit: If send failed.
    """
    if result:
        click.echo("\nNotification sent successfully!")
        logger.info("Notification sent via CLI", extra={"recipients": list(recipients)})
    else:
        logger.error("Notification sending failed via CLI", extra={"recipients": list(recipients)})
        click.echo("\nNotification sending failed.", err=True)
        raise SystemExit(1)


def _handle_notification_error(exc: Exception) -> None:
    """Handle notification errors.

    Parameters
    ----------
    exc:
        Exception that occurred.

    Raises
    ------
    SystemExit: Always exits with code 1.
    """
    if isinstance(exc, ValueError):
        logger.error("Invalid notification parameters", extra={"error": str(exc)})
        click.echo(f"\nError: Invalid notification parameters - {exc}", err=True)
    elif isinstance(exc, RuntimeError):
        logger.error("SMTP delivery failed", extra={"error": str(exc)})
        click.echo(f"\nError: Failed to send notification - {exc}", err=True)
    else:
        logger.error(
            "Unexpected error sending notification",
            extra={"error": str(exc), "error_type": type(exc).__name__},
            exc_info=True,
        )
        click.echo(f"\nError: Unexpected error - {exc}", err=True)
    raise SystemExit(1)


def send_notification_command(
    recipients: tuple[str, ...],
    subject: str,
    message: str,
) -> None:
    """Execute send-notification command logic."""
    with lib_log_rich.runtime.bind(
        job_id="cli-send-notification",
        extra={"command": "send-notification", "recipients": list(recipients), "subject": subject},
    ):
        try:
            # Load and validate email configuration
            config = get_config()
            email_config = load_email_config_from_dict(config.as_dict())
            validate_smtp_configuration(email_config)

            logger.info(
                "Sending notification",
                extra={"recipients": list(recipients), "subject": subject},
            )

            # Send notification
            result = send_notification(
                config=email_config,
                recipients=list(recipients),
                subject=subject,
                message=message,
            )

            _handle_notification_result(result, recipients)

        except Exception as exc:
            _handle_notification_error(exc)
