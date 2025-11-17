"""Tests for ZFS domain models - the foundation of our type system.

This module validates:
- PoolHealth enumeration and its query methods
- Severity enumeration with ordering semantics
- PoolStatus value object with error detection
- PoolIssue value object with string representation
- CheckResult aggregate with filtering capabilities

All tests here are pure domain logic - no I/O, no OS dependencies.
They run identically on Windows, macOS, and Linux.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from check_zpools.models import CheckResult, PoolHealth, PoolIssue, PoolStatus, Severity


# ============================================================================
# Test Fixtures & Builder Helpers
# ============================================================================


def a_healthy_pool_named(name: str) -> PoolStatus:
    """Create a healthy pool with realistic defaults.

    This pool is ONLINE with comfortable capacity and no errors.
    Use this when the pool's health is not the focus of your test.
    """
    return PoolStatus(
        name=name,
        health=PoolHealth.ONLINE,
        capacity_percent=45.0,
        size_bytes=1_000_000_000_000,  # 1 TB
        allocated_bytes=450_000_000_000,  # 450 GB
        free_bytes=550_000_000_000,  # 550 GB
        read_errors=0,
        write_errors=0,
        checksum_errors=0,
        last_scrub=datetime.now(timezone.utc),
        scrub_errors=0,
        scrub_in_progress=False,
    )


def a_pool_with(**overrides: object) -> PoolStatus:
    """Create a pool with specific attributes overridden.

    Use this when you need to test a specific pool characteristic.
    All unspecified fields get sensible defaults.

    Examples:
        a_pool_with(read_errors=5)
        a_pool_with(health=PoolHealth.DEGRADED, capacity_percent=92.5)
    """
    defaults: dict[str, object] = {
        "name": "test-pool",
        "health": PoolHealth.ONLINE,
        "capacity_percent": 50.0,
        "size_bytes": 1_000_000_000_000,
        "allocated_bytes": 500_000_000_000,
        "free_bytes": 500_000_000_000,
        "read_errors": 0,
        "write_errors": 0,
        "checksum_errors": 0,
        "last_scrub": None,
        "scrub_errors": 0,
        "scrub_in_progress": False,
    }
    return PoolStatus(**{**defaults, **overrides})  # type: ignore[arg-type]


def an_issue_for_pool(
    pool_name: str,
    severity: Severity,
    category: str,
    message: str,
) -> PoolIssue:
    """Create a pool issue with the given attributes."""
    return PoolIssue(
        pool_name=pool_name,
        severity=severity,
        category=category,
        message=message,
        details={},
    )


# ============================================================================
# Tests: PoolHealth Enumeration
# ============================================================================


class TestPoolHealthStates:
    """The six ZFS health states are recognized and queryable."""

    @pytest.mark.os_agnostic
    def test_all_six_zfs_health_states_exist(self) -> None:
        """ZFS defines exactly six health states.

        These mirror the states that 'zpool status' can report:
        ONLINE, DEGRADED, FAULTED, OFFLINE, UNAVAIL, REMOVED.
        """
        expected = {"ONLINE", "DEGRADED", "FAULTED", "OFFLINE", "UNAVAIL", "REMOVED"}
        actual = {state.value for state in PoolHealth}

        assert actual == expected

    @pytest.mark.os_agnostic
    def test_health_states_can_be_constructed_from_strings(self) -> None:
        """When ZFS returns a health state as a string,
        we can construct the corresponding enum value."""
        assert PoolHealth("ONLINE") == PoolHealth.ONLINE
        assert PoolHealth("DEGRADED") == PoolHealth.DEGRADED
        assert PoolHealth("FAULTED") == PoolHealth.FAULTED

    @pytest.mark.os_agnostic
    def test_invalid_health_state_raises_value_error(self) -> None:
        """When given an unrecognized health state,
        the enum constructor raises ValueError."""
        with pytest.raises(ValueError):
            PoolHealth("INVALID_STATE")  # type: ignore[call-overload]


class TestPoolHealthQueries:
    """PoolHealth enum provides convenient query methods."""

    @pytest.mark.os_agnostic
    def test_only_online_is_considered_healthy(self) -> None:
        """Among all health states, only ONLINE represents a healthy pool."""
        assert PoolHealth.ONLINE.is_healthy() is True
        assert PoolHealth.DEGRADED.is_healthy() is False
        assert PoolHealth.FAULTED.is_healthy() is False
        assert PoolHealth.OFFLINE.is_healthy() is False
        assert PoolHealth.UNAVAIL.is_healthy() is False
        assert PoolHealth.REMOVED.is_healthy() is False

    @pytest.mark.os_agnostic
    def test_faulted_unavail_and_removed_are_critical(self) -> None:
        """The three most severe states are considered critical."""
        assert PoolHealth.FAULTED.is_critical() is True
        assert PoolHealth.UNAVAIL.is_critical() is True
        assert PoolHealth.REMOVED.is_critical() is True

    @pytest.mark.os_agnostic
    def test_online_degraded_and_offline_are_not_critical(self) -> None:
        """Less severe states are not considered critical."""
        assert PoolHealth.ONLINE.is_critical() is False
        assert PoolHealth.DEGRADED.is_critical() is False
        assert PoolHealth.OFFLINE.is_critical() is False


# ============================================================================
# Tests: Severity Enumeration
# ============================================================================


class TestSeverityLevels:
    """The four severity levels exist and are comparable."""

    @pytest.mark.os_agnostic
    def test_all_four_severity_levels_exist(self) -> None:
        """We define exactly four severity levels:
        OK, INFO, WARNING, CRITICAL."""
        expected = {"OK", "INFO", "WARNING", "CRITICAL"}
        actual = {sev.value for sev in Severity}

        assert actual == expected

    @pytest.mark.os_agnostic
    def test_severities_have_natural_ordering(self) -> None:
        """Severities can be compared: OK < INFO < WARNING < CRITICAL."""
        assert Severity.OK < Severity.INFO
        assert Severity.INFO < Severity.WARNING
        assert Severity.WARNING < Severity.CRITICAL
        assert Severity.CRITICAL > Severity.OK

    @pytest.mark.os_agnostic
    def test_max_returns_highest_severity(self) -> None:
        """When finding the maximum of multiple severities,
        the most critical one wins."""
        severities = [Severity.INFO, Severity.CRITICAL, Severity.WARNING, Severity.OK]
        assert max(severities) == Severity.CRITICAL

    @pytest.mark.os_agnostic
    def test_max_of_non_critical_severities_returns_highest(self) -> None:
        """Among WARNING, INFO, and OK, WARNING is highest."""
        severities = [Severity.OK, Severity.INFO, Severity.WARNING]
        assert max(severities) == Severity.WARNING

    @pytest.mark.os_agnostic
    def test_severities_support_equality_comparison(self) -> None:
        """Severities can be compared for equality."""
        assert Severity.CRITICAL == Severity.CRITICAL
        assert Severity.WARNING != Severity.CRITICAL


# ============================================================================
# Tests: PoolStatus Value Object
# ============================================================================


class TestPoolStatusCreation:
    """PoolStatus can be created with all required fields."""

    @pytest.mark.os_agnostic
    def test_a_pool_status_remembers_all_its_attributes(self) -> None:
        """When we create a PoolStatus with specific values,
        it faithfully preserves them all."""
        now = datetime.now(timezone.utc)

        pool = PoolStatus(
            name="rpool",
            health=PoolHealth.ONLINE,
            capacity_percent=45.2,
            size_bytes=1_000_000_000_000,
            allocated_bytes=452_000_000_000,
            free_bytes=548_000_000_000,
            read_errors=0,
            write_errors=0,
            checksum_errors=0,
            last_scrub=now,
            scrub_errors=0,
            scrub_in_progress=False,
        )

        assert pool.name == "rpool"
        assert pool.health == PoolHealth.ONLINE
        assert pool.capacity_percent == 45.2
        assert pool.size_bytes == 1_000_000_000_000
        assert pool.allocated_bytes == 452_000_000_000
        assert pool.free_bytes == 548_000_000_000
        assert pool.read_errors == 0
        assert pool.write_errors == 0
        assert pool.checksum_errors == 0
        assert pool.last_scrub == now
        assert pool.scrub_errors == 0
        assert pool.scrub_in_progress is False


class TestPoolStatusImmutability:
    """PoolStatus is a frozen value object - it cannot be modified."""

    @pytest.mark.os_agnostic
    def test_pool_name_cannot_be_changed_after_creation(self) -> None:
        """Once created, a pool's name is locked forever.
        Attempting to modify it raises AttributeError."""
        pool = a_healthy_pool_named("rpool")

        with pytest.raises(AttributeError):
            pool.name = "new_name"  # type: ignore[misc]

    @pytest.mark.os_agnostic
    def test_pool_health_cannot_be_modified(self) -> None:
        """The pool's health status is immutable."""
        pool = a_healthy_pool_named("test")

        with pytest.raises(AttributeError):
            pool.health = PoolHealth.DEGRADED  # type: ignore[misc]


