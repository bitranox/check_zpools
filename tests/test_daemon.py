"""Integration tests for daemon monitoring loop following clean architecture principles.

Design Philosophy
-----------------
These tests validate daemon behavior through real orchestration with minimal mocking:
- Test names read like plain English sentences describing exact behavior
- Each test validates ONE specific behavior - no multi-assert kitchen sinks
- Real daemon loop behavior - tests actual monitoring cycle orchestration
- OS-agnostic where possible, POSIX-specific for signal handling
- Deterministic - no timing dependencies beyond minimal waits

Test Structure Pattern
----------------------
1. Given: Setup minimal test state (fixtures, mocks)
2. When: Execute ONE daemon action
3. Then: Assert ONE specific outcome

Coverage Strategy
-----------------
- Daemon lifecycle: Initialization, start, stop
- Check cycles: Data fetching, parsing, monitoring
- Alert handling: New issues, duplicates, recoveries
- Error recovery: Transient failures, invalid data
- Signal handling: SIGTERM/SIGINT (POSIX only)
"""

from __future__ import annotations

import signal
import threading
import time
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from check_zpools.daemon import ZPoolDaemon
from check_zpools.models import CheckResult, PoolIssue, PoolStatus, Severity


# =============================================================================
# OS Markers
# =============================================================================

# Most daemon tests are OS-agnostic - monitoring logic works same on all platforms
# Signal handling tests require POSIX (SIGTERM/SIGINT not available on Windows)


# =============================================================================
# Note: Shared fixtures like healthy_pool_status are defined in conftest.py
# and automatically available to all test files.
# =============================================================================


# =============================================================================
# Test Fixtures - Daemon-Specific Test Data
# =============================================================================


@pytest.fixture
def capacity_warning_issue() -> PoolIssue:
    """Create a capacity warning issue for daemon testing.

    Why
        Represents a non-critical pool issue that triggers alerts.
        Used for testing alert handling and recovery notifications.

    Returns
        PoolIssue with WARNING severity and capacity category.
    """
    return PoolIssue(
        pool_name="rpool",
        severity=Severity.WARNING,
        category="capacity",
        message="Pool at 85.0% capacity",
        details={},
    )


@pytest.fixture
def healthy_pool_json() -> dict:
    """Create realistic ZFS status JSON for a healthy pool (--json-int format).

    Why
        Simulates actual 'zpool status -j --json-int' output.
        Used by daemon tests that need valid ZFS JSON data.

    Returns
        Dict matching ZFS JSON format with ONLINE pool.
    """
    return {
        "output_version": {"command": "zpool status", "vers_major": 0, "vers_minor": 1},
        "pools": {
            "rpool": {
                "name": "rpool",
                "state": "ONLINE",
                "pool_guid": 17068583395379267683,
                "txg": 2888298,
                "spa_version": 5000,
                "zpl_version": 5,
                "vdevs": {
                    "rpool": {
                        "name": "rpool",
                        "vdev_type": "root",
                        "state": "ONLINE",
                        "alloc_space": int(0.5 * 1024**4),  # 50% used
                        "total_space": 1024**4,  # 1 TB
                        "def_space": 1024**4,
                        "read_errors": 0,
                        "write_errors": 0,
                        "checksum_errors": 0,
                    }
                },
                "scan_stats": {
                    "function": "SCRUB",
                    "state": "FINISHED",
                    "start_time": int(datetime.now(UTC).timestamp()) - 86400,  # 1 day ago
                    "end_time": int(datetime.now(UTC).timestamp()) - 86400,
                    "errors": 0,
                },
            }
        },
    }


@pytest.fixture
def degraded_pool_json() -> dict:
    """Create realistic ZFS status JSON for a degraded pool (--json-int format).

    Why
        Simulates actual 'zpool status -j --json-int' output for unhealthy pool.
        Used for testing error detection and alert handling.

    Returns
        Dict matching ZFS JSON format with DEGRADED pool.
    """
    return {
        "output_version": {"command": "zpool status", "vers_major": 0, "vers_minor": 1},
        "pools": {
            "rpool": {
                "name": "rpool",
                "state": "DEGRADED",
                "pool_guid": 17068583395379267683,
                "txg": 2966143,
                "spa_version": 5000,
                "zpl_version": 5,
                "vdevs": {
                    "rpool": {
                        "name": "rpool",
                        "vdev_type": "root",
                        "state": "DEGRADED",
                        "alloc_space": int(0.5 * 1024**4),
                        "total_space": 1024**4,
                        "def_space": 1024**4,
                        "read_errors": 5,
                        "write_errors": 2,
                        "checksum_errors": 1,
                    }
                },
                "scan_stats": {
                    "function": "SCRUB",
                    "state": "FINISHED",
                    "start_time": int(datetime.now(UTC).timestamp()) - 86400,
                    "end_time": int(datetime.now(UTC).timestamp()) - 86400,
                    "errors": 3,
                },
            }
        },
    }


