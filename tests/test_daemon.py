"""Tests for daemon monitoring loop.

Tests cover:
- Check cycle execution
- Signal handling (SIGTERM/SIGINT on POSIX)
- Error recovery
- Alert management integration
- State persistence

Most tests are OS-agnostic (daemon logic works everywhere).
Signal handling tests are POSIX-only (SIGTERM/SIGINT).
"""

from __future__ import annotations

import signal
import threading
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from check_zpools.daemon import ZPoolDaemon
from check_zpools.models import CheckResult, PoolHealth, PoolIssue, PoolStatus, Severity


# ============================================================================
# Test Data Builders
# ============================================================================


def a_healthy_pool_for_daemon(name: str = "rpool") -> PoolStatus:
    """Create a healthy pool for daemon testing."""
    return PoolStatus(
        name=name,
        health=PoolHealth.ONLINE,
        capacity_percent=50.0,
        size_bytes=1024**4,
        allocated_bytes=int(0.5 * 1024**4),
        free_bytes=int(0.5 * 1024**4),
        read_errors=0,
        write_errors=0,
        checksum_errors=0,
        last_scrub=datetime.now(UTC),
        scrub_errors=0,
        scrub_in_progress=False,
    )


def a_capacity_issue_for_daemon(pool_name: str, capacity: float = 85.0) -> PoolIssue:
    """Create a capacity warning issue."""
    return PoolIssue(
        pool_name=pool_name,
        severity=Severity.WARNING,
        category="capacity",
        message=f"Pool at {capacity}% capacity",
        details={},
    )


def an_ok_check_result() -> CheckResult:
    """Create a check result with no issues."""
    return CheckResult(
        timestamp=datetime.now(UTC),
        pools=[],
        issues=[],
        overall_severity=Severity.OK,
    )


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def healthy_pool_json() -> dict:
    """Realistic JSON for a healthy pool (from zpool status -j)."""
    return {
        "output_version": {"command": "zpool status", "vers_major": 0, "vers_minor": 1},
        "pools": {
            "rpool": {
                "name": "rpool",
                "type": "POOL",
                "state": "ONLINE",
                "pool_guid": "17068583395379267683",
                "txg": "2888298",
                "spa_version": "5000",
                "zpl_version": "5",
                "vdev_tree": {"type": "root", "stats": {"read_errors": 0, "write_errors": 0, "checksum_errors": 0}},
                "scan": {
                    "state": "finished",
                    "start_time": int(datetime.now(UTC).timestamp()) - 86400,  # 1 day ago
                    "end_time": int(datetime.now(UTC).timestamp()) - 86400,
                    "errors": 0,
                },
            }
        },
    }


@pytest.fixture
def degraded_pool_json() -> dict:
    """Realistic JSON for a degraded pool (from zpool status -j)."""
    return {
        "output_version": {"command": "zpool status", "vers_major": 0, "vers_minor": 1},
        "pools": {
            "rpool": {
                "name": "rpool",
                "type": "POOL",
                "state": "DEGRADED",
                "pool_guid": "17068583395379267683",
                "txg": "2966143",
                "spa_version": "5000",
                "zpl_version": "5",
                "vdev_tree": {"type": "root", "stats": {"read_errors": 5, "write_errors": 2, "checksum_errors": 1}},
                "scan": {
                    "state": "finished",
                    "start_time": int(datetime.now(UTC).timestamp()) - 86400,
                    "end_time": int(datetime.now(UTC).timestamp()) - 86400,
                    "errors": 3,
                },
            }
        },
    }


@pytest.fixture
def pool_list_json() -> dict:
    """Realistic JSON from zpool list -j command."""
    return {
        "output_version": {"command": "zpool list", "vers_major": 0, "vers_minor": 1},
        "pools": {
            "rpool": {
                "name": "rpool",
                "type": "POOL",
                "state": "ONLINE",
                "pool_guid": "17068583395379267683",
                "txg": "2888298",
                "spa_version": "5000",
                "zpl_version": "5",
                "properties": {
                    "health": {"value": "ONLINE"},
                    "size": {
                        "value": str(1024**4)  # 1 TB
                    },
                    "allocated": {
                        "value": str(int(0.5 * 1024**4))  # 50% used
                    },
                    "free": {"value": str(int(0.5 * 1024**4))},
                    "capacity": {"value": "50"},
                },
            }
        },
    }


