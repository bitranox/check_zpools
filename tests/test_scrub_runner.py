"""Tests for scrub orchestration.

Design Philosophy
-----------------
The runner is exercised through its real code path with a scripted ZFS client
substituted at the :class:`~check_zpools.scrub_runner.ZFSScrubPort` seam - no
patching of module internals. Sleeping and the clock are injected, so a test
covering a scrub that polls 500 times still runs instantly.

The central property under test is the ABSENCE of a timeout: the loop must end
when, and only when, ZFS stops reporting a running scan.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from check_zpools.models import ScanState, ScrubAction, ScrubRunOptions
from check_zpools.scrub_runner import run_scrub_cycle
from check_zpools.zfs_client import ZFSCommandError

FIXED_NOW = datetime(2026, 7, 31, 7, 0, tzinfo=timezone.utc)


def scan_payload(**pools: dict[str, Any]) -> dict[str, Any]:
    """Build a `zpool status -j` style payload from per-pool scan_stats.

    Examples
    --------
    >>> payload = scan_payload(rpool={"function": "SCRUB", "state": "FINISHED"})
    >>> payload["pools"]["rpool"]["scan_stats"]["state"]
    'FINISHED'
    """
    return {"pools": {name: {"name": name, "scan_stats": stats} for name, stats in pools.items()}}


def idle(**overrides: Any) -> dict[str, Any]:
    """Scan stats for a pool whose last scrub finished cleanly."""
    return {
        "function": "SCRUB",
        "state": "FINISHED",
        "start_time": 1700000000,
        "end_time": 1700000300,
        "to_examine": 1000,
        "examined": 1000,
        "issued": 1000,
        "errors": 0,
        **overrides,
    }


def scanning(**overrides: Any) -> dict[str, Any]:
    """Scan stats for a pool with a scrub in progress."""
    return {
        "function": "SCRUB",
        "state": "SCANNING",
        "start_time": 1700000000,
        "end_time": 0,
        "to_examine": 1000,
        "examined": 400,
        "issued": 250,
        "errors": 0,
        **overrides,
    }


def resilvering(**overrides: Any) -> dict[str, Any]:
    """Scan stats for a pool with a resilver in progress."""
    return scanning(function="RESILVER", **overrides)


class ScriptedZFSClient:
    """Test double replaying scripted status snapshots and recording starts.

    Why
        Stands in at the ZFSScrubPort seam so the runner's real loop is
        exercised without a ZFS host. The last snapshot repeats forever, so a
        script only needs to describe the states that change.
    """

    def __init__(self, snapshots: list[dict[str, Any]], *, fail_pools: dict[str, str] | None = None) -> None:
        self.snapshots = list(snapshots)
        self.fail_pools = fail_pools or {}
        self.started: list[str] = []
        self.reads = 0

    def get_pool_status(self) -> dict[str, Any]:
        """Return the next scripted snapshot, repeating the last one."""
        self.reads += 1
        if len(self.snapshots) > 1:
            return self.snapshots.pop(0)
        return self.snapshots[0]

    def start_scrub(self, pool_name: str) -> None:
        """Record the start, or raise the scripted failure for this pool."""
        if pool_name in self.fail_pools:
            raise ZFSCommandError(["zpool", "scrub", pool_name], 1, self.fail_pools[pool_name])
        self.started.append(pool_name)


class RecordingSleeper:
    """Sleep replacement recording every requested interval."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        """Record the requested sleep instead of performing it."""
        self.calls.append(seconds)


def advancing_clock(step_seconds: int = 1) -> Any:
    """Return a clock that advances by a fixed step on every call."""
    state = {"ticks": 0}

    def _now() -> datetime:
        value = FIXED_NOW + timedelta(seconds=state["ticks"] * step_seconds)
        state["ticks"] += 1
        return value

    return _now


@pytest.mark.os_agnostic
class TestStartingScrubs:
    """How the runner decides what to do with each pool."""

    def test_starts_a_scrub_on_an_idle_pool(self) -> None:
        """Given an idle pool, when a cycle runs, then a scrub is started for it."""
        client = ScriptedZFSClient([scan_payload(rpool=idle())])

        run_scrub_cycle(client, ScrubRunOptions(wait=False), sleep=RecordingSleeper(), now=advancing_clock())

        assert client.started == ["rpool"]

    def test_adopts_a_scrub_that_is_already_running(self) -> None:
        """Given a pool already scrubbing, when a cycle runs, then it is not restarted."""
        client = ScriptedZFSClient([scan_payload(rpool=scanning())])

        result = run_scrub_cycle(client, ScrubRunOptions(wait=False), sleep=RecordingSleeper(), now=advancing_clock())

        assert client.started == []
        assert result.outcomes[0].action == ScrubAction.ADOPTED

    def test_skips_a_pool_that_is_resilvering(self) -> None:
        """Given a resilvering pool, when a cycle runs, then no scrub is issued for it."""
        client = ScriptedZFSClient([scan_payload(tank=resilvering())])

        result = run_scrub_cycle(client, ScrubRunOptions(wait=False), sleep=RecordingSleeper(), now=advancing_clock())

        assert client.started == []
        assert result.outcomes[0].action == ScrubAction.SKIPPED
        assert "RESILVER" in result.outcomes[0].reason

    def test_a_skipped_pool_is_reported_as_a_problem(self) -> None:
        """Given a resilvering pool, when a cycle runs, then the result flags a problem."""
        client = ScriptedZFSClient([scan_payload(tank=resilvering())])

        result = run_scrub_cycle(client, ScrubRunOptions(wait=False), sleep=RecordingSleeper(), now=advancing_clock())

        assert result.has_problems()

    def test_attempts_the_start_when_skipping_is_disabled(self) -> None:
        """Given skipping is off, when another scan runs, then the start is attempted anyway."""
        client = ScriptedZFSClient([scan_payload(tank=resilvering())])

        result = run_scrub_cycle(client, ScrubRunOptions(wait=False, skip_if_other_scan_running=False), sleep=RecordingSleeper(), now=advancing_clock())

        assert client.started == ["tank"]
        assert result.outcomes[0].action == ScrubAction.STARTED

    def test_records_a_refused_start_without_aborting_other_pools(self) -> None:
        """Given one pool refuses the start, when a cycle runs, then the other still starts."""
        client = ScriptedZFSClient(
            [scan_payload(busy=idle(), fine=idle())],
            fail_pools={"busy": "currently scrubbing"},
        )

        result = run_scrub_cycle(client, ScrubRunOptions(wait=False), sleep=RecordingSleeper(), now=advancing_clock())

        assert client.started == ["fine"]
        actions = {outcome.pool_name: outcome.action for outcome in result.outcomes}
        assert actions["busy"] == ScrubAction.FAILED_TO_START
        assert actions["fine"] == ScrubAction.STARTED

    def test_reports_a_pool_that_does_not_exist(self) -> None:
        """Given a pool name the host lacks, when a cycle runs, then it is reported, not ignored."""
        client = ScriptedZFSClient([scan_payload(rpool=idle())])

        result = run_scrub_cycle(client, ScrubRunOptions(pools=("typo",), wait=False), sleep=RecordingSleeper(), now=advancing_clock())

        assert result.outcomes[0].action == ScrubAction.FAILED_TO_START
        assert "not found" in result.outcomes[0].reason

    def test_dry_run_starts_nothing(self) -> None:
        """Given dry-run, when a cycle runs, then no scrub is issued."""
        client = ScriptedZFSClient([scan_payload(rpool=idle())])

        result = run_scrub_cycle(client, ScrubRunOptions(dry_run=True), sleep=RecordingSleeper(), now=advancing_clock())

        assert client.started == []
        assert result.outcomes[0].action == ScrubAction.DRY_RUN

    def test_scrubs_every_pool_when_none_is_named(self) -> None:
        """Given no pool selection, when a cycle runs, then every pool is scrubbed."""
        client = ScriptedZFSClient([scan_payload(one=idle(), two=idle())])

        run_scrub_cycle(client, ScrubRunOptions(wait=False), sleep=RecordingSleeper(), now=advancing_clock())

        assert client.started == ["one", "two"]

    def test_scrubs_only_the_named_pool(self) -> None:
        """Given a pool selection, when a cycle runs, then the others are untouched."""
        client = ScriptedZFSClient([scan_payload(one=idle(), two=idle())])

        run_scrub_cycle(client, ScrubRunOptions(pools=("two",), wait=False), sleep=RecordingSleeper(), now=advancing_clock())

        assert client.started == ["two"]


@pytest.mark.os_agnostic
class TestWaitingForCompletion:
    """The wait loop - the part that replaces the shell sleep loop."""

    def test_waits_until_the_scan_state_leaves_scanning(self) -> None:
        """Given a scrub that runs for two polls, when waiting, then it sleeps twice."""
        sleeper = RecordingSleeper()
        client = ScriptedZFSClient(
            [
                scan_payload(rpool=idle()),
                scan_payload(rpool=scanning()),
                scan_payload(rpool=scanning()),
                scan_payload(rpool=idle()),
            ]
        )

        run_scrub_cycle(client, ScrubRunOptions(poll_interval_seconds=30), sleep=sleeper, now=advancing_clock())

        assert sleeper.calls == [30, 30]

    def test_a_very_long_scrub_is_never_cut_short(self) -> None:
        """Given a scrub still running after 500 polls, when waiting, then it is still waited out.

        This is the regression guard for the bug this command replaces: the old
        shell implementation aborted after a fixed five hours and reported a
        healthy pool as failed. There must be no upper bound here at all.
        """
        sleeper = RecordingSleeper()
        polls = 500
        client = ScriptedZFSClient([scan_payload(rpool=idle()), *([scan_payload(rpool=scanning())] * polls), scan_payload(rpool=idle())])

        result = run_scrub_cycle(client, ScrubRunOptions(poll_interval_seconds=60), sleep=sleeper, now=advancing_clock())

        assert len(sleeper.calls) == polls
        assert result.outcomes[0].final_scan is not None
        assert result.outcomes[0].final_scan.state == ScanState.FINISHED
        assert not result.has_problems()

    def test_no_wait_returns_while_the_scrub_is_still_running(self) -> None:
        """Given --no-wait, when a cycle runs, then it never sleeps."""
        sleeper = RecordingSleeper()
        client = ScriptedZFSClient([scan_payload(rpool=idle()), scan_payload(rpool=scanning())])

        result = run_scrub_cycle(client, ScrubRunOptions(wait=False), sleep=sleeper, now=advancing_clock())

        assert sleeper.calls == []
        assert result.waited is False

    def test_a_running_scrub_left_by_no_wait_is_not_a_problem(self) -> None:
        """Given --no-wait, when the scrub is still running, then that is not reported as failure."""
        client = ScriptedZFSClient([scan_payload(rpool=scanning())])

        result = run_scrub_cycle(client, ScrubRunOptions(wait=False), sleep=RecordingSleeper(), now=advancing_clock())

        assert not result.has_problems()

    def test_does_not_wait_when_every_pool_was_skipped(self) -> None:
        """Given only skipped pools, when a cycle runs, then there is nothing to wait for."""
        sleeper = RecordingSleeper()
        client = ScriptedZFSClient([scan_payload(tank=resilvering())])

        run_scrub_cycle(client, ScrubRunOptions(poll_interval_seconds=30), sleep=sleeper, now=advancing_clock())

        assert sleeper.calls == []

    def test_waits_for_the_slowest_pool(self) -> None:
        """Given two pools, when one finishes first, then waiting continues for the other."""
        sleeper = RecordingSleeper()
        client = ScriptedZFSClient(
            [
                scan_payload(fast=idle(), slow=idle()),
                scan_payload(fast=scanning(), slow=scanning()),
                scan_payload(fast=idle(), slow=scanning()),
                scan_payload(fast=idle(), slow=idle()),
            ]
        )

        run_scrub_cycle(client, ScrubRunOptions(poll_interval_seconds=10), sleep=sleeper, now=advancing_clock())

        assert sleeper.calls == [10, 10]

    def test_a_pool_that_vanishes_mid_scrub_is_reported(self) -> None:
        """Given a pool exported mid-scrub, when waiting ends, then it is flagged as a problem."""
        client = ScriptedZFSClient([scan_payload(gone=idle()), scan_payload()])

        result = run_scrub_cycle(client, ScrubRunOptions(poll_interval_seconds=5), sleep=RecordingSleeper(), now=advancing_clock())

        assert result.outcomes[0].final_scan is None
        assert result.has_problems()


@pytest.mark.os_agnostic
class TestCycleResult:
    """What the cycle reports back."""

    def test_a_clean_finished_scrub_is_not_a_problem(self) -> None:
        """Given a scrub that finished without errors, when it ends, then nothing is flagged."""
        client = ScriptedZFSClient([scan_payload(rpool=idle())])

        result = run_scrub_cycle(client, ScrubRunOptions(), sleep=RecordingSleeper(), now=advancing_clock())

        assert not result.has_problems()

    def test_a_scrub_that_found_errors_is_a_problem(self) -> None:
        """Given a scrub that reported errors, when it ends, then the pool is flagged."""
        client = ScriptedZFSClient([scan_payload(rpool=idle(errors=3))])

        result = run_scrub_cycle(client, ScrubRunOptions(), sleep=RecordingSleeper(), now=advancing_clock())

        assert result.has_problems()
        assert [outcome.pool_name for outcome in result.problems()] == ["rpool"]

    def test_a_canceled_scrub_is_a_problem(self) -> None:
        """Given a scrub that was canceled, when it ends, then the pool is flagged."""
        client = ScriptedZFSClient([scan_payload(rpool=idle(state="CANCELED"))])

        result = run_scrub_cycle(client, ScrubRunOptions(), sleep=RecordingSleeper(), now=advancing_clock())

        assert result.has_problems()

    def test_reports_the_cycle_duration(self) -> None:
        """Given a finished cycle, when it is reported, then the elapsed time is included."""
        client = ScriptedZFSClient([scan_payload(rpool=idle())])

        result = run_scrub_cycle(client, ScrubRunOptions(), sleep=RecordingSleeper(), now=advancing_clock(step_seconds=42))

        assert result.duration == timedelta(seconds=42)

    def test_rejects_a_non_positive_poll_interval(self) -> None:
        """Given a zero poll interval, when a cycle starts, then it refuses to spin."""
        client = ScriptedZFSClient([scan_payload(rpool=idle())])

        with pytest.raises(ValueError, match="poll_interval_seconds"):
            run_scrub_cycle(client, ScrubRunOptions(poll_interval_seconds=0), sleep=RecordingSleeper(), now=advancing_clock())
