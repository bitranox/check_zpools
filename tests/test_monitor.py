"""Tests for ZFS pool monitoring logic.

Purpose
-------
Validate threshold checking, issue detection, and severity determination
across all monitoring categories.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone

from check_zpools.models import PoolHealth, PoolStatus, Severity
from check_zpools.monitor import MonitorConfig, PoolMonitor


@pytest.fixture
def default_config() -> MonitorConfig:
    """Provide default monitoring configuration."""
    return MonitorConfig()


@pytest.fixture
def strict_config() -> MonitorConfig:
    """Provide strict monitoring configuration."""
    return MonitorConfig(
        capacity_warning_percent=70,
        capacity_critical_percent=80,
        scrub_max_age_days=7,
        read_errors_warning=1,
        write_errors_warning=1,
        checksum_errors_warning=1,
    )


@pytest.fixture
def healthy_pool() -> PoolStatus:
    """Provide healthy pool status."""
    return PoolStatus(
        name="rpool",
        health=PoolHealth.ONLINE,
        capacity_percent=50.0,
        size_bytes=1_000_000_000,
        allocated_bytes=500_000_000,
        free_bytes=500_000_000,
        read_errors=0,
        write_errors=0,
        checksum_errors=0,
        last_scrub=datetime.now(timezone.utc) - timedelta(days=1),
        scrub_errors=0,
        scrub_in_progress=False,
    )


class TestMonitorConfig:
    """Tests for MonitorConfig dataclass."""

    def test_default_config_values(self) -> None:
        """Verify default threshold values."""
        config = MonitorConfig()

        assert config.capacity_warning_percent == 80
        assert config.capacity_critical_percent == 90
        assert config.scrub_max_age_days == 30
        assert config.read_errors_warning == 1
        assert config.write_errors_warning == 1
        assert config.checksum_errors_warning == 1

    def test_custom_config_values(self) -> None:
        """Verify custom configuration."""
        config = MonitorConfig(
            capacity_warning_percent=75,
            capacity_critical_percent=85,
            scrub_max_age_days=14,
        )

        assert config.capacity_warning_percent == 75
        assert config.capacity_critical_percent == 85
        assert config.scrub_max_age_days == 14

    def test_validation_rejects_warning_gte_critical(self) -> None:
        """Verify validation rejects warning >= critical."""
        with pytest.raises(ValueError, match="must be less than"):
            MonitorConfig(capacity_warning_percent=90, capacity_critical_percent=80)

        with pytest.raises(ValueError, match="must be less than"):
            MonitorConfig(capacity_warning_percent=85, capacity_critical_percent=85)

    def test_validation_rejects_invalid_percentages(self) -> None:
        """Verify validation rejects out-of-range percentages."""
        with pytest.raises(ValueError, match="between 0 and 100"):
            MonitorConfig(capacity_warning_percent=-10)

        with pytest.raises(ValueError, match="between 0 and 100"):
            MonitorConfig(capacity_critical_percent=150)


class TestHealthChecking:
    """Tests for pool health state checking."""

    def test_healthy_pool_has_no_health_issue(self, default_config: MonitorConfig, healthy_pool: PoolStatus) -> None:
        """Verify ONLINE pool generates no health issue."""
        monitor = PoolMonitor(default_config)
        issues = monitor.check_pool(healthy_pool)

        health_issues = [i for i in issues if i.category == "health"]
        assert len(health_issues) == 0

    def test_degraded_pool_generates_warning(self, default_config: MonitorConfig) -> None:
        """Verify DEGRADED pool generates WARNING."""
        pool = PoolStatus(
            name="rpool",
            health=PoolHealth.DEGRADED,
            capacity_percent=50.0,
            size_bytes=1000,
            allocated_bytes=500,
            free_bytes=500,
            read_errors=0,
            write_errors=0,
            checksum_errors=0,
            last_scrub=None,
            scrub_errors=0,
            scrub_in_progress=False,
        )

        monitor = PoolMonitor(default_config)
        issues = monitor.check_pool(pool)

        health_issues = [i for i in issues if i.category == "health"]
        assert len(health_issues) == 1
        assert health_issues[0].severity == Severity.WARNING
        assert "DEGRADED" in health_issues[0].message

    def test_faulted_pool_generates_critical(self, default_config: MonitorConfig) -> None:
        """Verify FAULTED pool generates CRITICAL."""
        pool = PoolStatus(
            name="rpool",
            health=PoolHealth.FAULTED,
            capacity_percent=50.0,
            size_bytes=1000,
            allocated_bytes=500,
            free_bytes=500,
            read_errors=0,
            write_errors=0,
            checksum_errors=0,
            last_scrub=None,
            scrub_errors=0,
            scrub_in_progress=False,
        )

        monitor = PoolMonitor(default_config)
        issues = monitor.check_pool(pool)

        health_issues = [i for i in issues if i.category == "health"]
        assert len(health_issues) == 1
        assert health_issues[0].severity == Severity.CRITICAL


class TestCapacityChecking:
    """Tests for capacity threshold checking."""

    def test_capacity_below_warning_no_issue(self, default_config: MonitorConfig) -> None:
        """Verify capacity below warning threshold generates no issue."""
        pool = PoolStatus(
            name="rpool",
            health=PoolHealth.ONLINE,
            capacity_percent=75.0,  # Below default 80% warning
            size_bytes=1000,
            allocated_bytes=750,
            free_bytes=250,
            read_errors=0,
            write_errors=0,
            checksum_errors=0,
            last_scrub=None,
            scrub_errors=0,
            scrub_in_progress=False,
        )

        monitor = PoolMonitor(default_config)
        issues = monitor.check_pool(pool)

        capacity_issues = [i for i in issues if i.category == "capacity"]
        assert len(capacity_issues) == 0

    def test_capacity_at_warning_threshold(self, default_config: MonitorConfig) -> None:
        """Verify capacity at warning threshold generates WARNING."""
        pool = PoolStatus(
            name="rpool",
            health=PoolHealth.ONLINE,
            capacity_percent=80.0,  # At default 80% warning
            size_bytes=1000,
            allocated_bytes=800,
            free_bytes=200,
            read_errors=0,
            write_errors=0,
            checksum_errors=0,
            last_scrub=None,
            scrub_errors=0,
            scrub_in_progress=False,
        )

        monitor = PoolMonitor(default_config)
        issues = monitor.check_pool(pool)

        capacity_issues = [i for i in issues if i.category == "capacity"]
        assert len(capacity_issues) == 1
        assert capacity_issues[0].severity == Severity.WARNING
        assert "80.0%" in capacity_issues[0].message

    def test_capacity_at_critical_threshold(self, default_config: MonitorConfig) -> None:
        """Verify capacity at critical threshold generates CRITICAL."""
        pool = PoolStatus(
            name="rpool",
            health=PoolHealth.ONLINE,
            capacity_percent=90.0,  # At default 90% critical
            size_bytes=1000,
            allocated_bytes=900,
            free_bytes=100,
            read_errors=0,
            write_errors=0,
            checksum_errors=0,
            last_scrub=None,
            scrub_errors=0,
            scrub_in_progress=False,
        )

        monitor = PoolMonitor(default_config)
        issues = monitor.check_pool(pool)

        capacity_issues = [i for i in issues if i.category == "capacity"]
        assert len(capacity_issues) == 1
        assert capacity_issues[0].severity == Severity.CRITICAL
        assert "90.0%" in capacity_issues[0].message

    def test_capacity_between_warning_and_critical(self, default_config: MonitorConfig) -> None:
        """Verify capacity between thresholds generates WARNING."""
        pool = PoolStatus(
            name="rpool",
            health=PoolHealth.ONLINE,
            capacity_percent=85.0,  # Between 80% and 90%
            size_bytes=1000,
            allocated_bytes=850,
            free_bytes=150,
            read_errors=0,
            write_errors=0,
            checksum_errors=0,
            last_scrub=None,
            scrub_errors=0,
            scrub_in_progress=False,
        )

        monitor = PoolMonitor(default_config)
        issues = monitor.check_pool(pool)

        capacity_issues = [i for i in issues if i.category == "capacity"]
        assert len(capacity_issues) == 1
        assert capacity_issues[0].severity == Severity.WARNING


class TestErrorChecking:
    """Tests for I/O and checksum error checking."""

    def test_no_errors_generates_no_issues(self, default_config: MonitorConfig, healthy_pool: PoolStatus) -> None:
        """Verify pool with no errors generates no error issues."""
        monitor = PoolMonitor(default_config)
        issues = monitor.check_pool(healthy_pool)

        error_issues = [i for i in issues if i.category == "errors"]
        assert len(error_issues) == 0

    def test_read_errors_generate_warning(self, default_config: MonitorConfig) -> None:
        """Verify read errors generate WARNING."""
        pool = PoolStatus(
            name="rpool",
            health=PoolHealth.ONLINE,
            capacity_percent=50.0,
            size_bytes=1000,
            allocated_bytes=500,
            free_bytes=500,
            read_errors=5,
            write_errors=0,
            checksum_errors=0,
            last_scrub=None,
            scrub_errors=0,
            scrub_in_progress=False,
        )

        monitor = PoolMonitor(default_config)
        issues = monitor.check_pool(pool)

        error_issues = [i for i in issues if i.category == "errors"]
        assert len(error_issues) == 1
        assert error_issues[0].severity == Severity.WARNING
        assert "5 read errors" in error_issues[0].message

    def test_write_errors_generate_warning(self, default_config: MonitorConfig) -> None:
        """Verify write errors generate WARNING."""
        pool = PoolStatus(
            name="rpool",
            health=PoolHealth.ONLINE,
            capacity_percent=50.0,
            size_bytes=1000,
            allocated_bytes=500,
            free_bytes=500,
            read_errors=0,
            write_errors=3,
            checksum_errors=0,
            last_scrub=None,
            scrub_errors=0,
            scrub_in_progress=False,
        )

        monitor = PoolMonitor(default_config)
        issues = monitor.check_pool(pool)

        error_issues = [i for i in issues if i.category == "errors"]
        assert len(error_issues) == 1
        assert error_issues[0].severity == Severity.WARNING
        assert "3 write errors" in error_issues[0].message

    def test_checksum_errors_generate_warning(self, default_config: MonitorConfig) -> None:
        """Verify checksum errors generate WARNING."""
        pool = PoolStatus(
            name="rpool",
            health=PoolHealth.ONLINE,
            capacity_percent=50.0,
            size_bytes=1000,
            allocated_bytes=500,
            free_bytes=500,
            read_errors=0,
            write_errors=0,
            checksum_errors=2,
            last_scrub=None,
            scrub_errors=0,
            scrub_in_progress=False,
        )

        monitor = PoolMonitor(default_config)
        issues = monitor.check_pool(pool)

        error_issues = [i for i in issues if i.category == "errors"]
        assert len(error_issues) == 1
        assert error_issues[0].severity == Severity.WARNING
        assert "checksum errors" in error_issues[0].message
        assert "corruption" in error_issues[0].message.lower()

    def test_multiple_error_types_generate_multiple_issues(self, default_config: MonitorConfig) -> None:
        """Verify multiple error types generate separate issues."""
        pool = PoolStatus(
            name="rpool",
            health=PoolHealth.ONLINE,
            capacity_percent=50.0,
            size_bytes=1000,
            allocated_bytes=500,
            free_bytes=500,
            read_errors=1,
            write_errors=2,
            checksum_errors=3,
            last_scrub=None,
            scrub_errors=0,
            scrub_in_progress=False,
        )

        monitor = PoolMonitor(default_config)
        issues = monitor.check_pool(pool)

        error_issues = [i for i in issues if i.category == "errors"]
        assert len(error_issues) == 3  # One for each error type


class TestScrubChecking:
    """Tests for scrub status checking."""

    def test_recent_scrub_no_errors_generates_no_issue(self, default_config: MonitorConfig, healthy_pool: PoolStatus) -> None:
        """Verify recent scrub with no errors generates no issue."""
        monitor = PoolMonitor(default_config)
        issues = monitor.check_pool(healthy_pool)

        scrub_issues = [i for i in issues if i.category == "scrub"]
        assert len(scrub_issues) == 0

    def test_never_scrubbed_generates_info(self, default_config: MonitorConfig) -> None:
        """Verify never-scrubbed pool generates INFO."""
        pool = PoolStatus(
            name="rpool",
            health=PoolHealth.ONLINE,
            capacity_percent=50.0,
            size_bytes=1000,
            allocated_bytes=500,
            free_bytes=500,
            read_errors=0,
            write_errors=0,
            checksum_errors=0,
            last_scrub=None,
            scrub_errors=0,
            scrub_in_progress=False,
        )

        monitor = PoolMonitor(default_config)
        issues = monitor.check_pool(pool)

        scrub_issues = [i for i in issues if i.category == "scrub"]
        assert len(scrub_issues) == 1
        assert scrub_issues[0].severity == Severity.INFO
        assert "never been scrubbed" in scrub_issues[0].message

    def test_old_scrub_generates_info(self, default_config: MonitorConfig) -> None:
        """Verify old scrub generates INFO."""
        pool = PoolStatus(
            name="rpool",
            health=PoolHealth.ONLINE,
            capacity_percent=50.0,
            size_bytes=1000,
            allocated_bytes=500,
            free_bytes=500,
            read_errors=0,
            write_errors=0,
            checksum_errors=0,
            last_scrub=datetime.now(timezone.utc) - timedelta(days=45),  # > 30 days
            scrub_errors=0,
            scrub_in_progress=False,
        )

        monitor = PoolMonitor(default_config)
        issues = monitor.check_pool(pool)

        scrub_issues = [i for i in issues if i.category == "scrub"]
        assert len(scrub_issues) == 1
        assert scrub_issues[0].severity == Severity.INFO
        assert "45 days old" in scrub_issues[0].message

    def test_scrub_errors_generate_warning(self, default_config: MonitorConfig) -> None:
        """Verify scrub errors generate WARNING."""
        pool = PoolStatus(
            name="rpool",
            health=PoolHealth.ONLINE,
            capacity_percent=50.0,
            size_bytes=1000,
            allocated_bytes=500,
            free_bytes=500,
            read_errors=0,
            write_errors=0,
            checksum_errors=0,
            last_scrub=datetime.now(timezone.utc) - timedelta(days=1),
            scrub_errors=5,
            scrub_in_progress=False,
        )

        monitor = PoolMonitor(default_config)
        issues = monitor.check_pool(pool)

        scrub_issues = [i for i in issues if i.category == "scrub"]
        assert len(scrub_issues) == 1
        assert scrub_issues[0].severity == Severity.WARNING
        assert "5 errors" in scrub_issues[0].message

    def test_scrub_age_disabled_with_zero_max_age(self) -> None:
        """Verify scrub age checking disabled when max_age=0."""
        config = MonitorConfig(scrub_max_age_days=0)
        pool = PoolStatus(
            name="rpool",
            health=PoolHealth.ONLINE,
            capacity_percent=50.0,
            size_bytes=1000,
            allocated_bytes=500,
            free_bytes=500,
            read_errors=0,
            write_errors=0,
            checksum_errors=0,
            last_scrub=None,  # Never scrubbed
            scrub_errors=0,
            scrub_in_progress=False,
        )

        monitor = PoolMonitor(config)
        issues = monitor.check_pool(pool)

        scrub_issues = [i for i in issues if i.category == "scrub"]
        assert len(scrub_issues) == 0  # No scrub age checking


class TestCheckAllPools:
    """Tests for checking multiple pools."""

    def test_check_all_pools_aggregates_results(self, default_config: MonitorConfig) -> None:
        """Verify check_all_pools returns aggregated result."""
        pools = {
            "pool1": PoolStatus(
                name="pool1",
                health=PoolHealth.ONLINE,
                capacity_percent=50.0,
                size_bytes=1000,
                allocated_bytes=500,
                free_bytes=500,
                read_errors=0,
                write_errors=0,
                checksum_errors=0,
                last_scrub=datetime.now(timezone.utc),
                scrub_errors=0,
                scrub_in_progress=False,
            ),
            "pool2": PoolStatus(
                name="pool2",
                health=PoolHealth.DEGRADED,
                capacity_percent=85.0,
                size_bytes=1000,
                allocated_bytes=850,
                free_bytes=150,
                read_errors=5,
                write_errors=0,
                checksum_errors=0,
                last_scrub=None,
                scrub_errors=0,
                scrub_in_progress=False,
            ),
        }

        monitor = PoolMonitor(default_config)
        result = monitor.check_all_pools(pools)

        assert len(result.pools) == 2
        assert len(result.issues) > 0
        assert result.overall_severity == Severity.WARNING  # From pool2

    def test_overall_severity_is_maximum(self, default_config: MonitorConfig) -> None:
        """Verify overall_severity is max of all issue severities."""
        pools = {
            "critical_pool": PoolStatus(
                name="critical_pool",
                health=PoolHealth.FAULTED,  # CRITICAL
                capacity_percent=50.0,
                size_bytes=1000,
                allocated_bytes=500,
                free_bytes=500,
                read_errors=0,
                write_errors=0,
                checksum_errors=0,
                last_scrub=None,
                scrub_errors=0,
                scrub_in_progress=False,
            ),
            "warning_pool": PoolStatus(
                name="warning_pool",
                health=PoolHealth.ONLINE,
                capacity_percent=85.0,  # WARNING
                size_bytes=1000,
                allocated_bytes=850,
                free_bytes=150,
                read_errors=0,
                write_errors=0,
                checksum_errors=0,
                last_scrub=None,
                scrub_errors=0,
                scrub_in_progress=False,
            ),
        }

        monitor = PoolMonitor(default_config)
        result = monitor.check_all_pools(pools)

        assert result.overall_severity == Severity.CRITICAL

    def test_all_healthy_pools_severity_ok(self, default_config: MonitorConfig, healthy_pool: PoolStatus) -> None:
        """Verify all healthy pools result in OK severity."""
        pools = {"pool1": healthy_pool}

        monitor = PoolMonitor(default_config)
        result = monitor.check_all_pools(pools)

        assert result.overall_severity == Severity.OK
        assert len(result.issues) == 0