@pytest.fixture
def mock_zfs_client(healthy_pool_json: dict, pool_list_json: dict) -> Mock:
    """Create mock ZFS client that returns realistic JSON data."""
    client = Mock()
    # Return valid ZFS JSON that parser can handle
    client.get_pool_list.return_value = pool_list_json
    client.get_pool_status.return_value = healthy_pool_json
    return client


@pytest.fixture
def mock_monitor() -> Mock:
    """Create mock pool monitor."""
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
    """Create mock email alerter."""
    alerter = Mock()
    alerter.send_alert.return_value = True
    alerter.send_recovery.return_value = True
    return alerter


@pytest.fixture
def mock_state_manager() -> Mock:
    """Create mock alert state manager."""
    manager = Mock()
    manager.should_alert.return_value = True
    return manager


@pytest.fixture
def daemon_config() -> dict:
    """Create test daemon configuration."""
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
    """Create daemon instance with mocks."""
    return ZPoolDaemon(
        zfs_client=mock_zfs_client,
        monitor=mock_monitor,
        alerter=mock_alerter,
        state_manager=mock_state_manager,
        config=daemon_config,
    )


@pytest.mark.os_agnostic
class TestDaemonInitialization:
    """When creating a daemon, configuration is applied correctly."""

    def test_daemon_remembers_all_provided_components(
        self,
        mock_zfs_client: Mock,
        mock_monitor: Mock,
        mock_alerter: Mock,
        mock_state_manager: Mock,
        daemon_config: dict,
    ) -> None:
        """When initializing with all components,
        the daemon stores references to each."""
        daemon = ZPoolDaemon(
            zfs_client=mock_zfs_client,
            monitor=mock_monitor,
            alerter=mock_alerter,
            state_manager=mock_state_manager,
            config=daemon_config,
        )

        assert daemon.zfs_client == mock_zfs_client
        assert daemon.monitor == mock_monitor
        assert daemon.alerter == mock_alerter
        assert daemon.state_manager == mock_state_manager

    def test_daemon_applies_configured_check_interval(
        self,
        mock_zfs_client: Mock,
        mock_monitor: Mock,
        mock_alerter: Mock,
        mock_state_manager: Mock,
        daemon_config: dict,
    ) -> None:
        """When config specifies check_interval_seconds,
        the daemon uses that interval."""
        daemon = ZPoolDaemon(
            zfs_client=mock_zfs_client,
            monitor=mock_monitor,
            alerter=mock_alerter,
            state_manager=mock_state_manager,
            config=daemon_config,
        )

        assert daemon.check_interval == 1

    def test_daemon_uses_five_minute_default_when_interval_not_specified(
        self,
        mock_zfs_client: Mock,
        mock_monitor: Mock,
        mock_alerter: Mock,
        mock_state_manager: Mock,
    ) -> None:
        """When config omits check_interval_seconds,
        the daemon defaults to 300 seconds (5 minutes)."""
        daemon = ZPoolDaemon(
            zfs_client=mock_zfs_client,
            monitor=mock_monitor,
            alerter=mock_alerter,
            state_manager=mock_state_manager,
            config={},
        )

        assert daemon.check_interval == 300


@pytest.mark.os_agnostic
class TestCheckCycle:
    """When daemon executes a check cycle, it orchestrates data flow correctly."""

    def test_check_cycle_fetches_pool_list_from_zfs(self, daemon: ZPoolDaemon, mock_zfs_client: Mock) -> None:
        """When running a check cycle,
        the daemon fetches pool list from ZFS client."""
        daemon._run_check_cycle()

        mock_zfs_client.get_pool_list.assert_called_once()

    def test_check_cycle_fetches_pool_status_from_zfs(self, daemon: ZPoolDaemon, mock_zfs_client: Mock) -> None:
        """When running a check cycle,
        the daemon fetches pool status from ZFS client."""
        daemon._run_check_cycle()

        mock_zfs_client.get_pool_status.assert_called_once()

    def test_check_cycle_passes_parsed_pools_to_monitor(self, daemon: ZPoolDaemon, mock_monitor: Mock) -> None:
        """When running a check cycle,
        parsed pool data is passed to the monitor."""
        daemon._run_check_cycle()

        mock_monitor.check_all_pools.assert_called_once()
        call_args = mock_monitor.check_all_pools.call_args[0][0]
        assert isinstance(call_args, dict)
        assert len(call_args) > 0

    def test_check_cycle_monitors_specific_pool_by_name(self, daemon: ZPoolDaemon, mock_monitor: Mock) -> None:
        """When running a check cycle,
        the monitor receives pools keyed by name."""
        daemon._run_check_cycle()

        call_args = mock_monitor.check_all_pools.call_args[0][0]
        assert "rpool" in call_args

    def test_check_cycle_recovers_from_zfs_fetch_errors(self, daemon: ZPoolDaemon, mock_zfs_client: Mock) -> None:
        """When ZFS client raises an error,
        the check cycle logs and continues without crashing."""
        mock_zfs_client.get_pool_list.side_effect = RuntimeError("ZFS error")

        # Should not raise
        daemon._run_check_cycle()

    def test_check_cycle_recovers_from_parse_errors(self, daemon: ZPoolDaemon, mock_zfs_client: Mock) -> None:
        """When ZFS returns invalid data that fails parsing,
        the check cycle logs and continues without crashing."""
        mock_zfs_client.get_pool_list.return_value = {"invalid": "data"}

        # Should not raise
        daemon._run_check_cycle()


