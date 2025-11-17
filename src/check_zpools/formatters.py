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
from io import StringIO

from rich.console import Console
from rich.table import Table

from .models import CheckResult, Severity


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
        Multi-line text output with color markup.
    """
    lines: list[str] = []

    # Header
    timestamp_str = result.timestamp.strftime("%Y-%m-%d %H:%M:%S")
    lines.append(f"\nZFS Pool Check - {timestamp_str}")
    lines.append(f"Overall Status: {result.overall_severity.value.upper()}\n")

    # Pool Status Summary as Table
    table = Table(title="Pool Status", show_header=True, header_style="bold cyan")
    table.add_column("Pool", style="bold", no_wrap=True)
    table.add_column("Health", justify="center")
    table.add_column("Capacity", justify="right")
    table.add_column("Size", justify="right")
    table.add_column("Read Errors", justify="right")
    table.add_column("Write Errors", justify="right")
    table.add_column("Checksum Errors", justify="right")

    for pool in result.pools:
        # Determine colors
        health_color = "green" if pool.health.is_healthy() else "red"
        capacity_color = "green" if pool.capacity_percent < 80 else ("yellow" if pool.capacity_percent < 90 else "red")
        error_color = "green" if not pool.has_errors() else "red"

        # Format size in human-readable format
        size_gb = pool.size_bytes / (1024**3)
        if size_gb >= 1024:
            size_str = f"{size_gb / 1024:.1f}T"
        else:
            size_str = f"{size_gb:.1f}G"

        table.add_row(
            pool.name,
            f"[{health_color}]{pool.health.value}[/{health_color}]",
            f"[{capacity_color}]{pool.capacity_percent:.1f}%[/{capacity_color}]",
            size_str,
            f"[{error_color}]{pool.read_errors}[/{error_color}]",
            f"[{error_color}]{pool.write_errors}[/{error_color}]",
            f"[{error_color}]{pool.checksum_errors}[/{error_color}]",
        )

    # Render table to string
    console = Console(file=StringIO(), force_terminal=True, width=120)
    console.print(table)
    table_output = console.file.getvalue()  # type: ignore
    lines.append(table_output)

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
    "get_exit_code_for_severity",
]
