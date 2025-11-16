"""Tests for ZFS data models.

Purpose
-------
Validate data model behavior, enumeration values, helper methods, and
immutability constraints. Ensures models provide correct type safety
and convenience methods.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from check_zpools.models import CheckResult, PoolHealth, PoolIssue, PoolStatus, Severity


class TestPoolHealth:
    """Tests for PoolHealth enumeration."""

    def test_all_health_states_defined(self) -> None:
        """Verify all expected ZFS health states are enumerated."""
        expected_states = {"ONLINE", "DEGRADED", "FAULTED", "OFFLINE", "UNAVAIL", "REMOVED"}
        actual_states = {state.value for state in PoolHealth}
        assert actual_states == expected_states

    def test_health_from_string(self) -> None:
        """Verify health states can be constructed from strings."""
        assert PoolHealth("ONLINE") == PoolHealth.ONLINE
        assert PoolHealth("DEGRADED") == PoolHealth.DEGRADED
        assert PoolHealth("FAULTED") == PoolHealth.FAULTED

    def test_invalid_health_raises_error(self) -> None:
        """Verify invalid health state raises ValueError."""
        with pytest.raises(ValueError):
            PoolHealth("INVALID_STATE")  # type: ignore[call-overload]

    def test_is_healthy_only_true_for_online(self) -> None:
        """Verify is_healthy() returns True only for ONLINE."""
        assert PoolHealth.ONLINE.is_healthy() is True
        assert PoolHealth.DEGRADED.is_healthy() is False
        assert PoolHealth.FAULTED.is_healthy() is False
        assert PoolHealth.OFFLINE.is_healthy() is False
        assert PoolHealth.UNAVAIL.is_healthy() is False
        assert PoolHealth.REMOVED.is_healthy() is False

    def test_is_critical_for_severe_states(self) -> None:
        """Verify is_critical() returns True for FAULTED, UNAVAIL, REMOVED."""
        assert PoolHealth.FAULTED.is_critical() is True
        assert PoolHealth.UNAVAIL.is_critical() is True
        assert PoolHealth.REMOVED.is_critical() is True
        assert PoolHealth.ONLINE.is_critical() is False
        assert PoolHealth.DEGRADED.is_critical() is False
        assert PoolHealth.OFFLINE.is_critical() is False


class TestSeverity:
    """Tests for Severity enumeration."""

    def test_all_severities_defined(self) -> None:
        """Verify all expected severity levels are enumerated."""
        expected_severities = {"OK", "INFO", "WARNING", "CRITICAL"}
        actual_severities = {sev.value for sev in Severity}
        assert actual_severities == expected_severities

    def test_severity_ordering(self) -> None:
        """Verify severity levels can be compared and ordered."""
        assert Severity.OK < Severity.INFO
        assert Severity.INFO < Severity.WARNING
        assert Severity.WARNING < Severity.CRITICAL
        assert Severity.CRITICAL > Severity.OK

    def test_max_severity_returns_highest(self) -> None:
        """Verify max() returns highest severity."""
        severities = [Severity.INFO, Severity.CRITICAL, Severity.WARNING, Severity.OK]
        assert max(severities) == Severity.CRITICAL

        severities2 = [Severity.OK, Severity.INFO, Severity.WARNING]
        assert max(severities2) == Severity.WARNING

    def test_severity_equality(self) -> None:
        """Verify severity equality comparisons."""
        assert Severity.CRITICAL == Severity.CRITICAL
        assert Severity.WARNING != Severity.CRITICAL


class TestPoolStatus:
    """Tests for PoolStatus dataclass."""

    def test_pool_status_creation(self) -> None:
        """Verify PoolStatus can be created with all fields."""
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
        assert pool.read_errors == 0
        assert pool.last_scrub == now

    def test_pool_status_is_frozen(self) -> None:
        """Verify PoolStatus is immutable (frozen dataclass)."""
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

        with pytest.raises(AttributeError):
            pool.name = "new_name"  # type: ignore[misc]

    def test_has_errors_detects_read_errors(self) -> None:
        """Verify has_errors() returns True for read errors."""
        pool = PoolStatus(
            name="test",
            health=PoolHealth.ONLINE,
            capacity_percent=50.0,
            size_bytes=1000,
            allocated_bytes=500,
            free_bytes=500,
            read_errors=1,
            write_errors=0,
            checksum_errors=0,
            last_scrub=None,
            scrub_errors=0,
            scrub_in_progress=False,
        )
        assert pool.has_errors() is True

    def test_has_errors_detects_write_errors(self) -> None:
        """Verify has_errors() returns True for write errors."""
        pool = PoolStatus(
            name="test",
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
        assert pool.has_errors() is True

    def test_has_errors_detects_checksum_errors(self) -> None:
        """Verify has_errors() returns True for checksum errors."""
        pool = PoolStatus(
            name="test",
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
        assert pool.has_errors() is True

    def test_has_errors_false_when_no_errors(self) -> None:
        """Verify has_errors() returns False when no errors present."""
        pool = PoolStatus(
            name="test",
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
        assert pool.has_errors() is False


class TestPoolIssue:
    """Tests for PoolIssue dataclass."""

    def test_pool_issue_creation(self) -> None:
        """Verify PoolIssue can be created with all fields."""
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

    def test_pool_issue_is_frozen(self) -> None:
        """Verify PoolIssue is immutable (frozen dataclass)."""
        issue = PoolIssue(
            pool_name="rpool",
            severity=Severity.WARNING,
            category="capacity",
            message="High capacity",
            details={},
        )

        with pytest.raises(AttributeError):
            issue.pool_name = "other"  # type: ignore[misc]

    def test_pool_issue_str_representation(self) -> None:
        """Verify PoolIssue has useful string representation."""
        issue = PoolIssue(
            pool_name="rpool",
            severity=Severity.WARNING,
            category="capacity",
            message="Pool at 85% capacity",
            details={},
        )

        assert str(issue) == "[WARNING] rpool: Pool at 85% capacity"
        assert "WARNING" in str(issue)
        assert "rpool" in str(issue)


class TestCheckResult:
    """Tests for CheckResult dataclass."""

    def test_check_result_creation(self) -> None:
        """Verify CheckResult can be created with all fields."""
        now = datetime.now(timezone.utc)
        pool = PoolStatus(
            name="rpool",
            health=PoolHealth.ONLINE,
            capacity_percent=45.0,
            size_bytes=1000,
            allocated_bytes=450,
            free_bytes=550,
            read_errors=0,
            write_errors=0,
            checksum_errors=0,
            last_scrub=None,
            scrub_errors=0,
            scrub_in_progress=False,
        )

        result = CheckResult(
            timestamp=now,
            pools=[pool],
            issues=[],
            overall_severity=Severity.OK,
        )

        assert result.timestamp == now
        assert len(result.pools) == 1
        assert len(result.issues) == 0
        assert result.overall_severity == Severity.OK

    def test_check_result_is_frozen(self) -> None:
        """Verify CheckResult is immutable (frozen dataclass)."""
        result = CheckResult(
            timestamp=datetime.now(timezone.utc),
            pools=[],
            issues=[],
            overall_severity=Severity.OK,
        )

        with pytest.raises(AttributeError):
            result.overall_severity = Severity.CRITICAL  # type: ignore[misc]

    def test_has_issues_returns_false_when_empty(self) -> None:
        """Verify has_issues() returns False for empty issues list."""
        result = CheckResult(
            timestamp=datetime.now(timezone.utc),
            pools=[],
            issues=[],
            overall_severity=Severity.OK,
        )
        assert result.has_issues() is False

    def test_has_issues_returns_true_when_issues_present(self) -> None:
        """Verify has_issues() returns True when issues exist."""
        issue = PoolIssue(
            pool_name="rpool",
            severity=Severity.WARNING,
            category="capacity",
            message="High usage",
            details={},
        )
        result = CheckResult(
            timestamp=datetime.now(timezone.utc),
            pools=[],
            issues=[issue],
            overall_severity=Severity.WARNING,
        )
        assert result.has_issues() is True

    def test_critical_issues_filters_correctly(self) -> None:
        """Verify critical_issues() returns only CRITICAL severity."""
        issue1 = PoolIssue("pool1", Severity.WARNING, "capacity", "High", {})
        issue2 = PoolIssue("pool2", Severity.CRITICAL, "health", "Faulted", {})
        issue3 = PoolIssue("pool3", Severity.INFO, "scrub", "Old scrub", {})

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

    def test_warning_issues_filters_correctly(self) -> None:
        """Verify warning_issues() returns only WARNING severity."""
        issue1 = PoolIssue("pool1", Severity.WARNING, "capacity", "High", {})
        issue2 = PoolIssue("pool2", Severity.CRITICAL, "health", "Faulted", {})
        issue3 = PoolIssue("pool3", Severity.WARNING, "errors", "I/O errors", {})

        result = CheckResult(
            timestamp=datetime.now(timezone.utc),
            pools=[],
            issues=[issue1, issue2, issue3],
            overall_severity=Severity.CRITICAL,
        )

        warnings = result.warning_issues()
        assert len(warnings) == 2
        assert all(issue.severity == Severity.WARNING for issue in warnings)

    def test_check_result_with_multiple_pools(self) -> None:
        """Verify CheckResult can contain multiple pools."""
        pool1 = PoolStatus(
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
        pool2 = PoolStatus(
            name="zpool-data",
            health=PoolHealth.DEGRADED,
            capacity_percent=85.0,
            size_bytes=5000,
            allocated_bytes=4250,
            free_bytes=750,
            read_errors=1,
            write_errors=0,
            checksum_errors=0,
            last_scrub=None,
            scrub_errors=0,
            scrub_in_progress=False,
        )

        result = CheckResult(
            timestamp=datetime.now(timezone.utc),
            pools=[pool1, pool2],
            issues=[],
            overall_severity=Severity.OK,
        )

        assert len(result.pools) == 2
        assert result.pools[0].name == "rpool"
        assert result.pools[1].name == "zpool-data"
