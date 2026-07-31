"""Send email command implementation."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import lib_log_rich.runtime

from ... import safe_console
from ...cli_email_handlers import handle_send_email_error, validate_smtp_configuration
from ...config import load_settings
from ...mail import send_email

if TYPE_CHECKING:
    from ...models import EmailMessage

logger = logging.getLogger(__name__)


def _log_send_email_request(message: EmailMessage) -> None:
    """Log the outgoing request.

    Why
        Takes the message rather than four of its fields: the group travels
        together everywhere else, and splitting it here was the last place that
        re-derived it.
    """
    logger.info(
        "Sending email via CLI",
        extra={
            "recipients": message.recipients,
            "subject": message.subject,
            "has_html": bool(message.body_html),
            "attachment_count": len(message.attachments),
        },
    )


def _handle_send_result(*, result: bool, recipients: tuple[str, ...]) -> None:
    """Handle email send result.

    Parameters
    ----------
    result:
        Whether email was sent successfully.
    recipients:
        Email recipients.

    Raises
    ------
    SystemExit: If send failed.
    """
    if result:
        safe_console.echo("\nEmail sent successfully!")
        logger.info("Email sent via CLI", extra={"recipients": list(recipients)})
    else:
        logger.error("Email sending failed via CLI", extra={"recipients": list(recipients)})
        safe_console.echo("\nEmail sending failed.", err=True)
        raise SystemExit(1)


def send_email_command(message: EmailMessage) -> None:
    """Execute send-email command logic."""
    with lib_log_rich.runtime.bind(
        job_id="cli-send-email",
        extra={"command": "send-email", "recipients": message.recipients, "subject": message.subject},
    ):
        try:
            # Load and validate email configuration
            email_config = load_settings().email
            validate_smtp_configuration(email_config)

            _log_send_email_request(message)

            result = send_email(config=email_config, message=message)

            _handle_send_result(result=result, recipients=tuple(message.recipients))

        except (ValueError, FileNotFoundError, RuntimeError) as exc:
            handle_send_email_error(exc, type(exc).__name__)
        except Exception as exc:
            handle_send_email_error(exc, "Exception")
