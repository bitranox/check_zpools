"""Tests for scrub scan parsing and reporting.

Parsing is driven by a JSON fixture in the exact shape
`zpool status -j --json-int` emits, covering a finished scrub, a running
scrub, a resilver, a scrub that found errors, and a pool that was never
scanned.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from check_zpools.models import (
    PoolScrubOutcome,
    ScanFunction,
    ScanRun,
    ScanState,
    ScrubAction,
    ScrubCycleResult,
)
from check_zpools.scrub_report import (
    build_scrub_subject,
    format_duration,
    format_scrub_summary_json,
    format_scrub_summary_text,
)
from check_zpools.zfs_parser import ZFSParser

FIXED_NOW = datetime(2026, 7, 31, 7, 0, tzinfo=timezone.utc)


@pytest.fixture
def scan_fixture() -> dict[str, Any]:
    """Load the scan-focused zpool status fixture."""
    with (Path(__file__).parent / "zpool_status_scans.json").open() as handle:
        return json.load(handle)


@pytest.fixture
def scans(scan_fixture: dict[str, Any]) -> dict[str, ScanRun]:
    """Parse the fixture into scan records."""
    return ZFSParser().parse_scan_runs(scan_fixture)


@pytest.mark.os_agnostic
class TestParseScanRuns:
    """Turning zpool status JSON into scan records."""

    def test_reads_every_pool(self, scans: dict[str, ScanRun]) -> None:
        """Given a status payload, when parsed, then every pool has a scan record."""
        assert set(scans) == {
            "pool-finished",
            "pool-scanning",
            "pool-resilvering",
            "pool-with-errors",
            "pool-never-scanned",
        }

    def test_identifies_a_running_scrub(self, scans: dict[str, ScanRun]) -> None:
        """Given a scanning pool, when parsed, then it reports as a running scrub."""
        scan = scans["pool-scanning"]
        assert scan.is_running
        assert scan.is_scrub

    def test_distinguishes_a_resilver_from_a_scrub(self, scans: dict[str, ScanRun]) -> None:
        """Given a resilvering pool, when parsed, then it is running but not a scrub."""
        scan = scans["pool-resilvering"]
        assert scan.is_running
        assert not scan.is_scrub
        assert scan.function == ScanFunction.RESILVER

    def test_a_never_scanned_pool_yields_an_empty_scan(self, scans: dict[str, ScanRun]) -> None:
        """Given a pool without scan_stats, when parsed, then it reports NONE, not a missing key."""
        scan = scans["pool-never-scanned"]
        assert scan.function == ScanFunction.NONE
        assert scan.state == ScanState.NONE
        assert scan.start_time is None

    def test_reports_progress_from_issued_bytes(self, scans: dict[str, ScanRun]) -> None:
        """Given a scan a quarter issued, when parsed, then progress is 25 percent."""
        assert scans["pool-scanning"].progress_percent == pytest.approx(25.0)

    def test_a_running_scan_has_no_end_time(self, scans: dict[str, ScanRun]) -> None:
        """Given end_time is 0, when parsed, then it decodes to None rather than 1970."""
        assert scans["pool-scanning"].end_time is None
        assert scans["pool-scanning"].duration is None

    def test_a_finished_scan_reports_its_duration(self, scans: dict[str, ScanRun]) -> None:
        """Given a finished scan, when parsed, then start and end give the duration."""
        assert scans["pool-finished"].duration == timedelta(seconds=300)

    def test_reports_scan_errors(self, scans: dict[str, ScanRun]) -> None:
        """Given a scrub that found errors, when parsed, then the count survives."""
        assert scans["pool-with-errors"].errors == 7

    def test_reports_time_spent_paused(self, scans: dict[str, ScanRun]) -> None:
        """Given a paused scan, when parsed, then the paused seconds survive."""
        assert scans["pool-scanning"].paused_seconds == 120


def make_result(*outcomes: PoolScrubOutcome, dry_run: bool = False) -> ScrubCycleResult:
    """Build a cycle result spanning five minutes."""
    return ScrubCycleResult(
        started_at=FIXED_NOW,
        finished_at=FIXED_NOW + timedelta(minutes=5),
        outcomes=list(outcomes),
        waited=True,
        dry_run=dry_run,
    )


@pytest.mark.os_agnostic
class TestFormatDuration:
    """Duration rendering."""

    def test_renders_hours_minutes_seconds(self) -> None:
        """Given a multi-hour duration, when formatted, then it reads HH:MM:SS."""
        assert format_duration(timedelta(hours=7, minutes=30, seconds=5)) == "07:30:05"

    def test_renders_an_unknown_duration_as_a_dash(self) -> None:
        """Given no duration, when formatted, then it reads as a dash."""
        assert format_duration(None) == "-"


@pytest.mark.os_agnostic
class TestSubject:
    """Email subject lines."""

    def test_a_clean_cycle_reads_as_completed(self) -> None:
        """Given no problems, when the subject is built, then it says completed."""
        subject = build_scrub_subject(make_result(), subject_prefix="[ZFS]", hostname="node")
        assert subject == "[ZFS] [node] ZFS scrub completed"

    def test_a_cycle_with_problems_says_so(self, scans: dict[str, ScanRun]) -> None:
        """Given a failed pool, when the subject is built, then it flags problems."""
        outcome = PoolScrubOutcome("tank", ScrubAction.FAILED_TO_START, reason="refused")
        subject = build_scrub_subject(make_result(outcome), subject_prefix="[ZFS]", hostname="node")
        assert "problems detected" in subject

    def test_a_dry_run_is_labelled(self) -> None:
        """Given a dry run, when the subject is built, then it is not mistaken for a real one."""
        subject = build_scrub_subject(make_result(dry_run=True), subject_prefix="[ZFS]", hostname="node")
        assert "dry run" in subject


@pytest.mark.os_agnostic
class TestTextReport:
    """The plain-text summary used for console and email."""

    def test_names_the_host(self) -> None:
        """Given a cycle, when reported, then the host is named."""
        assert "Host: node" in format_scrub_summary_text(make_result(), hostname="node")

    def test_marks_a_healthy_pool_as_ok(self, scans: dict[str, ScanRun]) -> None:
        """Given a clean scrub, when reported, then the pool line reads OK."""
        outcome = PoolScrubOutcome("pool-finished", ScrubAction.STARTED, final_scan=scans["pool-finished"])
        report = format_scrub_summary_text(make_result(outcome), hostname="node")
        assert "[OK] Pool: pool-finished" in report

    def test_marks_a_pool_with_errors_as_a_problem(self, scans: dict[str, ScanRun]) -> None:
        """Given a scrub that found errors, when reported, then the pool line reads PROBLEM."""
        outcome = PoolScrubOutcome("pool-with-errors", ScrubAction.STARTED, final_scan=scans["pool-with-errors"])
        report = format_scrub_summary_text(make_result(outcome), hostname="node")
        assert "[PROBLEM] Pool: pool-with-errors" in report

    def test_explains_why_a_pool_was_skipped(self, scans: dict[str, ScanRun]) -> None:
        """Given a skipped pool, when reported, then the reason is included."""
        outcome = PoolScrubOutcome("tank", ScrubAction.SKIPPED, reason="a RESILVER is already running on this pool")
        report = format_scrub_summary_text(make_result(outcome), hostname="node")
        assert "Reason: a RESILVER is already running on this pool" in report

    def test_reports_the_scan_duration(self, scans: dict[str, ScanRun]) -> None:
        """Given a finished scrub, when reported, then its duration is shown."""
        outcome = PoolScrubOutcome("pool-finished", ScrubAction.STARTED, final_scan=scans["pool-finished"])
        report = format_scrub_summary_text(make_result(outcome), hostname="node")
        assert "Duration: 00:05:00" in report


@pytest.mark.os_agnostic
class TestJsonReport:
    """The machine-readable summary."""

    def test_is_valid_json(self, scans: dict[str, ScanRun]) -> None:
        """Given a cycle, when rendered as JSON, then it parses."""
        outcome = PoolScrubOutcome("pool-finished", ScrubAction.STARTED, final_scan=scans["pool-finished"])
        payload = json.loads(format_scrub_summary_json(make_result(outcome), hostname="node"))
        assert payload["hostname"] == "node"

    def test_carries_the_per_pool_scan_detail(self, scans: dict[str, ScanRun]) -> None:
        """Given a finished scrub, when rendered as JSON, then its scan block is present."""
        outcome = PoolScrubOutcome("pool-finished", ScrubAction.STARTED, final_scan=scans["pool-finished"])
        payload = json.loads(format_scrub_summary_json(make_result(outcome), hostname="node"))
        pool = payload["pools"][0]
        assert pool["scan"]["state"] == "FINISHED"
        assert pool["scan"]["duration_seconds"] == 300.0

    def test_flags_problems_at_the_top_level(self, scans: dict[str, ScanRun]) -> None:
        """Given a problem, when rendered as JSON, then a consumer can see it without digging."""
        outcome = PoolScrubOutcome("pool-with-errors", ScrubAction.STARTED, final_scan=scans["pool-with-errors"])
        payload = json.loads(format_scrub_summary_json(make_result(outcome), hostname="node"))
        assert payload["has_problems"] is True

    def test_a_pool_without_a_scan_serialises_as_null(self) -> None:
        """Given a pool with no scan record, when rendered as JSON, then scan is null."""
        outcome = PoolScrubOutcome("typo", ScrubAction.FAILED_TO_START, reason="pool not found on this host")
        payload = json.loads(format_scrub_summary_json(make_result(outcome), hostname="node"))
        assert payload["pools"][0]["scan"] is None