class TestPoolStatusErrorDetection:
    """PoolStatus accurately reports whether it has I/O errors."""

    @pytest.mark.os_agnostic
    def test_a_pool_with_read_errors_knows_it_has_problems(self) -> None:
        """A pool with any read errors reports has_errors() as True."""
        pool = a_pool_with(read_errors=1)

        assert pool.has_errors() is True

    @pytest.mark.os_agnostic
    def test_a_pool_with_write_errors_knows_it_has_problems(self) -> None:
        """A pool with any write errors reports has_errors() as True."""
        pool = a_pool_with(write_errors=3)

        assert pool.has_errors() is True

    @pytest.mark.os_agnostic
    def test_a_pool_with_checksum_errors_knows_it_has_problems(self) -> None:
        """A pool with any checksum errors reports has_errors() as True."""
        pool = a_pool_with(checksum_errors=2)

        assert pool.has_errors() is True

    @pytest.mark.os_agnostic
    def test_a_pool_with_multiple_error_types_reports_errors(self) -> None:
        """A pool with several types of errors still reports has_errors() as True."""
        pool = a_pool_with(read_errors=1, write_errors=2, checksum_errors=3)

        assert pool.has_errors() is True

    @pytest.mark.os_agnostic
    def test_a_pool_with_zero_errors_is_error_free(self) -> None:
        """A pool with no I/O errors of any kind reports has_errors() as False."""
        pool = a_pool_with(read_errors=0, write_errors=0, checksum_errors=0)

        assert pool.has_errors() is False


