"""Email sending adapter using btx_lib_mail.

Purpose
-------
Provides a clean wrapper around btx_lib_mail that integrates with the
application's configuration system and logging infrastructure. Isolates
email functionality behind a domain-appropriate interface.

Contents
--------
* :class:`EmailConfig` – Configuration container for email settings
* :func:`send_email` – Primary email sending interface
* :func:`send_notification` – Convenience wrapper for simple notifications

System Role
-----------
Acts as the email adapter layer, bridging btx_lib_mail with the application's
configuration and logging systems while keeping domain logic decoupled from
email mechanics.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence, cast

from btx_lib_mail.lib_mail import ConfMail, send as btx_send

logger = logging.getLogger(__name__)


def _default_smtp_hosts() -> list[str]:
    """Factory function for default SMTP hosts list."""
    return []


@dataclass(frozen=True, slots=True)
class EmailConfig:
    """Email configuration container.

    Why
        Provides a domain-appropriate configuration object that maps cleanly
        to lib_layered_config while remaining independent of btx_lib_mail's
        internal structure.

    Fields
    ------
    smtp_hosts:
        List of SMTP servers in 'host[:port]' format. Tried in order until
        one succeeds.
    from_address:
        Default sender address for outgoing emails.
    smtp_username:
        Optional SMTP authentication username.
    smtp_password:
        Optional SMTP authentication password.
    use_starttls:
        Enable STARTTLS negotiation.
    timeout:
        Socket timeout in seconds for SMTP operations.
    raise_on_missing_attachments:
        When True, missing attachment files raise FileNotFoundError.
    raise_on_invalid_recipient:
        When True, invalid email addresses raise ValueError.

    Examples
    --------
    >>> config = EmailConfig(
    ...     smtp_hosts=["smtp.example.com:587"],
    ...     from_address="noreply@example.com"
    ... )
    >>> config.smtp_hosts
    ['smtp.example.com:587']
    """

    smtp_hosts: list[str] = field(default_factory=_default_smtp_hosts)
    from_address: str = "noreply@localhost"
    smtp_username: str | None = None
    smtp_password: str | None = None
    use_starttls: bool = True
    timeout: float = 30.0
    raise_on_missing_attachments: bool = True
    raise_on_invalid_recipient: bool = True

    def __post_init__(self) -> None:
        """Validate configuration values.

        Why
            Catch common configuration mistakes early with clear error messages
            rather than allowing invalid values to cause obscure failures later.

        Raises
            ValueError: When configuration values are invalid.

        Examples
        --------
        >>> EmailConfig(timeout=-5.0)  # doctest: +IGNORE_EXCEPTION_DETAIL
        Traceback (most recent call last):
        ...
        ValueError: timeout must be positive, got -5.0

        >>> EmailConfig(from_address="not-an-email")  # doctest: +IGNORE_EXCEPTION_DETAIL
        Traceback (most recent call last):
        ...
        ValueError: from_address must contain @, got 'not-an-email'
        """
        # Validate timeout is positive
        if self.timeout <= 0:
            raise ValueError(f"timeout must be positive, got {self.timeout}")

        # Validate from_address contains @
        if "@" not in self.from_address:
            raise ValueError(f"from_address must contain @, got {self.from_address!r}")

        # Validate smtp_hosts format
        for host in self.smtp_hosts:
            if ":" in host:
                parts = host.split(":")
                if len(parts) != 2:
                    raise ValueError(f"Invalid SMTP host format (expected 'host:port'): {host!r}")
                try:
                    port = int(parts[1])
                    if not (1 <= port <= 65535):
                        raise ValueError(f"Port must be 1-65535 in {host!r}")
                except ValueError as e:
                    if "invalid literal" in str(e):
                        raise ValueError(f"Port must be numeric in {host!r}") from e
                    raise

    def to_conf_mail(self) -> ConfMail:
        """Convert to btx_lib_mail ConfMail object.

        Why
            Isolates the adapter dependency on btx_lib_mail types from the
            rest of the application.

        Returns
            ConfMail instance configured with current settings.

        Examples
        --------
        >>> config = EmailConfig(smtp_hosts=["smtp.example.com"])
        >>> conf = config.to_conf_mail()
        >>> conf.smtphosts
        ['smtp.example.com']
        """
        # Pydantic model type inference limitation in strict mode
        return ConfMail(
            smtphosts=self.smtp_hosts,  # type: ignore[reportUnknownVariableType]
            smtp_username=self.smtp_username,
            smtp_password=self.smtp_password,
            smtp_use_starttls=self.use_starttls,
            smtp_timeout=self.timeout,
            raise_on_missing_attachments=self.raise_on_missing_attachments,
            raise_on_invalid_recipient=self.raise_on_invalid_recipient,
        )


def _resolve_credentials(config: EmailConfig) -> tuple[str, str] | None:
    """Extract credentials tuple from config when both username and password exist."""
    if config.smtp_username and config.smtp_password:
        return (config.smtp_username, config.smtp_password)
    return None


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
    >>> from unittest.mock import patch, MagicMock
    >>> config = EmailConfig(
    ...     smtp_hosts=["smtp.example.com"],
    ...     from_address="sender@example.com"
    ... )
    >>> with patch("smtplib.SMTP") as mock_smtp:
    ...     result = send_email(
    ...         config=config,
    ...         recipients="recipient@example.com",
    ...         subject="Test",
    ...         body="Hello"
    ...     )
    >>> result
    True
    """
    sender = from_address if from_address is not None else config.from_address

    logger.info(
        "Sending email",
        extra={
            "from": sender,
            "recipients": recipients if isinstance(recipients, str) else list(recipients),
            "subject": subject,
            "has_html": bool(body_html),
            "attachment_count": len(attachments) if attachments else 0,
        },
    )

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

        logger.info(
            "Email sent successfully",
            extra={
                "from": sender,
                "recipients": recipients if isinstance(recipients, str) else list(recipients),
            },
        )

        return result

    except Exception as e:
        logger.error(
            "Failed to send email",
            extra={
                "error": str(e),
                "from": sender,
                "recipients": recipients if isinstance(recipients, str) else list(recipients),
            },
            exc_info=True,
        )
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
    >>> with patch("smtplib.SMTP"):
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


