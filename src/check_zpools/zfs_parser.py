"""ZFS JSON output parser.

Purpose
-------
Parse JSON output from `zpool list -j` and `zpool status -j` commands into
typed PoolStatus objects. Handles missing fields, type conversions, and data
merging from multiple sources.

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
- Type conversions (strings to datetime, bytes to ints, etc.)
- Merges data from multiple commands (list + status)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, cast

from .models import PoolHealth, PoolStatus

logger = logging.getLogger(__name__)


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
    ...     "output_version": {"command": "zpool list"},
    ...     "pools": {
    ...         "rpool": {
    ...             "name": "rpool",
    ...             "state": "ONLINE",
    ...             "properties": {
    ...                 "health": {"value": "ONLINE"},
    ...                 "capacity": {"value": "45"},
    ...                 "size": {"value": "1000000000"},
    ...                 "allocated": {"value": "450000000"},
    ...                 "free": {"value": "550000000"},
    ...             }
    ...         }
    ...     }
    ... }
    >>> pools = parser.parse_pool_list(json_data)  # doctest: +SKIP
    >>> pools["rpool"].name  # doctest: +SKIP
    'rpool'
    """

    def parse_pool_list(self, json_data: dict[str, Any]) -> dict[str, PoolStatus]:
        """Parse `zpool list -j` JSON output into PoolStatus objects.

        Why
            Extracts capacity, size, and health information from zpool list
            command. This is the primary source for capacity monitoring.

        Parameters
        ----------
        json_data:
            Parsed JSON from `zpool list -j` command.

        Returns
        -------
        dict[str, PoolStatus]:
            Dictionary mapping pool name to PoolStatus object.

        Raises
        ------
        ZFSParseError:
            When required fields are missing or invalid.

        Examples
        --------
        >>> parser = ZFSParser()
        >>> data = {"pools": {"rpool": {...}}}  # doctest: +SKIP
        >>> pools = parser.parse_pool_list(data)  # doctest: +SKIP
        """
        pools: dict[str, PoolStatus] = {}

        try:
            pools_data = json_data.get("pools", {})
            if not pools_data:
                logger.warning("No pools found in zpool list output")
                return pools

            for pool_name, pool_data in pools_data.items():
                try:
                    pool_status = self._parse_pool_from_list(pool_name, pool_data)
                    pools[pool_name] = pool_status
                    logger.debug(f"Parsed pool from list: {pool_name}")
                except Exception as exc:
                    logger.error(
                        f"Failed to parse pool {pool_name} from list",
                        extra={"pool_name": pool_name, "error": str(exc)},
                        exc_info=True,
                    )
                    # Continue parsing other pools
                    continue

            return pools

        except Exception as exc:
            logger.error("Failed to parse zpool list output", exc_info=True)
            raise ZFSParseError(f"Failed to parse zpool list output: {exc}") from exc

    def parse_pool_status(self, json_data: dict[str, Any]) -> dict[str, PoolStatus]:
        """Parse `zpool status -j` JSON output into PoolStatus objects.

        Why
            Extracts error counts, scrub information, and detailed health
            status. Complements zpool list with additional metrics.

        Parameters
        ----------
        json_data:
            Parsed JSON from `zpool status -j` command.

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
                    pool_status = self._parse_pool_from_status(pool_name, pool_data)
                    pools[pool_name] = pool_status
                    logger.debug(f"Parsed pool from status: {pool_name}")
                except Exception as exc:
                    logger.error(
                        f"Failed to parse pool {pool_name} from status",
                        extra={"pool_name": pool_name, "error": str(exc)},
                        exc_info=True,
                    )
                    continue

            return pools

        except Exception as exc:
            logger.error("Failed to parse zpool status output", exc_info=True)
            raise ZFSParseError(f"Failed to parse zpool status output: {exc}") from exc

    def merge_pool_data(
        self,
        list_data: dict[str, PoolStatus],
        status_data: dict[str, PoolStatus],
    ) -> dict[str, PoolStatus]:
        """Merge data from zpool list and zpool status.

        Why
            zpool list provides capacity info, zpool status provides errors
            and scrub info. Merging gives complete picture.

        Parameters
        ----------
        list_data:
            Pools from parse_pool_list()
        status_data:
            Pools from parse_pool_status()

        Returns
        -------
        dict[str, PoolStatus]:
            Merged pool data with all available information.

        Examples
        --------
        >>> parser = ZFSParser()
        >>> list_pools = {...}  # doctest: +SKIP
        >>> status_pools = {...}  # doctest: +SKIP
        >>> merged = parser.merge_pool_data(list_pools, status_pools)  # doctest: +SKIP
        """
        merged: dict[str, PoolStatus] = {}

        # Start with all pools from list (capacity data)
        for pool_name, list_pool in list_data.items():
            if pool_name in status_data:
                # Merge with status data (errors, scrub)
                status_pool = status_data[pool_name]
                merged[pool_name] = PoolStatus(
                    name=pool_name,
                    health=status_pool.health,  # Prefer status health
                    capacity_percent=list_pool.capacity_percent,
                    size_bytes=list_pool.size_bytes,
                    allocated_bytes=list_pool.allocated_bytes,
                    free_bytes=list_pool.free_bytes,
                    read_errors=status_pool.read_errors,
                    write_errors=status_pool.write_errors,
                    checksum_errors=status_pool.checksum_errors,
                    last_scrub=status_pool.last_scrub,
                    scrub_errors=status_pool.scrub_errors,
                    scrub_in_progress=status_pool.scrub_in_progress,
                )
                logger.debug(f"Merged data for pool: {pool_name}")
            else:
                # No status data, use list data with defaults
                merged[pool_name] = list_pool

        # Add any pools only in status (shouldn't happen normally)
        for pool_name, status_pool in status_data.items():
            if pool_name not in merged:
                logger.warning(f"Pool {pool_name} in status but not in list")
                merged[pool_name] = status_pool

        return merged

    def _parse_pool_from_list(self, pool_name: str, pool_data: dict[str, Any]) -> PoolStatus:
        """Parse single pool from zpool list output.

        Parameters
        ----------
        pool_name:
            Name of the pool
        pool_data:
            Pool data from JSON

        Returns
        -------
        PoolStatus:
            Parsed pool status with capacity information
        """
        props = pool_data.get("properties", {})

        # Extract health state
        health_value = self._get_property_value(props, "health", "UNKNOWN")
        try:
            health = PoolHealth(health_value)
        except ValueError:
            logger.warning(f"Unknown health state '{health_value}' for pool {pool_name}, using OFFLINE")
            health = PoolHealth.OFFLINE

        # Extract capacity metrics
        capacity_str = self._get_property_value(props, "capacity", "0")
        capacity_percent = float(capacity_str)

        size_str = self._get_property_value(props, "size", "0")
        size_bytes = self._parse_size_to_bytes(size_str)

        allocated_str = self._get_property_value(props, "allocated", "0")
        allocated_bytes = self._parse_size_to_bytes(allocated_str)

        free_str = self._get_property_value(props, "free", "0")
        free_bytes = self._parse_size_to_bytes(free_str)

        # Create PoolStatus with list data (errors/scrub will be defaults)
        return PoolStatus(
            name=pool_name,
            health=health,
            capacity_percent=capacity_percent,
            size_bytes=size_bytes,
            allocated_bytes=allocated_bytes,
            free_bytes=free_bytes,
            read_errors=0,  # Not in list output
            write_errors=0,
            checksum_errors=0,
            last_scrub=None,
            scrub_errors=0,
            scrub_in_progress=False,
        )

    def _parse_pool_from_status(self, pool_name: str, pool_data: dict[str, Any]) -> PoolStatus:
        """Parse single pool from zpool status output.

        Parameters
        ----------
        pool_name:
            Name of the pool
        pool_data:
            Pool data from JSON

        Returns
        -------
        PoolStatus:
            Parsed pool status with error and scrub information
        """
        # Extract health state
        state = pool_data.get("state", "UNKNOWN")
        try:
            health = PoolHealth(state)
        except ValueError:
            logger.warning(f"Unknown health state '{state}' for pool {pool_name}")
            health = PoolHealth.OFFLINE

        # Extract error counts from vdev tree
        errors = self._extract_error_counts(pool_data)

        # Extract scrub information
        scan_info = pool_data.get("scan", {})
        last_scrub = self._parse_scrub_time(scan_info)
        scrub_errors = scan_info.get("errors", 0)
        scrub_in_progress = scan_info.get("state", "") == "scanning"

        # Create PoolStatus with status data (capacity will be defaults)
        return PoolStatus(
            name=pool_name,
            health=health,
            capacity_percent=0.0,  # Not in status output
            size_bytes=0,
            allocated_bytes=0,
            free_bytes=0,
            read_errors=errors["read"],
            write_errors=errors["write"],
            checksum_errors=errors["checksum"],
            last_scrub=last_scrub,
            scrub_errors=scrub_errors,
            scrub_in_progress=scrub_in_progress,
        )

    def _get_property_value(self, props: dict[str, Any], key: str, default: str) -> str:
        """Extract property value from ZFS properties dict.

        Parameters
        ----------
        props:
            Properties dictionary from JSON
        key:
            Property name to extract
        default:
            Default value if property missing

        Returns
        -------
        str:
            Property value or default
        """
        prop_data = props.get(key, {})
        if isinstance(prop_data, dict):
            # Cast to dict[str, Any] for type checker
            prop_dict = cast(dict[str, Any], prop_data)
            return str(prop_dict.get("value", default))
        return str(default)

    def _parse_size_to_bytes(self, size_str: str) -> int:
        """Convert size string to bytes.

        Parameters
        ----------
        size_str:
            Size as string (may be numeric or with suffix like "1.5T")

        Returns
        -------
        int:
            Size in bytes
        """
        try:
            # If it's already a number, return it
            return int(float(size_str))
        except ValueError:
            # Try to parse with suffix (K, M, G, T, P)
            # This is a simplified version; ZFS may use different formats
            logger.debug(f"Parsing size string: {size_str}")
            return int(float(size_str))  # Placeholder for now

    def _extract_error_counts(self, pool_data: dict[str, Any]) -> dict[str, int]:
        """Extract total error counts from vdev tree.

        Parameters
        ----------
        pool_data:
            Pool data from zpool status JSON

        Returns
        -------
        dict:
            Dictionary with 'read', 'write', 'checksum' error counts
        """
        errors = {"read": 0, "write": 0, "checksum": 0}

        # Error counts are in the vdev tree
        vdev_tree = pool_data.get("vdev_tree", {})
        stats = vdev_tree.get("stats", {})

        errors["read"] = int(stats.get("read_errors", 0))
        errors["write"] = int(stats.get("write_errors", 0))
        errors["checksum"] = int(stats.get("checksum_errors", 0))

        return errors

    def _parse_scrub_time(self, scan_info: dict[str, Any]) -> datetime | None:
        """Parse scrub completion time from scan info.

        Parameters
        ----------
        scan_info:
            Scan/scrub information from zpool status

        Returns
        -------
        datetime | None:
            Timestamp of last completed scrub, or None if never scrubbed
        """
        if not scan_info:
            return None

        # Look for end_time or start_time depending on scan state
        end_time = scan_info.get("end_time")
        if end_time:
            try:
                # ZFS timestamps are typically Unix epoch seconds
                return datetime.fromtimestamp(end_time, tz=timezone.utc)
            except (ValueError, TypeError, OSError) as exc:
                logger.warning(f"Failed to parse scrub end_time {end_time}: {exc}")
                return None

        return None


__all__ = [
    "ZFSParser",
    "ZFSParseError",
]
