"""Tests for daemon monitoring loop.

Tests cover:
- Check cycle execution
- Signal handling (SIGTERM/SIGINT)
- Error recovery
- Alert management integration
- State persistence
"""

from __future__ import annotations

import signal
import threading
from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pytest

from check_zpools.daemon import ZPoolDaemon
from check_zpools.models import CheckResult, PoolHealth, PoolIssue, PoolStatus, Severity


@pytest.fixture
def healthy_pool_json() -> dict:
    """Realistic JSON for a healthy pool (from zpool status -j)."""
    return {
        "output_version": {
            "command": "zpool status",
            "vers_major": 0,
            "vers_minor": 1
        },
        "pools": {
            "rpool": {
                "name": "rpool",
                "type": "POOL",
                "state": "ONLINE",
                "pool_guid": "17068583395379267683",
                "txg": "2888298",
                "spa_version": "5000",
                "zpl_version": "5",
                "vdev_tree": {
                    "type": "root",
                    "stats": {
                        "read_errors": 0,
                        "write_errors": 0,
                        "checksum_errors": 0
                    }
                },
                "scan": {
                    "state": "finished",
                    "start_time": int(datetime.now(UTC).timestamp()) - 86400,  # 1 day ago
                    "end_time": int(datetime.now(UTC).timestamp()) - 86400,
                    "errors": 0,
                }
            }
        }
    }


@pytest.fixture
def degraded_pool_json() -> dict:
    """Realistic JSON for a degraded pool (from zpool status -j)."""
    return {
        "output_version": {
            "command": "zpool status",
            "vers_major": 0,
            "vers_minor": 1
        },
        "pools": {
            "rpool": {
                "name": "rpool",
                "type": "POOL",
                "state": "DEGRADED",
                "pool_guid": "17068583395379267683",
                "txg": "2966143",
                "spa_version": "5000",
                "zpl_version": "5",
                "vdev_tree": {
                    "type": "root",
                    "stats": {
                        "read_errors": 5,
                        "write_errors": 2,
                        "checksum_errors": 1
                    }
                },
                "scan": {
                    "state": "finished",
                    "start_time": int(datetime.now(UTC).timestamp()) - 86400,
                    "end_time": int(datetime.now(UTC).timestamp()) - 86400,
                    "errors": 3,
                }
            }
        }
    }


@pytest.fixture
def pool_list_json() -> dict:
    """Realistic JSON from zpool list -j command."""
    return {
        "output_version": {
            "command": "zpool list",
            "vers_major": 0,
            "vers_minor": 1
        },
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
                    "health": {
                        "value": "ONLINE"
                    },
                    "size": {
                        "value": str(1024**4)  # 1 TB
                    },
                    "allocated": {
                        "value": str(int(0.5 * 1024**4))  # 50% used
                    },
                    "free": {
                        "value": str(int(0.5 * 1024**4))
                    },
                    "capacity": {
                        "value": "50"
                    }
                }
            }
        }
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


class TestDaemonInitialization:
    """Test daemon initialization."""

    def test_daemon_initializes_with_config(
        self,
        mock_zfs_client: Mock,
        mock_monitor: Mock,
        mock_alerter: Mock,
        mock_state_manager: Mock,
        daemon_config: dict,
    ) -> None:
        """Daemon should initialize with provided components."""
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
        assert daemon.check_interval == 1

    def test_daemon_uses_default_interval(
        self,
        mock_zfs_client: Mock,
        mock_monitor: Mock,
        mock_alerter: Mock,
        mock_state_manager: Mock,
    ) -> None:
        """Daemon should use default interval if not specified."""
        daemon = ZPoolDaemon(
            zfs_client=mock_zfs_client,
            monitor=mock_monitor,
            alerter=mock_alerter,
            state_manager=mock_state_manager,
            config={},
        )

        assert daemon.check_interval == 300  # 5 minutes default


