"""Tests for ZFS JSON parser.

Purpose
-------
Validate ZFS JSON parsing logic using sample data files. Tests handle various
pool states, missing fields, and data merging scenarios.
"""

from __future__ import annotations

import json
import pytest
from datetime import datetime
from pathlib import Path

from check_zpools.models import PoolHealth
from check_zpools.zfs_parser import ZFSParser


@pytest.fixture
def parser() -> ZFSParser:
    """Provide ZFSParser instance for tests."""
    return ZFSParser()


@pytest.fixture
def sample_data_dir() -> Path:
    """Get path to test data directory."""
    return Path(__file__).parent


@pytest.fixture
def zpool_list_ok(sample_data_dir: Path) -> dict:
    """Load zpool list sample with healthy pools."""
    with open(sample_data_dir / "zpool_list_ok_sample.json") as f:
        return json.load(f)


@pytest.fixture
def zpool_status_degraded(sample_data_dir: Path) -> dict:
    """Load zpool status sample with degraded pool."""
    with open(sample_data_dir / "zpool_status_degraded.json") as f:
        return json.load(f)


@pytest.fixture
def zpool_status_with_errors(sample_data_dir: Path) -> dict:
    """Load zpool status sample with errors."""
    with open(sample_data_dir / "zpool_status_with_errors.json") as f:
        return json.load(f)


class TestParsePoolList:
    """Tests for parsing zpool list output."""

    def test_parse_empty_pools(self, parser: ZFSParser) -> None:
        """Verify parser handles empty pools dict."""
        data = {"output_version": {"command": "zpool list"}, "pools": {}}
        pools = parser.parse_pool_list(data)
        assert len(pools) == 0

    def test_parse_missing_pools_key(self, parser: ZFSParser) -> None:
        """Verify parser handles missing pools key."""
        data = {"output_version": {"command": "zpool list"}}
        pools = parser.parse_pool_list(data)
        assert len(pools) == 0

    def test_parse_single_healthy_pool(self, parser: ZFSParser, zpool_list_ok: dict) -> None:
        """Verify parser extracts pool from zpool list output."""
        pools = parser.parse_pool_list(zpool_list_ok)

        assert len(pools) > 0
        assert "rpool" in pools

        rpool = pools["rpool"]
        assert rpool.name == "rpool"
        assert rpool.health == PoolHealth.ONLINE
        # Note: capacity_percent might be 0 in some test data
        assert rpool.size_bytes >= 0
        assert rpool.allocated_bytes >= 0
        assert rpool.free_bytes >= 0

    def test_parse_multiple_pools(self, parser: ZFSParser, zpool_list_ok: dict) -> None:
        """Verify parser handles multiple pools."""
        pools = parser.parse_pool_list(zpool_list_ok)

        # Sample data has multiple pools
        assert len(pools) >= 1

        # Verify each pool has required fields
        for pool_name, pool_status in pools.items():
            assert pool_status.name == pool_name
            assert isinstance(pool_status.health, PoolHealth)
            assert pool_status.capacity_percent >= 0.0
            assert pool_status.size_bytes >= 0

    def test_parse_pool_with_missing_properties(self, parser: ZFSParser) -> None:
        """Verify parser handles missing properties gracefully."""
        data = {
            "pools": {
                "testpool": {
                    "name": "testpool",
                    "state": "ONLINE",
                    "properties": {
                        # Missing capacity, size, etc.
                        "health": {"value": "ONLINE"}
                    },
                }
            }
        }

        pools = parser.parse_pool_list(data)
        assert len(pools) == 1
        assert pools["testpool"].name == "testpool"
        assert pools["testpool"].health == PoolHealth.ONLINE


