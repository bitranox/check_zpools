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
    table.add_column("Capacity", justify="right")
    table.add_column("Size", justify="right")
    table.add_column("Errors (R/W/C)", justify="right")
    table.add_column("Last Scrub", justify="right")
    return table


def _format_pool_row(pool: PoolStatus) -> tuple[str, str, str, str, str, str]:
    """Format a pool status into table row data with Rich markup.

    Parameters
    ----------
    pool:
        Pool status to format.

    Returns
    -------
    tuple[str, str, str, str, str, str]:
        Formatted values for: name, health, capacity, size, errors, scrub
    """
    # Determine colors
    health_color = "green" if pool.health.is_healthy() else "red"
    capacity_color = "green" if pool.capacity_percent < 80 else ("yellow" if pool.capacity_percent < 90 else "red")
    error_color = "green" if not pool.has_errors() else "red"

    # Format size in human-readable format
    size_gb = pool.size_bytes / (1024**3)
    if size_gb >= 1024:
        size_tb = size_gb / 1024
        size_str = f"{size_tb:.2f} TB"
    else:
        size_str = f"{size_gb:.2f} GB"

    # Format errors as R/W/C
    errors_str = f"{pool.read_errors}/{pool.write_errors}/{pool.checksum_errors}"

    # Format last scrub time
    scrub_text, scrub_color = _format_last_scrub(pool.last_scrub)

    return (
        pool.name,
        f"[{health_color}]{pool.health.value}[/{health_color}]",
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

    # Calculate time difference
    now = datetime.now(timezone.utc)
    # Ensure last_scrub is timezone-aware
    if last_scrub.tzinfo is None:
        last_scrub_aware = last_scrub.replace(tzinfo=timezone.utc)
    else:
        last_scrub_aware = last_scrub

    delta = now - last_scrub_aware
    days = delta.days

    # Format relative time
    if days == 0:
        text = "Today"
        color = "green"
    elif days == 1:
        text = "Yesterday"
        color = "green"
    elif days < 7:
        text = f"{days}d ago"
        color = "green"
    elif days < 30:
        weeks = days // 7
        text = f"{weeks}w ago"
        color = "green"
    elif days < 60:
        text = f"{days}d ago"
        color = "yellow"  # Warning: approaching 2 months
    else:
        months = days // 30
        text = f"{months}mo ago"
        color = "red"  # Critical: very old scrub

    return (text, color)


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
