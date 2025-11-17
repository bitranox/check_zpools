"""Tests for output formatters.

Tests cover:
- JSON formatting with various result types
- Text formatting with issues and without issues
- Severity color mapping
- Exit code mapping
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from check_zpools.formatters import (
    format_check_result_json,
    format_check_result_text,
    get_exit_code_for_severity,
)
from check_zpools.models import CheckResult, PoolHealth, PoolIssue, PoolStatus, Severity


@pytest.fixture
def healthy_pool() -> PoolStatus:
    """Create a healthy pool status."""
    return PoolStatus(
        name="rpool",
        health=PoolHealth.ONLINE,
        capacity_percent=50.0,
        size_bytes=1024**4,  # 1 TB
        allocated_bytes=int(0.5 * 1024**4),
        free_bytes=int(0.5 * 1024**4),
        read_errors=0,
        write_errors=0,
        checksum_errors=0,
        last_scrub=datetime.now(UTC),
        scrub_errors=0,
        scrub_in_progress=False,
    )


@pytest.fixture
def warning_issue() -> PoolIssue:
    """Create a warning severity issue."""
    return PoolIssue(
        pool_name="rpool",
        severity=Severity.WARNING,
        category="capacity",
        message="Pool capacity is high",
        details={"threshold": "80%", "current": "85%"},
    )


@pytest.fixture
def critical_issue() -> PoolIssue:
    """Create a critical severity issue."""
    return PoolIssue(
        pool_name="rpool",
        severity=Severity.CRITICAL,
        category="health",
        message="Pool is degraded",
        details={"state": "DEGRADED"},
    )


@pytest.fixture
def ok_check_result(healthy_pool: PoolStatus) -> CheckResult:
    """Create a check result with no issues."""
    return CheckResult(
        timestamp=datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC),
        pools=[healthy_pool],
        issues=[],
        overall_severity=Severity.OK,
    )


@pytest.fixture
def warning_check_result(healthy_pool: PoolStatus, warning_issue: PoolIssue) -> CheckResult:
    """Create a check result with warning issues."""
    return CheckResult(
        timestamp=datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC),
        pools=[healthy_pool],
        issues=[warning_issue],
        overall_severity=Severity.WARNING,
    )


@pytest.fixture
def critical_check_result(healthy_pool: PoolStatus, critical_issue: PoolIssue) -> CheckResult:
    """Create a check result with critical issues."""
    return CheckResult(
        timestamp=datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC),
        pools=[healthy_pool],
        issues=[critical_issue],
        overall_severity=Severity.CRITICAL,
    )


class TestFormatCheckResultJson:
    """Test JSON formatting of check results."""

    def test_format_ok_result(self, ok_check_result: CheckResult) -> None:
        """Should format OK result as valid JSON."""
        result = format_check_result_json(ok_check_result)

        # Parse JSON to verify it's valid
        data = json.loads(result)

        assert data["timestamp"] == "2025-01-15T10:30:00+00:00"
        assert data["overall_severity"] == "OK"
        assert len(data["pools"]) == 1
        assert data["pools"][0]["name"] == "rpool"
        assert data["pools"][0]["health"] == "ONLINE"
        assert data["pools"][0]["capacity_percent"] == 50.0
        assert data["issues"] == []

    def test_format_warning_result(self, warning_check_result: CheckResult) -> None:
        """Should format warning result with issue details."""
        result = format_check_result_json(warning_check_result)

        data = json.loads(result)

        assert data["overall_severity"] == "WARNING"
        assert len(data["issues"]) == 1
        assert data["issues"][0]["pool_name"] == "rpool"
        assert data["issues"][0]["severity"] == "WARNING"
        assert data["issues"][0]["category"] == "capacity"
        assert data["issues"][0]["message"] == "Pool capacity is high"
        assert data["issues"][0]["details"]["threshold"] == "80%"

    def test_format_critical_result(self, critical_check_result: CheckResult) -> None:
        """Should format critical result with issue details."""
        result = format_check_result_json(critical_check_result)

        data = json.loads(result)

        assert data["overall_severity"] == "CRITICAL"
        assert len(data["issues"]) == 1
        assert data["issues"][0]["severity"] == "CRITICAL"
        assert data["issues"][0]["category"] == "health"

    def test_format_multiple_pools(self, healthy_pool: PoolStatus) -> None:
        """Should format result with multiple pools."""
        pool2 = PoolStatus(
            name="tank",
            health=PoolHealth.ONLINE,
            capacity_percent=30.0,
            size_bytes=2 * 1024**4,
            allocated_bytes=int(0.3 * 2 * 1024**4),
            free_bytes=int(0.7 * 2 * 1024**4),
            read_errors=0,
            write_errors=0,
            checksum_errors=0,
            last_scrub=None,
            scrub_errors=0,
            scrub_in_progress=False,
        )

        result = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[healthy_pool, pool2],
            issues=[],
            overall_severity=Severity.OK,
        )

        json_output = format_check_result_json(result)
        data = json.loads(json_output)

        assert len(data["pools"]) == 2
        assert data["pools"][0]["name"] == "rpool"
        assert data["pools"][1]["name"] == "tank"

    def test_format_multiple_issues(self, healthy_pool: PoolStatus, warning_issue: PoolIssue, critical_issue: PoolIssue) -> None:
        """Should format result with multiple issues."""
        result = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[healthy_pool],
            issues=[warning_issue, critical_issue],
            overall_severity=Severity.CRITICAL,
        )

        json_output = format_check_result_json(result)
        data = json.loads(json_output)

        assert len(data["issues"]) == 2
        assert data["issues"][0]["severity"] == "WARNING"
        assert data["issues"][1]["severity"] == "CRITICAL"

    def test_json_is_pretty_printed(self, ok_check_result: CheckResult) -> None:
        """Should format JSON with indentation."""
        result = format_check_result_json(ok_check_result)

        # Pretty printed JSON should have newlines
        assert "\n" in result
        # Should have 2-space indentation
        assert "  " in result


class TestFormatCheckResultText:
    """Test text formatting of check results."""

    def test_format_ok_result(self, ok_check_result: CheckResult) -> None:
        """Should format OK result as human-readable text."""
        result = format_check_result_text(ok_check_result)

        assert "ZFS Pool Check" in result
        assert "2025-01-15 10:30:00" in result
        assert "Overall Status: OK" in result
        assert "[green]No issues detected[/green]" in result
        assert "Pools Checked: 1" in result

    def test_format_warning_result(self, warning_check_result: CheckResult) -> None:
        """Should format warning result with colored issue."""
        result = format_check_result_text(warning_check_result)

        assert "Overall Status: WARNING" in result
        assert "Issues Found:" in result
        assert "[yellow]WARNING[/yellow]" in result
        assert "rpool: Pool capacity is high" in result
        assert "Pools Checked: 1" in result

    def test_format_critical_result(self, critical_check_result: CheckResult) -> None:
        """Should format critical result with red color."""
        result = format_check_result_text(critical_check_result)

        assert "Overall Status: CRITICAL" in result
        assert "Issues Found:" in result
        assert "[red]CRITICAL[/red]" in result
        assert "rpool: Pool is degraded" in result

    def test_format_multiple_issues(self, healthy_pool: PoolStatus) -> None:
        """Should format all issues in result."""
        issue1 = PoolIssue(
            pool_name="rpool",
            severity=Severity.WARNING,
            category="capacity",
            message="High capacity",
            details={},
        )
        issue2 = PoolIssue(
            pool_name="rpool",
            severity=Severity.CRITICAL,
            category="health",
            message="Degraded",
            details={},
        )

        result = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[healthy_pool],
            issues=[issue1, issue2],
            overall_severity=Severity.CRITICAL,
        )

        text = format_check_result_text(result)

        assert "High capacity" in text
        assert "Degraded" in text
        assert "[yellow]WARNING[/yellow]" in text
        assert "[red]CRITICAL[/red]" in text

    def test_format_info_severity(self, healthy_pool: PoolStatus) -> None:
        """Should format INFO severity with green color."""
        issue = PoolIssue(
            pool_name="rpool",
            severity=Severity.INFO,
            category="scrub",
            message="Scrub completed",
            details={},
        )

        result = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[healthy_pool],
            issues=[issue],
            overall_severity=Severity.INFO,
        )

        text = format_check_result_text(result)

        assert "[green]INFO[/green]" in text
        assert "Scrub completed" in text


class TestGetExitCodeForSeverity:
    """Test exit code mapping for severities."""

    def test_ok_severity_returns_zero(self) -> None:
        """OK severity should return exit code 0."""
        assert get_exit_code_for_severity(Severity.OK) == 0

    def test_info_severity_returns_zero(self) -> None:
        """INFO severity should return exit code 0."""
        assert get_exit_code_for_severity(Severity.INFO) == 0

    def test_warning_severity_returns_one(self) -> None:
        """WARNING severity should return exit code 1."""
        assert get_exit_code_for_severity(Severity.WARNING) == 1

    def test_critical_severity_returns_two(self) -> None:
        """CRITICAL severity should return exit code 2."""
        assert get_exit_code_for_severity(Severity.CRITICAL) == 2