# ============================================================================
# Tests: PoolIssue Value Object
# ============================================================================


class TestPoolIssueCreation:
    """PoolIssue captures a problem with a specific pool."""

    @pytest.mark.os_agnostic
    def test_an_issue_remembers_its_pool_and_severity(self) -> None:
        """When we create an issue for a pool,
        it remembers which pool and how severe the problem is."""
        issue = PoolIssue(
            pool_name="rpool",
            severity=Severity.CRITICAL,
            category="health",
            message="Pool is DEGRADED",
            details={"expected": "ONLINE", "actual": "DEGRADED"},
        )

        assert issue.pool_name == "rpool"
        assert issue.severity == Severity.CRITICAL
        assert issue.category == "health"
        assert issue.message == "Pool is DEGRADED"
        assert issue.details["expected"] == "ONLINE"
        assert issue.details["actual"] == "DEGRADED"


class TestPoolIssueImmutability:
    """PoolIssue is a frozen value object."""

    @pytest.mark.os_agnostic
    def test_issue_pool_name_cannot_be_changed(self) -> None:
        """Once created, an issue's pool name is immutable."""
        issue = an_issue_for_pool("rpool", Severity.WARNING, "capacity", "High usage")

        with pytest.raises(AttributeError):
            issue.pool_name = "other"  # type: ignore[misc]

    @pytest.mark.os_agnostic
    def test_issue_severity_cannot_be_modified(self) -> None:
        """An issue's severity level is locked at creation."""
        issue = an_issue_for_pool("rpool", Severity.WARNING, "capacity", "High usage")

        with pytest.raises(AttributeError):
            issue.severity = Severity.CRITICAL  # type: ignore[misc]


class TestPoolIssueStringRepresentation:
    """PoolIssue has a useful string representation for logging."""

    @pytest.mark.os_agnostic
    def test_issue_string_contains_severity_pool_and_message(self) -> None:
        """The string representation shows: [SEVERITY] pool_name: message."""
        issue = an_issue_for_pool("rpool", Severity.WARNING, "capacity", "Pool at 85% capacity")

        issue_str = str(issue)
        assert issue_str == "[WARNING] rpool: Pool at 85% capacity"

    @pytest.mark.os_agnostic
    def test_critical_issue_string_shows_critical_severity(self) -> None:
        """A critical issue clearly shows CRITICAL in its string representation."""
        issue = an_issue_for_pool("zpool", Severity.CRITICAL, "health", "Pool is FAULTED")

        assert "[CRITICAL]" in str(issue)
        assert "zpool" in str(issue)
        assert "FAULTED" in str(issue)


# ============================================================================
# Tests: CheckResult Aggregate
# ============================================================================


