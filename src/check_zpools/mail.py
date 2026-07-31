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
from typing import TYPE_CHECKING, Any

from btx_lib_mail.lib_mail import ConfMail
from btx_lib_mail.lib_mail import send as btx_send
from pydantic import BaseModel, ConfigDict, Field, SecretStr, TypeAdapter, ValidationError, model_validator

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

logger = logging.getLogger(__name__)

#: Highest valid TCP port number.
MAX_PORT_NUMBER = 65535

#: Expected number of parts when splitting a "host:port" string.
HOST_PORT_PARTS_COUNT = 2


def _default_smtp_hosts() -> list[str]:
    """Factory function for default SMTP hosts list."""
    return []


class EmailConfig(BaseModel):
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

    model_config = ConfigDict(frozen=True, extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _drop_uncoercible_values(cls, data: Any) -> Any:
        """Drop config values that cannot become their declared type, so the default applies.

        Why
            This model parses an operator-edited config file that a monitoring
            daemon loads at startup on every node. A single typo (`timeout =
            "abc"`) must not turn that daemon into a crash loop, so an
            unusable value falls back to the field default - the long-standing
            behaviour of this loader. Unlike the silent fallback it replaces,
            each dropped value is logged, so the typo is still discoverable.

        Examples
        --------
        >>> EmailConfig.model_validate({"timeout": "not_a_number"}).timeout
        30.0
        >>> EmailConfig.model_validate({"timeout": 5.0}).timeout
        5.0
        """
        if not isinstance(data, dict):
            return data
        usable: dict[str, Any] = {}
        for name, field_info in cls.model_fields.items():
            if name not in data:
                continue
            value = data[name]
            try:
                TypeAdapter(field_info.annotation).validate_python(value)
            except ValidationError:
                logger.warning(
                    "Ignoring unusable value for email.%s, using default",
                    name,
                    extra={"field": name, "value_type": type(value).__name__},
                )
                continue
            usable[name] = value
        return usable

    smtp_hosts: list[str] = Field(default_factory=_default_smtp_hosts)
    from_address: str = "noreply@localhost"
    smtp_username: str | None = None
    smtp_password: str | None = None
    use_starttls: bool = True
    timeout: float = 30.0
    raise_on_missing_attachments: bool = True
    raise_on_invalid_recipient: bool = True

    def _validate_timeout(self) -> None:
        """Validate timeout is positive.

        Raises
        ------
        ValueError: If timeout is not positive.
        """
        if self.timeout <= 0:
            raise ValueError(f"timeout must be positive, got {self.timeout}")

    def _validate_from_address(self) -> None:
        """Validate from_address contains @.

        Raises
        ------
        ValueError: If from_address doesn't contain @.
        """
        if "@" not in self.from_address:
            raise ValueError(f"from_address must contain @, got {self.from_address!r}")

    def _validate_smtp_host_port(self, host: str, port_str: str) -> None:
        """Validate SMTP host port is numeric and in valid range.

        Parameters
        ----------
        host:
            Full host string (for error messages).
        port_str:
            Port string to validate.

        Raises
        ------
        ValueError: If port is invalid.
        """
        try:
            port = int(port_str)
            if not (1 <= port <= MAX_PORT_NUMBER):
                raise ValueError(f"Port must be 1-65535 in {host!r}")
        except ValueError as e:
            if "invalid literal" in str(e):
                raise ValueError(f"Port must be numeric in {host!r}") from e
            raise

    def _validate_smtp_host(self, host: str) -> None:
        """Validate single SMTP host format.

        Parameters
        ----------
        host:
            SMTP host string, optionally with :port.

        Raises
        ------
        ValueError: If host format is invalid.
        """
        if ":" not in host:
            return

        parts = host.split(":")
        if len(parts) != HOST_PORT_PARTS_COUNT:
            raise ValueError(f"Invalid SMTP host format (expected 'host:port'): {host!r}")

        self._validate_smtp_host_port(host, parts[1])

    @model_validator(mode="after")
    def _validate(self) -> EmailConfig:
        """Validate configuration values.

        Why
            Catch common configuration mistakes early with clear error messages
            rather than allowing invalid values to cause obscure failures later.

        Raises
            ValueError: When configuration values are invalid.

        Examples
        --------
        Pydantic wraps the failure, and its ValidationError is a ValueError, so
        callers catching ValueError keep working:

        >>> EmailConfig(timeout=-5.0)  # doctest: +IGNORE_EXCEPTION_DETAIL
        Traceback (most recent call last):
        ...
        pydantic_core._pydantic_core.ValidationError: timeout must be positive

        >>> try:
        ...     EmailConfig(from_address="not-an-email")
        ... except ValueError as exc:
        ...     "from_address must contain @" in str(exc)
        True
        """
        self._validate_timeout()
        self._validate_from_address()
        for host in self.smtp_hosts:
            self._validate_smtp_host(host)
        return self

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
            smtp_password=SecretStr(self.smtp_password) if self.smtp_password is not None else None,
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


def load_email_config_from_dict(config_dict: Mapping[str, Any]) -> EmailConfig:
    """Parse the `email` section of the layered configuration into EmailConfig.

    Why
        The configuration arrives as a plain mapping from lib_layered_config;
        this is the boundary where it becomes a validated model. Pydantic does
        the coercion and the type checking, so there is no hand-rolled
        extraction to keep in sync with the field list.

    Parameters
    ----------
    config_dict:
        Configuration mapping, expected to carry an `email` section.

    Returns
    -------
    EmailConfig:
        Validated email settings, defaults applied for anything absent.

    Raises
    ------
    ValueError:
        When a present value fails validation (pydantic's ValidationError is
        a ValueError).

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
    section = config_dict.get("email", {})
    return EmailConfig.model_validate(section if isinstance(section, dict) else {})


__all__ = [
    "EmailConfig",
    "load_email_config_from_dict",
    "send_email",
    "send_notification",
]