@pytest.mark.os_agnostic
class TestAlertHandling:
    """When daemon detects issues, it manages alerts intelligently."""

    def test_new_issue_triggers_email_alert(
        self,
        daemon: ZPoolDaemon,
        mock_alerter: Mock,
        mock_state_manager: Mock,
        mock_monitor: Mock,
    ) -> None:
        """When a new issue is detected,
        the daemon sends an alert email."""
        pool = a_healthy_pool_for_daemon("rpool")
        issue = a_capacity_issue_for_daemon("rpool")

        mock_monitor.check_all_pools.return_value = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[pool],
            issues=[issue],
            overall_severity=Severity.WARNING,
        )
        mock_state_manager.should_alert.return_value = True

        daemon._run_check_cycle()

        assert mock_alerter.send_alert.call_count == 1

    def test_new_issue_alert_includes_issue_details(
        self,
        daemon: ZPoolDaemon,
        mock_alerter: Mock,
        mock_state_manager: Mock,
        mock_monitor: Mock,
    ) -> None:
        """When alerting on a new issue,
        the alert includes the issue object."""
        pool = a_healthy_pool_for_daemon("rpool")
        issue = a_capacity_issue_for_daemon("rpool")

        mock_monitor.check_all_pools.return_value = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[pool],
            issues=[issue],
            overall_severity=Severity.WARNING,
        )
        mock_state_manager.should_alert.return_value = True

        daemon._run_check_cycle()

        call_args = mock_alerter.send_alert.call_args[0]
        assert call_args[0] == issue

    def test_new_issue_alert_includes_pool_status(
        self,
        daemon: ZPoolDaemon,
        mock_alerter: Mock,
        mock_state_manager: Mock,
        mock_monitor: Mock,
    ) -> None:
        """When alerting on a new issue,
        the alert includes the pool status."""
        pool = a_healthy_pool_for_daemon("rpool")
        issue = a_capacity_issue_for_daemon("rpool")

        mock_monitor.check_all_pools.return_value = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[pool],
            issues=[issue],
            overall_severity=Severity.WARNING,
        )
        mock_state_manager.should_alert.return_value = True

        daemon._run_check_cycle()

        call_args = mock_alerter.send_alert.call_args[0]
        assert call_args[1].name == "rpool"

    def test_new_issue_updates_state_manager(
        self,
        daemon: ZPoolDaemon,
        mock_alerter: Mock,
        mock_state_manager: Mock,
        mock_monitor: Mock,
    ) -> None:
        """When alerting on a new issue,
        the state manager records the alert."""
        pool = a_healthy_pool_for_daemon("rpool")
        issue = a_capacity_issue_for_daemon("rpool")

        mock_monitor.check_all_pools.return_value = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[pool],
            issues=[issue],
            overall_severity=Severity.WARNING,
        )
        mock_state_manager.should_alert.return_value = True

        daemon._run_check_cycle()

        mock_state_manager.record_alert.assert_called_once_with(issue)

    def test_duplicate_issue_alert_is_suppressed(
        self,
        daemon: ZPoolDaemon,
        mock_alerter: Mock,
        mock_state_manager: Mock,
        mock_monitor: Mock,
    ) -> None:
        """When state manager indicates an issue is a duplicate,
        no alert email is sent."""
        pool = a_healthy_pool_for_daemon("rpool")
        issue = a_capacity_issue_for_daemon("rpool")

        mock_monitor.check_all_pools.return_value = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[pool],
            issues=[issue],
            overall_severity=Severity.WARNING,
        )
        mock_state_manager.should_alert.return_value = False

        daemon._run_check_cycle()

        mock_alerter.send_alert.assert_not_called()

    def test_ok_severity_issues_do_not_trigger_alerts(
        self,
        daemon: ZPoolDaemon,
        mock_alerter: Mock,
        mock_monitor: Mock,
    ) -> None:
        """When an issue has OK severity,
        no alert is sent by default."""
        pool = a_healthy_pool_for_daemon("rpool")
        issue = PoolIssue(
            pool_name="rpool",
            severity=Severity.OK,
            category="health",
            message="Pool healthy",
            details={},
        )

        mock_monitor.check_all_pools.return_value = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[pool],
            issues=[issue],
            overall_severity=Severity.OK,
        )

        daemon._run_check_cycle()

        mock_alerter.send_alert.assert_not_called()


