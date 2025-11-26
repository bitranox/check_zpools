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
import subprocess  # nosec B404 - subprocess used only for exception handling (TimeoutExpired)
from datetime import datetime
from typing import TYPE_CHECKING, Any

from . import __init__conf__
from .mail import EmailConfig, send_email
from .models import PoolIssue, PoolStatus, Severity
from .zfs_client import ZFSCommandError

if TYPE_CHECKING:
    from .zfs_client import ZFSClient

logger = logging.getLogger(__name__)

# Binary unit multipliers (powers of 1024)
_BYTES_PER_KB = 1024
_BYTES_PER_MB = 1024**2
_BYTES_PER_GB = 1024**3
_BYTES_PER_TB = 1024**4
_BYTES_PER_PB = 1024**5


def _format_bytes_human(size_bytes: int) -> str:
    """Format bytes into human-readable size with appropriate unit.

    Why
    ---
    Sizes should be displayed in the most readable unit (GB, TB, PB)
    based on the actual value, with 2 decimal places for precision.

    Parameters
    ----------
    size_bytes:
        Size in bytes to format.

    Returns
    -------
    str
        Formatted size string (e.g., "9.48 GB", "1.25 TB").
    """
    if size_bytes >= _BYTES_PER_PB:
        return f"{size_bytes / _BYTES_PER_PB:.2f} PB"
    if size_bytes >= _BYTES_PER_TB:
        return f"{size_bytes / _BYTES_PER_TB:.2f} TB"
    if size_bytes >= _BYTES_PER_GB:
        return f"{size_bytes / _BYTES_PER_GB:.2f} GB"
    if size_bytes >= _BYTES_PER_MB:
        return f"{size_bytes / _BYTES_PER_MB:.2f} MB"
    if size_bytes >= _BYTES_PER_KB:
        return f"{size_bytes / _BYTES_PER_KB:.2f} KB"
    return f"{size_bytes} B"


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
    capacity_warning_percent:
        Capacity percentage threshold for warning alerts (default: 80).
    capacity_critical_percent:
        Capacity percentage threshold for critical alerts (default: 90).
    scrub_max_age_days:
        Maximum days since last scrub before warning (default: 30).
    """

    def __init__(
        self,
        email_config: EmailConfig,
        alert_config: dict[str, Any],
        capacity_warning_percent: int = 80,
        capacity_critical_percent: int = 90,
        scrub_max_age_days: int = 30,
        zfs_client: ZFSClient | None = None,
    ):
        self.email_config = email_config
        self.subject_prefix = alert_config.get("subject_prefix", "[ZFS Alert]")
        self.recipients = alert_config.get("alert_recipients", [])
        self.include_ok_alerts = alert_config.get("send_ok_emails", False)
        self.include_recovery_alerts = alert_config.get("send_recovery_emails", True)
        self.alert_on_severities = set(severity.upper() for severity in alert_config.get("alert_on_severities", ["CRITICAL", "WARNING"]))
        self.capacity_warning_percent = capacity_warning_percent
        self.capacity_critical_percent = capacity_critical_percent
        self.scrub_max_age_days = scrub_max_age_days
        self.zfs_client = zfs_client

    def send_alert(self, issue: PoolIssue, pool: PoolStatus) -> bool:
        """Send email alert for a specific pool issue.

        Why
        ---
        Administrators need to be notified of pool issues with enough
        context to investigate and resolve them.

        What
        ---
        Formats issue and pool data into a clear email message and sends
        via SMTP. Returns success/failure status. Respects severity
        filtering based on alert_on_severities configuration.

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

        # Check if this severity should trigger an alert
        if issue.severity.value not in self.alert_on_severities:
            logger.debug(
                "Skipping alert - severity not in alert_on_severities",
                extra={
                    "pool": pool.name,
                    "severity": issue.severity.value,
                    "alert_on_severities": list(self.alert_on_severities),
                },
            )
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
        hostname = socket.gethostname()
        return f"{self.subject_prefix} [{hostname}] {severity.value.upper()} - {pool_name}: {message}"

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
        hostname = socket.gethostname()
        return f"{self.subject_prefix} [{hostname}] RECOVERY - {pool_name}: {category} issue resolved"

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

        lines: list[str] = []

        # Delegate sections to specialized methods
        # Each method returns a list of lines to avoid double-joining
        lines.extend(self._format_alert_header(issue, pool, hostname, timestamp))
        lines.extend(self._format_pool_details_section(pool))
        lines.extend(self._format_recommended_actions_section(issue, pool))
        lines.extend(self._format_alert_footer(hostname))

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

        # Add zpool status output if ZFS client is available
        self._append_zpool_status(lines, pool.name, "email")

        return "\n".join(lines)

    def _format_alert_header(self, issue: PoolIssue, pool: PoolStatus, hostname: str, timestamp: str) -> list[str]:
        """Format alert email header with issue details.

        Parameters
        ----------
        issue:
            The pool issue being reported.
        pool:
            Complete pool status for context.
        hostname:
            System hostname.
        timestamp:
            Formatted timestamp string.

        Returns
        -------
        list[str]
            List of formatted header lines.
        """
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

        return lines

    def _format_pool_details_section(self, pool: PoolStatus) -> list[str]:
        """Format pool statistics section for alert email.

        Parameters
        ----------
        pool:
            Complete pool status for context.

        Returns
        -------
        list[str]
            List of formatted pool details lines.
        """
        # Format pool capacity with human-readable sizes
        capacity_pct = pool.capacity_percent
        used_str = _format_bytes_human(pool.allocated_bytes)
        total_str = _format_bytes_human(pool.size_bytes)
        free_str = _format_bytes_human(pool.free_bytes)

        # Format scrub information
        if pool.last_scrub:
            scrub_date = pool.last_scrub.strftime("%Y-%m-%d %H:%M:%S")
            scrub_age = self._calculate_scrub_age_days(pool)
            scrub_info = f"{scrub_date} ({scrub_age} days ago, {pool.scrub_errors} errors)"
        else:
            scrub_info = "Never"

        if pool.scrub_in_progress:
            scrub_info += " [SCRUB IN PROGRESS]"

        return [
            "",
            "POOL DETAILS:",
            f"  Capacity: {capacity_pct:.2f} % used ({used_str} / {total_str})",
            f"  Free Space: {free_str}",
            f"  Errors: {pool.read_errors} read, {pool.write_errors} write, {pool.checksum_errors} checksum",
            f"  Last Scrub: {scrub_info}",
        ]

    def _format_recommended_actions_section(self, issue: PoolIssue, pool: PoolStatus) -> list[str]:
        """Format recommended actions section based on issue category.

        Parameters
        ----------
        issue:
            The pool issue being reported.
        pool:
            Complete pool status for context.

        Returns
        -------
        list[str]
            List of formatted recommended action lines.
        """
        lines = [
            "",
            "RECOMMENDED ACTIONS:",
            f"  1. Run 'zpool status {pool.name}' to investigate",
        ]

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

        return lines

    def _format_alert_footer(self, hostname: str) -> list[str]:
        """Format alert email footer.

        Parameters
        ----------
        hostname:
            System hostname.

        Returns
        -------
        list[str]
            List of formatted footer lines.
        """
        return [
            "",
            "---",
            f"Generated by {__init__conf__.title} v{__init__conf__.version}",
            f"Hostname: {hostname}",
        ]

    def _format_complete_pool_status(self, pool: PoolStatus) -> str:
        """Format complete pool status in zpool-like text format.

        Why
        ---
        Provides detailed pool information in email for troubleshooting
        without requiring SSH access to the server.

        What
        ---
        Formats all pool metrics in a structured, readable text format
        similar to `zpool status` output. Delegates to specialized formatting
        methods for each section.

        Parameters
        ----------
        pool:
            Pool status to format.

        Returns
        -------
        str
            Complete formatted pool status.
        """
        lines: list[str] = []

        # Pool header
        lines.extend(
            [
                f"Pool: {pool.name}",
                f"State: {pool.health.value}",
                "",
            ]
        )

        # Delegate each section to specialized methods
        # Each method returns a list of lines to avoid double-joining
        lines.extend(self._format_capacity_section(pool))
        lines.extend(self._format_error_statistics_section(pool))
        lines.extend(self._format_scrub_status_section(pool))
        lines.extend(self._format_health_assessment_section(pool))
        notes_lines = self._format_notes_section(pool)
        if notes_lines:  # Only add if not empty
            lines.extend(notes_lines)

        return "\n".join(lines)

    def _format_capacity_section(self, pool: PoolStatus) -> list[str]:
        """Format capacity information section.

        Parameters
        ----------
        pool:
            Pool status to format.

        Returns
        -------
        list[str]
            List of formatted lines for capacity section.
        """
        capacity_pct = pool.capacity_percent
        total_str = _format_bytes_human(pool.size_bytes)
        used_str = _format_bytes_human(pool.allocated_bytes)
        free_str = _format_bytes_human(pool.free_bytes)

        return [
            "Capacity:",
            f"  Total:     {total_str} [{pool.size_bytes:,} bytes]",
            f"  Used:      {used_str} [{pool.allocated_bytes:,} bytes]",
            f"  Free:      {free_str} [{pool.free_bytes:,} bytes]",
            f"  Usage:     {capacity_pct:.2f} %",
            "",
        ]

    def _format_error_statistics_section(self, pool: PoolStatus) -> list[str]:
        """Format error statistics section.

        Parameters
        ----------
        pool:
            Pool status to format.

        Returns
        -------
        list[str]
            List of formatted lines for error statistics section.
        """
        total_errors = pool.read_errors + pool.write_errors + pool.checksum_errors
        error_status = "ERRORS DETECTED" if total_errors > 0 else "No errors"

        return [
            f"Error Statistics: {error_status}",
            f"  Read Errors:      {pool.read_errors:,}",
            f"  Write Errors:     {pool.write_errors:,}",
            f"  Checksum Errors:  {pool.checksum_errors:,}",
            f"  Total Errors:     {total_errors:,}",
            "",
        ]

    def _format_scrub_status_section(self, pool: PoolStatus) -> list[str]:
        """Format scrub status section.

        Parameters
        ----------
        pool:
            Pool status to format.

        Returns
        -------
        list[str]
            List of formatted lines for scrub status section.
        """
        lines: list[str] = []

        if pool.last_scrub:
            scrub_date = pool.last_scrub.strftime("%Y-%m-%d %H:%M:%S %Z")
            scrub_age_days = self._calculate_scrub_age_days(pool)
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

        return lines

    def _format_health_assessment_section(self, pool: PoolStatus) -> list[str]:
        """Format health assessment section.

        Parameters
        ----------
        pool:
            Pool status to format.

        Returns
        -------
        list[str]
            List of formatted lines for health assessment section.
        """
        if pool.health.is_healthy():
            health_msg = "✓ Pool is healthy and operating normally"
        elif pool.health.is_critical():
            health_msg = "✗ CRITICAL: Pool is in a critical state requiring immediate attention"
        else:
            health_msg = "⚠ WARNING: Pool is degraded and should be investigated"

        return [
            "Health Assessment:",
            f"  {health_msg}",
            "",
        ]

    def _format_notes_section(self, pool: PoolStatus) -> list[str]:
        """Format additional notes section.

        Parameters
        ----------
        pool:
            Pool status to format.

        Returns
        -------
        list[str]
            List of formatted lines for notes section (empty list if no notes).
        """
        notes: list[str] = []
        capacity_pct = pool.capacity_percent
        total_errors = pool.read_errors + pool.write_errors + pool.checksum_errors

        # Capacity warnings based on configured thresholds
        if capacity_pct >= self.capacity_critical_percent:
            notes.append(f"⚠ Capacity critically high (≥{self.capacity_critical_percent}%)")
        elif capacity_pct >= self.capacity_warning_percent:
            notes.append(f"⚠ Capacity high (≥{self.capacity_warning_percent}%)")

        # Error warnings
        if total_errors > 0:
            notes.append(f"⚠ {total_errors} I/O or checksum errors detected")

        # Scrub age warnings based on configured threshold
        scrub_age_days = self._calculate_scrub_age_days(pool)
        if scrub_age_days is not None:
            if scrub_age_days > self.scrub_max_age_days:
                notes.append(f"⚠ Scrub is {scrub_age_days} days old (recommended: <{self.scrub_max_age_days} days)")
        else:
            notes.append("⚠ Pool has never been scrubbed")

        if notes:
            lines = ["Notes:"]
            for note in notes:
                lines.append(f"  {note}")
            lines.append("")
            return lines

        return []  # Return empty list instead of empty string

    def _calculate_scrub_age_days(self, pool: PoolStatus) -> int | None:
        """Calculate days since last scrub.

        Parameters
        ----------
        pool:
            Pool status to check.

        Returns
        -------
        int | None
            Number of days since last scrub, or None if never scrubbed.
        """
        if not pool.last_scrub:
            return None
        return (datetime.now() - pool.last_scrub.replace(tzinfo=None)).days

    def _append_zpool_status(
        self,
        lines: list[str],
        pool_name: str,
        email_type: str = "email",
    ) -> None:
        """Append zpool status output to email lines.

        Why
            Eliminates code duplication between alert and recovery email formatting.
            Centralizes zpool status fetching and error handling in one place.

        Parameters
        ----------
        lines:
            List to append status output to (modified in place).
        pool_name:
            Name of the pool to get status for.
        email_type:
            Type of email for logging ("email" or "recovery email").
        """
        if self.zfs_client is None:
            return

        try:
            zpool_status_output = self.zfs_client.get_pool_status_text(pool_name=pool_name)
            lines.extend(
                [
                    "",
                    "=" * 70,
                    "ZPOOL STATUS OUTPUT",
                    "=" * 70,
                    zpool_status_output.rstrip(),
                ]
            )
        except (ZFSCommandError, subprocess.TimeoutExpired, RuntimeError) as exc:
            logger.warning(
                f"Failed to fetch zpool status output for {email_type}",
                extra={
                    "pool": pool_name,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )
            # Continue without zpool status - don't fail the entire email

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

            # Add zpool status output if ZFS client is available
            self._append_zpool_status(lines, pool.name, "recovery email")

        return "\n".join(lines)