@pytest.fixture
def mock_zfs_client(healthy_pool_json: dict) -> Mock:
    """Create mock ZFS client that returns realistic JSON data.

    Why
        Avoids actual ZFS command execution in tests.
        Returns valid JSON that parser can process.

    Returns
        Mock with get_pool_status method (single command with --json-int).
    """
    client = Mock()
    client.get_pool_status.return_value = healthy_pool_json
    return client


@pytest.fixture
def mock_monitor() -> Mock:
    """Create mock pool monitor.

    Why
        Daemon delegates pool checking to monitor.
        Mock allows testing daemon orchestration.

    Returns
        Mock with check_all_pools method returning OK result.
    """
    monitor = Mock()
    monitor.check_all_pools.return_value = CheckResult(
        timestamp=datetime.now(UTC),
        pools=[],
        issues=[],
        overall_severity=Severity.OK,
    )
    return monitor


@pytest.fixture
def mock_alerter() -> Mock:
    """Create mock email alerter.

    Why
        Daemon sends alerts via alerter.
        Mock allows testing alert logic without SMTP.

    Returns
        Mock with send_alert and send_recovery methods.
    """
    alerter = Mock()
    alerter.send_alert.return_value = True
    alerter.send_recovery.return_value = True
    return alerter


@pytest.fixture
def mock_state_manager() -> Mock:
    """Create mock alert state manager.

    Why
        State manager tracks alert history for deduplication.
        Mock allows testing alert suppression logic.

    Returns
        Mock with should_alert, record_alert, clear_issue methods.
    """
    manager = Mock()
    manager.should_alert.return_value = True
    return manager


@pytest.fixture
def daemon_config() -> dict:
    """Create test daemon configuration.

    Why
        Fast check interval for testing (1 second vs 5 minute default).
        Disables optional features for focused testing.

    Returns
        Dict with minimal daemon configuration.
    """
    return {
        "check_interval_seconds": 1,  # Fast for testing
        "pools_to_monitor": [],
        "send_ok_emails": False,
        "send_recovery_emails": True,
    }


@pytest.fixture
def daemon(
    mock_zfs_client: Mock,
    mock_monitor: Mock,
    mock_alerter: Mock,
    mock_state_manager: Mock,
    daemon_config: dict,
) -> ZPoolDaemon:
    """Create daemon instance with all mocks configured.

    Why
        Provides fully-wired daemon for testing.
        All dependencies mocked to focus on daemon logic.

    Returns
        ZPoolDaemon ready for testing.
    """
    return ZPoolDaemon(
        zfs_client=mock_zfs_client,
        monitor=mock_monitor,
        alerter=mock_alerter,
        state_manager=mock_state_manager,
        config=daemon_config,
    )


# =============================================================================
# Daemon Initialization Tests
# =============================================================================