class TestCheckCycle:
    """Test single check cycle execution."""

    def test_run_check_cycle_fetches_zfs_data(self, daemon: ZPoolDaemon, mock_zfs_client: Mock) -> None:
        """Check cycle should fetch pool list and status."""
        daemon._run_check_cycle()

        mock_zfs_client.get_pool_list.assert_called_once()
        mock_zfs_client.get_pool_status.assert_called_once()

    def test_run_check_cycle_parses_pool_data(self, daemon: ZPoolDaemon, mock_monitor: Mock) -> None:
        """Check cycle should parse ZFS data and call monitor."""
        # Real parser will parse the JSON from mock_zfs_client
        daemon._run_check_cycle()

        # Verify monitor was called with parsed pool data
        mock_monitor.check_all_pools.assert_called_once()
        # Verify pool data was passed (dict with pool names as keys)
        call_args = mock_monitor.check_all_pools.call_args[0][0]
        assert isinstance(call_args, dict)
        assert len(call_args) > 0

    def test_run_check_cycle_monitors_pools(self, daemon: ZPoolDaemon, mock_monitor: Mock) -> None:
        """Check cycle should run monitor on parsed pools."""
        daemon._run_check_cycle()

        # Verify monitor was called
        mock_monitor.check_all_pools.assert_called_once()

        # Verify it was called with pool dict
        call_args = mock_monitor.check_all_pools.call_args[0][0]
        assert isinstance(call_args, dict)
        assert "rpool" in call_args

    def test_run_check_cycle_handles_zfs_fetch_error(self, daemon: ZPoolDaemon, mock_zfs_client: Mock) -> None:
        """Check cycle should handle ZFS command failures gracefully."""
        mock_zfs_client.get_pool_list.side_effect = RuntimeError("ZFS error")

        # Should not raise - error logged
        daemon._run_check_cycle()

    def test_run_check_cycle_handles_parse_error(self, daemon: ZPoolDaemon, mock_zfs_client: Mock) -> None:
        """Check cycle should handle parse errors gracefully."""
        # Return invalid JSON that will cause parse error
        mock_zfs_client.get_pool_list.return_value = {"invalid": "data"}

        # Should not raise - error logged
        daemon._run_check_cycle()


