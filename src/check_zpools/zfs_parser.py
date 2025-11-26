"""ZFS JSON output parser.

Purpose
-------
Parse JSON output from `zpool status -j --json-int` command into typed
PoolStatus objects. With --json-int flag, all numeric values are integers
requiring no string parsing.

Contents
--------
* :class:`ZFSParseError` – Exception raised when parsing fails
* :class:`ZFSParser` – Main parser for ZFS JSON output

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
from typing import Any, Protocol

from .models import DeviceStatus, PoolHealth, PoolStatus

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


class DictLike(Protocol):
    """Protocol for dict-like objects supporting basic dict operations.

    Why
        Enables parser to accept both dict[str, Any] and Pydantic models
        that implement dict-like interface, maintaining backward compatibility
        while supporting new type-safe responses.
    """

    def get(self, key: str, default: Any = None) -> Any: ...

    def __getitem__(self, key: str) -> Any: ...

    def __contains__(self, key: str) -> bool: ...


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

    def parse_pool_status(self, json_data: dict[str, Any] | DictLike) -> dict[str, PoolStatus]:
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
            pools_data = json_data.get("pools", {})
            if not pools_data:
                logger.warning("No pools found in zpool status output")
                return pools

            for pool_name, pool_data in pools_data.items():
                try:
                    pool_status = self._parse_pool(pool_name, pool_data)
                    pools[pool_name] = pool_status
                    logger.debug(f"Parsed pool: {pool_name}")
                except Exception as exc:
                    logger.error(
                        f"Failed to parse pool {pool_name}",
                        extra={"pool_name": pool_name, "error": str(exc)},
                        exc_info=True,
                    )
                    continue

            return pools

        except Exception as exc:
            logger.error("Failed to parse zpool status output", exc_info=True)
            raise ZFSParseError(f"Failed to parse zpool status output: {exc}") from exc

    def _parse_pool(self, pool_name: str, pool_data: dict[str, Any]) -> PoolStatus:
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
        state = pool_data.get("state", "UNKNOWN")
        health = self._parse_health_state(state, pool_name)

        # Extract capacity and error counts from root vdev
        root_vdev = self._get_root_vdev(pool_data, pool_name)
        capacity_info = self._extract_capacity_from_vdev(root_vdev)
        errors = self._extract_errors_from_vdev(root_vdev)

        # Extract scrub information
        scrub_info = self._extract_scrub_info(pool_data)

        # Find faulted/degraded devices recursively
        faulted_devices = self._find_problematic_devices(root_vdev)

        return PoolStatus(
            name=pool_name,
            health=health,
            capacity_percent=capacity_info["capacity_percent"],
            size_bytes=capacity_info["size_bytes"],
            allocated_bytes=capacity_info["allocated_bytes"],
            free_bytes=capacity_info["free_bytes"],
            read_errors=errors.read,
            write_errors=errors.write,
            checksum_errors=errors.checksum,
            last_scrub=scrub_info["last_scrub"],
            scrub_errors=scrub_info["scrub_errors"],
            scrub_in_progress=scrub_info["scrub_in_progress"],
            faulted_devices=tuple(faulted_devices),
        )

    def _get_root_vdev(self, pool_data: dict[str, Any], pool_name: str) -> dict[str, Any]:
        """Get the root vdev for a pool.

        Parameters
        ----------
        pool_data:
            Pool data from JSON
        pool_name:
            Name of the pool (root vdev has same name)

        Returns
        -------
        dict[str, Any]:
            Root vdev data, or empty dict if not found
        """
        vdevs = pool_data.get("vdevs", {})
        return vdevs.get(pool_name, {})

    def _extract_capacity_from_vdev(self, root_vdev: dict[str, Any]) -> dict[str, Any]:
        """Extract capacity metrics from root vdev.

        With --json-int, values are already integers (bytes).

        Parameters
        ----------
        root_vdev:
            Root vdev data from zpool status JSON

        Returns
        -------
        dict:
            Dictionary with capacity_percent, size_bytes, allocated_bytes, free_bytes
        """
        # Get integer values directly (no string parsing needed)
        alloc_space = root_vdev.get("alloc_space", 0)
        total_space = root_vdev.get("total_space", 0)

        # Ensure we have integers
        try:
            allocated_bytes = int(alloc_space)
            size_bytes = int(total_space)
        except (ValueError, TypeError):
            logger.warning(
                "Invalid capacity values in vdev",
                extra={"alloc_space": alloc_space, "total_space": total_space},
            )
            allocated_bytes = 0
            size_bytes = 0

        # Calculate derived values
        free_bytes = size_bytes - allocated_bytes if size_bytes > 0 else 0
        capacity_percent = (allocated_bytes / size_bytes * 100) if size_bytes > 0 else 0.0

        return {
            "capacity_percent": capacity_percent,
            "size_bytes": size_bytes,
            "allocated_bytes": allocated_bytes,
            "free_bytes": free_bytes,
        }

    def _extract_errors_from_vdev(self, root_vdev: dict[str, Any]) -> ErrorCounts:
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
        try:
            return ErrorCounts(
                read=int(root_vdev.get("read_errors", 0)),
                write=int(root_vdev.get("write_errors", 0)),
                checksum=int(root_vdev.get("checksum_errors", 0)),
            )
        except (ValueError, TypeError) as exc:
            logger.warning(f"Invalid error counts in vdev: {exc}")
            return ErrorCounts()

    def _extract_scrub_info(self, pool_data: dict[str, Any]) -> dict[str, Any]:
        """Extract scrub information from pool status data.

        With --json-int, timestamps are Unix integers.

        Parameters
        ----------
        pool_data:
            Pool data from zpool status JSON

        Returns
        -------
        dict:
            Dictionary with last_scrub, scrub_errors, scrub_in_progress
        """
        scan_info = pool_data.get("scan_stats", pool_data.get("scan", {}))

        # Parse scrub time from integer timestamp
        last_scrub = self._parse_scrub_time(scan_info)

        # Get scrub errors (already integer with --json-int)
        scrub_errors_raw = scan_info.get("errors", 0)
        try:
            scrub_errors = int(scrub_errors_raw)
        except (ValueError, TypeError):
            logger.warning(f"Invalid scrub_errors value '{scrub_errors_raw}', using 0")
            scrub_errors = 0

        # Check if scrub is in progress
        state = str(scan_info.get("state", "")).upper()
        scrub_in_progress = state == "SCANNING"

        return {
            "last_scrub": last_scrub,
            "scrub_errors": scrub_errors,
            "scrub_in_progress": scrub_in_progress,
        }

    def _parse_scrub_time(self, scan_info: dict[str, Any]) -> datetime | None:
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
        if not scan_info:
            return None

        # Try timestamp fields in order of preference
        # With --json-int these are already integers
        for field in ["end_time", "pass_start", "start_time"]:
            time_value = scan_info.get(field)
            if time_value is not None:
                try:
                    timestamp = int(time_value)
                    if timestamp > 0:
                        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
                except (ValueError, TypeError, OSError) as exc:
                    logger.debug(f"Failed to parse timestamp field '{field}': {exc}")
                    continue

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
            logger.warning(f"Unknown health state '{health_value}' for pool {pool_name}, using OFFLINE")
            return PoolHealth.OFFLINE

    def _find_problematic_devices(self, vdev: dict[str, Any]) -> list[DeviceStatus]:
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

        # Check if this vdev itself is problematic (only for disk/leaf devices)
        vdev_type = str(vdev.get("vdev_type", "")).lower()
        state = str(vdev.get("state", "UNKNOWN")).upper()
        name = str(vdev.get("name", "unknown"))

        # Get error counts
        read_errors = self._safe_int(vdev.get("read_errors", 0))
        write_errors = self._safe_int(vdev.get("write_errors", 0))
        checksum_errors = self._safe_int(vdev.get("checksum_errors", 0))

        # Only report leaf devices (disks) - not containers like mirror/raidz
        is_leaf = vdev_type in ("disk", "file", "spare", "cache", "log")
        is_problematic = state in ("FAULTED", "DEGRADED", "OFFLINE", "UNAVAIL", "REMOVED")
        has_errors = read_errors > 0 or write_errors > 0 or checksum_errors > 0

        if is_leaf and (is_problematic or has_errors):
            device = DeviceStatus(
                name=name,
                state=state,
                read_errors=read_errors,
                write_errors=write_errors,
                checksum_errors=checksum_errors,
                vdev_type=vdev_type,
            )
            problematic.append(device)
            logger.debug(
                f"Found problematic device: {name}",
                extra={
                    "device": name,
                    "state": state,
                    "read_errors": read_errors,
                    "write_errors": write_errors,
                    "checksum_errors": checksum_errors,
                },
            )

        # Recursively check child vdevs
        children = vdev.get("vdevs", {})
        if isinstance(children, dict):
            for child_vdev in children.values():
                if isinstance(child_vdev, dict):
                    problematic.extend(self._find_problematic_devices(child_vdev))

        return problematic

    def _safe_int(self, value: Any) -> int:
        """Safely convert value to int.

        Parameters
        ----------
        value:
            Value to convert.

        Returns
        -------
        int:
            Integer value, or 0 if conversion fails.
        """
        try:
            return int(value)
        except (ValueError, TypeError):
            return 0


__all__ = [
    "ZFSParser",
    "ZFSParseError",
]