@pytest.mark.os_agnostic
class TestDaemonInitializationStoresComponents:
    """Daemon initialization stores all provided components."""

    def test_stores_zfs_client_reference(
        self,
        mock_zfs_client: Mock,
        mock_monitor: Mock,
        mock_alerter: Mock,
        mock_state_manager: Mock,
        daemon_config: dict,
    ) -> None:
        """When initializing with ZFS client, stores reference.

        Given: ZFS client instance
        When: Creating daemon with client
        Then: Daemon stores client reference
        """
        daemon = ZPoolDaemon(
            zfs_client=mock_zfs_client,
            monitor=mock_monitor,
            alerter=mock_alerter,
            state_manager=mock_state_manager,
            config=daemon_config,
        )

        assert daemon.zfs_client == mock_zfs_client

    def test_stores_monitor_reference(
        self,
        mock_zfs_client: Mock,
        mock_monitor: Mock,
        mock_alerter: Mock,
        mock_state_manager: Mock,
        daemon_config: dict,
    ) -> None:
        """When initializing with monitor, stores reference.

        Given: Pool monitor instance
        When: Creating daemon with monitor
        Then: Daemon stores monitor reference
        """
        daemon = ZPoolDaemon(
            zfs_client=mock_zfs_client,
            monitor=mock_monitor,
            alerter=mock_alerter,
            state_manager=mock_state_manager,
            config=daemon_config,
        )

        assert daemon.monitor == mock_monitor

    def test_stores_alerter_reference(
        self,
        mock_zfs_client: Mock,
        mock_monitor: Mock,
        mock_alerter: Mock,
        mock_state_manager: Mock,
        daemon_config: dict,
    ) -> None:
        """When initializing with alerter, stores reference.

        Given: Email alerter instance
        When: Creating daemon with alerter
        Then: Daemon stores alerter reference
        """
        daemon = ZPoolDaemon(
            zfs_client=mock_zfs_client,
            monitor=mock_monitor,
            alerter=mock_alerter,
            state_manager=mock_state_manager,
            config=daemon_config,
        )

        assert daemon.alerter == mock_alerter

    def test_stores_state_manager_reference(
        self,
        mock_zfs_client: Mock,
        mock_monitor: Mock,
        mock_alerter: Mock,
        mock_state_manager: Mock,
        daemon_config: dict,
    ) -> None:
        """When initializing with state manager, stores reference.

        Given: Alert state manager instance
        When: Creating daemon with state manager
        Then: Daemon stores state manager reference
        """
        daemon = ZPoolDaemon(
            zfs_client=mock_zfs_client,
            monitor=mock_monitor,
            alerter=mock_alerter,
            state_manager=mock_state_manager,
            config=daemon_config,
        )

        assert daemon.state_manager == mock_state_manager


@pytest.mark.os_agnostic
class TestDaemonInitializationAppliesConfiguration:
    """Daemon initialization applies configuration values."""

    def test_uses_configured_check_interval(
        self,
        mock_zfs_client: Mock,
        mock_monitor: Mock,
        mock_alerter: Mock,
        mock_state_manager: Mock,
    ) -> None:
        """When config specifies check_interval_seconds, uses that interval.

        Given: Config with check_interval_seconds=1
        When: Creating daemon with config
        Then: Daemon check_interval is 1
        """
        daemon = ZPoolDaemon(
            zfs_client=mock_zfs_client,
            monitor=mock_monitor,
            alerter=mock_alerter,
            state_manager=mock_state_manager,
            config={"check_interval_seconds": 1},
        )

        assert daemon.check_interval == 1

    def test_defaults_to_five_minutes_when_interval_not_specified(
        self,
        mock_zfs_client: Mock,
        mock_monitor: Mock,
        mock_alerter: Mock,
        mock_state_manager: Mock,
    ) -> None:
        """When config omits check_interval_seconds, defaults to 300 seconds.

        Given: Empty config
        When: Creating daemon with config
        Then: Daemon check_interval is 300 (5 minutes)
        """
        daemon = ZPoolDaemon(
            zfs_client=mock_zfs_client,
            monitor=mock_monitor,
            alerter=mock_alerter,
            state_manager=mock_state_manager,
            config={},
        )

        assert daemon.check_interval == 300


# =============================================================================
# Check Cycle Tests - Data Orchestration
# =============================================================================


@pytest.mark.os_agnostic
class TestCheckCycleFetchesZFSData:
    """Check cycle fetches pool data from ZFS."""

    def test_fetches_pool_status_from_zfs_client(self, daemon: ZPoolDaemon, mock_zfs_client: Mock) -> None:
        """When running check cycle, fetches pool status.

        Given: Daemon with ZFS client
        When: Running _run_check_cycle
        Then: Calls get_pool_status once (single command with --json-int)
        """
        daemon._run_check_cycle()

        mock_zfs_client.get_pool_status.assert_called_once()