class TestCheckResultCreation:
    """CheckResult aggregates pools and issues from a monitoring check."""

    @pytest.mark.os_agnostic
    def test_a_check_result_remembers_timestamp_pools_and_issues(self) -> None:
        """When we create a check result,
        it preserves the timestamp, pools, issues, and overall severity."""
        now = datetime.now(timezone.utc)
        pool = a_healthy_pool_named("rpool")

        result = CheckResult(
            timestamp=now,
            pools=[pool],
            issues=[],
            overall_severity=Severity.OK,
        )

        assert result.timestamp == now
        assert len(result.pools) == 1
        assert result.pools[0].name == "rpool"
        assert len(result.issues) == 0
        assert result.overall_severity == Severity.OK


class TestCheckResultImmutability:
    """CheckResult is a frozen aggregate."""

    @pytest.mark.os_agnostic
    def test_overall_severity_cannot_be_changed(self) -> None:
        """Once a check result is created, its severity is immutable."""
        result = CheckResult(
            timestamp=datetime.now(timezone.utc),
            pools=[],
            issues=[],
            overall_severity=Severity.OK,
        )

        with pytest.raises(AttributeError):
            result.overall_severity = Severity.CRITICAL  # type: ignore[misc]


class TestCheckResultIssueQueries:
    """CheckResult provides convenient queries for issues."""

    @pytest.mark.os_agnostic
    def test_check_result_with_no_issues_reports_none(self) -> None:
        """When there are no issues, has_issues() returns False."""
        result = CheckResult(
            timestamp=datetime.now(timezone.utc),
            pools=[],
            issues=[],
            overall_severity=Severity.OK,
        )

        assert result.has_issues() is False

    @pytest.mark.os_agnostic
    def test_check_result_with_any_issue_reports_it(self) -> None:
        """When even one issue exists, has_issues() returns True."""
        issue = an_issue_for_pool("rpool", Severity.WARNING, "capacity", "High usage")
        result = CheckResult(
            timestamp=datetime.now(timezone.utc),
            pools=[],
            issues=[issue],
            overall_severity=Severity.WARNING,
        )

        assert result.has_issues() is True


class TestCheckResultIssueFiltering:
    """CheckResult can filter issues by severity."""

    @pytest.mark.os_agnostic
    def test_critical_issues_returns_only_critical_severity(self) -> None:
        """critical_issues() filters to only CRITICAL severity issues."""
        issue1 = an_issue_for_pool("pool1", Severity.WARNING, "capacity", "High")
        issue2 = an_issue_for_pool("pool2", Severity.CRITICAL, "health", "Faulted")
        issue3 = an_issue_for_pool("pool3", Severity.INFO, "scrub", "Old scrub")

        result = CheckResult(
            timestamp=datetime.now(timezone.utc),
            pools=[],
            issues=[issue1, issue2, issue3],
            overall_severity=Severity.CRITICAL,
        )

        critical = result.critical_issues()

        assert len(critical) == 1
        assert critical[0].severity == Severity.CRITICAL
        assert critical[0].pool_name == "pool2"

    @pytest.mark.os_agnostic
    def test_warning_issues_returns_only_warning_severity(self) -> None:
        """warning_issues() filters to only WARNING severity issues."""
        issue1 = an_issue_for_pool("pool1", Severity.WARNING, "capacity", "High")
        issue2 = an_issue_for_pool("pool2", Severity.CRITICAL, "health", "Faulted")
        issue3 = an_issue_for_pool("pool3", Severity.WARNING, "errors", "I/O errors")

        result = CheckResult(
            timestamp=datetime.now(timezone.utc),
            pools=[],
            issues=[issue1, issue2, issue3],
            overall_severity=Severity.CRITICAL,
        )

        warnings = result.warning_issues()

        assert len(warnings) == 2
        assert all(issue.severity == Severity.WARNING for issue in warnings)
        assert {w.pool_name for w in warnings} == {"pool1", "pool3"}

    @pytest.mark.os_agnostic
    def test_filtering_with_no_matching_issues_returns_empty_list(self) -> None:
        """When no issues match the filter, an empty list is returned."""
        issue = an_issue_for_pool("pool1", Severity.INFO, "scrub", "Old")

        result = CheckResult(
            timestamp=datetime.now(timezone.utc),
            pools=[],
            issues=[issue],
            overall_severity=Severity.INFO,
        )

        assert result.critical_issues() == []
        assert result.warning_issues() == []


