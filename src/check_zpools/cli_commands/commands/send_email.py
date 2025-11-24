"""Send email command implementation."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import lib_log_rich.runtime
import rich_click as click

from ...cli_email_handlers import handle_send_email_error, validate_smtp_configuration
from ...config import get_config
from ...mail import load_email_config_from_dict, send_email

logger = logging.getLogger(__name__)


def _prepare_attachments(attachments: tuple[str, ...]) -> list[Path] | None:
    """Convert attachment strings to Path objects.

    Parameters
    ----------
    attachments:
        Tuple of attachment file paths.

    Returns
    -------
    list[Path] | None:
        List of Path objects, or None if no attachments.
    """
    return [Path(p) for p in attachments] if attachments else None


def _log_send_email_request(recipients: tuple[str, ...], subject: str, body_html: str, attachments: tuple[str, ...]) -> None:
    """Log email send request details.

    Parameters
    ----------
    recipients:
        Email recipients.
    subject:
        Email subject.
    body_html:
        HTML body content.
    attachments:
        Attachment file paths.
    """
    logger.info(
        "Sending email",
        extra={
            "recipients": list(recipients),
            "subject": subject,
            "has_html": bool(body_html),
            "attachment_count": len(attachments) if attachments else 0,
        },
    )


def _handle_send_result(result: bool, recipients: tuple[str, ...]) -> None:
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
        click.echo("\nEmail sent successfully!")
        logger.info("Email sent via CLI", extra={"recipients": list(recipients)})
    else:
        logger.error("Email sending failed via CLI", extra={"recipients": list(recipients)})
        click.echo("\nEmail sending failed.", err=True)
        raise SystemExit(1)


def send_email_command(
    recipients: tuple[str, ...],
    subject: str,
    body: str,
    body_html: str,
    from_address: Optional[str],
    attachments: tuple[str, ...],
) -> None:
    """Execute send-email command logic."""
    with lib_log_rich.runtime.bind(
        job_id="cli-send-email",
        extra={"command": "send-email", "recipients": list(recipients), "subject": subject},
    ):
        try:
            # Load and validate email configuration
            config = get_config()
            email_config = load_email_config_from_dict(config.as_dict())
            validate_smtp_configuration(email_config)

            # Prepare and send email
            attachment_paths = _prepare_attachments(attachments)
            _log_send_email_request(recipients, subject, body_html, attachments)

            result = send_email(
                config=email_config,
                recipients=list(recipients),
                subject=subject,
                body=body,
                body_html=body_html,
                from_address=from_address,
                attachments=attachment_paths,
            )

            _handle_send_result(result, recipients)

        except (ValueError, FileNotFoundError, RuntimeError) as exc:
            handle_send_email_error(exc, type(exc).__name__)
        except Exception as exc:
            handle_send_email_error(exc, "Exception")