@pytest.mark.os_agnostic
class TestCheckCyclePassesDataToMonitor:
    """Check cycle passes parsed pool data to monitor."""

    def test_passes_parsed_pools_dictionary_to_monitor(self, daemon: ZPoolDaemon, mock_monitor: Mock) -> None:
        """When running check cycle, passes pool dict to monitor.

        Given: Daemon with monitor
        When: Running _run_check_cycle
        Then: Calls check_all_pools with dict
        """
        daemon._run_check_cycle()

        mock_monitor.check_all_pools.assert_called_once()
        call_args = mock_monitor.check_all_pools.call_args[0][0]
        assert isinstance(call_args, dict)

    def test_passes_non_empty_pools_dictionary(self, daemon: ZPoolDaemon, mock_monitor: Mock) -> None:
        """When running check cycle, passes non-empty pool dict.

        Given: ZFS client returning pool data
        When: Running _run_check_cycle
        Then: Monitor receives dict with pools
        """
        daemon._run_check_cycle()

        call_args = mock_monitor.check_all_pools.call_args[0][0]
        assert len(call_args) > 0

    def test_passes_pool_keyed_by_name(self, daemon: ZPoolDaemon, mock_monitor: Mock) -> None:
        """When running check cycle, pool dict keyed by name.

        Given: ZFS returning 'rpool' data
        When: Running _run_check_cycle
        Then: Monitor receives dict with 'rpool' key
        """
        daemon._run_check_cycle()

        call_args = mock_monitor.check_all_pools.call_args[0][0]
        assert "rpool" in call_args


# =============================================================================
# Error Recovery Tests - Resilience
# =============================================================================


@pytest.mark.os_agnostic
class TestCheckCycleRecoversFromErrors:
    """Check cycle recovers gracefully from errors."""

    def test_continues_after_zfs_fetch_error(self, daemon: ZPoolDaemon, mock_zfs_client: Mock) -> None:
        """When ZFS client raises error, logs and continues.

        Given: ZFS client that raises RuntimeError
        When: Running _run_check_cycle
        Then: Does not crash (returns normally)
        """
        mock_zfs_client.get_pool_status.side_effect = RuntimeError("ZFS error")

        # Should not raise
        daemon._run_check_cycle()

    def test_continues_after_parse_error(self, daemon: ZPoolDaemon, mock_zfs_client: Mock) -> None:
        """When ZFS returns invalid data, logs and continues.

        Given: ZFS client returning invalid JSON
        When: Running _run_check_cycle
        Then: Does not crash (returns normally)
        """
        mock_zfs_client.get_pool_status.return_value = {"invalid": "data"}

        # Should not raise
        daemon._run_check_cycle()


# =============================================================================
# Alert Handling Tests - Issue Detection
# =============================================================================


@pytest.mark.os_agnostic
class TestAlertHandlingSendsAlertsForNewIssues:
    """Alert handling sends emails for newly detected issues."""

    def test_sends_alert_when_new_issue_detected(
        self,
        daemon: ZPoolDaemon,
        mock_alerter: Mock,
        mock_state_manager: Mock,
        mock_monitor: Mock,
        healthy_pool_status: PoolStatus,
        capacity_warning_issue: PoolIssue,
    ) -> None:
        """When new issue is detected, sends alert email.

        Given: Monitor returns result with WARNING issue
        And: State manager indicates issue is new
        When: Running _run_check_cycle
        Then: Calls send_alert once
        """
        mock_monitor.check_all_pools.return_value = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[healthy_pool_status],
            issues=[capacity_warning_issue],
            overall_severity=Severity.WARNING,
        )
        mock_state_manager.should_alert.return_value = True

        daemon._run_check_cycle()

        assert mock_alerter.send_alert.call_count == 1

    def test_alert_includes_issue_details(
        self,
        daemon: ZPoolDaemon,
        mock_alerter: Mock,
        mock_state_manager: Mock,
        mock_monitor: Mock,
        healthy_pool_status: PoolStatus,
        capacity_warning_issue: PoolIssue,
    ) -> None:
        """When sending alert, includes issue object.

        Given: Monitor returns result with issue
        When: Running _run_check_cycle
        Then: send_alert called with issue as first arg
        """
        mock_monitor.check_all_pools.return_value = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[healthy_pool_status],
            issues=[capacity_warning_issue],
            overall_severity=Severity.WARNING,
        )
        mock_state_manager.should_alert.return_value = True

        daemon._run_check_cycle()

        call_args = mock_alerter.send_alert.call_args[0]
        assert call_args[0] == capacity_warning_issue

    def test_alert_includes_pool_status(
        self,
        daemon: ZPoolDaemon,
        mock_alerter: Mock,
        mock_state_manager: Mock,
        mock_monitor: Mock,
        healthy_pool_status: PoolStatus,
        capacity_warning_issue: PoolIssue,
    ) -> None:
        """When sending alert, includes pool status.

        Given: Monitor returns result with pool status
        When: Running _run_check_cycle
        Then: send_alert called with pool status as second arg
        """
        mock_monitor.check_all_pools.return_value = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[healthy_pool_status],
            issues=[capacity_warning_issue],
            overall_severity=Severity.WARNING,
        )
        mock_state_manager.should_alert.return_value = True

        daemon._run_check_cycle()

        call_args = mock_alerter.send_alert.call_args[0]
        assert call_args[1].name == "rpool"


