"""Output formatters for CLI commands.

Purpose
-------
Provides formatting functions for various CLI outputs, keeping the CLI module
minimal and focused on command wiring. All heavy formatting logic is centralized
here following the Single Responsibility Principle.

Contents
--------
* :func:`format_check_result_json` - Format check results as JSON
* :func:`format_check_result_text` - Format check results as human-readable text
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

from rich.console import Console
from rich.table import Table

from .models import CheckResult, PoolIssue, PoolStatus, Severity


def format_check_result_json(result: CheckResult) -> str:
    """Format check result as JSON.

    Parameters
    ----------
    result:
        Check result to format.

    Returns
    -------
    str
        JSON-formatted string with indentation.
    """
    data = {
        "timestamp": result.timestamp.isoformat(),
        "pools": [
            {
                "name": pool.name,
                "health": pool.health.value,
                "capacity_percent": pool.capacity_percent,
            }
            for pool in result.pools
        ],
        "issues": [
            {
                "pool_name": issue.pool_name,
                "severity": issue.severity.value,
                "category": issue.category,
                "message": issue.message,
                "details": issue.details,
            }
            for issue in result.issues
        ],
        "overall_severity": result.overall_severity.value,
    }
    return json.dumps(data, indent=2)


def format_check_result_text(result: CheckResult) -> str:
    """Format check result as human-readable text.

    Parameters
    ----------
    result:
        Check result to format.

    Returns
    -------
    str
        Multi-line text output with Rich markup (NOT ANSI codes).

    Notes
    -----
    This function returns a string with Rich markup tags like [green]text[/green].
    The caller should use Rich Console.print() to render it, NOT click.echo().
    """
    lines: list[str] = []

    # Header
    timestamp_str = result.timestamp.strftime("%Y-%m-%d %H:%M:%S")
    lines.append(f"\nZFS Pool Check - {timestamp_str}")
    lines.append(f"Overall Status: {result.overall_severity.value.upper()}\n")

    # Pool Status Summary - we'll add this as a special marker
    # The table will be rendered separately in display_check_result_text()
    lines.append("__TABLE_PLACEHOLDER__")

    # Issues
    if result.issues:
        lines.append("\nIssues Found:")
        for issue in result.issues:
            severity_color = _get_severity_color(issue.severity)
            lines.append(f"  [{severity_color}]{issue.severity.value}[/{severity_color}] {issue.pool_name}: {issue.message}")
    else:
        lines.append("\n[green]No issues detected[/green]")

    # Summary
    lines.append(f"\nPools Checked: {len(result.pools)}")

    return "\n".join(lines)


def _build_pool_status_table() -> Table:
    """Create a Rich table for pool status display.

    Returns
    -------
    Table:
        Configured table with columns for pool status information.
    """
    table = Table(title="Pool Status", show_header=True, header_style="bold cyan")
    table.add_column("Pool", style="bold", no_wrap=True)
    table.add_column("Health", justify="center")
    table.add_column("Devices", justify="center")
    table.add_column("Capacity", justify="right")
    table.add_column("Size", justify="right")
    table.add_column("Errors (R/W/C)", justify="right")
    table.add_column("Last Scrub", justify="right")
    return table


def _get_capacity_color(capacity_percent: float) -> str:
    """Determine color for capacity display.

    Parameters
    ----------
    capacity_percent:
        Capacity percentage (0-100).

    Returns
    -------
    str:
        Color name for Rich markup.
    """
    if capacity_percent < 80:
        return "green"
    if capacity_percent < 90:
        return "yellow"
    return "red"


def _format_pool_size(size_bytes: int) -> str:
    """Format pool size in human-readable format.

    Parameters
    ----------
    size_bytes:
        Pool size in bytes.

    Returns
    -------
    str:
        Formatted size (e.g., "1.50 TB" or "500.00 GB").
    """
    size_gb = size_bytes / (1024**3)
    if size_gb >= 1024:
        size_tb = size_gb / 1024
        return f"{size_tb:.2f} TB"
    return f"{size_gb:.2f} GB"


def _format_pool_errors(read: int, write: int, checksum: int) -> str:
    """Format error counts as R/W/C string.

    Parameters
    ----------
    read:
        Read error count.
    write:
        Write error count.
    checksum:
        Checksum error count.

    Returns
    -------
    str:
        Formatted error string (e.g., "0/0/0").
    """
    return f"{read}/{write}/{checksum}"


def _format_faulted_devices(pool: PoolStatus) -> tuple[str, str]:
    """Format faulted devices count with color.

    Parameters
    ----------
    pool:
        Pool status to format.

    Returns
    -------
    tuple[str, str]:
        Tuple of (formatted_text, color_name).
    """
    faulted_count = len(pool.faulted_devices)
    if faulted_count == 0:
        return ("OK", "green")
    return (f"{faulted_count} FAULTED", "red")


def _format_pool_row(pool: PoolStatus) -> tuple[str, str, str, str, str, str, str]:
    """Format a pool status into table row data with Rich markup.

    Parameters
    ----------
    pool:
        Pool status to format.

    Returns
    -------
    tuple[str, str, str, str, str, str, str]:
        Formatted values for: name, health, devices, capacity, size, errors, scrub
    """
    # Determine colors
    health_color = "green" if pool.health.is_healthy() else "red"
    capacity_color = _get_capacity_color(pool.capacity_percent)
    error_color = "green" if not pool.has_errors() else "red"

    # Format components
    size_str = _format_pool_size(pool.size_bytes)
    errors_str = _format_pool_errors(pool.read_errors, pool.write_errors, pool.checksum_errors)
    scrub_text, scrub_color = _format_last_scrub(pool.last_scrub)
    devices_text, devices_color = _format_faulted_devices(pool)

    return (
        pool.name,
        f"[{health_color}]{pool.health.value}[/{health_color}]",
        f"[{devices_color}]{devices_text}[/{devices_color}]",
        f"[{capacity_color}]{pool.capacity_percent:.1f}%[/{capacity_color}]",
        size_str,
        f"[{error_color}]{errors_str}[/{error_color}]",
        f"[{scrub_color}]{scrub_text}[/{scrub_color}]",
    )


def _display_issues(issues: list[PoolIssue], console: Console) -> None:
    """Display issues list to console.

    Parameters
    ----------
    issues:
        List of pool issues to display.
    console:
        Rich Console instance for output.
    """
    if issues:
        console.print("\nIssues Found:")
        for issue in issues:
            severity_color = _get_severity_color(issue.severity)
            console.print(f"  [{severity_color}]{issue.severity.value}[/{severity_color}] {issue.pool_name}: {issue.message}")
    else:
        console.print("\n[green]No issues detected[/green]")


def display_check_result_text(result: CheckResult, console: Console | None = None) -> None:
    """Display check result as formatted text output directly to console.

    Parameters
    ----------
    result:
        Check result to display.
    console:
        Rich Console instance to use for output. If None, creates a new one
        writing to stdout.

    Notes
    -----
    This function directly prints to the console rather than returning a string.
    This avoids issues with mixed ANSI codes and Rich markup.
    """
    if console is None:
        console = Console(file=sys.stdout, legacy_windows=False)

    # Header
    timestamp_str = result.timestamp.strftime("%Y-%m-%d %H:%M:%S")
    console.print(f"\nZFS Pool Check - {timestamp_str}")
    console.print(f"Overall Status: {result.overall_severity.value.upper()}\n")

    # Build and populate pool status table
    table = _build_pool_status_table()
    for pool in result.pools:
        table.add_row(*_format_pool_row(pool))
    console.print(table)

    # Display issues
    _display_issues(result.issues, console)

    # Summary
    console.print(f"\nPools Checked: {len(result.pools)}")


def _make_timezone_aware(dt: datetime) -> datetime:
    """Ensure datetime is timezone-aware (UTC).

    Parameters
    ----------
    dt:
        Datetime to make aware.

    Returns
    -------
    datetime
        Timezone-aware datetime in UTC.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _calculate_scrub_age_days(last_scrub: datetime) -> int:
    """Calculate age of last scrub in days.

    Parameters
    ----------
    last_scrub:
        Timestamp of last scrub.

    Returns
    -------
    int
        Number of days since last scrub.
    """
    now = datetime.now(timezone.utc)
    last_scrub_aware = _make_timezone_aware(last_scrub)
    delta = now - last_scrub_aware
    return delta.days


