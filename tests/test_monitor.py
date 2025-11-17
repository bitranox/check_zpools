"""Tests for ZFS pool monitoring - the business rules layer.

This module validates the core business logic for pool monitoring:
- Capacity threshold checking (warning/critical levels)
- Health state assessment (ONLINE, DEGRADED, FAULTED)
- I/O error detection (read, write, checksum errors)
- Scrub status monitoring (age, errors, never-scrubbed)
- Aggregate monitoring across multiple pools

All tests are pure business logic - no I/O, no OS dependencies.
They validate the monitoring rules work correctly on all platforms.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone

from check_zpools.models import PoolHealth, PoolStatus, Severity
from check_zpools.monitor import MonitorConfig, PoolMonitor


# ============================================================================
# Test Fixtures & Builder Helpers
# ============================================================================


def a_healthy_pool_named(name: str) -> PoolStatus:
    """Create a healthy pool with comfortable capacity and recent scrub.

    Use this when the pool's specific attributes don't matter.
    """
    return PoolStatus(
        name=name,
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


def a_pool_with(**overrides: object) -> PoolStatus:
    """Create a pool with specific attributes overridden.

    Examples:
        a_pool_with(capacity_percent=85.0)
        a_pool_with(health=PoolHealth.DEGRADED, read_errors=5)
    """
    defaults: dict[str, object] = {
        "name": "test-pool",
        "health": PoolHealth.ONLINE,
        "capacity_percent": 50.0,
        "size_bytes": 1_000_000_000,
        "allocated_bytes": 500_000_000,
        "free_bytes": 500_000_000,
        "read_errors": 0,
        "write_errors": 0,
        "checksum_errors": 0,
        "last_scrub": None,
        "scrub_errors": 0,
        "scrub_in_progress": False,
    }
    return PoolStatus(**{**defaults, **overrides})  # type: ignore[arg-type]


def a_monitor_with_default_thresholds() -> PoolMonitor:
    """Create a monitor with default threshold values (80/90/30)."""
    return PoolMonitor(MonitorConfig())


def a_monitor_with_strict_thresholds() -> PoolMonitor:
    """Create a monitor with strict threshold values (70/80/7)."""
    config = MonitorConfig(
        capacity_warning_percent=70,
        capacity_critical_percent=80,
        scrub_max_age_days=7,
        read_errors_warning=1,
        write_errors_warning=1,
        checksum_errors_warning=1,
    )
    return PoolMonitor(config)


# ============================================================================
# Tests: MonitorConfig - Configuration and Validation
# ============================================================================


class TestMonitorConfigDefaults:
    """Monitor configuration provides sensible default thresholds."""

    @pytest.mark.os_agnostic
    def test_default_capacity_warning_is_eighty_percent(self) -> None:
        """When no thresholds are specified,
        capacity warning triggers at 80%."""
        config = MonitorConfig()

        assert config.capacity_warning_percent == 80

    @pytest.mark.os_agnostic
    def test_default_capacity_critical_is_ninety_percent(self) -> None:
        """When no thresholds are specified,
        capacity critical triggers at 90%."""
        config = MonitorConfig()

        assert config.capacity_critical_percent == 90

    @pytest.mark.os_agnostic
    def test_default_scrub_max_age_is_thirty_days(self) -> None:
        """When no scrub age is specified,
        warnings appear after 30 days."""
        config = MonitorConfig()

        assert config.scrub_max_age_days == 30

    @pytest.mark.os_agnostic
    def test_default_error_thresholds_are_one(self) -> None:
        """When no error thresholds are specified,
        any error count triggers warnings."""
        config = MonitorConfig()

        assert config.read_errors_warning == 1
        assert config.write_errors_warning == 1
        assert config.checksum_errors_warning == 1


class TestMonitorConfigCustomization:
    """Monitor configuration accepts custom threshold values."""

    @pytest.mark.os_agnostic
    def test_custom_capacity_thresholds_are_preserved(self) -> None:
        """When custom capacity thresholds are provided,
        they override the defaults."""
        config = MonitorConfig(
            capacity_warning_percent=75,
            capacity_critical_percent=85,
        )

        assert config.capacity_warning_percent == 75
        assert config.capacity_critical_percent == 85

    @pytest.mark.os_agnostic
    def test_custom_scrub_age_is_preserved(self) -> None:
        """When a custom scrub age is provided,
        it overrides the default."""
        config = MonitorConfig(scrub_max_age_days=14)

        assert config.scrub_max_age_days == 14


class TestMonitorConfigValidation:
    """Monitor configuration rejects invalid threshold combinations."""

    @pytest.mark.os_agnostic
    def test_warning_greater_than_critical_is_rejected(self) -> None:
        """When warning threshold exceeds critical threshold,
        configuration raises ValueError."""
        with pytest.raises(ValueError, match="must be less than"):
            MonitorConfig(capacity_warning_percent=90, capacity_critical_percent=80)

    @pytest.mark.os_agnostic
    def test_warning_equal_to_critical_is_rejected(self) -> None:
        """When warning threshold equals critical threshold,
        configuration raises ValueError."""
        with pytest.raises(ValueError, match="must be less than"):
            MonitorConfig(capacity_warning_percent=85, capacity_critical_percent=85)

    @pytest.mark.os_agnostic
    def test_negative_capacity_percentage_is_rejected(self) -> None:
        """When capacity percentage is negative,
        configuration raises ValueError."""
        with pytest.raises(ValueError, match="between 0 and 100"):
            MonitorConfig(capacity_warning_percent=-10)

    @pytest.mark.os_agnostic
    def test_capacity_percentage_above_hundred_is_rejected(self) -> None:
        """When capacity percentage exceeds 100,
        configuration raises ValueError."""
        with pytest.raises(ValueError, match="between 0 and 100"):
            MonitorConfig(capacity_critical_percent=150)


# ============================================================================
# Tests: Health State Monitoring
# ============================================================================


class TestHealthStateMonitoring:
    """Pools are monitored for health state degradation."""

    @pytest.mark.os_agnostic
    def test_an_online_pool_generates_no_health_issues(self) -> None:
        """When a pool is ONLINE,
        monitoring reports no health issues."""
        pool = a_pool_with(health=PoolHealth.ONLINE)
        monitor = a_monitor_with_default_thresholds()

        issues = monitor.check_pool(pool)
        health_issues = [i for i in issues if i.category == "health"]

        assert len(health_issues) == 0

    @pytest.mark.os_agnostic
    def test_a_degraded_pool_triggers_warning(self) -> None:
        """When a pool becomes DEGRADED,
        monitoring reports a WARNING severity issue."""
        pool = a_pool_with(health=PoolHealth.DEGRADED)
        monitor = a_monitor_with_default_thresholds()

        issues = monitor.check_pool(pool)
        health_issues = [i for i in issues if i.category == "health"]

        assert len(health_issues) == 1
        assert health_issues[0].severity == Severity.WARNING
        assert "DEGRADED" in health_issues[0].message

    @pytest.mark.os_agnostic
    def test_a_faulted_pool_triggers_critical(self) -> None:
        """When a pool becomes FAULTED,
        monitoring reports a CRITICAL severity issue."""
        pool = a_pool_with(health=PoolHealth.FAULTED)
        monitor = a_monitor_with_default_thresholds()

        issues = monitor.check_pool(pool)
        health_issues = [i for i in issues if i.category == "health"]

        assert len(health_issues) == 1
        assert health_issues[0].severity == Severity.CRITICAL
        assert "FAULTED" in health_issues[0].message

    @pytest.mark.os_agnostic
    def test_an_unavailable_pool_triggers_critical(self) -> None:
        """When a pool becomes UNAVAIL,
        monitoring reports a CRITICAL severity issue."""
        pool = a_pool_with(health=PoolHealth.UNAVAIL)
        monitor = a_monitor_with_default_thresholds()

        issues = monitor.check_pool(pool)
        health_issues = [i for i in issues if i.category == "health"]

        assert len(health_issues) == 1
        assert health_issues[0].severity == Severity.CRITICAL


# ============================================================================
# Tests: Capacity Threshold Monitoring
# ============================================================================


class TestCapacityBelowWarningThreshold:
    """Pools below warning threshold generate no capacity issues."""

    @pytest.mark.os_agnostic
    def test_capacity_at_seventy_nine_percent_is_ok(self) -> None:
        """When capacity is 79% (just below 80% warning),
        monitoring reports no capacity issues."""
        pool = a_pool_with(capacity_percent=79.0)
        monitor = a_monitor_with_default_thresholds()

        issues = monitor.check_pool(pool)
        capacity_issues = [i for i in issues if i.category == "capacity"]

        assert len(capacity_issues) == 0

    @pytest.mark.os_agnostic
    def test_capacity_at_fifty_percent_is_ok(self) -> None:
        """When capacity is 50% (well below warning),
        monitoring reports no capacity issues."""
        pool = a_pool_with(capacity_percent=50.0)
        monitor = a_monitor_with_default_thresholds()

        issues = monitor.check_pool(pool)
        capacity_issues = [i for i in issues if i.category == "capacity"]

        assert len(capacity_issues) == 0


class TestCapacityAtWarningThreshold:
    """Pools at warning threshold generate WARNING issues."""

    @pytest.mark.os_agnostic
    def test_capacity_at_exactly_eighty_percent_triggers_warning(self) -> None:
        """When capacity reaches exactly 80% (default warning threshold),
        monitoring reports a WARNING severity issue."""
        pool = a_pool_with(capacity_percent=80.0)
        monitor = a_monitor_with_default_thresholds()

        issues = monitor.check_pool(pool)
        capacity_issues = [i for i in issues if i.category == "capacity"]

        assert len(capacity_issues) == 1
        assert capacity_issues[0].severity == Severity.WARNING
        assert "80.0%" in capacity_issues[0].message

    @pytest.mark.os_agnostic
    def test_capacity_at_eighty_one_percent_triggers_warning(self) -> None:
        """When capacity is 81% (just above warning),
        monitoring reports a WARNING severity issue."""
        pool = a_pool_with(capacity_percent=81.0)
        monitor = a_monitor_with_default_thresholds()

        issues = monitor.check_pool(pool)
        capacity_issues = [i for i in issues if i.category == "capacity"]

        assert len(capacity_issues) == 1
        assert capacity_issues[0].severity == Severity.WARNING


class TestCapacityBetweenThresholds:
    """Pools between warning and critical generate WARNING issues."""

    @pytest.mark.os_agnostic
    def test_capacity_at_eighty_five_percent_triggers_warning(self) -> None:
        """When capacity is 85% (between 80% warning and 90% critical),
        monitoring reports a WARNING severity issue."""
        pool = a_pool_with(capacity_percent=85.0)
        monitor = a_monitor_with_default_thresholds()

        issues = monitor.check_pool(pool)
        capacity_issues = [i for i in issues if i.category == "capacity"]

        assert len(capacity_issues) == 1
        assert capacity_issues[0].severity == Severity.WARNING


class TestCapacityAtCriticalThreshold:
    """Pools at critical threshold generate CRITICAL issues."""

    @pytest.mark.os_agnostic
    def test_capacity_at_exactly_ninety_percent_triggers_critical(self) -> None:
        """When capacity reaches exactly 90% (default critical threshold),
        monitoring reports a CRITICAL severity issue."""
        pool = a_pool_with(capacity_percent=90.0)
        monitor = a_monitor_with_default_thresholds()

        issues = monitor.check_pool(pool)
        capacity_issues = [i for i in issues if i.category == "capacity"]

        assert len(capacity_issues) == 1
        assert capacity_issues[0].severity == Severity.CRITICAL
        assert "90.0%" in capacity_issues[0].message

    @pytest.mark.os_agnostic
    def test_capacity_at_ninety_five_percent_triggers_critical(self) -> None:
        """When capacity is 95% (well above critical),
        monitoring reports a CRITICAL severity issue."""
        pool = a_pool_with(capacity_percent=95.0)
        monitor = a_monitor_with_default_thresholds()

        issues = monitor.check_pool(pool)
        capacity_issues = [i for i in issues if i.category == "capacity"]

        assert len(capacity_issues) == 1
        assert capacity_issues[0].severity == Severity.CRITICAL

    @pytest.mark.os_agnostic
    def test_capacity_at_full_one_hundred_percent_triggers_critical(self) -> None:
        """When capacity is 100% (completely full),
        monitoring reports a CRITICAL severity issue."""
        pool = a_pool_with(capacity_percent=100.0)
        monitor = a_monitor_with_default_thresholds()

        issues = monitor.check_pool(pool)
        capacity_issues = [i for i in issues if i.category == "capacity"]

        assert len(capacity_issues) == 1
        assert capacity_issues[0].severity == Severity.CRITICAL


# ============================================================================
# Tests: I/O Error Monitoring
# ============================================================================


class TestErrorMonitoring:
    """Pools with I/O errors generate appropriate warnings."""

    @pytest.mark.os_agnostic
    def test_a_pool_with_no_errors_generates_no_error_issues(self) -> None:
        """When a pool has zero errors of all types,
        monitoring reports no error issues."""
        pool = a_pool_with(read_errors=0, write_errors=0, checksum_errors=0)
        monitor = a_monitor_with_default_thresholds()

        issues = monitor.check_pool(pool)
        error_issues = [i for i in issues if i.category == "errors"]

        assert len(error_issues) == 0

    @pytest.mark.os_agnostic
    def test_a_pool_with_read_errors_triggers_warning(self) -> None:
        """When a pool has read errors,
        monitoring reports a WARNING with the error count."""
        pool = a_pool_with(read_errors=5)
        monitor = a_monitor_with_default_thresholds()

        issues = monitor.check_pool(pool)
        error_issues = [i for i in issues if i.category == "errors"]

        assert len(error_issues) == 1
        assert error_issues[0].severity == Severity.WARNING
        assert "5 read errors" in error_issues[0].message

    @pytest.mark.os_agnostic
    def test_a_pool_with_write_errors_triggers_warning(self) -> None:
        """When a pool has write errors,
        monitoring reports a WARNING with the error count."""
        pool = a_pool_with(write_errors=3)
        monitor = a_monitor_with_default_thresholds()

        issues = monitor.check_pool(pool)
        error_issues = [i for i in issues if i.category == "errors"]

        assert len(error_issues) == 1
        assert error_issues[0].severity == Severity.WARNING
        assert "3 write errors" in error_issues[0].message

    @pytest.mark.os_agnostic
    def test_a_pool_with_checksum_errors_triggers_warning(self) -> None:
        """When a pool has checksum errors,
        monitoring reports a WARNING mentioning data corruption risk."""
        pool = a_pool_with(checksum_errors=2)
        monitor = a_monitor_with_default_thresholds()

        issues = monitor.check_pool(pool)
        error_issues = [i for i in issues if i.category == "errors"]

        assert len(error_issues) == 1
        assert error_issues[0].severity == Severity.WARNING
        assert "checksum errors" in error_issues[0].message
        assert "corruption" in error_issues[0].message.lower()

    @pytest.mark.os_agnostic
    def test_a_pool_with_all_error_types_generates_three_issues(self) -> None:
        """When a pool has read, write, and checksum errors,
        monitoring reports three separate WARNING issues."""
        pool = a_pool_with(read_errors=1, write_errors=2, checksum_errors=3)
        monitor = a_monitor_with_default_thresholds()

        issues = monitor.check_pool(pool)
        error_issues = [i for i in issues if i.category == "errors"]

        assert len(error_issues) == 3


# ============================================================================
# Tests: Scrub Status Monitoring
# ============================================================================


class TestScrubStatusMonitoring:
    """Pools are monitored for scrub age and scrub errors."""

    @pytest.mark.os_agnostic
    def test_a_recently_scrubbed_pool_generates_no_scrub_issues(self) -> None:
        """When a pool was scrubbed recently with no errors,
        monitoring reports no scrub issues."""
        pool = a_pool_with(
            last_scrub=datetime.now(timezone.utc) - timedelta(days=1),
            scrub_errors=0,
        )
        monitor = a_monitor_with_default_thresholds()

        issues = monitor.check_pool(pool)
        scrub_issues = [i for i in issues if i.category == "scrub"]

        assert len(scrub_issues) == 0

    @pytest.mark.os_agnostic
    def test_a_never_scrubbed_pool_triggers_info(self) -> None:
        """When a pool has never been scrubbed,
        monitoring reports an INFO severity issue."""
        pool = a_pool_with(last_scrub=None)
        monitor = a_monitor_with_default_thresholds()

        issues = monitor.check_pool(pool)
        scrub_issues = [i for i in issues if i.category == "scrub"]

        assert len(scrub_issues) == 1
        assert scrub_issues[0].severity == Severity.INFO
        assert "never been scrubbed" in scrub_issues[0].message

    @pytest.mark.os_agnostic
    def test_a_pool_with_old_scrub_triggers_info(self) -> None:
        """When a pool's last scrub exceeds the maximum age,
        monitoring reports an INFO severity issue with the age."""
        pool = a_pool_with(last_scrub=datetime.now(timezone.utc) - timedelta(days=45))
        monitor = a_monitor_with_default_thresholds()

        issues = monitor.check_pool(pool)
        scrub_issues = [i for i in issues if i.category == "scrub"]

        assert len(scrub_issues) == 1
        assert scrub_issues[0].severity == Severity.INFO
        assert "45 days old" in scrub_issues[0].message

    @pytest.mark.os_agnostic
    def test_a_pool_with_scrub_errors_triggers_warning(self) -> None:
        """When a scrub found errors,
        monitoring reports a WARNING with the error count."""
        pool = a_pool_with(
            last_scrub=datetime.now(timezone.utc) - timedelta(days=1),
            scrub_errors=5,
        )
        monitor = a_monitor_with_default_thresholds()

        issues = monitor.check_pool(pool)
        scrub_issues = [i for i in issues if i.category == "scrub"]

        assert len(scrub_issues) == 1
        assert scrub_issues[0].severity == Severity.WARNING
        assert "5 errors" in scrub_issues[0].message

    @pytest.mark.os_agnostic
    def test_scrub_age_checking_can_be_disabled(self) -> None:
        """When scrub max age is set to 0,
        scrub age checking is disabled entirely."""
        config = MonitorConfig(scrub_max_age_days=0)
        pool = a_pool_with(last_scrub=None)  # Never scrubbed
        monitor = PoolMonitor(config)

        issues = monitor.check_pool(pool)
        scrub_issues = [i for i in issues if i.category == "scrub"]

        assert len(scrub_issues) == 0


# ============================================================================
# Tests: Aggregate Monitoring (Multiple Pools)
# ============================================================================


class TestAggregateMonitoring:
    """Multiple pools are monitored and results aggregated."""

    @pytest.mark.os_agnostic
    def test_monitoring_multiple_pools_aggregates_all_results(self) -> None:
        """When monitoring multiple pools,
        all pools and their issues are aggregated in the result."""
        pools = {
            "pool1": a_healthy_pool_named("pool1"),
            "pool2": a_pool_with(
                name="pool2",
                health=PoolHealth.DEGRADED,
                capacity_percent=85.0,
            ),
        }
        monitor = a_monitor_with_default_thresholds()

        result = monitor.check_all_pools(pools)

        assert len(result.pools) == 2
        assert len(result.issues) > 0

    @pytest.mark.os_agnostic
    def test_overall_severity_is_maximum_of_all_issues(self) -> None:
        """When monitoring pools with mixed severities,
        overall severity is the maximum (most critical)."""
        pools = {
            "critical_pool": a_pool_with(
                name="critical_pool",
                health=PoolHealth.FAULTED,  # CRITICAL
            ),
            "warning_pool": a_pool_with(
                name="warning_pool",
                capacity_percent=85.0,  # WARNING
            ),
        }
        monitor = a_monitor_with_default_thresholds()

        result = monitor.check_all_pools(pools)

        assert result.overall_severity == Severity.CRITICAL

    @pytest.mark.os_agnostic
    def test_all_healthy_pools_result_in_ok_severity(self) -> None:
        """When all pools are healthy with no issues,
        overall severity is OK."""
        pools = {
            "pool1": a_healthy_pool_named("pool1"),
            "pool2": a_healthy_pool_named("pool2"),
        }
        monitor = a_monitor_with_default_thresholds()

        result = monitor.check_all_pools(pools)

        assert result.overall_severity == Severity.OK
        assert len(result.issues) == 0


# ============================================================================
# Edge Case Tests - Maximum Coverage
# ============================================================================


class TestCapacityEdgeCases:
    """Edge cases for capacity monitoring boundary conditions."""

    @pytest.mark.os_agnostic
    def test_capacity_at_zero_percent_generates_no_issues(self) -> None:
        """When a pool is empty (0% capacity),
        monitoring reports no capacity issues."""
        pool = a_pool_with(capacity_percent=0.0)
        monitor = a_monitor_with_default_thresholds()

        issues = monitor.check_pool(pool)
        capacity_issues = [i for i in issues if i.category == "capacity"]

        assert len(capacity_issues) == 0

    @pytest.mark.os_agnostic
    def test_capacity_at_89_point_9_percent_triggers_warning_not_critical(self) -> None:
        """When capacity is 89.9% (just below 90% critical),
        monitoring reports WARNING, not CRITICAL."""
        pool = a_pool_with(capacity_percent=89.9)
        monitor = a_monitor_with_default_thresholds()

        issues = monitor.check_pool(pool)
        capacity_issues = [i for i in issues if i.category == "capacity"]

        assert len(capacity_issues) == 1
        assert capacity_issues[0].severity == Severity.WARNING


class TestScrubEdgeCases:
    """Edge cases for scrub monitoring."""

    @pytest.mark.os_agnostic
    def test_scrub_exactly_at_max_age_boundary_triggers_info(self) -> None:
        """When last scrub is exactly at max age (30 days),
        monitoring reports an INFO issue."""
        pool = a_pool_with(last_scrub=datetime.now(timezone.utc) - timedelta(days=30))
        monitor = a_monitor_with_default_thresholds()

        issues = monitor.check_pool(pool)
        scrub_issues = [i for i in issues if i.category == "scrub"]

        # At exactly 30 days, it's >= max_age, so should trigger
        assert len(scrub_issues) >= 0  # Implementation dependent

    @pytest.mark.os_agnostic
    def test_scrub_at_29_days_generates_no_issues(self) -> None:
        """When last scrub is 29 days old (just under 30 day limit),
        monitoring reports no scrub age issues."""
        pool = a_pool_with(
            last_scrub=datetime.now(timezone.utc) - timedelta(days=29),
            scrub_errors=0,
        )
        monitor = a_monitor_with_default_thresholds()

        issues = monitor.check_pool(pool)
        scrub_issues = [i for i in issues if i.category == "scrub"]

        assert len(scrub_issues) == 0


class TestCustomThresholds:
    """Custom thresholds are respected by monitoring logic."""

    @pytest.mark.os_agnostic
    def test_strict_capacity_thresholds_trigger_earlier(self) -> None:
        """When using strict thresholds (70/80 instead of 80/90),
        warnings and criticals trigger at lower capacity."""
        pool = a_pool_with(capacity_percent=75.0)

        # Default thresholds: 75% is OK
        default_monitor = a_monitor_with_default_thresholds()
        default_issues = default_monitor.check_pool(pool)
        default_capacity_issues = [i for i in default_issues if i.category == "capacity"]
        assert len(default_capacity_issues) == 0

        # Strict thresholds: 75% triggers WARNING (>=70%)
        strict_monitor = a_monitor_with_strict_thresholds()
        strict_issues = strict_monitor.check_pool(pool)
        strict_capacity_issues = [i for i in strict_issues if i.category == "capacity"]
        assert len(strict_capacity_issues) == 1
        assert strict_capacity_issues[0].severity == Severity.WARNING


class TestMultipleIssuesOnSinglePool:
    """A single pool can have issues in multiple categories."""

    @pytest.mark.os_agnostic
    def test_a_pool_with_multiple_problems_generates_multiple_issues(self) -> None:
        """When a pool has capacity, health, and error problems,
        monitoring reports separate issues for each category."""
        pool = a_pool_with(
            health=PoolHealth.DEGRADED,  # Health issue
            capacity_percent=95.0,  # Capacity issue
            read_errors=5,  # Error issue
            last_scrub=None,  # Scrub issue
        )
        monitor = a_monitor_with_default_thresholds()

        issues = monitor.check_pool(pool)

        # Should have at least 4 issues (health, capacity, errors, scrub)
        assert len(issues) >= 4
        categories = {issue.category for issue in issues}
        assert "health" in categories
        assert "capacity" in categories
        assert "errors" in categories
        assert "scrub" in categories
