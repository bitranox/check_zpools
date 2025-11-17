"""Behaviour-layer stories: every helper, a single note."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from check_zpools import behaviors
from check_zpools.models import CheckResult, PoolHealth, PoolStatus, Severity


@pytest.mark.os_agnostic
def test_when_the_greeting_is_sung_it_reaches_the_buffer() -> None:
    buffer = StringIO()

    behaviors.emit_greeting(stream=buffer)

    assert buffer.getvalue() == "Hello World\n"


@pytest.mark.os_agnostic
def test_when_no_stream_is_named_stdout_hears_the_song(capsys: pytest.CaptureFixture[str]) -> None:
    behaviors.emit_greeting()

    captured = capsys.readouterr()

    assert captured.out == "Hello World\n"
    assert captured.err == ""


@pytest.mark.os_agnostic
def test_when_flush_is_possible_the_stream_is_polished() -> None:
    @dataclass
    class MemoryStream:
        ledger: list[str]
        flushed: bool = False

        def write(self, text: str) -> None:
            self.ledger.append(text)

        def flush(self) -> None:
            self.flushed = True

    stream = MemoryStream([])

    behaviors.emit_greeting(stream=stream)  # type: ignore[arg-type]

    assert stream.ledger == ["Hello World\n"]
    assert stream.flushed is True


@pytest.mark.os_agnostic
def test_when_failure_is_invoked_a_runtime_error_rises() -> None:
    with pytest.raises(RuntimeError, match="I should fail"):
        behaviors.raise_intentional_failure()


@pytest.mark.os_agnostic
def test_when_no_work_is_requested_the_placeholder_sits_still() -> None:
    assert behaviors.noop_main() is None


@pytest.mark.os_agnostic
class TestBuildMonitorConfig:
    """Test monitor configuration builder validation."""

    def test_build_with_defaults(self) -> None:
        """Should build config with default values when not specified."""
        config: dict = {}

        result = behaviors._build_monitor_config(config)

        assert result.capacity_warning_percent == 80
        assert result.capacity_critical_percent == 90
        assert result.scrub_max_age_days == 30

    def test_build_with_custom_capacity(self) -> None:
        """Should use custom capacity thresholds."""
        config = {
            "zfs": {
                "capacity": {
                    "warning_percent": 70,
                    "critical_percent": 85,
                }
            }
        }

        result = behaviors._build_monitor_config(config)

        assert result.capacity_warning_percent == 70
        assert result.capacity_critical_percent == 85

    def test_build_with_custom_scrub(self) -> None:
        """Should use custom scrub age threshold."""
        config = {"zfs": {"scrub": {"max_age_days": 60}}}

        result = behaviors._build_monitor_config(config)

        assert result.scrub_max_age_days == 60

    def test_build_with_custom_errors(self) -> None:
        """Should use custom error thresholds."""
        config = {
            "zfs": {
                "errors": {
                    "read_errors_warning": 5,
                    "write_errors_warning": 3,
                    "checksum_errors_warning": 1,
                }
            }
        }

        result = behaviors._build_monitor_config(config)

        assert result.read_errors_warning == 5
        assert result.write_errors_warning == 3
        assert result.checksum_errors_warning == 1

    def test_validate_warning_below_zero(self) -> None:
        """Should reject warning percent below 0."""
        config = {"zfs": {"capacity": {"warning_percent": -1}}}

        with pytest.raises(ValueError, match="warning_percent must be between 0 and 100"):
            behaviors._build_monitor_config(config)

    def test_validate_warning_zero(self) -> None:
        """Should reject warning percent of 0."""
        config = {"zfs": {"capacity": {"warning_percent": 0}}}

        with pytest.raises(ValueError, match="warning_percent must be between 0 and 100"):
            behaviors._build_monitor_config(config)

    def test_validate_warning_above_100(self) -> None:
        """Should reject warning percent above 100."""
        config = {"zfs": {"capacity": {"warning_percent": 101}}}

        with pytest.raises(ValueError, match="warning_percent must be between 0 and 100"):
            behaviors._build_monitor_config(config)

    def test_validate_critical_zero(self) -> None:
        """Should reject critical percent of 0."""
        config = {"zfs": {"capacity": {"critical_percent": 0}}}

        with pytest.raises(ValueError, match="critical_percent must be between 0 and 100"):
            behaviors._build_monitor_config(config)

    def test_validate_critical_above_100(self) -> None:
        """Should reject critical percent above 100."""
        config = {"zfs": {"capacity": {"critical_percent": 101}}}

        with pytest.raises(ValueError, match="critical_percent must be between 0 and 100"):
            behaviors._build_monitor_config(config)

    def test_validate_warning_greater_than_critical(self) -> None:
        """Should reject warning greater than critical."""
        config = {
            "zfs": {
                "capacity": {
                    "warning_percent": 90,
                    "critical_percent": 80,
                }
            }
        }

        with pytest.raises(ValueError, match="warning_percent.*must be less than critical_percent"):
            behaviors._build_monitor_config(config)

    def test_validate_warning_equal_to_critical(self) -> None:
        """Should reject warning equal to critical."""
        config = {
            "zfs": {
                "capacity": {
                    "warning_percent": 85,
                    "critical_percent": 85,
                }
            }
        }

        with pytest.raises(ValueError, match="warning_percent.*must be less than critical_percent"):
            behaviors._build_monitor_config(config)

    def test_validate_scrub_age_negative(self) -> None:
        """Should reject negative scrub age."""
        config = {"zfs": {"scrub": {"max_age_days": -1}}}

        with pytest.raises(ValueError, match="scrub.max_age_days must be non-negative"):
            behaviors._build_monitor_config(config)

    def test_validate_read_errors_negative(self) -> None:
        """Should reject negative read error threshold."""
        config = {"zfs": {"errors": {"read_errors_warning": -1}}}

        with pytest.raises(ValueError, match="read_errors_warning must be non-negative"):
            behaviors._build_monitor_config(config)

    def test_validate_write_errors_negative(self) -> None:
        """Should reject negative write error threshold."""
        config = {"zfs": {"errors": {"write_errors_warning": -1}}}

        with pytest.raises(ValueError, match="write_errors_warning must be non-negative"):
            behaviors._build_monitor_config(config)

    def test_validate_checksum_errors_negative(self) -> None:
        """Should reject negative checksum error threshold."""
        config = {"zfs": {"errors": {"checksum_errors_warning": -1}}}

        with pytest.raises(ValueError, match="checksum_errors_warning must be non-negative"):
            behaviors._build_monitor_config(config)

    def test_allow_scrub_age_zero(self) -> None:
        """Should allow scrub age of 0 (no scrub age checking)."""
        config = {"zfs": {"scrub": {"max_age_days": 0}}}

        result = behaviors._build_monitor_config(config)

        assert result.scrub_max_age_days == 0

    def test_allow_critical_100_percent(self) -> None:
        """Should allow critical at 100%."""
        config = {
            "zfs": {
                "capacity": {
                    "warning_percent": 95,
                    "critical_percent": 100,
                }
            }
        }

        result = behaviors._build_monitor_config(config)

        assert result.capacity_critical_percent == 100


@pytest.mark.os_agnostic
class TestCheckPoolsOnce:
    """Test check_pools_once integration."""

    @patch("check_zpools.behaviors.get_config")
    @patch("check_zpools.behaviors.ZFSClient")
    @patch("check_zpools.behaviors.ZFSParser")
    @patch("check_zpools.behaviors.PoolMonitor")
    def test_check_pools_once_success(
        self,
        mock_monitor_class: MagicMock,
        mock_parser_class: MagicMock,
        mock_client_class: MagicMock,
        mock_get_config: MagicMock,
    ) -> None:
        """Should successfully check pools and return results."""
        # Setup mocks
        mock_config = MagicMock()
        mock_config.as_dict.return_value = {"zfs": {}}
        mock_get_config.return_value = mock_config

        mock_client = MagicMock()
        mock_client.get_pool_list.return_value = {"pools": {}}
        mock_client.get_pool_status.return_value = {"pools": {}}
        mock_client_class.return_value = mock_client

        mock_parser = MagicMock()
        pool_status = PoolStatus(
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
        mock_parser.parse_pool_list.return_value = {"rpool": pool_status}
        mock_parser.parse_pool_status.return_value = {"rpool": pool_status}
        mock_parser.merge_pool_data.return_value = {"rpool": pool_status}
        mock_parser_class.return_value = mock_parser

        mock_monitor = MagicMock()
        expected_result = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[pool_status],
            issues=[],
            overall_severity=Severity.OK,
        )
        mock_monitor.check_all_pools.return_value = expected_result
        mock_monitor_class.return_value = mock_monitor

        # Execute
        result = behaviors.check_pools_once()

        # Verify
        assert result == expected_result
        mock_client.get_pool_list.assert_called_once()
        mock_client.get_pool_status.assert_called_once()
        mock_monitor.check_all_pools.assert_called_once()

    @patch("check_zpools.behaviors.get_config")
    @patch("check_zpools.behaviors.ZFSClient")
    def test_check_pools_once_with_custom_config(
        self,
        mock_client_class: MagicMock,
        mock_get_config: MagicMock,
    ) -> None:
        """Should use custom config when provided."""
        custom_config = {"zfs": {"capacity": {"warning_percent": 70}}}

        mock_client = MagicMock()
        mock_client.get_pool_list.return_value = {"pools": {}}
        mock_client.get_pool_status.return_value = {"pools": {}}
        mock_client_class.return_value = mock_client

        # Should not call get_config when custom config provided
        try:
            behaviors.check_pools_once(config=custom_config)
        except Exception:
            pass  # May fail due to incomplete mocking, but we check get_config wasn't called

        mock_get_config.assert_not_called()

    @patch("check_zpools.behaviors.ZFSClient")
    def test_check_pools_once_handles_zfs_not_available(
        self,
        mock_client_class: MagicMock,
    ) -> None:
        """Should propagate ZFSNotAvailableError."""
        from check_zpools.zfs_client import ZFSNotAvailableError

        mock_client = MagicMock()
        mock_client.get_pool_list.side_effect = ZFSNotAvailableError("ZFS not found")
        mock_client_class.return_value = mock_client

        with pytest.raises(ZFSNotAvailableError):
            behaviors.check_pools_once(config={})


@pytest.mark.os_agnostic
class TestGetStateFilePath:
    """Test state file path resolution."""

    def test_get_state_file_path_with_custom_path(self) -> None:
        """Should use custom path when provided in config."""
        config = {"daemon": {"state_file": "/custom/path/state.json"}}

        result = behaviors._get_state_file_path(config)

        # Use Path comparison for cross-platform compatibility
        assert result == Path("/custom/path/state.json")

    def test_get_state_file_path_with_default(self) -> None:
        """Should use default path when not specified."""
        config: dict = {}

        result = behaviors._get_state_file_path(config)

        # Should default to /var/lib/check_zpools/state.json
        assert "check_zpools" in str(result)
        assert "state.json" in str(result)