class TestAlertHandling:
    """Test alert management during check cycles."""

    def test_handle_check_result_sends_alerts_for_new_issues(
        self,
        daemon: ZPoolDaemon,
        mock_alerter: Mock,
        mock_state_manager: Mock,
        mock_monitor: Mock,
    ) -> None:
        """New issues should trigger alerts."""
        # Create pool status (parser will create this from JSON)
        pool = PoolStatus(
            name="rpool",
            health=PoolHealth.ONLINE,
            capacity_percent=85.0,
            size_bytes=1024**4,
            allocated_bytes=int(0.85 * 1024**4),
            free_bytes=int(0.15 * 1024**4),
            read_errors=0,
            write_errors=0,
            checksum_errors=0,
            last_scrub=datetime.now(UTC),
            scrub_errors=0,
            scrub_in_progress=False,
        )

        issue = PoolIssue(
            pool_name="rpool",
            severity=Severity.WARNING,
            category="capacity",
            message="High capacity",
            details={},
        )

        # Mock monitor to return result with issues
        mock_monitor.check_all_pools.return_value = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[pool],
            issues=[issue],
            overall_severity=Severity.WARNING,
        )

        mock_state_manager.should_alert.return_value = True

        daemon._run_check_cycle()

        # Verify alert was sent
        assert mock_alerter.send_alert.call_count == 1
        # Get the actual call args
        call_args = mock_alerter.send_alert.call_args[0]
        assert call_args[0] == issue
        assert call_args[1].name == "rpool"
        mock_state_manager.record_alert.assert_called_once_with(issue)

    def test_handle_check_result_suppresses_duplicate_alerts(
        self,
        daemon: ZPoolDaemon,
        mock_alerter: Mock,
        mock_state_manager: Mock,
        mock_monitor: Mock,
    ) -> None:
        """Duplicate alerts should be suppressed."""
        pool = PoolStatus(
            name="rpool",
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

        issue = PoolIssue(
            pool_name="rpool",
            severity=Severity.WARNING,
            category="capacity",
            message="High capacity",
            details={},
        )

        mock_monitor.check_all_pools.return_value = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[pool],
            issues=[issue],
            overall_severity=Severity.WARNING,
        )

        # State manager says don't alert (duplicate)
        mock_state_manager.should_alert.return_value = False

        daemon._run_check_cycle()

        # Alert should not be sent
        mock_alerter.send_alert.assert_not_called()

    def test_handle_check_result_skips_ok_severity(
        self,
        daemon: ZPoolDaemon,
        mock_alerter: Mock,
        mock_monitor: Mock,
    ) -> None:
        """OK severity should not trigger alerts by default."""
        pool = PoolStatus(
            name="rpool",
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


class TestRecoveryDetection:
    """Test recovery detection across check cycles."""

    def test_detect_recoveries_sends_notification(
        self,
        daemon: ZPoolDaemon,
        mock_alerter: Mock,
        mock_state_manager: Mock,
        mock_monitor: Mock,
    ) -> None:
        """Resolved issues should trigger recovery notification."""
        pool = PoolStatus(
            name="rpool",
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

        # First cycle: issue present
        issue = PoolIssue(
            pool_name="rpool",
            severity=Severity.WARNING,
            category="capacity",
            message="High capacity",
            details={},
        )

        mock_monitor.check_all_pools.return_value = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[pool],
            issues=[issue],
            overall_severity=Severity.WARNING,
        )

        # Skip alert to track issue
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

        # Should send recovery notification with pool status
        mock_alerter.send_recovery.assert_called_once()
        call_args = mock_alerter.send_recovery.call_args
        assert call_args[0][0] == "rpool"  # pool_name
        assert call_args[0][1] == "capacity"  # category
        assert call_args[0][2].name == "rpool"  # pool status
        mock_state_manager.clear_issue.assert_called_with("rpool", "capacity")


class TestSignalHandling:
    """Test graceful shutdown via signals."""

    def test_setup_signal_handlers_registers_handlers(self, daemon: ZPoolDaemon) -> None:
        """Signal handlers should be registered."""
        original_sigterm = signal.getsignal(signal.SIGTERM)
        original_sigint = signal.getsignal(signal.SIGINT)

        daemon._setup_signal_handlers()

        new_sigterm = signal.getsignal(signal.SIGTERM)
        new_sigint = signal.getsignal(signal.SIGINT)

        assert new_sigterm != original_sigterm
        assert new_sigint != original_sigint

    def test_stop_sets_shutdown_event(self, daemon: ZPoolDaemon) -> None:
        """Stop should set shutdown event."""
        daemon.running = True

        daemon.stop()

        assert daemon.shutdown_event.is_set()
        assert daemon.running is False

    def test_stop_is_idempotent(self, daemon: ZPoolDaemon) -> None:
        """Calling stop multiple times should be safe."""
        daemon.running = True

        daemon.stop()
        daemon.stop()  # Second call should be harmless

        assert daemon.shutdown_event.is_set()


class TestDaemonLoop:
    """Test daemon monitoring loop."""

    def test_monitoring_loop_executes_check_cycles(self, daemon: ZPoolDaemon, mock_monitor: Mock) -> None:
        """Monitoring loop should execute check cycles."""
        # Run loop in thread and stop after short time
        def run_loop():
            daemon._run_monitoring_loop()

        thread = threading.Thread(target=run_loop, daemon=True)
        thread.start()

        # Give it time to run at least one cycle
        import time

        time.sleep(1.5)  # Sleep longer than check interval
        daemon.stop()
        thread.join(timeout=2.0)

        # Should have run at least once
        assert mock_monitor.check_all_pools.call_count >= 1

    def test_monitoring_loop_recovers_from_errors(self, daemon: ZPoolDaemon, mock_zfs_client: Mock, pool_list_json: dict) -> None:
        """Monitoring loop should continue after errors."""
        call_count = 0

        def failing_get_pool_list():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Temporary error")
            return pool_list_json  # Return valid JSON on second call

        mock_zfs_client.get_pool_list.side_effect = failing_get_pool_list

        # Run loop
        def run_loop():
            daemon._run_monitoring_loop()

        thread = threading.Thread(target=run_loop, daemon=True)
        thread.start()

        daemon.shutdown_event.wait(timeout=1.0)
        daemon.stop()
        thread.join(timeout=1.0)

        # Should have called multiple times despite first failure
        assert call_count >= 2
