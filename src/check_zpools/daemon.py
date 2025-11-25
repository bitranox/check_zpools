"""Daemon mode for continuous ZFS pool monitoring.

Purpose
-------
Provide a long-running process that periodically checks ZFS pools, detects
issues, sends alerts, and manages alert state with intelligent deduplication.

Contents
--------
* :class:`ZPoolDaemon` - main daemon orchestrating periodic pool monitoring

Architecture
------------
The daemon runs in a loop with configurable check intervals. Each cycle:
1. Queries ZFS pool status via ZFSClient
2. Checks pools against thresholds via PoolMonitor
3. Determines which alerts to send via AlertStateManager
4. Sends email notifications via EmailAlerter
5. Updates alert state and sleeps until next interval

Graceful shutdown is handled via SIGTERM/SIGINT signal handlers.
"""

from __future__ import annotations

import logging
import signal
import threading
from datetime import datetime, timezone
from typing import Any

from . import __init__conf__
from .alert_state import AlertStateManager
from .alerting import EmailAlerter
from .models import CheckResult, PoolIssue, PoolStatus, Severity
from .monitor import PoolMonitor
from .zfs_client import ZFSClient
from .zfs_parser import ZFSParser

logger = logging.getLogger(__name__)


class ZPoolDaemon:
    """Continuous ZFS pool monitoring daemon with periodic checks.

    Why
    ---
    Administrators need proactive notification of pool issues rather than
    discovering them during failures. A daemon provides continuous monitoring
    with intelligent alerting.

    What
    ---
    Orchestrates periodic pool checking by coordinating ZFS client, monitor,
    alerter, and state manager. Handles graceful shutdown via signals.

    Parameters
    ----------
    zfs_client:
        Client for executing ZFS commands.
    monitor:
        Monitor for checking pools against thresholds.
    alerter:
        Email alerter for sending notifications.
    state_manager:
        Alert state manager for deduplication.
    config:
        Daemon configuration (interval, pools to monitor, etc).
    """

    def __init__(
        self,
        zfs_client: ZFSClient,
        monitor: PoolMonitor,
        alerter: EmailAlerter,
        state_manager: AlertStateManager,
        config: dict[str, Any],
    ):
        self.zfs_client = zfs_client
        self.monitor = monitor
        self.alerter = alerter
        self.state_manager = state_manager
        self.parser = ZFSParser()

        # Configuration
        self.check_interval = config.get("check_interval_seconds", 300)
        self.pools_to_monitor = config.get("pools_to_monitor", [])
        self.send_ok_emails = config.get("send_ok_emails", False)
        self.send_recovery_emails = config.get("send_recovery_emails", True)

        # Daemon state
        self.shutdown_event = threading.Event()
        self.running = False

        # Statistics tracking
        self.start_time = datetime.now(timezone.utc)
        self.check_count = 0

        # Track issues from previous cycle for recovery detection
        self.previous_issues: dict[str, set[str]] = {}

    def start(self) -> None:
        """Start daemon monitoring loop.

        Why
        ---
        Entry point for daemon mode that initializes signal handlers and
        begins the monitoring loop.

        What
        ---
        Sets up signal handlers for graceful shutdown, then enters the
        main monitoring loop until shutdown is requested.
        """
        # Prepare email configuration for logging
        smtp_hosts = ", ".join(self.alerter.email_config.smtp_hosts) if self.alerter.email_config.smtp_hosts else "none"
        alert_recipients = ", ".join(self.alerter.recipients) if self.alerter.recipients else "none"

        logger.info(
            "Starting ZFS pool monitoring daemon",
            extra={
                "version": __init__conf__.version,
                "interval_seconds": self.check_interval,
                "pools": self.pools_to_monitor or "all",
                "smtp_servers": smtp_hosts,
                "alert_recipients": alert_recipients,
                "send_recovery_emails": self.send_recovery_emails,
            },
        )

        # Log warnings if email alerting is not properly configured
        if not self.alerter.email_config.smtp_hosts:
            logger.error(
                "No SMTP servers configured - email alerts will not be sent",
                extra={"smtp_servers": "none"},
            )

        if not self.alerter.recipients:
            logger.error(
                "No alert recipients configured - email alerts will not be sent",
                extra={"alert_recipients": "none"},
            )

        self._setup_signal_handlers()
        self.running = True

        try:
            self._run_monitoring_loop()
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt, shutting down")
        except Exception as exc:
            logger.error(
                "Daemon crashed with unexpected error",
                extra={"error": str(exc), "error_type": type(exc).__name__},
                exc_info=True,
            )
            raise
        finally:
            self.stop()

    def stop(self) -> None:
        """Gracefully stop daemon.

        Why
        ---
        Ensures clean shutdown by completing current check cycle and
        persisting state before exit.

        What
        ---
        Sets shutdown flag and waits for current check to complete.
        """
        if not self.running:
            return

        logger.info("Stopping daemon gracefully")
        self.running = False
        self.shutdown_event.set()

        logger.info("Daemon stopped")

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown.

        Why
        ---
        Systemd and other process managers use SIGTERM to request shutdown.
        We need to handle this gracefully rather than abruptly terminating.

        What
        ---
        Registers handlers for SIGTERM and SIGINT that trigger graceful
        shutdown.
        """

        def signal_handler(signum: int, frame: Any) -> None:
            """Handle shutdown signals by triggering graceful daemon stop.

            Why
            ---
            When the daemon receives SIGTERM or SIGINT, it must shut down
            gracefully to complete the current check cycle and persist state.

            What
            ---
            Logs the received signal and triggers the daemon's stop() method
            to initiate graceful shutdown.

            Parameters
            ----------
            signum:
                Signal number received (SIGTERM=15, SIGINT=2).
            frame:
                Current stack frame (unused but required by signal API).
            """
            sig_name = signal.Signals(signum).name
            logger.info(f"Received {sig_name}, initiating shutdown")
            self.stop()

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

        logger.debug("Signal handlers installed")

    def _run_monitoring_loop(self) -> None:
        """Main monitoring loop that runs until shutdown.

        Why
        ---
        Continuous monitoring requires a loop that periodically checks pools
        and sleeps between cycles.

        What
        ---
        Executes check cycles at configured intervals until shutdown is
        requested. Handles errors gracefully to prevent daemon crashes.
        """
        while not self.shutdown_event.is_set():
            try:
                self._run_check_cycle()
            except Exception as exc:
                logger.error(
                    "Error during check cycle, continuing",
                    extra={"error": str(exc), "error_type": type(exc).__name__},
                    exc_info=True,
                )

            # Sleep with interruptible wait so shutdown is responsive
            self.shutdown_event.wait(timeout=self.check_interval)

    def _fetch_and_parse_pools(self) -> dict[str, PoolStatus] | None:
        """Fetch and parse ZFS pool data.

        Returns
        -------
        dict[str, PoolStatus] | None:
            Parsed pool data, or None if fetch/parse failed
        """
        # Fetch ZFS data (single command with --json-int provides all data)
        try:
            status_data = self.zfs_client.get_pool_status()
        except Exception as exc:
            logger.error(
                "Failed to fetch ZFS data",
                extra={"error": str(exc), "error_type": type(exc).__name__},
                exc_info=True,
            )
            return None

        # Parse into PoolStatus objects
        try:
            return self.parser.parse_pool_status(status_data)
        except Exception as exc:
            logger.error(
                "Failed to parse ZFS data",
                extra={"error": str(exc), "error_type": type(exc).__name__},
                exc_info=True,
            )
            return None

    def _filter_monitored_pools(self, pools: dict[str, PoolStatus]) -> dict[str, PoolStatus]:
        """Filter pools to only those being monitored.

        Parameters
        ----------
        pools:
            All available pools

        Returns
        -------
        dict[str, PoolStatus]:
            Filtered pool dictionary
        """
        if not self.pools_to_monitor:
            return pools

        filtered = {name: status for name, status in pools.items() if name in self.pools_to_monitor}
        logger.debug("Filtered to monitored pools", extra={"monitored": list(filtered.keys())})
        return filtered

    def _log_cycle_completion(self, check_start_time: datetime, pools: dict[str, PoolStatus], result: CheckResult) -> None:
        """Log check cycle completion statistics.

        Parameters
        ----------
        check_start_time:
            When this check cycle started
        pools:
            Pools that were checked
        result:
            Check results
        """
        uptime = check_start_time - self.start_time
        uptime_str = self._format_uptime(uptime.total_seconds())

        logger.info(
            "Check cycle completed",
            extra={
                "check_number": self.check_count,
                "uptime": uptime_str,
                "pools_checked": len(pools),
                "issues_found": len(result.issues),
                "severity": result.overall_severity.value,
            },
        )

    def _run_check_cycle(self) -> None:
        """Execute one complete pool check cycle.

        Why
        ---
        Each cycle must query pools, check for issues, send alerts, and
        detect recoveries. Consolidating this logic makes testing easier
        and ensures consistency.

        What
        ---
        1. Fetch pool data from ZFS
        2. Parse into PoolStatus objects
        3. Check against thresholds
        4. Send alerts for new/resendable issues
        5. Detect and notify recoveries
        """
        self.check_count += 1
        check_start_time = datetime.now(timezone.utc)
        logger.debug("Starting check cycle")

        # Fetch and parse pool data
        pools = self._fetch_and_parse_pools()
        if pools is None:
            return

        # Filter to monitored pools
        pools = self._filter_monitored_pools(pools)
        if not pools:
            logger.warning("No pools found to monitor")
            return

        # Check pools and process results
        result = self.monitor.check_all_pools(pools)
        self._log_cycle_completion(check_start_time, pools, result)
        self._log_pool_details(pools)

        # Handle recoveries and alerts
        self._detect_recoveries(result)
        current_issues = self._handle_check_result(result, pools)
        self.previous_issues = current_issues

    def _handle_check_result(self, result: CheckResult, pools: dict[str, Any]) -> dict[str, set[str]]:
        """Process check result by sending alerts for actionable issues.

        Why
        ---
        Not all issues warrant alerts (e.g., duplicates within resend interval).
        This method applies alert policy and sends emails for actionable issues.

        What
        ---
        1. Filter issues by severity (skip OK if configured)
        2. Check alert state to determine if alert should send
        3. Send alert emails
        4. Record alert state
        5. Return current issues for tracking

        Parameters
        ----------
        result:
            Check result containing issues.
        pools:
            Pool status dict for issue context.

        Returns
        -------
        dict[str, set[str]]:
            Dictionary mapping pool names to sets of issue categories.
        """
        # Track current issues for recovery detection
        current_issues: dict[str, set[str]] = {}

        for issue in result.issues:
            # Track this issue
            if issue.pool_name not in current_issues:
                current_issues[issue.pool_name] = set()
            current_issues[issue.pool_name].add(issue.category)

            # Check if alert should be sent
            if not self._should_send_alert(issue):
                continue

            # Get pool status
            pool = pools.get(issue.pool_name)
            if not pool:
                logger.warning(
                    "Cannot send alert - pool status not found",
                    extra={"pool": issue.pool_name},
                )
                continue

            # Send alert and record state
            self._send_alert_for_issue(issue, pool)

        # Return current issues for tracking
        return current_issues

    def _should_send_alert(self, issue: PoolIssue) -> bool:
        """Determine if an alert should be sent for an issue.

        Why
        ---
        Filters out OK-severity issues (if configured) and duplicate alerts
        within the resend interval to reduce alert fatigue.

        Parameters
        ----------
        issue:
            Issue to check.

        Returns
        -------
        bool:
            True if alert should be sent, False otherwise.
        """
        # Skip OK severity unless configured to send
        if issue.severity == Severity.OK and not self.send_ok_emails:
            logger.debug(
                "Skipping OK issue (send_ok_emails disabled)",
                extra={"pool": issue.pool_name, "category": issue.category},
            )
            return False

        # Check if we should send alert based on state
        if not self.state_manager.should_alert(issue):
            logger.debug(
                "Suppressing duplicate alert",
                extra={"pool": issue.pool_name, "category": issue.category},
            )
            return False

        return True

    def _send_alert_for_issue(self, issue: PoolIssue, pool: Any) -> None:
        """Send alert email and record state.

        Parameters
        ----------
        issue:
            Issue to alert about.
        pool:
            Pool status for context.
        """
        success = self.alerter.send_alert(issue, pool)
        if success:
            self.state_manager.record_alert(issue)
            logger.info(
                "Alert sent and recorded",
                extra={
                    "pool": issue.pool_name,
                    "category": issue.category,
                    "severity": issue.severity.value,
                },
            )
        else:
            logger.warning(
                "Failed to send alert",
                extra={"pool": issue.pool_name, "category": issue.category},
            )

    def _format_uptime(self, seconds: float) -> str:
        """Format uptime in human-readable format.

        Parameters
        ----------
        seconds:
            Total seconds of uptime.

        Returns
        -------
        str:
            Formatted uptime string (e.g., "2d 3h 45m", "5h 30m", "45m").
        """
        total_seconds = int(seconds)
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60

        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0 or len(parts) == 0:
            parts.append(f"{minutes}m")

        return " ".join(parts)

    def _format_bytes(self, bytes_value: int) -> str:
        """Format bytes in human-readable format.

        Parameters
        ----------
        bytes_value:
            Size in bytes.

        Returns
        -------
        str:
            Formatted size string (e.g., "1.00 TB", "464.00 GB").
        """
        units = ["B", "KB", "MB", "GB", "TB", "PB"]
        size = float(bytes_value)
        unit_index = 0

        while size >= 1024.0 and unit_index < len(units) - 1:
            size /= 1024.0
            unit_index += 1

        return f"{size:.2f} {units[unit_index]}"

    def _log_pool_details(self, pools: dict[str, Any]) -> None:
        """Log detailed information for each pool.

        Parameters
        ----------
        pools:
            Dictionary of pool statuses.
        """
        for pool_name, pool in pools.items():
            # Format last scrub time
            if pool.last_scrub:
                last_scrub = pool.last_scrub.strftime("%Y-%m-%d %H:%M:%S")
            else:
                last_scrub = "Never"

            logger.info(
                f"Pool: {pool_name}",
                extra={
                    "pool_name": pool_name,
                    "health": pool.health.value,
                    "capacity_percent": f"{pool.capacity_percent:.1f}%",
                    "size": self._format_bytes(pool.size_bytes),
                    "allocated": self._format_bytes(pool.allocated_bytes),
                    "free": self._format_bytes(pool.free_bytes),
                    "read_errors": pool.read_errors,
                    "write_errors": pool.write_errors,
                    "checksum_errors": pool.checksum_errors,
                    "last_scrub": last_scrub,
                    "scrub_errors": pool.scrub_errors,
                    "scrub_in_progress": pool.scrub_in_progress,
                },
            )

    def _detect_recoveries(self, result: CheckResult) -> None:
        """Detect and notify when previously alerted issues are resolved.

        Why
        ---
        Administrators should know when issues are resolved to reduce alert
        fatigue and provide closure.

        What
        ---
        Compares current issues with previous cycle to find resolved issues,
        then sends recovery emails and clears alert state.

        Parameters
        ----------
        result:
            Current check result.
        """
        if not self.send_recovery_emails:
            return

        # Build current issues map
        current_issues: dict[str, set[str]] = {}
        for issue in result.issues:
            if issue.pool_name not in current_issues:
                current_issues[issue.pool_name] = set()
            current_issues[issue.pool_name].add(issue.category)

        # Build pool dict for lookups
        pools_dict = {pool.name: pool for pool in result.pools}

        # Find resolved issues
        for pool_name, prev_categories in self.previous_issues.items():
            current_categories = current_issues.get(pool_name, set())
            resolved = prev_categories - current_categories

            for category in resolved:
                logger.info(
                    "Detected issue recovery",
                    extra={"pool": pool_name, "category": category},
                )

                # Send recovery email with current pool status
                pool_status = pools_dict.get(pool_name)
                success = self.alerter.send_recovery(pool_name, category, pool_status)
                if success:
                    # Clear alert state so future issues alert immediately
                    self.state_manager.clear_issue(pool_name, category)
                    logger.info(
                        "Recovery notification sent",
                        extra={"pool": pool_name, "category": category},
                    )