class TestCheckResultWithMultiplePools:
    """CheckResult can contain status for multiple pools."""

    @pytest.mark.os_agnostic
    def test_check_result_preserves_order_of_multiple_pools(self) -> None:
        """When multiple pools are included,
        they appear in the order they were given."""
        pool1 = a_pool_with(name="rpool", health=PoolHealth.ONLINE)
        pool2 = a_pool_with(name="zpool-data", health=PoolHealth.DEGRADED)
        pool3 = a_pool_with(name="backup-pool", health=PoolHealth.ONLINE)

        result = CheckResult(
            timestamp=datetime.now(timezone.utc),
            pools=[pool1, pool2, pool3],
            issues=[],
            overall_severity=Severity.OK,
        )

        assert len(result.pools) == 3
        assert result.pools[0].name == "rpool"
        assert result.pools[1].name == "zpool-data"
        assert result.pools[2].name == "backup-pool"


# ============================================================================
# Edge Case Tests - Maximum Coverage
# ============================================================================


class TestPoolStatusEdgeCases:
    """Edge cases and boundary conditions for PoolStatus."""

    @pytest.mark.os_agnostic
    def test_pool_with_zero_capacity_is_valid(self) -> None:
        """A pool can have 0% capacity (brand new, empty pool)."""
        pool = a_pool_with(
            capacity_percent=0.0,
            allocated_bytes=0,
            free_bytes=1_000_000_000_000,
        )

        assert pool.capacity_percent == 0.0
        assert pool.allocated_bytes == 0

    @pytest.mark.os_agnostic
    def test_pool_with_full_capacity_is_valid(self) -> None:
        """A pool can have 100% capacity (completely full)."""
        pool = a_pool_with(
            capacity_percent=100.0,
            allocated_bytes=1_000_000_000_000,
            free_bytes=0,
        )

        assert pool.capacity_percent == 100.0
        assert pool.free_bytes == 0

    @pytest.mark.os_agnostic
    def test_pool_with_no_last_scrub_is_valid(self) -> None:
        """A pool that has never been scrubbed has last_scrub=None."""
        pool = a_pool_with(last_scrub=None)

        assert pool.last_scrub is None

    @pytest.mark.os_agnostic
    def test_pool_with_scrub_in_progress_is_valid(self) -> None:
        """A pool can have a scrub currently running."""
        pool = a_pool_with(scrub_in_progress=True)

        assert pool.scrub_in_progress is True

    @pytest.mark.os_agnostic
    def test_pool_with_large_error_counts_is_valid(self) -> None:
        """Pools can accumulate large numbers of errors."""
        pool = a_pool_with(
            read_errors=9999,
            write_errors=8888,
            checksum_errors=7777,
        )

        assert pool.read_errors == 9999
        assert pool.write_errors == 8888
        assert pool.checksum_errors == 7777
        assert pool.has_errors() is True


class TestSeverityEdgeCases:
    """Edge cases for Severity comparisons."""

    @pytest.mark.os_agnostic
    def test_severity_ok_is_minimum(self) -> None:
        """OK is the lowest severity level."""
        assert Severity.OK < Severity.INFO
        assert Severity.OK < Severity.WARNING
        assert Severity.OK < Severity.CRITICAL

    @pytest.mark.os_agnostic
    def test_severity_critical_is_maximum(self) -> None:
        """CRITICAL is the highest severity level."""
        assert Severity.CRITICAL > Severity.WARNING
        assert Severity.CRITICAL > Severity.INFO
        assert Severity.CRITICAL > Severity.OK

    @pytest.mark.os_agnostic
    def test_max_of_single_severity_returns_that_severity(self) -> None:
        """max() of a single severity returns that severity."""
        assert max([Severity.WARNING]) == Severity.WARNING


class TestCheckResultEdgeCases:
    """Edge cases for CheckResult aggregate."""

    @pytest.mark.os_agnostic
    def test_check_result_with_empty_pools_list_is_valid(self) -> None:
        """A check result can have zero pools (e.g., ZFS not available)."""
        result = CheckResult(
            timestamp=datetime.now(timezone.utc),
            pools=[],
            issues=[],
            overall_severity=Severity.OK,
        )

        assert len(result.pools) == 0

    @pytest.mark.os_agnostic
    def test_check_result_with_many_issues_preserves_all(self) -> None:
        """A check result can contain many issues."""
        issues = [an_issue_for_pool(f"pool{i}", Severity.WARNING, "test", f"Issue {i}") for i in range(10)]

        result = CheckResult(
            timestamp=datetime.now(timezone.utc),
            pools=[],
            issues=issues,
            overall_severity=Severity.WARNING,
        )

        assert len(result.issues) == 10
        assert result.has_issues() is True
