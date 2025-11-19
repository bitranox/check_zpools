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
import re
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, cast

from .models import PoolHealth, PoolStatus

logger = logging.getLogger(__name__)

# Pre-compiled regex patterns for performance
# Pattern for parsing size strings with binary suffixes (e.g., "1.5T", "500G")
_SIZE_PATTERN = re.compile(r"^([0-9.]+)\s*([KMGTP])$")


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
        health = self._parse_health_state(health_value, pool_name)

        # Extract capacity metrics
        capacity_metrics = self._extract_capacity_metrics(props)

        # Create PoolStatus with list data (errors/scrub will be defaults)
        return PoolStatus(
            name=pool_name,
            health=health,
            capacity_percent=capacity_metrics["capacity_percent"],
            size_bytes=capacity_metrics["size_bytes"],
            allocated_bytes=capacity_metrics["allocated_bytes"],
            free_bytes=capacity_metrics["free_bytes"],
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
        health = self._parse_health_state(state, pool_name)

        # Extract error counts from vdev tree
        errors = self._extract_error_counts(pool_data)

        # Extract scrub information
        scrub_info = self._extract_scrub_info(pool_data)

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
            last_scrub=scrub_info["last_scrub"],
            scrub_errors=scrub_info["scrub_errors"],
            scrub_in_progress=scrub_info["scrub_in_progress"],
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

    @lru_cache(maxsize=32)
    def _parse_size_to_bytes(self, size_str: str) -> int:
        """Convert size string to bytes.

        Why Cached
        ----------
        Same size values appear repeatedly across multiple pools (e.g., "1000000").
        Caching eliminates redundant string-to-float-to-int conversions.
        maxsize=32 covers typical ZFS size variations without excessive memory.

        Parameters
        ----------
        size_str:
            Size as string. May be numeric ("1000000") or with suffix ("1.5T").
            Supports binary suffixes: K (1024), M (1024^2), G (1024^3),
            T (1024^4), P (1024^5).

        Returns
        -------
        int:
            Size in bytes

        Raises
        ------
        ValueError:
            If size_str cannot be parsed as number or number+suffix

        Examples
        --------
        >>> parser = ZFSParser()
        >>> parser._parse_size_to_bytes("1000000")
        1000000
        >>> parser._parse_size_to_bytes("1.5T")
        1649267441664
        >>> parser._parse_size_to_bytes("500G")
        536870912000
        """
        # Try parsing as plain number first (most common case)
        try:
            return int(float(size_str))
        except ValueError:
            pass

        # Parse with suffix (e.g., "1.5T", "500G", "10M")
        # Use pre-compiled pattern for performance
        match = _SIZE_PATTERN.match(size_str.strip().upper())

        if not match:
            raise ValueError(f"Cannot parse size string '{size_str}' - expected number or number+suffix (K/M/G/T/P)")

        value_str, suffix = match.groups()

        try:
            value = float(value_str)
        except ValueError as exc:
            raise ValueError(f"Invalid numeric value in size string '{size_str}'") from exc

        # Binary multipliers (1K = 1024 bytes, not 1000)
        multipliers = {
            "K": 1024,
            "M": 1024**2,
            "G": 1024**3,
            "T": 1024**4,
            "P": 1024**5,
        }

        multiplier = multipliers[suffix]
        result = int(value * multiplier)

        logger.debug(f"Parsed size string: '{size_str}' → {result} bytes", extra={"size_str": size_str, "value": value, "suffix": suffix, "bytes": result})

        return result

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

        # Error counts can be in different locations depending on ZFS version:
        # - Older format: pool_data["vdev_tree"]["stats"]
        # - Newer format: pool_data["vdevs"][pool_name] (root vdev)

        # Try newer format first (vdevs)
        vdevs = pool_data.get("vdevs", {})
        if vdevs:
            # The root vdev typically has the same name as the pool
            pool_name = pool_data.get("name", "")
            root_vdev = vdevs.get(pool_name, {})

            if root_vdev:
                try:
                    errors["read"] = int(root_vdev.get("read_errors", 0))
                    errors["write"] = int(root_vdev.get("write_errors", 0))
                    errors["checksum"] = int(root_vdev.get("checksum_errors", 0))
                    return errors
                except (ValueError, TypeError):
                    pass  # Fall through to try old format

        # Try older format (vdev_tree/stats)
        vdev_tree = pool_data.get("vdev_tree", {})
        if vdev_tree:
            stats = vdev_tree.get("stats", {})
            if stats:
                try:
                    errors["read"] = int(stats.get("read_errors", 0))
                    errors["write"] = int(stats.get("write_errors", 0))
                    errors["checksum"] = int(stats.get("checksum_errors", 0))
                    return errors
                except (ValueError, TypeError):
                    pass

        return errors

    def _try_parse_unix_timestamp(self, scan_info: dict[str, Any], field_names: list[str]) -> datetime | None:
        """Try parsing Unix timestamp from specified fields.

        Parameters
        ----------
        scan_info:
            Scan/scrub information from zpool status
        field_names:
            List of field names to try

        Returns
        -------
        datetime | None:
            Parsed timestamp in UTC, or None if parsing fails
        """
        for field in field_names:
            time_value = scan_info.get(field)
            if time_value is not None:
                try:
                    # Handle both int and string timestamps
                    timestamp = int(time_value) if isinstance(time_value, (int, str)) else time_value
                    return datetime.fromtimestamp(timestamp, tz=timezone.utc)
                except (ValueError, TypeError, OSError) as exc:
                    logger.debug(f"Failed to parse timestamp field '{field}' with value {time_value}: {exc}")
                    continue
        return None

    def _try_parse_datetime_string(self, scan_info: dict[str, Any], field_names: list[str]) -> datetime | None:
        """Try parsing human-readable datetime strings from specified fields.

        Parameters
        ----------
        scan_info:
            Scan/scrub information from zpool status
        field_names:
            List of field names to try

        Returns
        -------
        datetime | None:
            Parsed datetime in UTC, or None if parsing fails
        """
        for field in field_names:
            time_str = scan_info.get(field)
            if time_str and isinstance(time_str, str):
                try:
                    from dateutil import parser as dateutil_parser  # noqa: E402

                    parsed_dt = dateutil_parser.parse(time_str)
                    return self._normalize_timezone(parsed_dt)
                except (ValueError, ImportError) as exc:
                    logger.debug(f"Failed to parse datetime string '{field}' with value {time_str}: {exc}")
                    continue
        return None

    def _normalize_timezone(self, dt: datetime) -> datetime:
        """Normalize datetime to UTC timezone.

        Parameters
        ----------
        dt:
            Datetime to normalize

        Returns
        -------
        datetime:
            Datetime in UTC timezone
        """
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

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

        Notes
        -----
        Different ZFS versions use different field names and formats.
        This function tries multiple strategies to extract the timestamp.
        """
        if not scan_info:
            return None

        # Strategy 1: Try Unix timestamp fields (as integers or strings)
        timestamp_fields = ["pass_start", "end_time", "scrub_end", "func_e", "finish_time"]
        result = self._try_parse_unix_timestamp(scan_info, timestamp_fields)
        if result:
            return result

        # Strategy 2: Try parsing human-readable datetime strings
        # Format example: "Sun Nov 16 08:00:21 CET 2025"
        datetime_string_fields = ["end_time", "start_time"]
        result = self._try_parse_datetime_string(scan_info, datetime_string_fields)
        if result:
            return result

        # If we reach here, log what fields we actually found for debugging
        logger.debug(f"No valid scrub timestamp found in scan_info. Available fields: {list(scan_info.keys())}")
        return None

    def _parse_health_state(self, health_value: str, pool_name: str) -> PoolHealth:
        """Parse health state string into PoolHealth enum.

        Parameters
        ----------
        health_value:
            Raw health state string from ZFS.
        pool_name:
            Pool name for logging.

        Returns
        -------
        PoolHealth:
            Parsed health state, defaults to OFFLINE if unknown.
        """
        try:
            return PoolHealth(health_value)
        except ValueError:
            logger.warning(f"Unknown health state '{health_value}' for pool {pool_name}, using OFFLINE")
            return PoolHealth.OFFLINE

    def _extract_capacity_metrics(self, props: dict[str, Any]) -> dict[str, Any]:
        """Extract capacity metrics from pool properties.

        Parameters
        ----------
        props:
            Pool properties from zpool list JSON.

        Returns
        -------
        dict:
            Dictionary with capacity_percent, size_bytes, allocated_bytes, free_bytes.
        """
        capacity_str = self._get_property_value(props, "capacity", "0")

        # Strip trailing '%' if present (ZFS JSON format includes it)
        capacity_str = capacity_str.rstrip("%")

        # Defensive float conversion with fallback
        try:
            capacity_percent = float(capacity_str)
        except ValueError:
            logger.warning(f"Invalid capacity value '{capacity_str}', using 0.0 as fallback", extra={"capacity_str": capacity_str})
            capacity_percent = 0.0

        size_str = self._get_property_value(props, "size", "0")
        size_bytes = self._parse_size_to_bytes(size_str)

        allocated_str = self._get_property_value(props, "allocated", "0")
        allocated_bytes = self._parse_size_to_bytes(allocated_str)

        free_str = self._get_property_value(props, "free", "0")
        free_bytes = self._parse_size_to_bytes(free_str)

        return {
            "capacity_percent": capacity_percent,
            "size_bytes": size_bytes,
            "allocated_bytes": allocated_bytes,
            "free_bytes": free_bytes,
        }

    def _extract_scrub_info(self, pool_data: dict[str, Any]) -> dict[str, Any]:
        """Extract scrub information from pool status data.

        Parameters
        ----------
        pool_data:
            Pool data from zpool status JSON.

        Returns
        -------
        dict:
            Dictionary with last_scrub, scrub_errors, scrub_in_progress.
        """
        # Try both "scan_stats" (newer) and "scan" (older) field names
        scan_info = pool_data.get("scan_stats", pool_data.get("scan", {}))
        last_scrub = self._parse_scrub_time(scan_info)

        # Convert scrub_errors to int (may be string in JSON)
        scrub_errors_raw = scan_info.get("errors", 0)
        try:
            scrub_errors = int(scrub_errors_raw)
        except (ValueError, TypeError):
            logger.warning(f"Invalid scrub_errors value '{scrub_errors_raw}', using 0", extra={"scrub_errors": scrub_errors_raw})
            scrub_errors = 0

        # State can be "FINISHED", "SCANNING", "finished", "scanning", etc.
        state = scan_info.get("state", "").upper()
        scrub_in_progress = state == "SCANNING"

        return {
            "last_scrub": last_scrub,
            "scrub_errors": scrub_errors,
            "scrub_in_progress": scrub_in_progress,
        }


__all__ = [
    "ZFSParser",
    "ZFSParseError",
]
