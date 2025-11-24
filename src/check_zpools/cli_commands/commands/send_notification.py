"""Send notification command implementation."""

from __future__ import annotations

import logging

import lib_log_rich.runtime
import rich_click as click

from ...config import get_config
from ...mail import load_email_config_from_dict, send_notification

logger = logging.getLogger(__name__)


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

            if not email_config.smtp_hosts:
                logger.error("No SMTP hosts configured")
                click.echo(
                    "\nError: No SMTP hosts configured. Please configure email.smtp_hosts in your config file.",
                    err=True,
                )
                click.echo(
                    "See: bitranox-template-cli-app-config-log-mail config-deploy --target user",
                    err=True,
                )
                raise SystemExit(1)

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

            if result:
                click.echo("\nNotification sent successfully!")
                logger.info("Notification sent via CLI", extra={"recipients": list(recipients)})
            else:
                click.echo("\nNotification sending failed.", err=True)
                raise SystemExit(1)

        except ValueError as exc:
            logger.error("Invalid notification parameters", extra={"error": str(exc)})
            click.echo(f"\nError: Invalid notification parameters - {exc}", err=True)
            raise SystemExit(1)
        except RuntimeError as exc:
            logger.error("SMTP delivery failed", extra={"error": str(exc)})
            click.echo(f"\nError: Failed to send notification - {exc}", err=True)
            raise SystemExit(1)
        except Exception as exc:
            logger.error(
                "Unexpected error sending notification",
                extra={"error": str(exc), "error_type": type(exc).__name__},
                exc_info=True,
            )
            click.echo(f"\nError: Unexpected error - {exc}", err=True)
            raise SystemExit(1)
