"""Email sending adapter using btx_lib_mail.

Purpose
-------
Provides a clean wrapper around btx_lib_mail that integrates with the
application's configuration system and logging infrastructure. Isolates
email functionality behind a domain-appropriate interface.

Contents
--------
* :class:`EmailConfig` - Configuration container for email settings
* :func:`send_email` - Primary email sending interface
* :func:`send_notification` - Convenience wrapper for simple notifications

System Role
-----------
Acts as the email adapter layer, bridging btx_lib_mail with the application's
configuration and logging systems while keeping domain logic decoupled from
email mechanics.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from btx_lib_mail.lib_mail import ConfMail
from btx_lib_mail.lib_mail import send as btx_send
from pydantic import SecretStr

from .models import EmailConfig

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

logger = logging.getLogger(__name__)


def to_conf_mail(config: EmailConfig) -> ConfMail:
    """Convert the email settings to a btx_lib_mail ConfMail.

    Why
        Keeps the btx_lib_mail dependency in the adapter layer: the model is a
        plain configuration type that the bottom layer can own, and only this
        module knows what the mail library wants.

    Examples
    --------
    >>> to_conf_mail(EmailConfig(smtp_hosts=["smtp.example.com"])).smtphosts
    ['smtp.example.com']
    """
    return ConfMail(
        smtphosts=config.smtp_hosts,  # type: ignore[reportUnknownVariableType]
        smtp_username=config.smtp_username,
        smtp_password=SecretStr(config.smtp_password) if config.smtp_password is not None else None,
        smtp_use_starttls=config.use_starttls,
        smtp_timeout=config.timeout,
        raise_on_missing_attachments=config.raise_on_missing_attachments,
        raise_on_invalid_recipient=config.raise_on_invalid_recipient,
    )


def _resolve_credentials(config: EmailConfig) -> tuple[str, str] | None:
    """Extract credentials tuple from config when both username and password exist."""
    if config.smtp_username and config.smtp_password:
        return (config.smtp_username, config.smtp_password)
    return None


def _determine_sender(from_address: str | None, config: EmailConfig) -> str:
    """Determine sender address from override or config.

    Parameters
    ----------
    from_address:
        Optional override address.
    config:
        Email configuration with default sender.

    Returns
    -------
    str:
        Sender email address to use.
    """
    return from_address if from_address is not None else config.from_address


def _normalize_recipients(recipients: str | Sequence[str]) -> str | list[str]:
    """Normalize recipients for logging.

    Parameters
    ----------
    recipients:
        Single recipient or sequence.

    Returns
    -------
    str | list[str]:
        Recipients in logging-friendly format.
    """
    return recipients if isinstance(recipients, str) else list(recipients)


def _log_email_send_attempt(sender: str, recipients: str | Sequence[str], subject: str, body_html: str, attachments: Sequence[Path] | None) -> None:
    """Log email send attempt.

    Parameters
    ----------
    sender:
        Sender address.
    recipients:
        Recipients.
    subject:
        Email subject.
    body_html:
        HTML body.
    attachments:
        Attachments.
    """
    logger.info(
        "Sending email",
        extra={
            "from": sender,
            "recipients": _normalize_recipients(recipients),
            "subject": subject,
            "has_html": bool(body_html),
            "attachment_count": len(attachments) if attachments else 0,
        },
    )


def _log_email_success(sender: str, recipients: str | Sequence[str]) -> None:
    """Log successful email send.

    Parameters
    ----------
    sender:
        Sender address.
    recipients:
        Recipients.
    """
    logger.info(
        "Email sent successfully",
        extra={
            "from": sender,
            "recipients": _normalize_recipients(recipients),
        },
    )


def _log_email_failure(error: Exception, sender: str, recipients: str | Sequence[str]) -> None:
    """Log email send failure.

    Parameters
    ----------
    error:
        Exception that occurred.
    sender:
        Sender address.
    recipients:
        Recipients.
    """
    logger.error(
        "Failed to send email",
        extra={
            "error": str(error),
            "from": sender,
            "recipients": _normalize_recipients(recipients),
        },
        exc_info=True,
    )


def send_email(
    *,
    config: EmailConfig,
    recipients: str | Sequence[str],
    subject: str,
    body: str = "",
    body_html: str = "",
    from_address: str | None = None,
    attachments: Sequence[Path] | None = None,
) -> bool:
    """Send an email using configured SMTP settings.

    Why
        Provides the primary email-sending interface that integrates with
        application configuration while exposing a clean, typed API.

    Parameters
    ----------
    config:
        Email configuration containing SMTP settings and defaults.
    recipients:
        Single recipient address or sequence of addresses.
    subject:
        Email subject line (UTF-8 supported).
    body:
        Plain-text email body.
    body_html:
        HTML email body (optional, sent as multipart with plain text).
    from_address:
        Override sender address. Uses config.from_address when None.
    attachments:
        Optional sequence of file paths to attach.

    Returns
    -------
    bool:
        Always True when delivery succeeds. Failures raise exceptions.

    Raises
    ------
    ValueError:
        No valid recipients remain after validation.
    FileNotFoundError:
        Required attachment missing and config.raise_on_missing_attachments
        is True.
    RuntimeError:
        All SMTP hosts failed for a recipient.

    Side Effects
        Sends email via SMTP. Logs send attempts at INFO level and failures
        at ERROR level.

    Examples
    --------
    Stubbing ``btx_send`` keeps this example offline. It is this module's own
    boundary to the mail library, so unlike a stand-in for ``smtplib.SMTP`` it
    does not depend on how that library drives the connection internally.

    >>> from unittest.mock import patch
    >>> config = EmailConfig(
    ...     smtp_hosts=["smtp.example.com"],
    ...     from_address="sender@example.com"
    ... )
    >>> with patch("check_zpools.mail.btx_send", return_value=True):
    ...     result = send_email(
    ...         config=config,
    ...         recipients="recipient@example.com",
    ...         subject="Test",
    ...         body="Hello"
    ...     )
    >>> result
    True
    """
    sender = _determine_sender(from_address, config)
    _log_email_send_attempt(sender, recipients, subject, body_html, attachments)

    try:
        credentials = _resolve_credentials(config)

        result = btx_send(
            mail_from=sender,
            mail_recipients=recipients,
            mail_subject=subject,
            mail_body=body,
            mail_body_html=body_html,
            smtphosts=config.smtp_hosts,
            attachment_file_paths=attachments,
            credentials=credentials,
            use_starttls=config.use_starttls,
            timeout=config.timeout,
        )

        _log_email_success(sender, recipients)
        return result

    except Exception as e:
        _log_email_failure(e, sender, recipients)
        raise


def send_notification(
    *,
    config: EmailConfig,
    recipients: str | Sequence[str],
    subject: str,
    message: str,
) -> bool:
    """Send a simple plain-text notification email.

    Why
        Convenience wrapper for the common case of sending simple notifications
        without HTML or attachments.

    Parameters
    ----------
    config:
        Email configuration containing SMTP settings.
    recipients:
        Single recipient address or sequence of addresses.
    subject:
        Email subject line.
    message:
        Plain-text notification message.

    Returns
    -------
    bool:
        Always True when delivery succeeds. Failures raise exceptions.

    Raises
    ------
    ValueError:
        No valid recipients remain after validation.
    RuntimeError:
        All SMTP hosts failed for a recipient.

    Side Effects
        Sends email via SMTP. Logs send attempts.

    Examples
    --------
    >>> from unittest.mock import patch
    >>> config = EmailConfig(
    ...     smtp_hosts=["smtp.example.com"],
    ...     from_address="alerts@example.com"
    ... )
    >>> with patch("check_zpools.mail.btx_send", return_value=True):
    ...     result = send_notification(
    ...         config=config,
    ...         recipients="admin@example.com",
    ...         subject="System Alert",
    ...         message="Deployment completed successfully"
    ...     )
    >>> result
    True
    """
    return send_email(
        config=config,
        recipients=recipients,
        subject=subject,
        body=message,
    )


__all__ = [
    "EmailConfig",
    "send_email",
    "send_notification",
]