@pytest.mark.os_agnostic
class TestAlertHandlingRecordsNewIssues:
    """Alert handling records new issues in state manager."""

    def test_records_alert_in_state_manager(
        self,
        daemon: ZPoolDaemon,
        mock_alerter: Mock,
        mock_state_manager: Mock,
        mock_monitor: Mock,
        healthy_pool_status: PoolStatus,
        capacity_warning_issue: PoolIssue,
    ) -> None:
        """When sending alert, records in state manager.

        Given: New issue detected
        When: Running _run_check_cycle
        Then: Calls record_alert with issue
        """
        mock_monitor.check_all_pools.return_value = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[healthy_pool_status],
            issues=[capacity_warning_issue],
            overall_severity=Severity.WARNING,
        )
        mock_state_manager.should_alert.return_value = True

        daemon._run_check_cycle()

        mock_state_manager.record_alert.assert_called_once_with(capacity_warning_issue)


@pytest.mark.os_agnostic
class TestAlertHandlingSuppressesDuplicates:
    """Alert handling suppresses duplicate issue alerts."""

    def test_suppresses_alert_when_issue_is_duplicate(
        self,
        daemon: ZPoolDaemon,
        mock_alerter: Mock,
        mock_state_manager: Mock,
        mock_monitor: Mock,
        healthy_pool_status: PoolStatus,
        capacity_warning_issue: PoolIssue,
    ) -> None:
        """When state manager indicates duplicate, does not send alert.

        Given: Issue detected but state manager returns False for should_alert
        When: Running _run_check_cycle
        Then: send_alert is not called
        """
        mock_monitor.check_all_pools.return_value = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[healthy_pool_status],
            issues=[capacity_warning_issue],
            overall_severity=Severity.WARNING,
        )
        mock_state_manager.should_alert.return_value = False

        daemon._run_check_cycle()

        mock_alerter.send_alert.assert_not_called()

    def test_does_not_alert_for_ok_severity_issues(
        self,
        daemon: ZPoolDaemon,
        mock_alerter: Mock,
        mock_monitor: Mock,
        healthy_pool_status: PoolStatus,
    ) -> None:
        """When issue has OK severity, does not send alert.

        Given: Issue with Severity.OK
        When: Running _run_check_cycle
        Then: send_alert is not called
        """
        ok_issue = PoolIssue(
            pool_name="rpool",
            severity=Severity.OK,
            category="health",
            message="Pool healthy",
            details={},
        )

        mock_monitor.check_all_pools.return_value = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[healthy_pool_status],
            issues=[ok_issue],
            overall_severity=Severity.OK,
        )

        daemon._run_check_cycle()

        mock_alerter.send_alert.assert_not_called()


# =============================================================================
# Recovery Detection Tests - Issue Resolution
# =============================================================================