class TestParsePoolStatus:
    """Tests for parsing zpool status output."""

    def test_parse_degraded_pool(self, parser: ZFSParser, zpool_status_degraded: dict) -> None:
        """Verify parser detects degraded pool state."""
        pools = parser.parse_pool_status(zpool_status_degraded)

        assert "rpool" in pools
        rpool = pools["rpool"]

        assert rpool.name == "rpool"
        assert rpool.health == PoolHealth.DEGRADED
        assert rpool.read_errors == 0
        assert rpool.write_errors == 0
        assert rpool.checksum_errors == 0

    def test_parse_pool_with_errors(self, parser: ZFSParser, zpool_status_with_errors: dict) -> None:
        """Verify parser extracts error counts."""
        pools = parser.parse_pool_status(zpool_status_with_errors)

        assert "zpool-data" in pools
        pool = pools["zpool-data"]

        assert pool.name == "zpool-data"
        assert pool.health == PoolHealth.ONLINE
        assert pool.read_errors == 5
        assert pool.write_errors == 2
        assert pool.checksum_errors == 1

    def test_parse_scrub_information(self, parser: ZFSParser, zpool_status_degraded: dict) -> None:
        """Verify parser extracts scrub timestamps."""
        pools = parser.parse_pool_status(zpool_status_degraded)

        rpool = pools["rpool"]
        assert rpool.last_scrub is not None
        assert isinstance(rpool.last_scrub, datetime)
        assert rpool.last_scrub.tzinfo is not None  # Should have timezone
        assert rpool.scrub_errors == 0
        assert rpool.scrub_in_progress is False

    def test_parse_scrub_errors(self, parser: ZFSParser, zpool_status_with_errors: dict) -> None:
        """Verify parser detects scrub errors."""
        pools = parser.parse_pool_status(zpool_status_with_errors)

        pool = pools["zpool-data"]
        assert pool.scrub_errors == 3

    def test_parse_pool_with_unknown_health(self, parser: ZFSParser) -> None:
        """Verify parser handles unknown health states."""
        data = {
            "pools": {
                "testpool": {
                    "name": "testpool",
                    "state": "BOGUS_STATE",
                    "vdev_tree": {"stats": {}},
                    "scan": {},
                }
            }
        }

        pools = parser.parse_pool_status(data)
        assert pools["testpool"].health == PoolHealth.OFFLINE  # Default fallback


class TestMergePoolData:
    """Tests for merging data from list and status."""

    def test_merge_combines_capacity_and_errors(self, parser: ZFSParser) -> None:
        """Verify merge combines capacity from list with errors from status."""
        list_data = {
            "testpool": parser._parse_pool_from_list(
                "testpool",
                {
                    "name": "testpool",
                    "state": "ONLINE",
                    "properties": {
                        "health": {"value": "ONLINE"},
                        "capacity": {"value": "75"},
                        "size": {"value": "1000000"},
                        "allocated": {"value": "750000"},
                        "free": {"value": "250000"},
                    },
                },
            )
        }

        status_data = {
            "testpool": parser._parse_pool_from_status(
                "testpool",
                {
                    "name": "testpool",
                    "state": "DEGRADED",
                    "vdev_tree": {
                        "stats": {
                            "read_errors": 10,
                            "write_errors": 5,
                            "checksum_errors": 2,
                        }
                    },
                    "scan": {},
                },
            )
        }

        merged = parser.merge_pool_data(list_data, status_data)

        assert "testpool" in merged
        pool = merged["testpool"]

        # Should have capacity from list
        assert pool.capacity_percent == 75.0
        assert pool.size_bytes == 1000000
        assert pool.allocated_bytes == 750000
        assert pool.free_bytes == 250000

        # Should have errors from status
        assert pool.read_errors == 10
        assert pool.write_errors == 5
        assert pool.checksum_errors == 2

        # Should prefer health from status
        assert pool.health == PoolHealth.DEGRADED

    def test_merge_handles_pool_only_in_list(self, parser: ZFSParser) -> None:
        """Verify merge handles pools only present in list."""
        list_data = {
            "pool1": parser._parse_pool_from_list(
                "pool1",
                {
                    "name": "pool1",
                    "properties": {
                        "health": {"value": "ONLINE"},
                        "capacity": {"value": "50"},
                        "size": {"value": "1000"},
                        "allocated": {"value": "500"},
                        "free": {"value": "500"},
                    },
                },
            )
        }

        status_data = {}

        merged = parser.merge_pool_data(list_data, status_data)

        assert "pool1" in merged
        # Should have list data with default error counts
        assert merged["pool1"].capacity_percent == 50.0
        assert merged["pool1"].read_errors == 0

    def test_merge_handles_pool_only_in_status(self, parser: ZFSParser) -> None:
        """Verify merge handles pools only present in status."""
        list_data = {}

        status_data = {
            "pool2": parser._parse_pool_from_status(
                "pool2",
                {
                    "name": "pool2",
                    "state": "ONLINE",
                    "vdev_tree": {"stats": {"read_errors": 1}},
                    "scan": {},
                },
            )
        }

        merged = parser.merge_pool_data(list_data, status_data)

        assert "pool2" in merged
        # Should have status data with default capacity
        assert merged["pool2"].read_errors == 1
        assert merged["pool2"].capacity_percent == 0.0  # No capacity data


