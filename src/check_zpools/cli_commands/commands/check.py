"""Check command implementation."""

from __future__ import annotations

import logging

import lib_log_rich.runtime
import rich_click as click

from ...behaviors import check_pools_once
from ...cli_errors import handle_generic_error, handle_zfs_not_available
from ...formatters import display_check_result_text, format_check_result_json, get_exit_code_for_severity
from ...zfs_client import ZFSNotAvailableError

logger = logging.getLogger(__name__)


def check_command(format: str) -> None:
    """Execute check command logic."""
    with lib_log_rich.runtime.bind(job_id="cli-check", extra={"command": "check", "format": format}):
        try:
            result = check_pools_once()

            # Format and display output
            if format == "json":
                # JSON output - use click.echo for plain text
                output = format_check_result_json(result)
                click.echo(output)
            else:
                # Text output with Rich - print directly to avoid ANSI code issues
                display_check_result_text(result)

            # Exit with appropriate code
            exit_code = get_exit_code_for_severity(result.overall_severity)
            if exit_code != 0:
                logger.warning(
                    f"Check completed with {result.overall_severity.name} severity",
                    extra={
                        "exit_code": exit_code,
                        "severity": result.overall_severity.name,
                        "issue_count": len(result.issues),
                    },
                )
                raise SystemExit(exit_code)

        except ZFSNotAvailableError as exc:
            handle_zfs_not_available(exc, operation="Check")
        except Exception as exc:
            handle_generic_error(exc, operation="Check")