@pytest.mark.os_agnostic
class TestRecoveryDetectionSendsNotifications:
    """Recovery detection sends notifications when issues resolve."""

    def test_sends_recovery_when_issue_resolves(
        self,
        daemon: ZPoolDaemon,
        mock_alerter: Mock,
        mock_state_manager: Mock,
        mock_monitor: Mock,
        healthy_pool_status: PoolStatus,
        capacity_warning_issue: PoolIssue,
    ) -> None:
        """When issue from previous cycle resolves, sends recovery.

        Given: First cycle with issue, second cycle without
        When: Running two _run_check_cycle calls
        Then: send_recovery called once
        """
        # First cycle: issue present
        mock_monitor.check_all_pools.return_value = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[healthy_pool_status],
            issues=[capacity_warning_issue],
            overall_severity=Severity.WARNING,
        )
        mock_state_manager.should_alert.return_value = False
        daemon._run_check_cycle()

        # Second cycle: issue resolved
        mock_monitor.check_all_pools.return_value = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[healthy_pool_status],
            issues=[],
            overall_severity=Severity.OK,
        )
        daemon._run_check_cycle()

        mock_alerter.send_recovery.assert_called_once()

    def test_recovery_includes_pool_name(
        self,
        daemon: ZPoolDaemon,
        mock_alerter: Mock,
        mock_state_manager: Mock,
        mock_monitor: Mock,
        healthy_pool_status: PoolStatus,
        capacity_warning_issue: PoolIssue,
    ) -> None:
        """When sending recovery, includes pool name.

        Given: Issue resolves for 'rpool'
        When: Recovery notification sent
        Then: First arg is 'rpool'
        """
        mock_monitor.check_all_pools.return_value = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[healthy_pool_status],
            issues=[capacity_warning_issue],
            overall_severity=Severity.WARNING,
        )
        mock_state_manager.should_alert.return_value = False
        daemon._run_check_cycle()

        mock_monitor.check_all_pools.return_value = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[healthy_pool_status],
            issues=[],
            overall_severity=Severity.OK,
        )
        daemon._run_check_cycle()

        call_args = mock_alerter.send_recovery.call_args
        assert call_args[0][0] == "rpool"

    def test_recovery_includes_issue_category(
        self,
        daemon: ZPoolDaemon,
        mock_alerter: Mock,
        mock_state_manager: Mock,
        mock_monitor: Mock,
        healthy_pool_status: PoolStatus,
        capacity_warning_issue: PoolIssue,
    ) -> None:
        """When sending recovery, includes issue category.

        Given: Capacity issue resolves
        When: Recovery notification sent
        Then: Second arg is 'capacity'
        """
        mock_monitor.check_all_pools.return_value = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[healthy_pool_status],
            issues=[capacity_warning_issue],
            overall_severity=Severity.WARNING,
        )
        mock_state_manager.should_alert.return_value = False
        daemon._run_check_cycle()

        mock_monitor.check_all_pools.return_value = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[healthy_pool_status],
            issues=[],
            overall_severity=Severity.OK,
        )
        daemon._run_check_cycle()

        call_args = mock_alerter.send_recovery.call_args
        assert call_args[0][1] == "capacity"

    def test_recovery_includes_pool_status(
        self,
        daemon: ZPoolDaemon,
        mock_alerter: Mock,
        mock_state_manager: Mock,
        mock_monitor: Mock,
        healthy_pool_status: PoolStatus,
        capacity_warning_issue: PoolIssue,
    ) -> None:
        """When sending recovery, includes current pool status.

        Given: Issue resolves
        When: Recovery notification sent
        Then: Third arg is pool status
        """
        mock_monitor.check_all_pools.return_value = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[healthy_pool_status],
            issues=[capacity_warning_issue],
            overall_severity=Severity.WARNING,
        )
        mock_state_manager.should_alert.return_value = False
        daemon._run_check_cycle()

        mock_monitor.check_all_pools.return_value = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[healthy_pool_status],
            issues=[],
            overall_severity=Severity.OK,
        )
        daemon._run_check_cycle()

        call_args = mock_alerter.send_recovery.call_args
        assert call_args[0][2].name == "rpool"


@pytest.mark.os_agnostic
class TestRecoveryDetectionClearsState:
    """Recovery detection clears resolved issues from state."""

    def test_clears_issue_from_state_manager(
        self,
        daemon: ZPoolDaemon,
        mock_alerter: Mock,
        mock_state_manager: Mock,
        mock_monitor: Mock,
        healthy_pool_status: PoolStatus,
        capacity_warning_issue: PoolIssue,
    ) -> None:
        """When issue recovers, clears from state manager.

        Given: Issue resolves
        When: Recovery processed
        Then: Calls clear_issue with pool name and category
        """
        mock_monitor.check_all_pools.return_value = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[healthy_pool_status],
            issues=[capacity_warning_issue],
            overall_severity=Severity.WARNING,
        )
        mock_state_manager.should_alert.return_value = False
        daemon._run_check_cycle()

        mock_monitor.check_all_pools.return_value = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[healthy_pool_status],
            issues=[],
            overall_severity=Severity.OK,
        )
        daemon._run_check_cycle()

        mock_state_manager.clear_issue.assert_called_with("rpool", "capacity")