def load_email_config_from_dict(config_dict: Mapping[str, Any]) -> EmailConfig:
    """Load EmailConfig from a configuration dictionary.

    Why
        Bridges lib_layered_config's dictionary output with the typed
        EmailConfig dataclass, handling optional values and type conversions.

    Parameters
    ----------
    config_dict:
        Configuration dictionary typically from lib_layered_config.
        Expected to have an 'email' section with email settings.

    Returns
    -------
    EmailConfig:
        Configured email settings with defaults for missing values.

    Examples
    --------
    >>> config_dict = {
    ...     "email": {
    ...         "smtp_hosts": ["smtp.example.com:587"],
    ...         "from_address": "test@example.com"
    ...     }
    ... }
    >>> email_config = load_email_config_from_dict(config_dict)
    >>> email_config.from_address
    'test@example.com'
    >>> email_config.use_starttls
    True
    """
    email_section_raw = config_dict.get("email", {})
    email_section: Mapping[str, Any] = cast(Mapping[str, Any], email_section_raw if isinstance(email_section_raw, dict) else {})

    smtp_hosts_raw = email_section.get("smtp_hosts", [])
    smtp_hosts = cast(list[str], smtp_hosts_raw if isinstance(smtp_hosts_raw, list) else [])

    from_address_raw = email_section.get("from_address", "noreply@localhost")
    from_address: str = from_address_raw if isinstance(from_address_raw, str) else "noreply@localhost"

    smtp_username_raw = email_section.get("smtp_username")
    smtp_username: str | None = smtp_username_raw if isinstance(smtp_username_raw, str) else None

    smtp_password_raw = email_section.get("smtp_password")
    smtp_password: str | None = smtp_password_raw if isinstance(smtp_password_raw, str) else None

    use_starttls_raw = email_section.get("use_starttls", True)
    use_starttls: bool = use_starttls_raw if isinstance(use_starttls_raw, bool) else True

    timeout_raw = email_section.get("timeout", 30.0)
    timeout: float = float(timeout_raw) if isinstance(timeout_raw, (int, float)) else 30.0

    raise_on_missing_raw = email_section.get("raise_on_missing_attachments", True)
    raise_on_missing: bool = raise_on_missing_raw if isinstance(raise_on_missing_raw, bool) else True

    raise_on_invalid_raw = email_section.get("raise_on_invalid_recipient", True)
    raise_on_invalid: bool = raise_on_invalid_raw if isinstance(raise_on_invalid_raw, bool) else True

    return EmailConfig(
        smtp_hosts=smtp_hosts,
        from_address=from_address,
        smtp_username=smtp_username,
        smtp_password=smtp_password,
        use_starttls=use_starttls,
        timeout=timeout,
        raise_on_missing_attachments=raise_on_missing,
        raise_on_invalid_recipient=raise_on_invalid,
    )


__all__ = [
    "EmailConfig",
    "send_email",
    "send_notification",
    "load_email_config_from_dict",
]