def _format_scrub_age(days: int) -> tuple[str, str]:
    """Format scrub age as relative time with color.

    Parameters
    ----------
    days:
        Age in days.

    Returns
    -------
    tuple[str, str]
        Tuple of (formatted_text, color_name).
    """
    if days == 0:
        return ("Today", "green")
    if days == 1:
        return ("Yesterday", "green")
    if days < 7:
        return (f"{days}d ago", "green")
    if days < 30:
        weeks = days // 7
        return (f"{weeks}w ago", "green")
    if days < 60:
        return (f"{days}d ago", "yellow")  # Warning: approaching 2 months

    months = days // 30
    return (f"{months}mo ago", "red")  # Critical: very old scrub


def _format_last_scrub(last_scrub: datetime | None) -> tuple[str, str]:
    """Format last scrub timestamp as relative time with color coding.

    Parameters
    ----------
    last_scrub:
        Timestamp of last scrub, or None if never scrubbed.

    Returns
    -------
    tuple[str, str]
        Tuple of (formatted_text, color_name).
        - formatted_text: Human-readable relative time or "Never"
        - color_name: Color for Rich markup based on age
    """
    if last_scrub is None:
        return ("Never", "yellow")

    days = _calculate_scrub_age_days(last_scrub)
    return _format_scrub_age(days)


def _get_severity_color(severity: Severity) -> str:
    """Map severity to color name for rich markup.

    Parameters
    ----------
    severity:
        Severity level.

    Returns
    -------
    str
        Color name for rich console markup.
    """
    if severity.is_critical():
        return "red"
    elif severity.value == "WARNING":
        return "yellow"
    else:
        return "green"


def get_exit_code_for_severity(severity: Severity) -> int:
    """Map severity to exit code.

    Parameters
    ----------
    severity:
        Overall severity level.

    Returns
    -------
    int
        Exit code: 0=OK, 1=WARNING, 2=CRITICAL.
    """
    if severity.is_critical():
        return 2
    elif severity.value == "WARNING":
        return 1
    else:
        return 0


__all__ = [
    "format_check_result_json",
    "format_check_result_text",
    "display_check_result_text",
    "get_exit_code_for_severity",
]
