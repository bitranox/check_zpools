"""Scrub orchestration: start scrubs and wait for them to finish.

Purpose
-------
Start a scrub on the requested pools and then wait until no scrub is running
any more, reporting per-pool what happened.

Contents
--------
* :class:`ZFSScrubPort` - The slice of a ZFS client this module needs
* :func:`run_scrub_cycle` - Start scrubs, wait, and report

Re-exports :class:`~check_zpools.models.ScrubRunOptions` for callers that only
import this module.

System Role
-----------
Application layer between the CLI command and the ZFS adapter. Holds the
policy (which pool to start, which to adopt, which to leave alone) and the
wait loop; owns no I/O of its own beyond the injected client.

Architecture Notes
------------------
- **No timeout.** The wait ends when ZFS says no scan is running, and at no
  other point. A scrub legitimately takes many hours on a large pool, and a
  deadline can only ever turn a healthy slow pool into a false alarm.
- The clock and the sleep are injected, so tests exercise the real loop
  without real waiting.
- A per-pool failure never aborts the other pools.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Protocol

from .formatters import format_bytes_human
from .models import PoolScrubOutcome, ScanRun, ScrubAction, ScrubCycleResult, ScrubRunOptions
from .zfs_client import ZFSCommandError
from .zfs_parser import DictLike, ZFSParser

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL_SECONDS = 60.0


class ZFSScrubPort(Protocol):
    """The slice of a ZFS client that scrub orchestration depends on.

    Why
        Declaring the two calls this module makes - rather than depending on
        the concrete :class:`~check_zpools.zfs_client.ZFSClient` - lets tests
        substitute a scripted double at a real seam instead of patching module
        internals.
    """

    def get_pool_status(self) -> dict[str, Any] | DictLike:
        """Return parsed `zpool status -j --json-int` output."""
        ...

    def start_scrub(self, pool_name: str) -> None:
        """Start a scrub on one pool."""
        ...


def _utc_now() -> datetime:
    """Return the current UTC time (injection point for tests)."""
    return datetime.now(timezone.utc)


def run_scrub_cycle(
    client: ZFSScrubPort,
    options: ScrubRunOptions | None = None,
    *,
    parser: ZFSParser | None = None,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] = _utc_now,
) -> ScrubCycleResult:
    """Start a scrub on the requested pools and wait for completion.

    Why
        This replaces the classic shell pattern of `zpool scrub` followed by a
        `sleep` loop with a hard timeout. The timeout is the bug: on a large
        pool the scrub simply outlives it and a healthy run is reported as a
        failure. Here the wait is bounded by the scrub, not by a clock.

    What
        1. Read pool status once and classify every target pool.
        2. Start a scrub where one is warranted (adopting a scrub that is
           already running, and leaving a pool busy with another scan alone).
        3. While waiting is requested, re-read status until no target pool is
           scanning any more.

    Parameters
    ----------
    client:
        ZFS client providing status reads and scrub starts.
    options:
        What to do this cycle. Defaults to :class:`ScrubRunOptions` defaults:
        every pool, wait for completion, poll once a minute.
    parser:
        Parser to turn status output into scan records. A default is created
        when None.
    sleep:
        Sleep function, injected for tests.
    now:
        Clock function, injected for tests.

    Returns
    -------
    ScrubCycleResult:
        Per-pool outcomes plus cycle timing.

    Raises
    ------
    ValueError:
        When the polling cadence is not positive.

    Examples
    --------
    >>> run_scrub_cycle(client, ScrubRunOptions(pools=("rpool",), wait=False))  # doctest: +SKIP
    """
    active_options = options if options is not None else ScrubRunOptions()
    if active_options.poll_interval_seconds <= 0:
        raise ValueError(f"poll_interval_seconds must be positive, got {active_options.poll_interval_seconds}")

    active_parser = parser if parser is not None else ZFSParser()
    started_at = now()

    scans = active_parser.parse_scan_runs(client.get_pool_status())
    targets = _resolve_targets(active_options.pools, scans)
    logger.info(
        "Scrub cycle starting",
        extra={"pools": list(targets), "wait": active_options.wait, "dry_run": active_options.dry_run},
    )

    actions = {
        pool: _begin_pool(
            client,
            pool_name=pool,
            scan=scans.get(pool),
            skip_if_other_scan_running=active_options.skip_if_other_scan_running,
            dry_run=active_options.dry_run,
        )
        for pool in targets
    }

    awaited = [pool for pool, (action, _) in actions.items() if action in (ScrubAction.STARTED, ScrubAction.ADOPTED)]
    waited = active_options.wait and not active_options.dry_run
    if waited and awaited:
        scans = _wait_for_scans(
            client,
            parser=active_parser,
            pools=awaited,
            poll_interval_seconds=active_options.poll_interval_seconds,
            sleep=sleep,
        )

    outcomes = [
        PoolScrubOutcome(
            pool_name=pool,
            action=action,
            reason=reason,
            final_scan=scans.get(pool),
        )
        for pool, (action, reason) in actions.items()
    ]

    result = ScrubCycleResult(
        started_at=started_at,
        finished_at=now(),
        outcomes=outcomes,
        waited=waited,
        dry_run=active_options.dry_run,
    )
    logger.info(
        "Scrub cycle finished",
        extra={
            "duration_seconds": result.duration.total_seconds(),
            "problems": [outcome.pool_name for outcome in result.problems()],
        },
    )
    return result


def _resolve_targets(pools: Sequence[str] | None, scans: dict[str, ScanRun]) -> list[str]:
    """Return the pools to act on, keeping requested-but-unknown names.

    Why
        A pool name the host does not have must be reported, not silently
        dropped - a typo in a config file would otherwise look like success.

    Examples
    --------
    >>> _resolve_targets(None, {"a": None, "b": None})
    ['a', 'b']
    >>> _resolve_targets(["b", "nope"], {"a": None, "b": None})
    ['b', 'nope']
    """
    if not pools:
        return list(scans)
    return list(pools)


def _begin_pool(
    client: ZFSScrubPort,
    *,
    pool_name: str,
    scan: ScanRun | None,
    skip_if_other_scan_running: bool,
    dry_run: bool,
) -> tuple[ScrubAction, str]:
    """Decide what to do with one pool and do it.

    Why
        Starting a scrub on a pool that is already scanning fails ("currently
        scrubbing"), so the running case must be adopted rather than retried.
        That is exactly the case a daily schedule hits when the previous run
        has not finished yet.

    Returns
    -------
    tuple[ScrubAction, str]:
        The action taken and the reason (empty when nothing went wrong).
    """
    if scan is None:
        return ScrubAction.FAILED_TO_START, "pool not found on this host"

    if scan.is_running:
        if scan.is_scrub:
            logger.info("Scrub already running, adopting it", extra={"pool": pool_name})
            return ScrubAction.ADOPTED, ""
        if skip_if_other_scan_running:
            reason = f"a {scan.function.value} is already running on this pool"
            logger.warning("Skipping pool", extra={"pool": pool_name, "reason": reason})
            return ScrubAction.SKIPPED, reason

    if dry_run:
        return ScrubAction.DRY_RUN, ""

    try:
        client.start_scrub(pool_name)
    except ZFSCommandError as exc:
        logger.error("Failed to start scrub", extra={"pool": pool_name, "error": str(exc)})
        return ScrubAction.FAILED_TO_START, str(exc)
    return ScrubAction.STARTED, ""


def _wait_for_scans(
    client: ZFSScrubPort,
    *,
    parser: ZFSParser,
    pools: Sequence[str],
    poll_interval_seconds: float,
    sleep: Callable[[float], None],
) -> dict[str, ScanRun]:
    """Poll until none of the given pools is scanning any more.

    Why no timeout
        A scrub takes as long as the pool is big and busy - many hours on a
        large array, and legitimately longer after a bad night. Any deadline
        here reports a healthy scrub as a failure and teaches the operator to
        ignore the alert. The loop instead ends on the only authority that can
        answer the question: the pool's own scan state.

    Returns
    -------
    dict[str, ScanRun]:
        The final scan records from the last status read.
    """
    while True:
        scans = parser.parse_scan_runs(client.get_pool_status())
        running = [scans[pool] for pool in pools if pool in scans and scans[pool].is_running]
        if not running:
            return scans

        for scan in running:
            logger.info(
                "Scrub in progress: %s %.1f%% (%s of %s issued)",
                scan.pool_name,
                scan.progress_percent,
                format_bytes_human(scan.issued_bytes),
                format_bytes_human(scan.to_examine_bytes),
                extra={
                    "pool": scan.pool_name,
                    "progress_percent": scan.progress_percent,
                    "issued_bytes": scan.issued_bytes,
                    "to_examine_bytes": scan.to_examine_bytes,
                },
            )

        sleep(poll_interval_seconds)


__all__ = [
    "DEFAULT_POLL_INTERVAL_SECONDS",
    "ScrubRunOptions",
    "ZFSScrubPort",
    "run_scrub_cycle",
]
