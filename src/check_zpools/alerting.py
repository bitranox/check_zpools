"""Email alerting for ZFS pool issues.

Purpose
-------
Send email notifications when pool issues are detected, with rich formatting
that includes pool details, issue descriptions, and recommended actions.

Contents
--------
* :class:`EmailAlerter` - sends formatted email alerts for pool issues

Architecture
------------
The alerter formats pool issues into human-readable email messages with:
- Clear subject lines including severity and pool name
- Detailed body with issue descriptions and pool statistics
- Recommended actions for investigating issues

Integrates with the existing mail.py module for SMTP delivery.
"""

from __future__ import annotations

import logging
import socket
from datetime import datetime
from typing import Any

from . import __init__conf__
from .mail import EmailConfig, send_email
from .models import PoolIssue, PoolStatus, Severity

logger = logging.getLogger(__name__)


class EmailAlerter:
    """Send email alerts for ZFS pool issues with rich formatting.

    Why
    ---
    Pool issues need to be communicated clearly to administrators with
    enough context to take action. This class formats issues into
    readable emails with severity indicators.

    What
    ---
    Composes email subject lines and bodies based on pool issues and
    status, then delegates to the mail.py module for SMTP delivery.

    Parameters
    ----------
    email_config:
        SMTP configuration for sending emails.
    alert_config:
        Alert-specific configuration (recipients, subject prefix, etc).
    """

    def __init__(self, email_config: EmailConfig, alert_config: dict[str, Any]):
        self.email_config = email_config
        self.subject_prefix = alert_config.get("subject_prefix", "[ZFS Alert]")
        self.recipients = alert_config.get("alert_recipients", [])
        self.include_ok_alerts = alert_config.get("send_ok_emails", False)
        self.include_recovery_alerts = alert_config.get("send_recovery_emails", True)

    def send_alert(self, issue: PoolIssue, pool: PoolStatus) -> bool:
        """Send email alert for a specific pool issue.

        Why
        ---
        Administrators need to be notified of pool issues with enough
        context to investigate and resolve them.

        What
        ---
        Formats issue and pool data into a clear email message and sends
        via SMTP. Returns success/failure status.

        Parameters
        ----------
        issue:
            The detected pool issue to alert about.
        pool:
            Complete pool status for context.

        Returns
        -------
        bool
            True if email sent successfully, False otherwise.
        """
        if not self.recipients:
            logger.warning("No alert recipients configured, skipping email")
            return False

        subject = self._format_subject(issue.severity, pool.name, issue.message)
        body = self._format_body(issue, pool)

        logger.info(
            "Sending alert email",
            extra={
                "pool": pool.name,
                "severity": issue.severity.value,
                "category": issue.category,
                "recipients": self.recipients,
            },
        )

        try:
            return send_email(
                config=self.email_config,
                recipients=self.recipients,
                subject=subject,
                body=body,
            )
        except Exception as exc:
            logger.error(
                "Failed to send alert email",
                extra={
                    "pool": pool.name,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
                exc_info=True,
            )
            return False

    def send_recovery(self, pool_name: str, category: str) -> bool:
        """Send email notification when an issue is resolved.

        Why
        ---
        Administrators should know when previously alerted issues are
        resolved, providing closure and reducing confusion.

        What
        ---
        Sends a simple email indicating the issue category is now OK.

        Parameters
        ----------
        pool_name:
            Name of the pool that recovered.
        category:
            Issue category that was resolved.

        Returns
        -------
        bool
            True if email sent successfully, False otherwise.
        """
        if not self.include_recovery_alerts:
            logger.debug("Recovery emails disabled, skipping")
            return False

        if not self.recipients:
            logger.warning("No alert recipients configured, skipping email")
            return False

        subject = self._format_recovery_subject(pool_name, category)
        body = self._format_recovery_body(pool_name, category)

        logger.info(
            "Sending recovery email",
            extra={
                "pool": pool_name,
                "category": category,
                "recipients": self.recipients,
            },
        )

        try:
            return send_email(
                config=self.email_config,
                recipients=self.recipients,
                subject=subject,
                body=body,
            )
        except Exception as exc:
            logger.error(
                "Failed to send recovery email",
                extra={
                    "pool": pool_name,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
                exc_info=True,
            )
            return False

    def _format_subject(self, severity: Severity, pool_name: str, message: str) -> str:
        """Format email subject line with severity indicator.

        Parameters
        ----------
        severity:
            Issue severity level.
        pool_name:
            Name of affected pool.
        message:
            Short issue description.

        Returns
        -------
        str
            Formatted subject line.
        """
        return f"{self.subject_prefix} {severity.value.upper()} - {pool_name}: {message}"

    def _format_recovery_subject(self, pool_name: str, category: str) -> str:
        """Format recovery email subject line.

        Parameters
        ----------
        pool_name:
            Name of recovered pool.
        category:
            Issue category that resolved.

        Returns
        -------
        str
            Formatted subject line.
        """
        return f"{self.subject_prefix} RECOVERY - {pool_name}: {category} issue resolved"

    def _format_body(self, issue: PoolIssue, pool: PoolStatus) -> str:
        """Format plain-text email body with issue details and pool stats.

        Parameters
        ----------
        issue:
            The pool issue being reported.
        pool:
            Complete pool status for context.

        Returns
        -------
        str
            Formatted email body.
        """
        hostname = socket.gethostname()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z")

        # Format pool capacity
        capacity_pct = pool.capacity_percent
        used_tb = pool.allocated_bytes / (1024**4)
        total_tb = pool.size_bytes / (1024**4)
        free_tb = pool.free_bytes / (1024**4)

        # Format scrub information
        if pool.last_scrub:
            scrub_date = pool.last_scrub.strftime("%Y-%m-%d %H:%M:%S")
            scrub_age = (datetime.now() - pool.last_scrub.replace(tzinfo=None)).days
            scrub_info = f"{scrub_date} ({scrub_age} days ago, {pool.scrub_errors} errors)"
        else:
            scrub_info = "Never"

        if pool.scrub_in_progress:
            scrub_info += " [SCRUB IN PROGRESS]"

        # Build body sections
        lines = [
            f"ZFS Pool Alert - {issue.severity.value.upper()}",
            "",
            f"Pool: {pool.name}",
            f"Status: {pool.health.value}",
            f"Timestamp: {timestamp}",
            f"Host: {hostname}",
            "",
            "ISSUE DETECTED:",
            f"  Category: {issue.category}",
            f"  Severity: {issue.severity.value}",
            f"  Message: {issue.message}",
        ]

        # Add issue details if available
        if issue.details:
            lines.append("")
            lines.append("Details:")
            for key, value in issue.details.items():
                lines.append(f"  {key}: {value}")

        # Add pool statistics
        lines.extend(
            [
                "",
                "POOL DETAILS:",
                f"  Capacity: {capacity_pct:.1f}% used ({used_tb:.2f} TB / {total_tb:.2f} TB)",
                f"  Free Space: {free_tb:.2f} TB",
                f"  Errors: {pool.read_errors} read, {pool.write_errors} write, {pool.checksum_errors} checksum",
                f"  Last Scrub: {scrub_info}",
            ]
        )

        # Add recommended actions
        lines.extend(
            [
                "",
                "RECOMMENDED ACTIONS:",
                f"  1. Run 'zpool status {pool.name}' to investigate",
            ]
        )

        if issue.category == "capacity":
            lines.extend(
                [
                    "  2. Identify and remove unnecessary files",
                    "  3. Consider adding more storage capacity",
                ]
            )
        elif issue.category == "errors":
            lines.extend(
                [
                    "  2. Check system logs for hardware issues",
                    "  3. Consider running 'zpool scrub' if not in progress",
                ]
            )
        elif issue.category == "scrub":
            lines.extend(
                [
                    f"  2. Run 'zpool scrub {pool.name}' to start scrub",
                    "  3. Schedule regular scrubs via cron or systemd timer",
                ]
            )
        elif issue.category == "health":
            lines.extend(
                [
                    "  2. Check for failed or degraded devices",
                    "  3. Replace failed drives if necessary",
                ]
            )

        # Add footer
        lines.extend(
            [
                "",
                "---",
                f"Generated by {__init__conf__.title} v{__init__conf__.version}",
                f"Hostname: {hostname}",
            ]
        )

        return "\n".join(lines)

    def _format_recovery_body(self, pool_name: str, category: str) -> str:
        """Format recovery email body.

        Parameters
        ----------
        pool_name:
            Name of recovered pool.
        category:
            Issue category that resolved.

        Returns
        -------
        str
            Formatted email body.
        """
        hostname = socket.gethostname()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z")

        lines = [
            "ZFS Pool Recovery Notification",
            "",
            f"Pool: {pool_name}",
            f"Category: {category}",
            f"Timestamp: {timestamp}",
            f"Host: {hostname}",
            "",
            f"The {category} issue for pool '{pool_name}' has been resolved.",
            "",
            "No further action is required at this time.",
            "",
            "---",
            f"Generated by {__init__conf__.title} v{__init__conf__.version}",
            f"Hostname: {hostname}",
        ]

        return "\n".join(lines)
