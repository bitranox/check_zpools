"""Tests for output formatters.

Tests cover:
- JSON formatting with various result types
- Text formatting with issues and without issues
- Severity color mapping
- Exit code mapping

All tests are OS-agnostic (pure Python string formatting and JSON serialization).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from io import StringIO

from rich.console import Console

from check_zpools.formatters import (
    _format_last_scrub,
    display_check_result_text,
    format_check_result_json,
    format_check_result_text,
    get_exit_code_for_severity,
)
from check_zpools.models import CheckResult, PoolHealth, PoolIssue, PoolStatus, Severity


# ============================================================================
# Test Fixtures & Helpers
# ============================================================================


def a_healthy_pool_named(name: str) -> PoolStatus:
    """Create a healthy pool with sensible defaults."""
    return PoolStatus(
        name=name,
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


def a_pool_with(**overrides: object) -> PoolStatus:
    """Create a pool with specific attributes overridden."""
    defaults: dict[str, object] = {
        "name": "test-pool",
        "health": PoolHealth.ONLINE,
        "capacity_percent": 50.0,
        "size_bytes": 1024**4,
        "allocated_bytes": int(0.5 * 1024**4),
        "free_bytes": int(0.5 * 1024**4),
        "read_errors": 0,
        "write_errors": 0,
        "checksum_errors": 0,
        "last_scrub": datetime.now(UTC),
        "scrub_errors": 0,
        "scrub_in_progress": False,
    }
    return PoolStatus(**{**defaults, **overrides})  # type: ignore[arg-type]


def a_warning_issue_for(pool_name: str) -> PoolIssue:
    """Create a warning severity issue for capacity."""
    return PoolIssue(
        pool_name=pool_name,
        severity=Severity.WARNING,
        category="capacity",
        message="Pool capacity is high",
        details={"threshold": "80%", "current": "85%"},
    )


def a_critical_issue_for(pool_name: str) -> PoolIssue:
    """Create a critical severity issue for health."""
    return PoolIssue(
        pool_name=pool_name,
        severity=Severity.CRITICAL,
        category="health",
        message="Pool is degraded",
        details={"state": "DEGRADED"},
    )


def an_info_issue_for(pool_name: str) -> PoolIssue:
    """Create an info severity issue for scrub status."""
    return PoolIssue(
        pool_name=pool_name,
        severity=Severity.INFO,
        category="scrub",
        message="Scrub completed",
        details={},
    )


def an_issue_with(pool_name: str, severity: Severity, category: str, message: str) -> PoolIssue:
    """Create a custom issue with specific attributes."""
    return PoolIssue(
        pool_name=pool_name,
        severity=severity,
        category=category,
        message=message,
        details={},
    )


def a_check_result_with_no_issues() -> CheckResult:
    """Create a check result with healthy pool and no issues."""
    return CheckResult(
        timestamp=datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC),
        pools=[a_healthy_pool_named("rpool")],
        issues=[],
        overall_severity=Severity.OK,
    )


def a_check_result_with_warning() -> CheckResult:
    """Create a check result with one warning issue."""
    return CheckResult(
        timestamp=datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC),
        pools=[a_healthy_pool_named("rpool")],
        issues=[a_warning_issue_for("rpool")],
        overall_severity=Severity.WARNING,
    )


def a_check_result_with_critical() -> CheckResult:
    """Create a check result with one critical issue."""
    return CheckResult(
        timestamp=datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC),
        pools=[a_healthy_pool_named("rpool")],
        issues=[a_critical_issue_for("rpool")],
        overall_severity=Severity.CRITICAL,
    )


# ============================================================================
# Tests: JSON Formatting
# ============================================================================


class TestJsonFormattingWithNoIssues:
    """JSON formatter produces valid JSON for healthy pools."""

    @pytest.mark.os_agnostic
    def test_ok_result_produces_valid_json(self) -> None:
        """When formatting a check result with no issues,
        the output is valid, parseable JSON."""
        result = a_check_result_with_no_issues()

        json_output = format_check_result_json(result)
        data = json.loads(json_output)  # Should not raise

        assert isinstance(data, dict)

    @pytest.mark.os_agnostic
    def test_ok_result_includes_timestamp(self) -> None:
        """When formatting an OK result,
        the JSON includes the ISO 8601 timestamp."""
        result = a_check_result_with_no_issues()

        json_output = format_check_result_json(result)
        data = json.loads(json_output)

        assert data["timestamp"] == "2025-01-15T10:30:00+00:00"

    @pytest.mark.os_agnostic
    def test_ok_result_includes_overall_severity(self) -> None:
        """When formatting an OK result,
        the JSON includes overall_severity as 'OK'."""
        result = a_check_result_with_no_issues()

        json_output = format_check_result_json(result)
        data = json.loads(json_output)

        assert data["overall_severity"] == "OK"

    @pytest.mark.os_agnostic
    def test_ok_result_includes_pool_details(self) -> None:
        """When formatting an OK result,
        the JSON includes all pool attributes."""
        result = a_check_result_with_no_issues()

        json_output = format_check_result_json(result)
        data = json.loads(json_output)

        assert len(data["pools"]) == 1
        assert data["pools"][0]["name"] == "rpool"
        assert data["pools"][0]["health"] == "ONLINE"
        assert data["pools"][0]["capacity_percent"] == 50.0

    @pytest.mark.os_agnostic
    def test_ok_result_includes_empty_issues_list(self) -> None:
        """When formatting an OK result with no problems,
        the JSON includes an empty issues array."""
        result = a_check_result_with_no_issues()

        json_output = format_check_result_json(result)
        data = json.loads(json_output)

        assert data["issues"] == []


class TestJsonFormattingWithWarningIssues:
    """JSON formatter correctly formats WARNING severity issues."""

    @pytest.mark.os_agnostic
    def test_warning_result_includes_warning_severity(self) -> None:
        """When formatting a result with a warning,
        the overall_severity is 'WARNING'."""
        result = a_check_result_with_warning()

        json_output = format_check_result_json(result)
        data = json.loads(json_output)

        assert data["overall_severity"] == "WARNING"

    @pytest.mark.os_agnostic
    def test_warning_result_includes_issue_details(self) -> None:
        """When formatting a warning result,
        the JSON includes all issue attributes."""
        result = a_check_result_with_warning()

        json_output = format_check_result_json(result)
        data = json.loads(json_output)

        assert len(data["issues"]) == 1
        issue = data["issues"][0]
        assert issue["pool_name"] == "rpool"
        assert issue["severity"] == "WARNING"
        assert issue["category"] == "capacity"
        assert issue["message"] == "Pool capacity is high"

    @pytest.mark.os_agnostic
    def test_warning_result_includes_issue_detail_fields(self) -> None:
        """When formatting a warning with custom details,
        the JSON preserves the details dictionary."""
        result = a_check_result_with_warning()

        json_output = format_check_result_json(result)
        data = json.loads(json_output)

        assert data["issues"][0]["details"]["threshold"] == "80%"
        assert data["issues"][0]["details"]["current"] == "85%"


class TestJsonFormattingWithCriticalIssues:
    """JSON formatter correctly formats CRITICAL severity issues."""

    @pytest.mark.os_agnostic
    def test_critical_result_includes_critical_severity(self) -> None:
        """When formatting a result with a critical issue,
        the overall_severity is 'CRITICAL'."""
        result = a_check_result_with_critical()

        json_output = format_check_result_json(result)
        data = json.loads(json_output)

        assert data["overall_severity"] == "CRITICAL"

    @pytest.mark.os_agnostic
    def test_critical_result_includes_health_category(self) -> None:
        """When formatting a critical health issue,
        the JSON includes the 'health' category."""
        result = a_check_result_with_critical()

        json_output = format_check_result_json(result)
        data = json.loads(json_output)

        assert len(data["issues"]) == 1
        assert data["issues"][0]["severity"] == "CRITICAL"
        assert data["issues"][0]["category"] == "health"


class TestJsonFormattingWithMultipleEntities:
    """JSON formatter handles multiple pools and issues correctly."""

    @pytest.mark.os_agnostic
    def test_multiple_pools_appear_in_json_array(self) -> None:
        """When formatting a result with multiple pools,
        the JSON includes all pools in the array."""
        pool1 = a_healthy_pool_named("rpool")
        pool2 = a_pool_with(name="tank", capacity_percent=30.0, last_scrub=None)

        result = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[pool1, pool2],
            issues=[],
            overall_severity=Severity.OK,
        )

        json_output = format_check_result_json(result)
        data = json.loads(json_output)

        assert len(data["pools"]) == 2
        assert data["pools"][0]["name"] == "rpool"
        assert data["pools"][1]["name"] == "tank"

    @pytest.mark.os_agnostic
    def test_multiple_issues_appear_in_json_array(self) -> None:
        """When formatting a result with multiple issues,
        the JSON includes all issues in order."""
        pool = a_healthy_pool_named("rpool")
        warning = a_warning_issue_for("rpool")
        critical = a_critical_issue_for("rpool")

        result = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[pool],
            issues=[warning, critical],
            overall_severity=Severity.CRITICAL,
        )

        json_output = format_check_result_json(result)
        data = json.loads(json_output)

        assert len(data["issues"]) == 2
        assert data["issues"][0]["severity"] == "WARNING"
        assert data["issues"][1]["severity"] == "CRITICAL"


class TestJsonFormattingStyle:
    """JSON formatter produces human-readable pretty-printed output."""

    @pytest.mark.os_agnostic
    def test_json_output_is_pretty_printed_with_newlines(self) -> None:
        """When formatting any result,
        the JSON is pretty-printed with newlines."""
        result = a_check_result_with_no_issues()

        json_output = format_check_result_json(result)

        assert "\n" in json_output

    @pytest.mark.os_agnostic
    def test_json_output_uses_two_space_indentation(self) -> None:
        """When formatting any result,
        the JSON uses 2-space indentation."""
        result = a_check_result_with_no_issues()

        json_output = format_check_result_json(result)

        assert "  " in json_output


# ============================================================================
# Tests: Text Formatting
# ============================================================================


class TestTextFormattingWithNoIssues:
    """Text formatter produces human-readable output for healthy pools."""

    @pytest.mark.os_agnostic
    def test_ok_result_includes_header(self) -> None:
        """When formatting an OK result as text,
        the output includes a 'ZFS Pool Check' header."""
        result = a_check_result_with_no_issues()

        text = format_check_result_text(result)

        assert "ZFS Pool Check" in text

    @pytest.mark.os_agnostic
    def test_ok_result_includes_formatted_timestamp(self) -> None:
        """When formatting an OK result as text,
        the timestamp appears in human-readable format."""
        result = a_check_result_with_no_issues()

        text = format_check_result_text(result)

        assert "2025-01-15 10:30:00" in text

    @pytest.mark.os_agnostic
    def test_ok_result_shows_overall_status(self) -> None:
        """When formatting an OK result as text,
        the overall status is clearly labeled."""
        result = a_check_result_with_no_issues()

        text = format_check_result_text(result)

        assert "Overall Status: OK" in text

    @pytest.mark.os_agnostic
    def test_ok_result_shows_no_issues_message(self) -> None:
        """When formatting an OK result as text,
        a green 'No issues detected' message appears."""
        result = a_check_result_with_no_issues()

        text = format_check_result_text(result)

        assert "[green]No issues detected[/green]" in text

    @pytest.mark.os_agnostic
    def test_ok_result_shows_pool_count(self) -> None:
        """When formatting an OK result as text,
        the number of pools checked is displayed."""
        result = a_check_result_with_no_issues()

        text = format_check_result_text(result)

        assert "Pools Checked: 1" in text


class TestTextFormattingWithWarningIssues:
    """Text formatter colors WARNING issues in yellow."""

    @pytest.mark.os_agnostic
    def test_warning_result_shows_warning_status(self) -> None:
        """When formatting a warning result as text,
        the overall status is 'WARNING'."""
        result = a_check_result_with_warning()

        text = format_check_result_text(result)

        assert "Overall Status: WARNING" in text

    @pytest.mark.os_agnostic
    def test_warning_result_shows_issues_found_section(self) -> None:
        """When formatting a warning result as text,
        an 'Issues Found:' section appears."""
        result = a_check_result_with_warning()

        text = format_check_result_text(result)

        assert "Issues Found:" in text

    @pytest.mark.os_agnostic
    def test_warning_severity_appears_in_yellow(self) -> None:
        """When formatting a warning result as text,
        the WARNING severity is colored yellow."""
        result = a_check_result_with_warning()

        text = format_check_result_text(result)

        assert "[yellow]WARNING[/yellow]" in text

    @pytest.mark.os_agnostic
    def test_warning_result_includes_issue_message(self) -> None:
        """When formatting a warning result as text,
        the pool name and message appear."""
        result = a_check_result_with_warning()

        text = format_check_result_text(result)

        assert "rpool: Pool capacity is high" in text


class TestTextFormattingWithCriticalIssues:
    """Text formatter colors CRITICAL issues in red."""

    @pytest.mark.os_agnostic
    def test_critical_result_shows_critical_status(self) -> None:
        """When formatting a critical result as text,
        the overall status is 'CRITICAL'."""
        result = a_check_result_with_critical()

        text = format_check_result_text(result)

        assert "Overall Status: CRITICAL" in text

    @pytest.mark.os_agnostic
    def test_critical_severity_appears_in_red(self) -> None:
        """When formatting a critical result as text,
        the CRITICAL severity is colored red."""
        result = a_check_result_with_critical()

        text = format_check_result_text(result)

        assert "[red]CRITICAL[/red]" in text

    @pytest.mark.os_agnostic
    def test_critical_result_includes_issue_message(self) -> None:
        """When formatting a critical result as text,
        the pool name and degradation message appear."""
        result = a_check_result_with_critical()

        text = format_check_result_text(result)

        assert "rpool: Pool is degraded" in text


class TestTextFormattingWithInfoSeverity:
    """Text formatter colors INFO issues in green."""

    @pytest.mark.os_agnostic
    def test_info_severity_appears_in_green(self) -> None:
        """When formatting an info result as text,
        the INFO severity is colored green."""
        pool = a_healthy_pool_named("rpool")
        issue = an_info_issue_for("rpool")

        result = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[pool],
            issues=[issue],
            overall_severity=Severity.INFO,
        )

        text = format_check_result_text(result)

        assert "[green]INFO[/green]" in text

    @pytest.mark.os_agnostic
    def test_info_result_includes_message(self) -> None:
        """When formatting an info result as text,
        the informational message appears."""
        pool = a_healthy_pool_named("rpool")
        issue = an_info_issue_for("rpool")

        result = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[pool],
            issues=[issue],
            overall_severity=Severity.INFO,
        )

        text = format_check_result_text(result)

        assert "Scrub completed" in text


class TestTextFormattingWithMultipleIssues:
    """Text formatter displays all issues when multiple exist."""

    @pytest.mark.os_agnostic
    def test_multiple_issues_all_appear_in_output(self) -> None:
        """When formatting a result with multiple issues,
        all issue messages appear in the text."""
        pool = a_healthy_pool_named("rpool")
        issue1 = an_issue_with("rpool", Severity.WARNING, "capacity", "High capacity")
        issue2 = an_issue_with("rpool", Severity.CRITICAL, "health", "Degraded")

        result = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[pool],
            issues=[issue1, issue2],
            overall_severity=Severity.CRITICAL,
        )

        text = format_check_result_text(result)

        assert "High capacity" in text
        assert "Degraded" in text

    @pytest.mark.os_agnostic
    def test_multiple_issues_show_different_colors(self) -> None:
        """When formatting a result with mixed severities,
        each severity uses its appropriate color."""
        pool = a_healthy_pool_named("rpool")
        issue1 = an_issue_with("rpool", Severity.WARNING, "capacity", "High capacity")
        issue2 = an_issue_with("rpool", Severity.CRITICAL, "health", "Degraded")

        result = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[pool],
            issues=[issue1, issue2],
            overall_severity=Severity.CRITICAL,
        )

        text = format_check_result_text(result)

        assert "[yellow]WARNING[/yellow]" in text
        assert "[red]CRITICAL[/red]" in text


# ============================================================================
# Tests: Exit Code Mapping
# ============================================================================


class TestExitCodeMappingForOkAndInfo:
    """Exit codes for OK and INFO severities are zero."""

    @pytest.mark.os_agnostic
    def test_ok_severity_maps_to_exit_code_zero(self) -> None:
        """When severity is OK,
        the exit code is 0 (success)."""
        exit_code = get_exit_code_for_severity(Severity.OK)

        assert exit_code == 0

    @pytest.mark.os_agnostic
    def test_info_severity_maps_to_exit_code_zero(self) -> None:
        """When severity is INFO,
        the exit code is 0 (success)."""
        exit_code = get_exit_code_for_severity(Severity.INFO)

        assert exit_code == 0


class TestExitCodeMappingForWarning:
    """Exit code for WARNING severity is one."""

    @pytest.mark.os_agnostic
    def test_warning_severity_maps_to_exit_code_one(self) -> None:
        """When severity is WARNING,
        the exit code is 1 (warning)."""
        exit_code = get_exit_code_for_severity(Severity.WARNING)

        assert exit_code == 1


class TestExitCodeMappingForCritical:
    """Exit code for CRITICAL severity is two."""

    @pytest.mark.os_agnostic
    def test_critical_severity_maps_to_exit_code_two(self) -> None:
        """When severity is CRITICAL,
        the exit code is 2 (critical error)."""
        exit_code = get_exit_code_for_severity(Severity.CRITICAL)

        assert exit_code == 2


# ============================================================================
# Tests: Direct Console Display
# ============================================================================


class TestDisplayCheckResultTextWithNoIssues:
    """display_check_result_text() prints directly to console without ANSI code issues."""

    @pytest.mark.os_agnostic
    def test_display_includes_header_and_timestamp(self) -> None:
        """When displaying an OK result,
        the output includes header and formatted timestamp."""
        result = a_check_result_with_no_issues()
        buffer = StringIO()
        console = Console(file=buffer, legacy_windows=False)

        display_check_result_text(result, console)
        output = buffer.getvalue()

        assert "ZFS Pool Check" in output
        assert "2025-01-15 10:30:00" in output

    @pytest.mark.os_agnostic
    def test_display_shows_overall_status(self) -> None:
        """When displaying an OK result,
        the overall status appears."""
        result = a_check_result_with_no_issues()
        buffer = StringIO()
        console = Console(file=buffer, legacy_windows=False)

        display_check_result_text(result, console)
        output = buffer.getvalue()

        assert "Overall Status: OK" in output

    @pytest.mark.os_agnostic
    def test_display_shows_pool_status_table(self) -> None:
        """When displaying a result,
        a Pool Status table is rendered."""
        result = a_check_result_with_no_issues()
        buffer = StringIO()
        console = Console(file=buffer, legacy_windows=False)

        display_check_result_text(result, console)
        output = buffer.getvalue()

        assert "Pool Status" in output
        assert "rpool" in output

    @pytest.mark.os_agnostic
    def test_display_shows_no_issues_message(self) -> None:
        """When displaying an OK result,
        'No issues detected' message appears."""
        result = a_check_result_with_no_issues()
        buffer = StringIO()
        console = Console(file=buffer, legacy_windows=False)

        display_check_result_text(result, console)
        output = buffer.getvalue()

        assert "No issues detected" in output

    @pytest.mark.os_agnostic
    def test_display_shows_pools_checked_count(self) -> None:
        """When displaying any result,
        the pools checked count appears."""
        result = a_check_result_with_no_issues()
        buffer = StringIO()
        console = Console(file=buffer, legacy_windows=False)

        display_check_result_text(result, console)
        output = buffer.getvalue()

        assert "Pools Checked: 1" in output


class TestDisplayCheckResultTextWithIssues:
    """display_check_result_text() correctly formats issues with colors."""

    @pytest.mark.os_agnostic
    def test_display_shows_issues_found_section(self) -> None:
        """When displaying a result with issues,
        an 'Issues Found:' section appears."""
        result = a_check_result_with_warning()
        buffer = StringIO()
        console = Console(file=buffer, legacy_windows=False)

        display_check_result_text(result, console)
        output = buffer.getvalue()

        assert "Issues Found:" in output

    @pytest.mark.os_agnostic
    def test_display_shows_warning_issue_message(self) -> None:
        """When displaying a warning result,
        the issue message appears."""
        result = a_check_result_with_warning()
        buffer = StringIO()
        console = Console(file=buffer, legacy_windows=False)

        display_check_result_text(result, console)
        output = buffer.getvalue()

        assert "WARNING" in output
        assert "rpool: Pool capacity is high" in output

    @pytest.mark.os_agnostic
    def test_display_shows_critical_issue_message(self) -> None:
        """When displaying a critical result,
        the critical issue appears."""
        result = a_check_result_with_critical()
        buffer = StringIO()
        console = Console(file=buffer, legacy_windows=False)

        display_check_result_text(result, console)
        output = buffer.getvalue()

        assert "CRITICAL" in output
        assert "rpool: Pool is degraded" in output

    @pytest.mark.os_agnostic
    def test_display_shows_multiple_issues(self) -> None:
        """When displaying a result with multiple issues,
        all issues appear in output."""
        pool = a_healthy_pool_named("rpool")
        issue1 = an_issue_with("rpool", Severity.WARNING, "capacity", "High capacity")
        issue2 = an_issue_with("rpool", Severity.CRITICAL, "health", "Degraded")

        result = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[pool],
            issues=[issue1, issue2],
            overall_severity=Severity.CRITICAL,
        )

        buffer = StringIO()
        console = Console(file=buffer, legacy_windows=False)

        display_check_result_text(result, console)
        output = buffer.getvalue()

        assert "High capacity" in output
        assert "Degraded" in output


class TestDisplayCheckResultTextWithTableColumns:
    """display_check_result_text() includes all required table columns."""

    @pytest.mark.os_agnostic
    def test_table_includes_health_column(self) -> None:
        """When displaying pool status table,
        the Health column appears."""
        result = a_check_result_with_no_issues()
        buffer = StringIO()
        console = Console(file=buffer, legacy_windows=False)

        display_check_result_text(result, console)
        output = buffer.getvalue()

        assert "Health" in output
        assert "ONLINE" in output

    @pytest.mark.os_agnostic
    def test_table_includes_capacity_column(self) -> None:
        """When displaying pool status table,
        the Capacity column with percentage appears."""
        result = a_check_result_with_no_issues()
        buffer = StringIO()
        console = Console(file=buffer, legacy_windows=False)

        display_check_result_text(result, console)
        output = buffer.getvalue()

        # Column header may be truncated in narrow tables
        assert "Capaci" in output
        assert "50.0%" in output

    @pytest.mark.os_agnostic
    def test_table_includes_size_column_with_human_readable_format(self) -> None:
        """When displaying pool status table,
        the Size column shows human-readable size."""
        pool = a_pool_with(name="rpool", size_bytes=1024**4)  # 1 TB
        result = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[pool],
            issues=[],
            overall_severity=Severity.OK,
        )
        buffer = StringIO()
        console = Console(file=buffer, legacy_windows=False)

        display_check_result_text(result, console)
        output = buffer.getvalue()

        assert "Size" in output
        assert "1.00 TB" in output

    @pytest.mark.os_agnostic
    def test_table_includes_error_column(self) -> None:
        """When displaying pool status table,
        Errors (R/W/C) column appears."""
        result = a_check_result_with_no_issues()
        buffer = StringIO()
        console = Console(file=buffer, legacy_windows=False)

        display_check_result_text(result, console)
        output = buffer.getvalue()

        # Column header should contain "Errors" and "(R/W/C)"
        assert "Errors" in output
        assert "R/W/C" in output or "R/" in output  # May wrap

    @pytest.mark.os_agnostic
    def test_table_shows_pool_with_errors(self) -> None:
        """When displaying a pool with errors,
        error counts appear in the table."""
        pool = a_pool_with(
            name="tank",
            read_errors=5,
            write_errors=2,
            checksum_errors=1,
        )
        result = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[pool],
            issues=[],
            overall_severity=Severity.OK,
        )
        buffer = StringIO()
        console = Console(file=buffer, legacy_windows=False)

        display_check_result_text(result, console)
        output = buffer.getvalue()

        # Error counts should appear in R/W/C format
        assert "5/2/1" in output


class TestDisplayCheckResultTextWithMultiplePools:
    """display_check_result_text() handles multiple pools correctly."""

    @pytest.mark.os_agnostic
    def test_table_shows_all_pools(self) -> None:
        """When displaying multiple pools,
        all pool names appear in the table."""
        pool1 = a_healthy_pool_named("rpool")
        pool2 = a_pool_with(name="tank", capacity_percent=30.0, last_scrub=None)

        result = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[pool1, pool2],
            issues=[],
            overall_severity=Severity.OK,
        )

        buffer = StringIO()
        console = Console(file=buffer, legacy_windows=False)

        display_check_result_text(result, console)
        output = buffer.getvalue()

        assert "rpool" in output
        assert "tank" in output

    @pytest.mark.os_agnostic
    def test_pools_checked_count_matches_pool_count(self) -> None:
        """When displaying multiple pools,
        the pools checked count is correct."""
        pool1 = a_healthy_pool_named("rpool")
        pool2 = a_pool_with(name="tank", capacity_percent=30.0, last_scrub=None)

        result = CheckResult(
            timestamp=datetime.now(UTC),
            pools=[pool1, pool2],
            issues=[],
            overall_severity=Severity.OK,
        )

        buffer = StringIO()
        console = Console(file=buffer, legacy_windows=False)

        display_check_result_text(result, console)
        output = buffer.getvalue()

        assert "Pools Checked: 2" in output


class TestDisplayCheckResultTextDefaultConsole:
    """display_check_result_text() creates default console when none provided."""

    @pytest.mark.os_agnostic
    def test_can_call_without_console_parameter(self) -> None:
        """When calling display_check_result_text without console,
        it creates a default console and doesn't raise."""
        result = a_check_result_with_no_issues()

        # Should not raise - uses sys.stdout by default
        # We can't easily capture stdout here, so just verify it doesn't crash
        try:
            display_check_result_text(result)
            success = True
        except Exception:
            success = False

        assert success


