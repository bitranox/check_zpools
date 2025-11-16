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

    def send_recovery(self, pool_name: str, category: str, pool: PoolStatus | None = None) -> bool:
        """Send email notification when an issue is resolved.

        Why
        ---
        Administrators should know when previously alerted issues are
        resolved, providing closure and reducing confusion.

        What
        ---
        Sends a simple email indicating the issue category is now OK.
        Includes complete pool status if available for context.

        Parameters
        ----------
        pool_name:
            Name of the pool that recovered.
        category:
            Issue category that was resolved.
        pool:
            Optional complete pool status for detailed reporting.

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
        body = self._format_recovery_body(pool_name, category, pool)

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

        # Add complete pool status section
        lines.extend(
            [
                "",
                "=" * 70,
                "COMPLETE POOL STATUS",
                "=" * 70,
            ]
        )
        lines.append(self._format_complete_pool_status(pool))

        return "\n".join(lines)

    def _format_complete_pool_status(self, pool: PoolStatus) -> str:
        """Format complete pool status in zpool-like text format.

        Why
        ---
        Provides detailed pool information in email for troubleshooting
        without requiring SSH access to the server.

        What
        ---
        Formats all pool metrics in a structured, readable text format
        similar to `zpool status` output.

        Parameters
        ----------
        pool:
            Pool status to format.

        Returns
        -------
        str
            Complete formatted pool status.
        """
        lines = []

        # Pool header
        lines.extend(
            [
                f"Pool: {pool.name}",
                f"State: {pool.health.value}",
                "",
            ]
        )

        # Capacity information
        capacity_pct = pool.capacity_percent
        used_tb = pool.allocated_bytes / (1024**4)
        total_tb = pool.size_bytes / (1024**4)
        free_tb = pool.free_bytes / (1024**4)
        used_gb = pool.allocated_bytes / (1024**3)
        total_gb = pool.size_bytes / (1024**3)
        free_gb = pool.free_bytes / (1024**3)

        lines.extend(
            [
                "Capacity:",
                f"  Total:     {total_tb:.2f} TB ({total_gb:.2f} GB) [{pool.size_bytes:,} bytes]",
                f"  Used:      {used_tb:.2f} TB ({used_gb:.2f} GB) [{pool.allocated_bytes:,} bytes]",
                f"  Free:      {free_tb:.2f} TB ({free_gb:.2f} GB) [{pool.free_bytes:,} bytes]",
                f"  Usage:     {capacity_pct:.2f}%",
                "",
            ]
        )

        # Error statistics
        total_errors = pool.read_errors + pool.write_errors + pool.checksum_errors
        error_status = "ERRORS DETECTED" if total_errors > 0 else "No errors"

        lines.extend(
            [
                f"Error Statistics: {error_status}",
                f"  Read Errors:      {pool.read_errors:,}",
                f"  Write Errors:     {pool.write_errors:,}",
                f"  Checksum Errors:  {pool.checksum_errors:,}",
                f"  Total Errors:     {total_errors:,}",
                "",
            ]
        )

        # Scrub information
        if pool.last_scrub:
            scrub_date = pool.last_scrub.strftime("%Y-%m-%d %H:%M:%S %Z")
            scrub_age_days = (datetime.now() - pool.last_scrub.replace(tzinfo=None)).days
            scrub_status = "IN PROGRESS" if pool.scrub_in_progress else "Completed"
            scrub_errors_status = f"{pool.scrub_errors} errors found" if pool.scrub_errors > 0 else "No errors found"

            lines.extend(
                [
                    f"Scrub Status: {scrub_status}",
                    f"  Last Scrub:   {scrub_date}",
                    f"  Age:          {scrub_age_days} days",
                    f"  Errors:       {scrub_errors_status}",
                ]
            )
        else:
            lines.extend(
                [
                    "Scrub Status: Never scrubbed",
                    "  WARNING: No scrub has been performed on this pool",
                ]
            )

        if pool.scrub_in_progress:
            lines.append("  NOTE: A scrub is currently in progress")

        lines.append("")

        # Health assessment
        if pool.health.is_healthy():
            health_msg = "✓ Pool is healthy and operating normally"
        elif pool.health.is_critical():
            health_msg = "✗ CRITICAL: Pool is in a critical state requiring immediate attention"
        else:
            health_msg = "⚠ WARNING: Pool is degraded and should be investigated"

        lines.extend(
            [
                "Health Assessment:",
                f"  {health_msg}",
                "",
            ]
        )

        # Additional notes
        notes = []
        if capacity_pct >= 90:
            notes.append("⚠ Capacity critically high (≥90%)")
        elif capacity_pct >= 80:
            notes.append("⚠ Capacity high (≥80%)")

        if total_errors > 0:
            notes.append(f"⚠ {total_errors} I/O or checksum errors detected")

        if pool.last_scrub:
            scrub_age_days = (datetime.now() - pool.last_scrub.replace(tzinfo=None)).days
            if scrub_age_days > 30:
                notes.append(f"⚠ Scrub is {scrub_age_days} days old (recommended: <30 days)")
        else:
            notes.append("⚠ Pool has never been scrubbed")

        if notes:
            lines.append("Notes:")
            for note in notes:
                lines.append(f"  {note}")
            lines.append("")

        return "\n".join(lines)

    def _format_recovery_body(self, pool_name: str, category: str, pool: PoolStatus | None = None) -> str:
        """Format recovery email body.

        Parameters
        ----------
        pool_name:
            Name of recovered pool.
        category:
            Issue category that resolved.
        pool:
            Optional complete pool status for detailed reporting.

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

        # Add complete pool status if available
        if pool is not None:
            lines.extend(
                [
                    "",
                    "=" * 70,
                    "CURRENT POOL STATUS",
                    "=" * 70,
                ]
            )
            lines.append(self._format_complete_pool_status(pool))

        return "\n".join(lines)
