"""Send email command implementation."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import lib_log_rich.runtime
import rich_click as click

from ...cli_email_handlers import handle_send_email_error
from ...config import get_config
from ...mail import load_email_config_from_dict, send_email

logger = logging.getLogger(__name__)


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

            # Prepare attachments
            attachment_paths = [Path(p) for p in attachments] if attachments else None

            logger.info(
                "Sending email",
                extra={
                    "recipients": list(recipients),
                    "subject": subject,
                    "has_html": bool(body_html),
                    "attachment_count": len(attachments) if attachments else 0,
                },
            )

            # Send email
            result = send_email(
                config=email_config,
                recipients=list(recipients),
                subject=subject,
                body=body,
                body_html=body_html,
                from_address=from_address,
                attachments=attachment_paths,
            )

            if result:
                click.echo("\nEmail sent successfully!")
                logger.info("Email sent via CLI", extra={"recipients": list(recipients)})
            else:
                click.echo("\nEmail sending failed.", err=True)
                raise SystemExit(1)

        except (ValueError, FileNotFoundError, RuntimeError) as exc:
            handle_send_email_error(exc, type(exc).__name__)
        except Exception as exc:
            handle_send_email_error(exc, "Exception")