# ============================================================================
# Test _format_last_scrub Helper Function
# ============================================================================


class TestFormatLastScrub:
    """Test _format_last_scrub helper function for relative time formatting."""

    @pytest.mark.os_agnostic
    def test_none_returns_never_yellow(self) -> None:
        """When last_scrub is None,
        returns 'Never' in yellow color."""
        text, color = _format_last_scrub(None)

        assert text == "Never"
        assert color == "yellow"

    @pytest.mark.os_agnostic
    def test_today_returns_green(self) -> None:
        """When last_scrub is today,
        returns 'Today' in green color."""
        from datetime import timezone

        now = datetime.now(timezone.utc)
        text, color = _format_last_scrub(now)

        assert text == "Today"
        assert color == "green"

    @pytest.mark.os_agnostic
    def test_yesterday_returns_green(self) -> None:
        """When last_scrub was yesterday,
        returns 'Yesterday' in green color."""
        from datetime import timedelta, timezone

        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        text, color = _format_last_scrub(yesterday)

        assert text == "Yesterday"
        assert color == "green"

    @pytest.mark.os_agnostic
    def test_three_days_ago_returns_green(self) -> None:
        """When last_scrub was 3 days ago,
        returns '3d ago' in green color."""
        from datetime import timedelta, timezone

        three_days = datetime.now(timezone.utc) - timedelta(days=3)
        text, color = _format_last_scrub(three_days)

        assert text == "3d ago"
        assert color == "green"

    @pytest.mark.os_agnostic
    def test_six_days_ago_returns_green(self) -> None:
        """When last_scrub was 6 days ago (< 1 week),
        returns '6d ago' in green color."""
        from datetime import timedelta, timezone

        six_days = datetime.now(timezone.utc) - timedelta(days=6)
        text, color = _format_last_scrub(six_days)

        assert text == "6d ago"
        assert color == "green"

    @pytest.mark.os_agnostic
    def test_two_weeks_ago_returns_green(self) -> None:
        """When last_scrub was 2 weeks ago (14 days),
        returns '2w ago' in green color."""
        from datetime import timedelta, timezone

        two_weeks = datetime.now(timezone.utc) - timedelta(days=14)
        text, color = _format_last_scrub(two_weeks)

        assert text == "2w ago"
        assert color == "green"

    @pytest.mark.os_agnostic
    def test_29_days_ago_returns_green(self) -> None:
        """When last_scrub was 29 days ago (< 30 days),
        returns '4w ago' in green color."""
        from datetime import timedelta, timezone

        twenty_nine_days = datetime.now(timezone.utc) - timedelta(days=29)
        text, color = _format_last_scrub(twenty_nine_days)

        assert text == "4w ago"
        assert color == "green"

    @pytest.mark.os_agnostic
    def test_45_days_ago_returns_yellow(self) -> None:
        """When last_scrub was 45 days ago (30-60 days),
        returns '45d ago' in yellow color."""
        from datetime import timedelta, timezone

        forty_five_days = datetime.now(timezone.utc) - timedelta(days=45)
        text, color = _format_last_scrub(forty_five_days)

        assert text == "45d ago"
        assert color == "yellow"

    @pytest.mark.os_agnostic
    def test_59_days_ago_returns_yellow(self) -> None:
        """When last_scrub was 59 days ago (just under 60 days),
        returns '59d ago' in yellow color."""
        from datetime import timedelta, timezone

        fifty_nine_days = datetime.now(timezone.utc) - timedelta(days=59)
        text, color = _format_last_scrub(fifty_nine_days)

        assert text == "59d ago"
        assert color == "yellow"

    @pytest.mark.os_agnostic
    def test_90_days_ago_returns_red(self) -> None:
        """When last_scrub was 90 days ago (3 months),
        returns '3mo ago' in red color."""
        from datetime import timedelta, timezone

        ninety_days = datetime.now(timezone.utc) - timedelta(days=90)
        text, color = _format_last_scrub(ninety_days)

        assert text == "3mo ago"
        assert color == "red"

    @pytest.mark.os_agnostic
    def test_180_days_ago_returns_red(self) -> None:
        """When last_scrub was 180 days ago (6 months),
        returns '6mo ago' in red color."""
        from datetime import timedelta, timezone

        half_year = datetime.now(timezone.utc) - timedelta(days=180)
        text, color = _format_last_scrub(half_year)

        assert text == "6mo ago"
        assert color == "red"

    @pytest.mark.os_agnostic
    def test_naive_datetime_is_treated_as_utc(self) -> None:
        """When last_scrub is a naive datetime,
        it's treated as UTC and formatted correctly."""
        from datetime import timedelta

        # Create naive datetime (no timezone)
        naive_dt = datetime.now() - timedelta(days=5)

        text, color = _format_last_scrub(naive_dt)

        # Should format as "5d ago" or similar (depending on system timezone)
        # But should not crash or raise exception
        assert "ago" in text or text == "Today" or text == "Yesterday"
        assert color in ("green", "yellow", "red")

    @pytest.mark.os_agnostic
    def test_timezone_aware_datetime_converted_to_utc(self) -> None:
        """When last_scrub is timezone-aware,
        it's correctly converted to UTC for calculation."""
        from datetime import timedelta, timezone

        # Create a datetime 10 days ago in UTC
        ten_days_utc = datetime.now(timezone.utc) - timedelta(days=10)

        text, color = _format_last_scrub(ten_days_utc)

        assert text == "1w ago"
        assert color == "green"

    @pytest.mark.os_agnostic
    def test_boundary_7_days_shows_weeks(self) -> None:
        """When last_scrub is exactly 7 days ago,
        returns '1w ago' not '7d ago'."""
        from datetime import timedelta, timezone

        seven_days = datetime.now(timezone.utc) - timedelta(days=7)
        text, color = _format_last_scrub(seven_days)

        assert text == "1w ago"
        assert color == "green"

    @pytest.mark.os_agnostic
    def test_boundary_30_days_shows_days_not_months(self) -> None:
        """When last_scrub is exactly 30 days ago,
        returns days in yellow (not months in red)."""
        from datetime import timedelta, timezone

        thirty_days = datetime.now(timezone.utc) - timedelta(days=30)
        text, color = _format_last_scrub(thirty_days)

        assert text == "30d ago"
        assert color == "yellow"

    @pytest.mark.os_agnostic
    def test_boundary_60_days_shows_months(self) -> None:
        """When last_scrub is exactly 60 days ago,
        returns '2mo ago' in red."""
        from datetime import timedelta, timezone

        sixty_days = datetime.now(timezone.utc) - timedelta(days=60)
        text, color = _format_last_scrub(sixty_days)

        assert text == "2mo ago"
        assert color == "red"
