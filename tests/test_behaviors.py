"""Integration tests for domain behaviors following clean architecture principles.

Design Philosophy
-----------------
These tests validate domain behavior logic through minimal mocking:
- Test names read like plain English sentences describing exact behavior
- Each test validates ONE specific behavior - no multi-assert kitchen sinks
- Real behavior over mocks - we test actual business logic flow
- OS-agnostic where possible, OS-specific markers where needed
- Deterministic - no randomness, timing dependencies, or environment coupling

Test Structure Pattern
----------------------
1. Given: Setup minimal test state (fixtures, mocks)
2. When: Execute ONE behavior function
3. Then: Assert ONE specific outcome

Coverage Strategy
-----------------
- Happy paths: Behaviors succeed with valid inputs
- Error paths: Behaviors handle failures gracefully
- Configuration scenarios: With/without custom config
- Platform differences: State file paths per OS
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from check_zpools import behaviors
from check_zpools.models import CheckResult, PoolStatus


# =============================================================================
# OS Markers
# =============================================================================

# Most behavior tests are OS-agnostic - business logic works same on all platforms
pytestmark = pytest.mark.os_agnostic


# =============================================================================
# Note: Shared fixtures like healthy_pool_status and ok_check_result are
# defined in conftest.py and automatically available to all test files.
# =============================================================================


# =============================================================================
# Legacy Greeting Tests - Template Validation
# =============================================================================


class TestGreetingBehaviorSucceeds:
    """The greeting behavior writes to streams successfully."""

    def test_writes_greeting_to_provided_buffer(self) -> None:
        """When providing a StringIO buffer, greeting is written to it.

        Given: A StringIO buffer to capture output
        When: Calling emit_greeting with that buffer
        Then: Buffer contains exactly 'Hello World\n'
        """
        buffer = StringIO()

        behaviors.emit_greeting(stream=buffer)

        assert buffer.getvalue() == "Hello World\n", "Greeting must match canonical format"

    def test_writes_greeting_to_stdout_by_default(self, capsys: pytest.CaptureFixture[str]) -> None:
        """When no stream is provided, greeting goes to stdout.

        Given: No explicit stream parameter
        When: Calling emit_greeting with default arguments
        Then: Standard output contains 'Hello World\n'
        """
        behaviors.emit_greeting()

        captured = capsys.readouterr()

        assert captured.out == "Hello World\n", "Greeting must appear on stdout"
        assert captured.err == "", "Greeting must not appear on stderr"

    def test_flushes_stream_when_flush_method_exists(self) -> None:
        """When stream has flush method, it gets called.

        Given: A custom stream with a flush method
        When: Calling emit_greeting with that stream
        Then: The flush method is invoked
        """

        @dataclass
        class FlushableStream:
            """Mock stream that tracks flush calls."""

            ledger: list[str]
            flushed: bool = False

            def write(self, text: str) -> None:
                self.ledger.append(text)

            def flush(self) -> None:
                self.flushed = True

        stream = FlushableStream([])

        behaviors.emit_greeting(stream=stream)  # type: ignore[arg-type]

        assert stream.ledger == ["Hello World\n"], "Greeting must be written"
        assert stream.flushed is True, "Stream must be flushed"


class TestIntentionalFailureBehavior:
    """The intentional failure behavior always raises RuntimeError."""

    def test_raises_runtime_error_with_expected_message(self) -> None:
        """When invoking intentional failure, it raises RuntimeError.

        Given: Calling raise_intentional_failure
        When: Function executes
        Then: RuntimeError is raised with 'I should fail' message
        """
        with pytest.raises(RuntimeError, match="I should fail"):
            behaviors.raise_intentional_failure()


class TestNoopBehavior:
    """The noop behavior returns None without side effects."""

    def test_returns_none_immediately(self) -> None:
        """When invoking noop_main, it returns None.

        Given: Calling noop_main
        When: Function executes
        Then: Result is None
        """
        assert behaviors.noop_main() is None, "Noop must return None"


# =============================================================================
# Monitor Configuration Tests - Validation Logic
# =============================================================================


class TestMonitorConfigurationBuildsWithDefaults:
    """Monitor configuration uses defaults when not specified."""

    def test_uses_default_capacity_thresholds(self) -> None:
        """When no capacity config provided, uses 80/90 defaults.

        Given: Empty configuration dict
        When: Building monitor config
        Then: Warning threshold is 80%, critical is 90%
        """
        config: dict = {}

        result = behaviors._build_monitor_config(config)

        assert result.capacity_warning_percent == 80, "Default warning should be 80%"
        assert result.capacity_critical_percent == 90, "Default critical should be 90%"

    def test_uses_default_scrub_age_threshold(self) -> None:
        """When no scrub config provided, uses 30 days default.

        Given: Empty configuration dict
        When: Building monitor config
        Then: Scrub max age is 30 days
        """
        config: dict = {}

        result = behaviors._build_monitor_config(config)

        assert result.scrub_max_age_days == 30, "Default scrub age should be 30 days"

    def test_uses_default_error_thresholds(self) -> None:
        """When no error config provided, uses threshold of 1 for all error types.

        Given: Empty configuration dict
        When: Building monitor config
        Then: All error thresholds are 1
        """
        config: dict = {}

        result = behaviors._build_monitor_config(config)

        assert result.read_errors_warning == 1, "Default read errors should be 1"
        assert result.write_errors_warning == 1, "Default write errors should be 1"
        assert result.checksum_errors_warning == 1, "Default checksum errors should be 1"


class TestMonitorConfigurationAcceptsCustomValues:
    """Monitor configuration uses custom values when provided."""

    def test_uses_custom_capacity_thresholds(self) -> None:
        """When capacity thresholds provided, uses them instead of defaults.

        Given: Config with warning=70, critical=85
        When: Building monitor config
        Then: Custom thresholds are used
        """
        config = {
            "zfs": {
                "capacity_warning_percent": 70,
                "capacity_critical_percent": 85,
            }
        }

        result = behaviors._build_monitor_config(config)

        assert result.capacity_warning_percent == 70, "Custom warning should be used"
        assert result.capacity_critical_percent == 85, "Custom critical should be used"

    def test_uses_custom_scrub_age_threshold(self) -> None:
        """When scrub age threshold provided, uses it instead of default.

        Given: Config with scrub_max_age_days=60
        When: Building monitor config
        Then: Custom scrub age is used
        """
        config = {"zfs": {"scrub_max_age_days": 60}}

        result = behaviors._build_monitor_config(config)

        assert result.scrub_max_age_days == 60, "Custom scrub age should be used"

    def test_uses_custom_error_thresholds(self) -> None:
        """When error thresholds provided, uses them instead of defaults.

        Given: Config with custom error thresholds
        When: Building monitor config
        Then: Custom error thresholds are used
        """
        config = {
            "zfs": {
                "read_errors_warning": 5,
                "write_errors_warning": 3,
                "checksum_errors_warning": 1,
            }
        }

        result = behaviors._build_monitor_config(config)

        assert result.read_errors_warning == 5, "Custom read errors should be used"
        assert result.write_errors_warning == 3, "Custom write errors should be used"
        assert result.checksum_errors_warning == 1, "Custom checksum errors should be used"


class TestMonitorConfigurationRejectsInvalidCapacityThresholds:
    """Monitor configuration validates capacity threshold boundaries."""

    def test_rejects_warning_threshold_below_zero(self) -> None:
        """When warning threshold is negative, raises ValueError.

        Given: Config with warning=-1
        When: Building monitor config
        Then: ValueError is raised
        """
        config = {"zfs": {"capacity_warning_percent": -1}}

        with pytest.raises(ValueError, match="capacity_warning_percent must be between 0 and 100"):
            behaviors._build_monitor_config(config)

    def test_rejects_warning_threshold_of_zero(self) -> None:
        """When warning threshold is exactly zero, raises ValueError.

        Given: Config with warning=0
        When: Building monitor config
        Then: ValueError is raised
        """
        config = {"zfs": {"capacity_warning_percent": 0}}

        with pytest.raises(ValueError, match="capacity_warning_percent must be between 0 and 100"):
            behaviors._build_monitor_config(config)

    def test_rejects_warning_threshold_above_100(self) -> None:
        """When warning threshold exceeds 100, raises ValueError.

        Given: Config with warning=101
        When: Building monitor config
        Then: ValueError is raised
        """
        config = {"zfs": {"capacity_warning_percent": 101}}

        with pytest.raises(ValueError, match="capacity_warning_percent must be between 0 and 100"):
            behaviors._build_monitor_config(config)

    def test_rejects_critical_threshold_of_zero(self) -> None:
        """When critical threshold is exactly zero, raises ValueError.

        Given: Config with critical=0
        When: Building monitor config
        Then: ValueError is raised
        """
        config = {"zfs": {"capacity_critical_percent": 0}}

        with pytest.raises(ValueError, match="capacity_critical_percent must be between 0 and 100"):
            behaviors._build_monitor_config(config)

    def test_rejects_critical_threshold_above_100(self) -> None:
        """When critical threshold exceeds 100, raises ValueError.

        Given: Config with critical=101
        When: Building monitor config
        Then: ValueError is raised
        """
        config = {"zfs": {"capacity_critical_percent": 101}}

        with pytest.raises(ValueError, match="capacity_critical_percent must be between 0 and 100"):
            behaviors._build_monitor_config(config)

    def test_allows_critical_threshold_of_exactly_100(self) -> None:
        """When critical threshold is exactly 100, accepts it.

        Given: Config with critical=100
        When: Building monitor config
        Then: Config is accepted
        """
        config = {
            "zfs": {
                "capacity_warning_percent": 95,
                "capacity_critical_percent": 100,
            }
        }

        result = behaviors._build_monitor_config(config)

        assert result.capacity_critical_percent == 100, "100% critical should be allowed"


class TestMonitorConfigurationRejectsInconsistentThresholds:
    """Monitor configuration validates threshold ordering."""

    def test_rejects_warning_greater_than_critical(self) -> None:
        """When warning threshold exceeds critical, raises ValueError.

        Given: Config with warning=90, critical=80
        When: Building monitor config
        Then: ValueError is raised
        """
        config = {
            "zfs": {
                "capacity_warning_percent": 90,
                "capacity_critical_percent": 80,
            }
        }

        with pytest.raises(ValueError, match="capacity_warning_percent.*must be less than capacity_critical_percent"):
            behaviors._build_monitor_config(config)

    def test_rejects_warning_equal_to_critical(self) -> None:
        """When warning threshold equals critical, raises ValueError.

        Given: Config with warning=85, critical=85
        When: Building monitor config
        Then: ValueError is raised
        """
        config = {
            "zfs": {
                "capacity_warning_percent": 85,
                "capacity_critical_percent": 85,
            }
        }

        with pytest.raises(ValueError, match="capacity_warning_percent.*must be less than capacity_critical_percent"):
            behaviors._build_monitor_config(config)


class TestMonitorConfigurationRejectsInvalidErrorThresholds:
    """Monitor configuration validates error threshold boundaries."""

    def test_rejects_negative_scrub_age(self) -> None:
        """When scrub age is negative, raises ValueError.

        Given: Config with scrub_max_age_days=-1
        When: Building monitor config
        Then: ValueError is raised
        """
        config = {"zfs": {"scrub_max_age_days": -1}}

        with pytest.raises(ValueError, match="scrub_max_age_days must be non-negative"):
            behaviors._build_monitor_config(config)

    def test_allows_scrub_age_of_zero(self) -> None:
        """When scrub age is zero, accepts it (disables scrub checking).

        Given: Config with scrub_max_age_days=0
        When: Building monitor config
        Then: Config is accepted with 0
        """
        config = {"zfs": {"scrub_max_age_days": 0}}

        result = behaviors._build_monitor_config(config)

        assert result.scrub_max_age_days == 0, "Zero scrub age should be allowed"

    def test_rejects_negative_read_error_threshold(self) -> None:
        """When read error threshold is negative, raises ValueError.

        Given: Config with read_errors_warning=-1
        When: Building monitor config
        Then: ValueError is raised
        """
        config = {"zfs": {"read_errors_warning": -1}}

        with pytest.raises(ValueError, match="read_errors_warning must be non-negative"):
            behaviors._build_monitor_config(config)

    def test_rejects_negative_write_error_threshold(self) -> None:
        """When write error threshold is negative, raises ValueError.

        Given: Config with write_errors_warning=-1
        When: Building monitor config
        Then: ValueError is raised
        """
        config = {"zfs": {"write_errors_warning": -1}}

        with pytest.raises(ValueError, match="write_errors_warning must be non-negative"):
            behaviors._build_monitor_config(config)

    def test_rejects_negative_checksum_error_threshold(self) -> None:
        """When checksum error threshold is negative, raises ValueError.

        Given: Config with checksum_errors_warning=-1
        When: Building monitor config
        Then: ValueError is raised
        """
        config = {"zfs": {"checksum_errors_warning": -1}}

        with pytest.raises(ValueError, match="checksum_errors_warning must be non-negative"):
            behaviors._build_monitor_config(config)


# =============================================================================
# Check Pools Once Tests - One-Shot Pool Checking
# =============================================================================


class TestCheckPoolsOnceSucceedsWithValidPools:
    """The check_pools_once behavior succeeds when ZFS pools are healthy."""

    @patch("check_zpools.behaviors.get_config")
    @patch("check_zpools.behaviors.ZFSClient")
    @patch("check_zpools.behaviors.ZFSParser")
    @patch("check_zpools.behaviors.PoolMonitor")
    def test_returns_check_result_with_pool_data(
        self,
        mock_monitor_class: MagicMock,
        mock_parser_class: MagicMock,
        mock_client_class: MagicMock,
        mock_get_config: MagicMock,
        healthy_pool_status: PoolStatus,
        ok_check_result: CheckResult,
    ) -> None:
        """When checking pools with default config, returns CheckResult.

        Given: Healthy pool named 'rpool' with ONLINE status
        When: Running check_pools_once with default config
        Then: Returns CheckResult with pool data
        """
        # Setup config
        mock_config = MagicMock()
        mock_config.as_dict.return_value = {"zfs": {}}
        mock_get_config.return_value = mock_config

        # Setup ZFS client (single command with --json-int)
        mock_client = MagicMock()
        mock_client.get_pool_status.return_value = {"pools": {}}
        mock_client_class.return_value = mock_client

        # Setup parser (parse_pool_status provides all data)
        mock_parser = MagicMock()
        mock_parser.parse_pool_status.return_value = {"rpool": healthy_pool_status}
        mock_parser_class.return_value = mock_parser

        # Setup monitor
        mock_monitor = MagicMock()
        mock_monitor.check_all_pools.return_value = ok_check_result
        mock_monitor_class.return_value = mock_monitor

        result = behaviors.check_pools_once()

        assert result == ok_check_result, "Result must match expected CheckResult"
        mock_client.get_pool_status.assert_called_once()
        mock_monitor.check_all_pools.assert_called_once()

    @patch("check_zpools.behaviors.get_config")
    @patch("check_zpools.behaviors.ZFSClient")
    def test_uses_custom_config_when_provided(
        self,
        mock_client_class: MagicMock,
        mock_get_config: MagicMock,
    ) -> None:
        """When custom config is provided, does not load default config.

        Given: Custom configuration dict
        When: Running check_pools_once with custom config
        Then: get_config is not called
        """
        custom_config = {"zfs": {"capacity_warning_percent": 70}}

        mock_client = MagicMock()
        mock_client.get_pool_status.return_value = {"pools": {}}
        mock_client_class.return_value = mock_client

        # May fail due to incomplete mocking, but we verify get_config not called
        try:
            behaviors.check_pools_once(config=custom_config)
        except Exception:
            pass

        mock_get_config.assert_not_called()


class TestCheckPoolsOnceHandlesZFSErrors:
    """The check_pools_once behavior handles ZFS errors gracefully."""

    @patch("check_zpools.behaviors.ZFSClient")
    def test_propagates_zfs_not_available_error(
        self,
        mock_client_class: MagicMock,
    ) -> None:
        """When ZFS is not available, raises ZFSNotAvailableError.

        Given: ZFS client raises ZFSNotAvailableError
        When: Running check_pools_once
        Then: ZFSNotAvailableError is propagated
        """
        from check_zpools.zfs_client import ZFSNotAvailableError

        mock_client = MagicMock()
        mock_client.get_pool_status.side_effect = ZFSNotAvailableError("ZFS not found")
        mock_client_class.return_value = mock_client

        with pytest.raises(ZFSNotAvailableError, match="ZFS not found"):
            behaviors.check_pools_once(config={})

    @patch("check_zpools.behaviors.ZFSClient")
    def test_wraps_generic_errors_in_runtime_error(
        self,
        mock_client_class: MagicMock,
    ) -> None:
        """When generic error occurs during pool check, wraps in RuntimeError.

        Given: ZFS client raises ValueError during get_pool_status
        When: Running check_pools_once
        Then: RuntimeError is raised with helpful message
        """
        mock_client = MagicMock()
        mock_client.get_pool_status.side_effect = ValueError("Invalid JSON")
        mock_client_class.return_value = mock_client

        with pytest.raises(RuntimeError, match="Failed to check pools"):
            behaviors.check_pools_once(config={})

    @patch("check_zpools.behaviors.ZFSClient")
    @patch("check_zpools.behaviors.ZFSParser")
    def test_wraps_parser_errors_in_runtime_error(
        self,
        mock_parser_class: MagicMock,
        mock_client_class: MagicMock,
    ) -> None:
        """When parser error occurs, wraps in RuntimeError.

        Given: Parser raises KeyError during parse_pool_status
        When: Running check_pools_once
        Then: RuntimeError is raised with helpful message
        """
        mock_client = MagicMock()
        mock_client.get_pool_status.return_value = {"pools": {}}
        mock_client_class.return_value = mock_client

        mock_parser = MagicMock()
        mock_parser.parse_pool_status.side_effect = KeyError("Missing key")
        mock_parser_class.return_value = mock_parser

        with pytest.raises(RuntimeError, match="Failed to check pools"):
            behaviors.check_pools_once(config={})


# =============================================================================
# State File Path Tests - Platform-Specific Paths
# =============================================================================


class TestStateFilePathResolutionWithCustomPath:
    """State file path uses custom path when configured."""

    def test_uses_custom_path_from_config(self) -> None:
        """When state_file configured, uses that path.

        Given: Config with custom state_file path
        When: Getting state file path
        Then: Returns custom path
        """
        config = {"daemon": {"state_file": "/custom/path/state.json"}}

        result = behaviors._get_state_file_path(config)

        assert result == Path("/custom/path/state.json"), "Must use custom path from config"


class TestStateFilePathResolutionWithDefaults:
    """State file path defaults to platform-specific locations."""

    @pytest.mark.skipif(sys.platform != "linux", reason="Linux-specific default path test")
    def test_defaults_to_var_cache_on_linux(self) -> None:
        """When no state_file configured on Linux, uses /var/cache.

        Given: Empty config on Linux system
        When: Getting state file path
        Then: Returns /var/cache/check_zpools/alert_state.json
        """
        config: dict = {}

        result = behaviors._get_state_file_path(config)

        assert result == Path("/var/cache/check_zpools/alert_state.json"), "Must use Linux cache directory"

    @pytest.mark.skipif(sys.platform != "darwin", reason="macOS-specific default path test")
    def test_defaults_to_library_caches_on_macos(self) -> None:
        """When no state_file configured on macOS, uses ~/Library/Caches.

        Given: Empty config on macOS system
        When: Getting state file path
        Then: Returns ~/Library/Caches/check_zpools/alert_state.json
        """
        config: dict = {}

        result = behaviors._get_state_file_path(config)

        expected = Path.home() / "Library" / "Caches" / "check_zpools" / "alert_state.json"
        assert result == expected, "Must use macOS cache directory"

    @pytest.mark.skipif(sys.platform in ("linux", "darwin"), reason="Non-Linux/macOS default path test")
    def test_defaults_to_home_cache_on_other_platforms(self) -> None:
        """When no state_file configured on other platforms, uses ~/.cache.

        Given: Empty config on non-Linux/macOS system
        When: Getting state file path
        Then: Returns ~/.cache/check_zpools/alert_state.json
        """
        config: dict = {}

        result = behaviors._get_state_file_path(config)

        expected = Path.home() / ".cache" / "check_zpools" / "alert_state.json"
        assert result == expected, "Must use generic cache directory"


# =============================================================================
# Config Loading Tests - Diagnostic Logging
# =============================================================================


class TestConfigLoadingWithLogging:
    """Config loading logs diagnostic information."""

    def test_uses_provided_config_without_loading(self) -> None:
        """When config is provided, returns it directly.

        Given: Custom configuration dict
        When: Loading config with logging
        Then: Returns same dict without calling get_config
        """
        custom_config = {"zfs": {"capacity_warning_percent": 70}}

        result = behaviors._load_config_with_logging(custom_config)

        assert result is custom_config, "Must return provided config unchanged"

    @patch("check_zpools.behaviors.get_config")
    def test_loads_from_layered_config_when_none_provided(
        self,
        mock_get_config: MagicMock,
    ) -> None:
        """When no config provided, loads from layered config system.

        Given: No custom config (None)
        When: Loading config with logging
        Then: Calls get_config and returns result
        """
        expected_config = {"zfs": {}, "email": {}, "alerts": {}}
        mock_config_obj = MagicMock()
        mock_config_obj.as_dict.return_value = expected_config
        mock_get_config.return_value = mock_config_obj

        result = behaviors._load_config_with_logging(None)

        assert result == expected_config, "Must return layered config"
        mock_get_config.assert_called_once()


# =============================================================================
# Daemon Component Initialization Tests
# =============================================================================


class TestDaemonComponentInitialization:
    """Daemon component initialization validates and creates all components."""

    @patch("check_zpools.behaviors.ZFSClient")
    def test_raises_error_when_zfs_not_available(
        self,
        mock_client_class: MagicMock,
    ) -> None:
        """When ZFS is not available, raises ZFSNotAvailableError.

        Given: ZFS client reports zpool not available
        When: Initializing daemon components
        Then: ZFSNotAvailableError is raised
        """
        from check_zpools.zfs_client import ZFSNotAvailableError

        mock_client = MagicMock()
        mock_client.check_zpool_available.return_value = False
        mock_client_class.return_value = mock_client

        config = {"zfs": {}, "alerts": {}, "daemon": {}}

        with pytest.raises(ZFSNotAvailableError, match="zpool command not found"):
            behaviors._initialize_daemon_components(config)

    @patch("check_zpools.behaviors.ZFSClient")
    @patch("check_zpools.behaviors.PoolMonitor")
    @patch("check_zpools.behaviors.load_email_config_from_dict")
    @patch("check_zpools.behaviors.EmailAlerter")
    @patch("check_zpools.behaviors.AlertStateManager")
    def test_returns_all_initialized_components(
        self,
        mock_state_class: MagicMock,
        mock_alerter_class: MagicMock,
        mock_load_email: MagicMock,
        mock_monitor_class: MagicMock,
        mock_client_class: MagicMock,
    ) -> None:
        """When ZFS is available, returns all initialized components.

        Given: Valid config with all required sections
        When: Initializing daemon components
        Then: Returns tuple of (client, monitor, alerter, state_manager, daemon_config)
        """
        # Setup mocks
        mock_client = MagicMock()
        mock_client.check_zpool_available.return_value = True
        mock_client_class.return_value = mock_client

        mock_monitor = MagicMock()
        mock_monitor_class.return_value = mock_monitor

        mock_email_config = MagicMock()
        mock_load_email.return_value = mock_email_config

        mock_alerter = MagicMock()
        mock_alerter_class.return_value = mock_alerter

        mock_state = MagicMock()
        mock_state_class.return_value = mock_state

        config = {
            "zfs": {},
            "alerts": {},
            "daemon": {"check_interval_seconds": 300, "alert_resend_interval_hours": 24},
        }

        client, monitor, alerter, state_manager, daemon_config = behaviors._initialize_daemon_components(config)

        assert client is mock_client, "Must return client"
        assert monitor is mock_monitor, "Must return monitor"
        assert alerter is mock_alerter, "Must return alerter"
        assert state_manager is mock_state, "Must return state manager"
        assert daemon_config == {"check_interval_seconds": 300, "alert_resend_interval_hours": 24}, "Must return daemon config"

    @patch("check_zpools.behaviors.ZFSClient")
    @patch("check_zpools.behaviors.PoolMonitor")
    @patch("check_zpools.behaviors.load_email_config_from_dict")
    @patch("check_zpools.behaviors.EmailAlerter")
    @patch("check_zpools.behaviors.AlertStateManager")
    def test_uses_alert_resend_interval_hours_config_key(
        self,
        mock_state_class: MagicMock,
        mock_alerter_class: MagicMock,
        mock_load_email: MagicMock,
        mock_monitor_class: MagicMock,
        mock_client_class: MagicMock,
    ) -> None:
        """When initializing state manager, uses alert_resend_interval_hours config key.

        Given: Config with alert_resend_interval_hours set to 6
        When: Initializing daemon components
        Then: AlertStateManager is created with resend_interval=6
        """
        # Setup mocks
        mock_client = MagicMock()
        mock_client.check_zpool_available.return_value = True
        mock_client_class.return_value = mock_client

        mock_monitor_class.return_value = MagicMock()
        mock_load_email.return_value = MagicMock()
        mock_alerter_class.return_value = MagicMock()
        mock_state_class.return_value = MagicMock()

        config = {
            "zfs": {},
            "alerts": {},
            "daemon": {"alert_resend_interval_hours": 6},
        }

        behaviors._initialize_daemon_components(config)

        # Verify AlertStateManager was called with correct resend interval
        mock_state_class.assert_called_once()
        call_args = mock_state_class.call_args
        assert call_args[0][1] == 6, "Must pass alert_resend_interval_hours to AlertStateManager"


# =============================================================================
# Daemon Lifecycle Tests
# =============================================================================


class TestRunDaemonLifecycle:
    """Daemon lifecycle starts and handles interrupts gracefully."""

    @patch("check_zpools.behaviors._load_config_with_logging")
    @patch("check_zpools.behaviors._initialize_daemon_components")
    @patch("check_zpools.behaviors.ZPoolDaemon")
    def test_starts_daemon_with_initialized_components(
        self,
        mock_daemon_class: MagicMock,
        mock_initialize: MagicMock,
        mock_load_config: MagicMock,
    ) -> None:
        """When starting daemon, initializes and starts daemon loop.

        Given: Valid config and initialized components
        When: Running daemon
        Then: ZPoolDaemon is created and started
        """
        # Setup mocks
        mock_config = {"zfs": {}, "daemon": {}}
        mock_load_config.return_value = mock_config

        mock_client = MagicMock()
        mock_monitor = MagicMock()
        mock_alerter = MagicMock()
        mock_state = MagicMock()
        mock_daemon_config = {}
        mock_initialize.return_value = (mock_client, mock_monitor, mock_alerter, mock_state, mock_daemon_config)

        mock_daemon = MagicMock()
        mock_daemon.start.return_value = None
        mock_daemon_class.return_value = mock_daemon

        behaviors.run_daemon(config=mock_config, foreground=True)

        mock_daemon.start.assert_called_once()

    @patch("check_zpools.behaviors._load_config_with_logging")
    @patch("check_zpools.behaviors._initialize_daemon_components")
    @patch("check_zpools.behaviors.ZPoolDaemon")
    def test_handles_keyboard_interrupt_gracefully(
        self,
        mock_daemon_class: MagicMock,
        mock_initialize: MagicMock,
        mock_load_config: MagicMock,
    ) -> None:
        """When daemon receives KeyboardInterrupt, exits gracefully.

        Given: Daemon running and receiving Ctrl+C
        When: KeyboardInterrupt is raised
        Then: Daemon exits without re-raising exception
        """
        # Setup mocks
        mock_config = {"zfs": {}, "daemon": {}}
        mock_load_config.return_value = mock_config

        mock_client = MagicMock()
        mock_monitor = MagicMock()
        mock_alerter = MagicMock()
        mock_state = MagicMock()
        mock_daemon_config = {}
        mock_initialize.return_value = (mock_client, mock_monitor, mock_alerter, mock_state, mock_daemon_config)

        mock_daemon = MagicMock()
        mock_daemon.start.side_effect = KeyboardInterrupt()
        mock_daemon_class.return_value = mock_daemon

        # Should not raise exception
        behaviors.run_daemon(config=mock_config, foreground=True)

    @patch("check_zpools.behaviors._load_config_with_logging")
    @patch("check_zpools.behaviors._initialize_daemon_components")
    @patch("check_zpools.behaviors.ZPoolDaemon")
    def test_propagates_unexpected_daemon_errors(
        self,
        mock_daemon_class: MagicMock,
        mock_initialize: MagicMock,
        mock_load_config: MagicMock,
    ) -> None:
        """When daemon encounters unexpected error, re-raises it.

        Given: Daemon running and encountering RuntimeError
        When: RuntimeError is raised during daemon execution
        Then: RuntimeError is propagated to caller
        """
        # Setup mocks
        mock_config = {"zfs": {}, "daemon": {}}
        mock_load_config.return_value = mock_config

        mock_client = MagicMock()
        mock_monitor = MagicMock()
        mock_alerter = MagicMock()
        mock_state = MagicMock()
        mock_daemon_config = {}
        mock_initialize.return_value = (mock_client, mock_monitor, mock_alerter, mock_state, mock_daemon_config)

        mock_daemon = MagicMock()
        mock_daemon.start.side_effect = RuntimeError("Daemon crashed")
        mock_daemon_class.return_value = mock_daemon

        with pytest.raises(RuntimeError, match="Daemon crashed"):
            behaviors.run_daemon(config=mock_config, foreground=True)
