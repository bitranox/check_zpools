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
def mock_zfs_client() -> Mock:
    """Create mock ZFS client."""
    client = Mock()
    client.get_pool_list.return_value = {"pools": []}
    client.get_pool_status.return_value = {"pools": []}
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

    @patch("check_zpools.daemon.ZFSParser")
    def test_run_check_cycle_parses_pool_data(self, mock_parser_class: Mock, daemon: ZPoolDaemon) -> None:
        """Check cycle should parse ZFS data."""
        mock_parser = Mock()
        mock_parser_class.return_value = mock_parser

        # Create a minimal pool to avoid "No pools found" warning
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

        mock_parser.parse_pool_list.return_value = {"rpool": pool}
        mock_parser.parse_pool_status.return_value = {"rpool": pool}
        mock_parser.merge_pool_data.return_value = {"rpool": pool}

        daemon._run_check_cycle()

        mock_parser.parse_pool_list.assert_called_once()
        mock_parser.parse_pool_status.assert_called_once()
        mock_parser.merge_pool_data.assert_called_once()

    @patch("check_zpools.daemon.ZFSParser")
    def test_run_check_cycle_monitors_pools(self, mock_parser_class: Mock, daemon: ZPoolDaemon, mock_monitor: Mock) -> None:
        """Check cycle should run monitor on parsed pools."""
        mock_parser = Mock()
        mock_parser_class.return_value = mock_parser

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

        mock_parser.parse_pool_list.return_value = {"rpool": pool}
        mock_parser.parse_pool_status.return_value = {"rpool": pool}
        mock_parser.merge_pool_data.return_value = {"rpool": pool}

        daemon._run_check_cycle()

        mock_monitor.check_all_pools.assert_called_once()

    @patch("check_zpools.daemon.ZFSParser")
    def test_run_check_cycle_handles_zfs_fetch_error(self, mock_parser_class: Mock, daemon: ZPoolDaemon, mock_zfs_client: Mock) -> None:
        """Check cycle should handle ZFS command failures gracefully."""
        mock_zfs_client.get_pool_list.side_effect = RuntimeError("ZFS error")

        # Should not raise - error logged
        daemon._run_check_cycle()

    @patch("check_zpools.daemon.ZFSParser")
    def test_run_check_cycle_handles_parse_error(self, mock_parser_class: Mock, daemon: ZPoolDaemon) -> None:
        """Check cycle should handle parse errors gracefully."""
        mock_parser = Mock()
        mock_parser_class.return_value = mock_parser
        mock_parser.parse_pool_list.side_effect = ValueError("Parse error")

        # Should not raise - error logged
        daemon._run_check_cycle()


class TestAlertHandling:
    """Test alert management during check cycles."""

    @patch("check_zpools.daemon.ZFSParser")
    def test_handle_check_result_sends_alerts_for_new_issues(
        self,
        mock_parser_class: Mock,
        daemon: ZPoolDaemon,
        mock_alerter: Mock,
        mock_state_manager: Mock,
        mock_monitor: Mock,
    ) -> None:
        """New issues should trigger alerts."""
        # Setup parser
        mock_parser = Mock()
        mock_parser_class.return_value = mock_parser

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

        mock_parser.parse_pool_list.return_value = {"rpool": pool}
        mock_parser.parse_pool_status.return_value = {"rpool": pool}
        mock_parser.merge_pool_data.return_value = {"rpool": pool}

        mock_monitor.check_all_pools.return_value = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[pool],
            issues=[issue],
            overall_severity=Severity.WARNING,
        )

        mock_state_manager.should_alert.return_value = True

        daemon._run_check_cycle()

        mock_alerter.send_alert.assert_called_once_with(issue, pool)
        mock_state_manager.record_alert.assert_called_once_with(issue)

    @patch("check_zpools.daemon.ZFSParser")
    def test_handle_check_result_suppresses_duplicate_alerts(
        self,
        mock_parser_class: Mock,
        daemon: ZPoolDaemon,
        mock_alerter: Mock,
        mock_state_manager: Mock,
        mock_monitor: Mock,
    ) -> None:
        """Duplicate alerts should be suppressed."""
        mock_parser = Mock()
        mock_parser_class.return_value = mock_parser

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

        mock_parser.parse_pool_list.return_value = {"rpool": pool}
        mock_parser.parse_pool_status.return_value = {"rpool": pool}
        mock_parser.merge_pool_data.return_value = {"rpool": pool}

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

        mock_state_manager.should_alert.return_value = False

        daemon._run_check_cycle()

        mock_alerter.send_alert.assert_not_called()

    @patch("check_zpools.daemon.ZFSParser")
    def test_handle_check_result_skips_ok_severity(
        self,
        mock_parser_class: Mock,
        daemon: ZPoolDaemon,
        mock_alerter: Mock,
        mock_monitor: Mock,
    ) -> None:
        """OK severity should not trigger alerts by default."""
        mock_parser = Mock()
        mock_parser_class.return_value = mock_parser

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

        mock_parser.parse_pool_list.return_value = {"rpool": pool}
        mock_parser.parse_pool_status.return_value = {"rpool": pool}
        mock_parser.merge_pool_data.return_value = {"rpool": pool}

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

    @patch("check_zpools.daemon.ZFSParser")
    def test_detect_recoveries_sends_notification(
        self,
        mock_parser_class: Mock,
        daemon: ZPoolDaemon,
        mock_alerter: Mock,
        mock_state_manager: Mock,
        mock_monitor: Mock,
    ) -> None:
        """Resolved issues should trigger recovery notification."""
        mock_parser = Mock()
        mock_parser_class.return_value = mock_parser

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

        mock_parser.parse_pool_list.return_value = {"rpool": pool}
        mock_parser.parse_pool_status.return_value = {"rpool": pool}
        mock_parser.merge_pool_data.return_value = {"rpool": pool}

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

        # Should send recovery notification
        mock_alerter.send_recovery.assert_called_with("rpool", "capacity")
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

    @patch("check_zpools.daemon.ZFSParser")
    def test_monitoring_loop_executes_check_cycles(self, mock_parser_class: Mock, daemon: ZPoolDaemon, mock_monitor: Mock) -> None:
        """Monitoring loop should execute check cycles."""
        mock_parser = Mock()
        mock_parser_class.return_value = mock_parser

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

        mock_parser.parse_pool_list.return_value = {"rpool": pool}
        mock_parser.parse_pool_status.return_value = {"rpool": pool}
        mock_parser.merge_pool_data.return_value = {"rpool": pool}

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

    @patch("check_zpools.daemon.ZFSParser")
    def test_monitoring_loop_recovers_from_errors(self, mock_parser_class: Mock, daemon: ZPoolDaemon, mock_zfs_client: Mock) -> None:
        """Monitoring loop should continue after errors."""
        call_count = 0

        def failing_get_pool_list():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Temporary error")
            return {"pools": []}

        mock_zfs_client.get_pool_list.side_effect = failing_get_pool_list

        mock_parser = Mock()
        mock_parser_class.return_value = mock_parser
        mock_parser.parse_pool_list.return_value = {}
        mock_parser.parse_pool_status.return_value = {}
        mock_parser.merge_pool_data.return_value = {}

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