@pytest.mark.os_agnostic
class TestRecoveryDetection:
    """When issues resolve, daemon sends recovery notifications."""

    def test_resolved_issue_triggers_recovery_notification(
        self,
        daemon: ZPoolDaemon,
        mock_alerter: Mock,
        mock_state_manager: Mock,
        mock_monitor: Mock,
    ) -> None:
        """When an issue from previous cycle is resolved,
        a recovery notification is sent."""
        pool = a_healthy_pool_for_daemon("rpool")
        issue = a_capacity_issue_for_daemon("rpool")

        # First cycle: issue present
        mock_monitor.check_all_pools.return_value = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[pool],
            issues=[issue],
            overall_severity=Severity.WARNING,
        )
        mock_state_manager.should_alert.return_value = False
        daemon._run_check_cycle()

        # Second cycle: issue resolved
        mock_monitor.check_all_pools.return_value = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[pool],
            issues=[],
            overall_severity=Severity.OK,
        )
        daemon._run_check_cycle()

        mock_alerter.send_recovery.assert_called_once()

    def test_recovery_notification_includes_pool_name(
        self,
        daemon: ZPoolDaemon,
        mock_alerter: Mock,
        mock_state_manager: Mock,
        mock_monitor: Mock,
    ) -> None:
        """When sending recovery notification,
        the pool name is included."""
        pool = a_healthy_pool_for_daemon("rpool")
        issue = a_capacity_issue_for_daemon("rpool")

        mock_monitor.check_all_pools.return_value = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[pool],
            issues=[issue],
            overall_severity=Severity.WARNING,
        )
        mock_state_manager.should_alert.return_value = False
        daemon._run_check_cycle()

        mock_monitor.check_all_pools.return_value = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[pool],
            issues=[],
            overall_severity=Severity.OK,
        )
        daemon._run_check_cycle()

        call_args = mock_alerter.send_recovery.call_args
        assert call_args[0][0] == "rpool"

    def test_recovery_notification_includes_issue_category(
        self,
        daemon: ZPoolDaemon,
        mock_alerter: Mock,
        mock_state_manager: Mock,
        mock_monitor: Mock,
    ) -> None:
        """When sending recovery notification,
        the issue category is included."""
        pool = a_healthy_pool_for_daemon("rpool")
        issue = a_capacity_issue_for_daemon("rpool")

        mock_monitor.check_all_pools.return_value = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[pool],
            issues=[issue],
            overall_severity=Severity.WARNING,
        )
        mock_state_manager.should_alert.return_value = False
        daemon._run_check_cycle()

        mock_monitor.check_all_pools.return_value = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[pool],
            issues=[],
            overall_severity=Severity.OK,
        )
        daemon._run_check_cycle()

        call_args = mock_alerter.send_recovery.call_args
        assert call_args[0][1] == "capacity"

    def test_recovery_notification_includes_pool_status(
        self,
        daemon: ZPoolDaemon,
        mock_alerter: Mock,
        mock_state_manager: Mock,
        mock_monitor: Mock,
    ) -> None:
        """When sending recovery notification,
        the current pool status is included."""
        pool = a_healthy_pool_for_daemon("rpool")
        issue = a_capacity_issue_for_daemon("rpool")

        mock_monitor.check_all_pools.return_value = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[pool],
            issues=[issue],
            overall_severity=Severity.WARNING,
        )
        mock_state_manager.should_alert.return_value = False
        daemon._run_check_cycle()

        mock_monitor.check_all_pools.return_value = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[pool],
            issues=[],
            overall_severity=Severity.OK,
        )
        daemon._run_check_cycle()

        call_args = mock_alerter.send_recovery.call_args
        assert call_args[0][2].name == "rpool"

    def test_recovery_clears_issue_from_state_manager(
        self,
        daemon: ZPoolDaemon,
        mock_alerter: Mock,
        mock_state_manager: Mock,
        mock_monitor: Mock,
    ) -> None:
        """When an issue recovers,
        the state manager clears the issue."""
        pool = a_healthy_pool_for_daemon("rpool")
        issue = a_capacity_issue_for_daemon("rpool")

        mock_monitor.check_all_pools.return_value = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[pool],
            issues=[issue],
            overall_severity=Severity.WARNING,
        )
        mock_state_manager.should_alert.return_value = False
        daemon._run_check_cycle()

        mock_monitor.check_all_pools.return_value = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[pool],
            issues=[],
            overall_severity=Severity.OK,
        )
        daemon._run_check_cycle()

        mock_state_manager.clear_issue.assert_called_with("rpool", "capacity")


