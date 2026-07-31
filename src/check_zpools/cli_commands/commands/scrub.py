"""Scrub command implementation."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import lib_log_rich.runtime
import rich_click as click

from ...behaviors import deliver_scrub_summary, scrub_pools
from ...cli_errors import handle_generic_error, handle_zfs_not_available
from ...scrub_report import format_scrub_summary_json, format_scrub_summary_text
from ...zfs_client import ZFSNotAvailableError

if TYPE_CHECKING:
    from ...models import ScrubCycleResult

logger = logging.getLogger(__name__)


def scrub_command(
    *,
    pools: tuple[str, ...],
    output_format: str,
    wait: bool,
    poll_interval: float | None,
    send_email: bool,
    dry_run: bool,
) -> None:
    """Execute scrub command logic.

    Why
        Thin adapter: run the cycle, show it, mail it, and turn the outcome
        into an exit code a cron job can act on.
    """
    with lib_log_rich.runtime.bind(
        job_id="cli-scrub",
        extra={"command": "scrub", "pools": list(pools), "wait": wait, "dry_run": dry_run},
    ):
        try:
            result = scrub_pools(
                pools=pools,
                wait=wait,
                poll_interval_seconds=poll_interval,
                dry_run=dry_run,
            )

            if output_format == "json":
                click.echo(format_scrub_summary_json(result))
            else:
                click.echo(format_scrub_summary_text(result))

            # Report before mailing: a broken SMTP path must not swallow the
            # result of a scrub that took hours.
            if send_email and not dry_run:
                _deliver_summary(result)

            if result.has_problems():
                logger.warning(
                    "Scrub finished with problems",
                    extra={"pools": [outcome.pool_name for outcome in result.problems()]},
                )
                raise SystemExit(1)

        except ZFSNotAvailableError as exc:
            handle_zfs_not_available(exc, operation="Scrub")
        except SystemExit:
            raise
        except Exception as exc:
            handle_generic_error(exc, operation="Scrub")


def _deliver_summary(result: ScrubCycleResult) -> None:
    """Send the summary email, degrading to a warning when SMTP fails.

    Why
        The scrub itself succeeded or failed on its own merits. A mail server
        that is down must be visible (non-zero exit via the caller's problem
        check is not enough here, so it is reported on stderr and logged) but
        must not masquerade as a scrub failure.
    """
    try:
        deliver_scrub_summary(result)
    except Exception as exc:
        logger.exception("Failed to send scrub summary email", extra={"error": str(exc)})
        click.echo(f"\nWarning: scrub summary email could not be sent - {exc}", err=True)