class TestHelperMethods:
    """Tests for parser helper methods."""

    def test_get_property_value_with_dict(self, parser: ZFSParser) -> None:
        """Verify property value extraction from dict."""
        props = {"health": {"value": "ONLINE", "source": {"type": "NONE"}}}
        value = parser._get_property_value(props, "health", "UNKNOWN")
        assert value == "ONLINE"

    def test_get_property_value_missing_key(self, parser: ZFSParser) -> None:
        """Verify default returned for missing property."""
        props = {}
        value = parser._get_property_value(props, "health", "DEFAULT")
        assert value == "DEFAULT"

    def test_parse_size_to_bytes_numeric(self, parser: ZFSParser) -> None:
        """Verify numeric size strings are parsed."""
        assert parser._parse_size_to_bytes("1000000") == 1000000
        assert parser._parse_size_to_bytes("12345") == 12345

    def test_extract_error_counts_from_vdev_tree(self, parser: ZFSParser) -> None:
        """Verify error extraction from vdev stats."""
        pool_data = {
            "vdev_tree": {
                "stats": {
                    "read_errors": 10,
                    "write_errors": 5,
                    "checksum_errors": 3,
                }
            }
        }

        errors = parser._extract_error_counts(pool_data)
        assert errors["read"] == 10
        assert errors["write"] == 5
        assert errors["checksum"] == 3

    def test_extract_error_counts_missing_stats(self, parser: ZFSParser) -> None:
        """Verify defaults when stats missing."""
        pool_data = {"vdev_tree": {}}

        errors = parser._extract_error_counts(pool_data)
        assert errors["read"] == 0
        assert errors["write"] == 0
        assert errors["checksum"] == 0

    def test_parse_scrub_time_with_valid_timestamp(self, parser: ZFSParser) -> None:
        """Verify scrub time parsing from Unix timestamp."""
        scan_info = {"end_time": 1700000000}  # Unix timestamp

        scrub_time = parser._parse_scrub_time(scan_info)
        assert scrub_time is not None
        assert isinstance(scrub_time, datetime)
        assert scrub_time.year >= 2023  # Sanity check

    def test_parse_scrub_time_with_no_end_time(self, parser: ZFSParser) -> None:
        """Verify None returned when no end_time."""
        scan_info = {"state": "scanning"}

        scrub_time = parser._parse_scrub_time(scan_info)
        assert scrub_time is None

    def test_parse_scrub_time_with_empty_scan_info(self, parser: ZFSParser) -> None:
        """Verify None returned for empty scan info."""
        scrub_time = parser._parse_scrub_time({})
        assert scrub_time is None
