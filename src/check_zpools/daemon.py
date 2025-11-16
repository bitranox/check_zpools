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
from typing import Any

from .alert_state import AlertStateManager
from .alerting import EmailAlerter
from .models import CheckResult, Severity
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
        logger.info(
            "Starting ZFS pool monitoring daemon",
            extra={
                "interval_seconds": self.check_interval,
                "pools": self.pools_to_monitor or "all",
            },
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
        logger.debug("Starting check cycle")

        # Fetch ZFS data
        try:
            list_data = self.zfs_client.get_pool_list()
            status_data = self.zfs_client.get_pool_status()
        except Exception as exc:
            logger.error(
                "Failed to fetch ZFS data",
                extra={"error": str(exc), "error_type": type(exc).__name__},
                exc_info=True,
            )
            return

        # Parse into PoolStatus objects
        try:
            pools_from_list = self.parser.parse_pool_list(list_data)
            pools_from_status = self.parser.parse_pool_status(status_data)
            pools = self.parser.merge_pool_data(pools_from_list, pools_from_status)
        except Exception as exc:
            logger.error(
                "Failed to parse ZFS data",
                extra={"error": str(exc), "error_type": type(exc).__name__},
                exc_info=True,
            )
            return

        # Filter to monitored pools if configured
        if self.pools_to_monitor:
            pools = {name: status for name, status in pools.items() if name in self.pools_to_monitor}
            logger.debug(
                "Filtered to monitored pools",
                extra={"monitored": list(pools.keys())},
            )

        if not pools:
            logger.warning("No pools found to monitor")
            return

        # Check pools against thresholds
        result = self.monitor.check_all_pools(pools)

        logger.info(
            "Check cycle completed",
            extra={
                "pools_checked": len(pools),
                "issues_found": len(result.issues),
                "severity": result.overall_severity.value,
            },
        )

        # Process results
        self._handle_check_result(result, pools)

        # Detect and notify recoveries
        self._detect_recoveries(result)

    def _handle_check_result(self, result: CheckResult, pools: dict[str, Any]) -> None:
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

        Parameters
        ----------
        result:
            Check result containing issues.
        pools:
            Pool status dict for issue context.
        """
        # Track current issues for recovery detection
        current_issues: dict[str, set[str]] = {}

        for issue in result.issues:
            # Track this issue
            if issue.pool_name not in current_issues:
                current_issues[issue.pool_name] = set()
            current_issues[issue.pool_name].add(issue.category)

            # Skip OK severity unless configured to send
            if issue.severity == Severity.OK and not self.send_ok_emails:
                logger.debug(
                    "Skipping OK issue (send_ok_emails disabled)",
                    extra={"pool": issue.pool_name, "category": issue.category},
                )
                continue

            # Check if we should send alert based on state
            if not self.state_manager.should_alert(issue):
                logger.debug(
                    "Suppressing duplicate alert",
                    extra={"pool": issue.pool_name, "category": issue.category},
                )
                continue

            # Send alert
            pool = pools.get(issue.pool_name)
            if not pool:
                logger.warning(
                    "Cannot send alert - pool status not found",
                    extra={"pool": issue.pool_name},
                )
                continue

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

        # Update current issues for next cycle
        self.previous_issues = current_issues

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

        # Find resolved issues
        for pool_name, prev_categories in self.previous_issues.items():
            current_categories = current_issues.get(pool_name, set())
            resolved = prev_categories - current_categories

            for category in resolved:
                logger.info(
                    "Detected issue recovery",
                    extra={"pool": pool_name, "category": category},
                )

                # Send recovery email
                success = self.alerter.send_recovery(pool_name, category)
                if success:
                    # Clear alert state so future issues alert immediately
                    self.state_manager.clear_issue(pool_name, category)
                    logger.info(
                        "Recovery notification sent",
                        extra={"pool": pool_name, "category": category},
                    )