@pytest.mark.posix_only
class TestSignalHandling:
    """On POSIX systems, daemon handles SIGTERM/SIGINT for graceful shutdown."""

    def test_setup_registers_sigterm_handler(self, daemon: ZPoolDaemon) -> None:
        """When setting up signal handlers on POSIX,
        SIGTERM handler is registered."""
        original_sigterm = signal.getsignal(signal.SIGTERM)

        daemon._setup_signal_handlers()

        new_sigterm = signal.getsignal(signal.SIGTERM)
        assert new_sigterm != original_sigterm

    def test_setup_registers_sigint_handler(self, daemon: ZPoolDaemon) -> None:
        """When setting up signal handlers on POSIX,
        SIGINT handler is registered."""
        original_sigint = signal.getsignal(signal.SIGINT)

        daemon._setup_signal_handlers()

        new_sigint = signal.getsignal(signal.SIGINT)
        assert new_sigint != original_sigint


@pytest.mark.os_agnostic
class TestDaemonStopBehavior:
    """When daemon stop() is called, shutdown proceeds correctly."""

    def test_stop_sets_shutdown_event(self, daemon: ZPoolDaemon) -> None:
        """When stop() is called,
        the shutdown event is set."""
        daemon.running = True

        daemon.stop()

        assert daemon.shutdown_event.is_set()

    def test_stop_sets_running_flag_to_false(self, daemon: ZPoolDaemon) -> None:
        """When stop() is called,
        the running flag becomes False."""
        daemon.running = True

        daemon.stop()

        assert daemon.running is False

    def test_stop_is_idempotent(self, daemon: ZPoolDaemon) -> None:
        """When stop() is called multiple times,
        it completes safely without errors."""
        daemon.running = True

        daemon.stop()
        daemon.stop()  # Second call should be harmless

        assert daemon.shutdown_event.is_set()


@pytest.mark.os_agnostic
class TestDaemonLoop:
    """When daemon runs its monitoring loop, it executes periodic checks."""

    def test_loop_executes_at_least_one_check_cycle(self, daemon: ZPoolDaemon, mock_monitor: Mock) -> None:
        """When monitoring loop runs,
        at least one check cycle executes."""

        def run_loop():
            daemon._run_monitoring_loop()

        thread = threading.Thread(target=run_loop, daemon=True)
        thread.start()

        # Give it time to run at least one cycle
        import time

        time.sleep(1.5)  # Sleep longer than check interval (1 second)
        daemon.stop()
        thread.join(timeout=2.0)

        assert mock_monitor.check_all_pools.call_count >= 1

    def test_loop_continues_after_transient_errors(self, daemon: ZPoolDaemon, mock_zfs_client: Mock, pool_list_json: dict) -> None:
        """When a check cycle encounters an error,
        the loop continues and retries successfully."""
        call_count = 0

        def failing_then_succeeding_get_pool_list():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Temporary error")
            return pool_list_json

        mock_zfs_client.get_pool_list.side_effect = failing_then_succeeding_get_pool_list

        def run_loop():
            daemon._run_monitoring_loop()

        thread = threading.Thread(target=run_loop, daemon=True)
        thread.start()

        daemon.shutdown_event.wait(timeout=1.0)
        daemon.stop()
        thread.join(timeout=1.0)

        # Should have called multiple times despite first failure
        assert call_count >= 2