# =============================================================================
# Signal Handling Tests - Graceful Shutdown (POSIX Only)
# =============================================================================


@pytest.mark.posix_only
class TestSignalHandlingRegistersHandlers:
    """On POSIX systems, daemon registers signal handlers."""

    def test_registers_sigterm_handler(self, daemon: ZPoolDaemon) -> None:
        """When setting up signals, registers SIGTERM handler.

        Given: Daemon on POSIX system
        When: Calling _setup_signal_handlers
        Then: SIGTERM handler is changed
        """
        original_sigterm = signal.getsignal(signal.SIGTERM)

        daemon._setup_signal_handlers()

        new_sigterm = signal.getsignal(signal.SIGTERM)
        assert new_sigterm != original_sigterm

    def test_registers_sigint_handler(self, daemon: ZPoolDaemon) -> None:
        """When setting up signals, registers SIGINT handler.

        Given: Daemon on POSIX system
        When: Calling _setup_signal_handlers
        Then: SIGINT handler is changed
        """
        original_sigint = signal.getsignal(signal.SIGINT)

        daemon._setup_signal_handlers()

        new_sigint = signal.getsignal(signal.SIGINT)
        assert new_sigint != original_sigint


# =============================================================================
# Daemon Lifecycle Tests - Start/Stop
# =============================================================================


@pytest.mark.os_agnostic
class TestDaemonStopSetsShutdownState:
    """Daemon stop() method sets shutdown state correctly."""

    def test_sets_shutdown_event(self, daemon: ZPoolDaemon) -> None:
        """When stop() called, sets shutdown event.

        Given: Running daemon
        When: Calling stop()
        Then: shutdown_event is set
        """
        daemon.running = True

        daemon.stop()

        assert daemon.shutdown_event.is_set()

    def test_sets_running_flag_to_false(self, daemon: ZPoolDaemon) -> None:
        """When stop() called, sets running flag False.

        Given: Running daemon
        When: Calling stop()
        Then: running is False
        """
        daemon.running = True

        daemon.stop()

        assert daemon.running is False

    def test_is_idempotent(self, daemon: ZPoolDaemon) -> None:
        """When stop() called multiple times, handles safely.

        Given: Running daemon
        When: Calling stop() twice
        Then: No errors occur
        """
        daemon.running = True

        daemon.stop()
        daemon.stop()  # Second call should be harmless

        assert daemon.shutdown_event.is_set()


# =============================================================================
# Monitoring Loop Tests - Periodic Execution
# =============================================================================


@pytest.mark.os_agnostic
class TestMonitoringLoopExecutesCycles:
    """Monitoring loop executes check cycles periodically."""

    def test_executes_at_least_one_check_cycle(self, daemon: ZPoolDaemon, mock_monitor: Mock) -> None:
        """When loop runs, executes at least one check.

        Given: Daemon with 1-second check interval
        When: Loop runs for 1.5 seconds
        Then: check_all_pools called at least once
        """

        def run_loop():
            daemon._run_monitoring_loop()

        thread = threading.Thread(target=run_loop, daemon=True)
        thread.start()

        # Give it time to run at least one cycle
        time.sleep(1.5)  # Sleep longer than check interval (1 second)
        daemon.stop()
        thread.join(timeout=2.0)

        assert mock_monitor.check_all_pools.call_count >= 1

    def test_continues_after_transient_errors(self, daemon: ZPoolDaemon, mock_zfs_client: Mock, healthy_pool_json: dict) -> None:
        """When check cycle encounters error, loop continues.

        Given: ZFS client that fails once then succeeds
        When: Loop runs for 1 second
        Then: get_pool_status called multiple times (retry successful)
        """
        call_count = 0

        def failing_then_succeeding_get_pool_status():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Temporary error")
            return healthy_pool_json

        mock_zfs_client.get_pool_status.side_effect = failing_then_succeeding_get_pool_status

        def run_loop():
            daemon._run_monitoring_loop()

        thread = threading.Thread(target=run_loop, daemon=True)
        thread.start()

        daemon.shutdown_event.wait(timeout=1.0)
        daemon.stop()
        thread.join(timeout=1.0)

        # Should have called multiple times despite first failure
        assert call_count >= 2
