"""Tests for ZFS JSON parser.

Purpose
-------
Validate ZFS JSON parsing logic using sample data files. Tests handle various
pool states, missing fields, and parsing scenarios for zpool status --json-int.

All tests are OS-agnostic (JSON parsing logic works everywhere).
Tests use real ZFS JSON fixtures (not mocks).
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
def zpool_status_ok(sample_data_dir: Path) -> dict:
    """Load zpool status sample with healthy pools (--json-int format)."""
    with open(sample_data_dir / "zpool_status_ok.json") as f:
        return json.load(f)


@pytest.fixture
def zpool_status_degraded(sample_data_dir: Path) -> dict:
    """Load zpool status sample with degraded pool (--json-int format)."""
    with open(sample_data_dir / "zpool_status_degraded.json") as f:
        return json.load(f)


@pytest.fixture
def zpool_status_with_errors(sample_data_dir: Path) -> dict:
    """Load zpool status sample with errors (--json-int format)."""
    with open(sample_data_dir / "zpool_status_with_errors.json") as f:
        return json.load(f)


@pytest.mark.os_agnostic
class TestParsePoolStatus:
    """Tests for parsing zpool status --json-int output."""

    def test_parse_empty_pools(self, parser: ZFSParser) -> None:
        """Verify parser handles empty pools dict."""
        data = {"output_version": {"command": "zpool status"}, "pools": {}}
        pools = parser.parse_pool_status(data)
        assert len(pools) == 0

    def test_parse_missing_pools_key(self, parser: ZFSParser) -> None:
        """Verify parser handles missing pools key."""
        data = {"output_version": {"command": "zpool status"}}
        pools = parser.parse_pool_status(data)
        assert len(pools) == 0

    def test_parse_single_healthy_pool(self, parser: ZFSParser, zpool_status_ok: dict) -> None:
        """Verify parser extracts pool from zpool status output."""
        pools = parser.parse_pool_status(zpool_status_ok)

        assert len(pools) > 0
        assert "rpool" in pools

        rpool = pools["rpool"]
        assert rpool.name == "rpool"
        assert rpool.health == PoolHealth.ONLINE
        assert rpool.size_bytes > 0
        assert rpool.allocated_bytes > 0
        assert rpool.free_bytes > 0
        assert rpool.capacity_percent > 0

    def test_parse_multiple_pools(self, parser: ZFSParser, zpool_status_ok: dict) -> None:
        """Verify parser handles multiple pools."""
        pools = parser.parse_pool_status(zpool_status_ok)

        # Sample data has multiple pools
        assert len(pools) >= 1

        # Verify each pool has required fields
        for pool_name, pool_status in pools.items():
            assert pool_status.name == pool_name
            assert isinstance(pool_status.health, PoolHealth)
            assert pool_status.capacity_percent >= 0.0
            assert pool_status.size_bytes >= 0

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
                    "vdevs": {"testpool": {}},
                    "scan_stats": {},
                }
            }
        }

        pools = parser.parse_pool_status(data)
        assert pools["testpool"].health == PoolHealth.OFFLINE  # Default fallback

    def test_parse_pool_with_missing_vdev(self, parser: ZFSParser) -> None:
        """Verify parser handles missing vdev gracefully."""
        data = {
            "pools": {
                "testpool": {
                    "name": "testpool",
                    "state": "ONLINE",
                    "vdevs": {},  # No vdevs
                    "scan_stats": {},
                }
            }
        }

        pools = parser.parse_pool_status(data)
        assert len(pools) == 1
        assert pools["testpool"].name == "testpool"
        assert pools["testpool"].health == PoolHealth.ONLINE
        # Default capacity values when vdev missing
        assert pools["testpool"].capacity_percent == 0.0
        assert pools["testpool"].size_bytes == 0

    def test_parse_capacity_calculation(self, parser: ZFSParser) -> None:
        """Verify capacity percentage is calculated correctly from vdev data."""
        data = {
            "pools": {
                "testpool": {
                    "name": "testpool",
                    "state": "ONLINE",
                    "vdevs": {
                        "testpool": {
                            "alloc_space": 500000000000,  # 500GB allocated
                            "total_space": 1000000000000,  # 1TB total
                            "read_errors": 0,
                            "write_errors": 0,
                            "checksum_errors": 0,
                        }
                    },
                    "scan_stats": {},
                }
            }
        }

        pools = parser.parse_pool_status(data)
        pool = pools["testpool"]

        assert pool.capacity_percent == 50.0  # 50% used
        assert pool.size_bytes == 1000000000000
        assert pool.allocated_bytes == 500000000000
        assert pool.free_bytes == 500000000000


class TestHelperMethods:
    """Tests for parser helper methods."""

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

    def test_extract_capacity_from_vdev(self, parser: ZFSParser) -> None:
        """Verify capacity extraction from vdev with integer values."""
        root_vdev = {
            "alloc_space": 100000000,
            "total_space": 1000000000,
        }

        capacity = parser._extract_capacity_from_vdev(root_vdev)

        assert capacity["allocated_bytes"] == 100000000
        assert capacity["size_bytes"] == 1000000000
        assert capacity["free_bytes"] == 900000000
        assert capacity["capacity_percent"] == 10.0

    def test_extract_capacity_empty_vdev(self, parser: ZFSParser) -> None:
        """Verify default values for empty vdev."""
        capacity = parser._extract_capacity_from_vdev({})

        assert capacity["allocated_bytes"] == 0
        assert capacity["size_bytes"] == 0
        assert capacity["free_bytes"] == 0
        assert capacity["capacity_percent"] == 0.0

    def test_extract_errors_from_vdev(self, parser: ZFSParser) -> None:
        """Verify error extraction from vdev with integer values."""
        root_vdev = {
            "read_errors": 10,
            "write_errors": 5,
            "checksum_errors": 3,
        }

        errors = parser._extract_errors_from_vdev(root_vdev)

        assert errors.read == 10
        assert errors.write == 5
        assert errors.checksum == 3

    def test_extract_errors_empty_vdev(self, parser: ZFSParser) -> None:
        """Verify default values for empty vdev."""
        errors = parser._extract_errors_from_vdev({})

        assert errors.read == 0
        assert errors.write == 0
        assert errors.checksum == 0

    def test_get_root_vdev(self, parser: ZFSParser) -> None:
        """Verify root vdev extraction from pool data."""
        pool_data = {
            "vdevs": {
                "testpool": {
                    "alloc_space": 100,
                    "total_space": 1000,
                }
            }
        }

        root_vdev = parser._get_root_vdev(pool_data, "testpool")

        assert root_vdev["alloc_space"] == 100
        assert root_vdev["total_space"] == 1000

    def test_get_root_vdev_missing(self, parser: ZFSParser) -> None:
        """Verify empty dict returned when vdev missing."""
        pool_data = {"vdevs": {}}

        root_vdev = parser._get_root_vdev(pool_data, "testpool")

        assert root_vdev == {}

    def test_parse_health_state_valid(self, parser: ZFSParser) -> None:
        """Verify valid health states are parsed correctly."""
        assert parser._parse_health_state("ONLINE", "test") == PoolHealth.ONLINE
        assert parser._parse_health_state("DEGRADED", "test") == PoolHealth.DEGRADED
        assert parser._parse_health_state("FAULTED", "test") == PoolHealth.FAULTED
        assert parser._parse_health_state("OFFLINE", "test") == PoolHealth.OFFLINE

    def test_parse_health_state_unknown(self, parser: ZFSParser) -> None:
        """Verify unknown health state defaults to OFFLINE."""
        assert parser._parse_health_state("BOGUS", "test") == PoolHealth.OFFLINE
