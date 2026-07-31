"""ZFS JSON output parser.

Purpose
-------
Parse JSON output from `zpool status -j --json-int` command into typed
PoolStatus objects. With --json-int flag, all numeric values are integers
requiring no string parsing.

Contents
--------
* :class:`ZFSParseError` - Exception raised when parsing fails
* :class:`ZFSParser` - Main parser for ZFS JSON output (pool health and scan runs)

System Role
-----------
Transforms raw ZFS JSON into domain models. Separates parsing logic from
command execution, enabling testing without actual ZFS commands.

Architecture Notes
------------------
- Pure functions (no side effects, testable with fixtures)
- Defensive parsing (handles missing/malformed data gracefully)
- Direct integer access (no string parsing with --json-int)
- Single command source (zpool status provides all needed data)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from .models import (
    CapacityInfo,
    DeviceState,
    DeviceStatus,
    PoolHealth,
    PoolPayload,
    PoolStatus,
    ScanFunction,
    ScanRun,
    ScanState,
    ScanStatsPayload,
    ScrubInfo,
    VdevPayload,
    ZpoolStatusPayload,
)

logger = logging.getLogger(__name__)


@dataclass
class ErrorCounts:
    """ZFS error counts for a pool.

    Why
    ---
    Provides type-safe container for ZFS error metrics instead of dict.
    Enables IDE autocomplete and prevents typos in field names.

    Attributes
    ----------
    read:
        Number of read errors detected on pool devices.
    write:
        Number of write errors detected on pool devices.
    checksum:
        Number of checksum errors detected on pool devices.
    """

    read: int = 0
    write: int = 0
    checksum: int = 0


class ZFSParseError(ValueError):
    """Exception raised when ZFS JSON parsing fails.

    Why
        Distinguishes parsing errors from other value errors, enabling
        targeted exception handling and helpful error messages.
    """

    pass


class ZFSParser:
    """Parse ZFS JSON output into PoolStatus objects.

    Why
        Centralizes parsing logic for maintainability and testability.
        Allows mocking ZFS output in tests without subprocess calls.

    Examples
    --------
    >>> parser = ZFSParser()
    >>> json_data = {
    ...     "pools": {
    ...         "rpool": {
    ...             "name": "rpool",
    ...             "state": "ONLINE",
    ...             "vdevs": {
    ...                 "rpool": {
    ...                     "alloc_space": 93584101376,
    ...                     "total_space": 498216206336,
    ...                     "read_errors": 0,
    ...                     "write_errors": 0,
    ...                     "checksum_errors": 0,
    ...                 }
    ...             },
    ...             "scan_stats": {"end_time": 1764065040, "errors": 0, "state": "FINISHED"}
    ...         }
    ...     }
    ... }
    >>> pools = parser.parse_pool_status(json_data)  # doctest: +SKIP
    >>> pools["rpool"].name  # doctest: +SKIP
    'rpool'
    """

    def parse_pool_status(self, json_data: ZpoolStatusPayload) -> dict[str, PoolStatus]:
        """Parse `zpool status -j --json-int` JSON output into PoolStatus objects.

        Why
            Single source of all pool data - capacity, errors, scrub info.
            With --json-int, all numeric values are already integers.

        Parameters
        ----------
        json_data:
            Parsed JSON from `zpool status -j --json-int` command.

        Returns
        -------
        dict[str, PoolStatus]:
            Dictionary mapping pool name to PoolStatus object.

        Raises
        ------
        ZFSParseError:
            When required fields are missing or invalid.
        """
        pools: dict[str, PoolStatus] = {}

        try:
            if not json_data.pools:
                logger.warning("No pools found in zpool status output")
                return pools

            for pool_name, pool_data in json_data.pools.items():
                pool_status = self._try_parse_pool(pool_name, pool_data)
                if pool_status is not None:
                    pools[pool_name] = pool_status

            return pools

        except Exception as exc:
            logger.exception("Failed to parse zpool status output")
            raise ZFSParseError(f"Failed to parse zpool status output: {exc}") from exc

    def parse_scan_runs(self, json_data: ZpoolStatusPayload) -> dict[str, ScanRun]:
        """Parse the `scan_stats` block of every pool into ScanRun objects.

        Why
            `parse_pool_status` reduces the scan to three fields, which is all
            the health monitor needs. Driving a scrub needs the rest: which
            scan is running, its progress, and how the previous one ended.

        Parameters
        ----------
        json_data:
            The validated `zpool status -j --json-int` payload.

        Returns
        -------
        dict[str, ScanRun]:
            Dictionary mapping pool name to its current or last scan.
            A pool that has never been scanned yields a ScanRun with
            function NONE and state NONE, never a missing key.

        Raises
        ------
        ZFSParseError:
            When the top-level structure cannot be read.

        Examples
        --------
        >>> from check_zpools.models import ZpoolStatusPayload
        >>> parser = ZFSParser()
        >>> data = ZpoolStatusPayload.model_validate({"pools": {"rpool": {"scan_stats": {
        ...     "function": "SCRUB", "state": "SCANNING",
        ...     "to_examine": 200, "examined": 100, "issued": 50, "errors": 0,
        ... }}}})
        >>> runs = parser.parse_scan_runs(data)
        >>> runs["rpool"].is_running, runs["rpool"].progress_percent
        (True, 25.0)
        """
        runs: dict[str, ScanRun] = {}

        try:
            for pool_name, pool_data in json_data.pools.items():
                runs[pool_name] = self._parse_scan_run(pool_name, pool_data)
            return runs
        except Exception as exc:
            logger.exception("Failed to parse scan stats from zpool status output")
            raise ZFSParseError(f"Failed to parse scan stats: {exc}") from exc

    def _parse_scan_run(self, pool_name: str, pool_data: PoolPayload) -> ScanRun:
        """Build a ScanRun from one pool's `scan_stats` block.

        Why
            Missing or malformed scan data must degrade to "no scan known"
            rather than abort the run - a pool that has never been scrubbed
            simply has no scan_stats.

        Parameters
        ----------
        pool_name:
            Name of the pool.
        pool_data:
            Pool data from zpool status JSON.

        Returns
        -------
        ScanRun:
            Typed scan record for the pool.
        """
        scan = pool_data.scan_block

        return ScanRun(
            pool_name=pool_name,
            function=ScanFunction.from_string(scan.function),
            state=ScanState.from_string(scan.state),
            start_time=self._parse_unix_time(scan.start_time),
            end_time=self._parse_unix_time(scan.end_time),
            to_examine_bytes=scan.to_examine,
            examined_bytes=scan.examined,
            issued_bytes=scan.issued,
            errors=scan.errors,
            paused_seconds=scan.scrub_spent_paused,
        )

    def _parse_unix_time(self, value: int) -> datetime | None:
        """Convert a `--json-int` Unix timestamp to an aware datetime.

        Why
            ZFS writes 0 for "not set" (an end_time of 0 means still running),
            which would otherwise decode to 1970.

        Parameters
        ----------
        value:
            Unix timestamp from the payload; 0 means "not set".

        Returns
        -------
        datetime | None:
            UTC timestamp, or None when unset or unparseable.
        """
        if value <= 0:
            return None
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (OverflowError, OSError) as exc:
            logger.debug("Failed to convert timestamp %s: %s", value, exc)
            return None

    def _try_parse_pool(self, pool_name: str, pool_data: PoolPayload) -> PoolStatus | None:
        """Parse a single pool, tolerating and logging per-pool failures.

        Why
            Keeps the try/except out of the caller's loop body (PERF203) while
            preserving the same per-pool resilience: one malformed pool must
            not abort parsing the rest of the zpool status output.

        Returns
        -------
        PoolStatus | None:
            The parsed pool, or None if parsing failed (already logged).
        """
        try:
            pool_status = self._parse_pool(pool_name, pool_data)
            logger.debug("Parsed pool: %s", pool_name)
        except Exception as exc:
            logger.exception(
                "Failed to parse pool %s",
                pool_name,
                extra={"pool_name": pool_name, "error": str(exc)},
            )
            return None

        return pool_status

    def _parse_pool(self, pool_name: str, pool_data: PoolPayload) -> PoolStatus:
        """Parse single pool from zpool status --json-int output.

        Parameters
        ----------
        pool_name:
            Name of the pool
        pool_data:
            Pool data from JSON

        Returns
        -------
        PoolStatus:
            Complete pool status with all metrics
        """
        # Extract health state
        health = self._parse_health_state(pool_data.state, pool_name)

        # Extract capacity and error counts from root vdev
        root_vdev = pool_data.root_vdev()
        capacity_info = self._extract_capacity_from_vdev(root_vdev)
        errors = self._extract_errors_from_vdev(root_vdev)

        # Extract scrub information
        scrub_info = self._extract_scrub_info(pool_data)

        # Find faulted/degraded devices recursively
        faulted_devices = self._find_problematic_devices(root_vdev)

        return PoolStatus(
            name=pool_name,
            health=health,
            capacity_percent=capacity_info.capacity_percent,
            size_bytes=capacity_info.size_bytes,
            allocated_bytes=capacity_info.allocated_bytes,
            free_bytes=capacity_info.free_bytes,
            read_errors=errors.read,
            write_errors=errors.write,
            checksum_errors=errors.checksum,
            last_scrub=scrub_info.last_scrub,
            scrub_errors=scrub_info.scrub_errors,
            scrub_in_progress=scrub_info.scrub_in_progress,
            faulted_devices=tuple(faulted_devices),
            scan_function=scrub_info.scan_function,
            scan_state=scrub_info.scan_state,
        )

    def _extract_capacity_from_vdev(self, root_vdev: VdevPayload) -> CapacityInfo:
        """Extract capacity metrics from root vdev.

        With --json-int, values are already integers (bytes).

        Parameters
        ----------
        root_vdev:
            Root vdev data from zpool status JSON

        Returns
        -------
        CapacityInfo:
            Typed container with capacity_percent, size_bytes, allocated_bytes, free_bytes
        """
        allocated_bytes = root_vdev.alloc_space
        size_bytes = root_vdev.total_space

        # Calculate derived values
        free_bytes = size_bytes - allocated_bytes if size_bytes > 0 else 0
        capacity_percent = (allocated_bytes / size_bytes * 100) if size_bytes > 0 else 0.0

        return CapacityInfo(
            capacity_percent=capacity_percent,
            size_bytes=size_bytes,
            allocated_bytes=allocated_bytes,
            free_bytes=free_bytes,
        )

    def _extract_errors_from_vdev(self, root_vdev: VdevPayload) -> ErrorCounts:
        """Extract error counts from root vdev.

        With --json-int, values are already integers.

        Parameters
        ----------
        root_vdev:
            Root vdev data from zpool status JSON

        Returns
        -------
        ErrorCounts:
            Type-safe container with read, write, and checksum error counts
        """
        return ErrorCounts(
            read=root_vdev.read_errors,
            write=root_vdev.write_errors,
            checksum=root_vdev.checksum_errors,
        )

    def _extract_scrub_info(self, pool_data: PoolPayload) -> ScrubInfo:
        """Extract scrub information from pool status data.

        With --json-int, timestamps are Unix integers.

        Parameters
        ----------
        pool_data:
            Pool data from zpool status JSON

        Returns
        -------
        ScrubInfo:
            Typed container with last_scrub, scrub_errors, scrub_in_progress
            and the scan function those fields describe.
        """
        scan_info = pool_data.scan_block

        # Parse scrub time from integer timestamp
        last_scrub = self._parse_scrub_time(scan_info)

        scrub_errors = scan_info.errors

        # A resilver occupies the same scan slot as a scrub, so SCANNING alone does
        # not mean "scrubbing" - a rebuilding pool would otherwise be reported as a
        # scrub in progress. Both the state AND the function have to agree.
        scan_state = ScanState.from_string(scan_info.state)
        scan_function = ScanFunction.from_string(scan_info.function)
        scrub_in_progress = scan_state == ScanState.SCANNING and scan_function == ScanFunction.SCRUB

        return ScrubInfo(
            last_scrub=last_scrub,
            scrub_errors=scrub_errors,
            scrub_in_progress=scrub_in_progress,
            scan_function=scan_function,
            scan_state=scan_state,
        )

    def _parse_scrub_time(self, scan_info: ScanStatsPayload) -> datetime | None:
        """Parse scrub completion time from scan info.

        With --json-int, timestamps are Unix integers.

        Parameters
        ----------
        scan_info:
            Scan/scrub information from zpool status

        Returns
        -------
        datetime | None:
            Timestamp of last completed scrub in UTC, or None if never scrubbed
        """
        # In order of preference: when the scan ended, when this pass began,
        # and finally when it started.
        for timestamp in (scan_info.end_time, scan_info.pass_start, scan_info.start_time):
            parsed = self._parse_unix_time(timestamp)
            if parsed is not None:
                return parsed

        return None

    def _parse_health_state(self, health_value: str, pool_name: str) -> PoolHealth:
        """Parse health state string into PoolHealth enum.

        Parameters
        ----------
        health_value:
            Raw health state string from ZFS
        pool_name:
            Pool name for logging

        Returns
        -------
        PoolHealth:
            Parsed health state, defaults to OFFLINE if unknown
        """
        try:
            return PoolHealth(health_value)
        except ValueError:
            logger.warning("Unknown health state '%s' for pool %s, using OFFLINE", health_value, pool_name)
            return PoolHealth.OFFLINE

    def _find_problematic_devices(self, vdev: VdevPayload) -> list[DeviceStatus]:
        """Recursively find devices that are faulted, degraded, or have errors.

        Why
        ---
        A pool can be ONLINE while containing FAULTED devices if redundancy
        exists. We need to traverse the entire vdev tree to find all
        problematic devices for proper alerting.

        Parameters
        ----------
        vdev:
            Vdev data from zpool status JSON (can be root, mirror, disk, etc.)

        Returns
        -------
        list[DeviceStatus]:
            List of devices that are not healthy or have errors.
        """
        problematic: list[DeviceStatus] = []

        vdev_type = vdev.vdev_type.lower()
        device_state = DeviceState.from_string(vdev.state.upper())
        name = vdev.name

        # Only report leaf devices (disks) - not containers like mirror/raidz
        if vdev.is_leaf_device and (device_state.is_problematic() or vdev.has_errors):
            device = DeviceStatus(
                name=name,
                state=device_state,
                read_errors=vdev.read_errors,
                write_errors=vdev.write_errors,
                checksum_errors=vdev.checksum_errors,
                vdev_type=vdev_type,
            )
            problematic.append(device)
            logger.debug(
                "Found problematic device: %s",
                name,
                extra={
                    "device": name,
                    "state": device_state.value,
                    "read_errors": vdev.read_errors,
                    "write_errors": vdev.write_errors,
                    "checksum_errors": vdev.checksum_errors,
                },
            )

        # Recursively check child vdevs
        for child_vdev in vdev.vdevs.values():
            problematic.extend(self._find_problematic_devices(child_vdev))

        return problematic


__all__ = [
    "ZFSParseError",
    "ZFSParser",
]
