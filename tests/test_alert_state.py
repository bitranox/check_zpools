"""Tests for alert state management module.

Tests cover:
- Alert state creation and tracking
- Deduplication logic (should_alert)
- State persistence (load/save)
- Recovery detection (clear_issue)
- Error handling (corrupt files, missing data)
- Boundary conditions (exact interval times)

All tests are OS-agnostic (pure Python state management and JSON serialization).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from check_zpools.alert_state import AlertState, AlertStateManager
from check_zpools.models import PoolIssue, Severity


# ============================================================================
# Test Helpers
# ============================================================================


def a_capacity_issue_for(pool_name: str) -> PoolIssue:
    """Create a capacity warning issue for a pool."""
    return PoolIssue(
        pool_name=pool_name,
        severity=Severity.WARNING,
        category="capacity",
        message=f"Pool {pool_name} capacity at 85%",
        details={"capacity_percent": 85},
    )


def an_error_issue_for(pool_name: str) -> PoolIssue:
    """Create an errors warning issue for a pool."""
    return PoolIssue(
        pool_name=pool_name,
        severity=Severity.WARNING,
        category="errors",
        message=f"Pool {pool_name} has read errors",
        details={},
    )


def a_health_issue_for(pool_name: str) -> PoolIssue:
    """Create a health critical issue for a pool."""
    return PoolIssue(
        pool_name=pool_name,
        severity=Severity.CRITICAL,
        category="health",
        message=f"Pool {pool_name} is degraded",
        details={},
    )


def an_alert_state(
    pool_name: str,
    category: str,
    hours_ago: int = 0,
    alert_count: int = 1,
    last_severity: str | None = None,
) -> AlertState:
    """Create an alert state with configurable age and severity."""
    timestamp = datetime.now(UTC) - timedelta(hours=hours_ago)
    return AlertState(
        pool_name=pool_name,
        issue_category=category,
        first_seen=timestamp,
        last_alerted=timestamp,
        alert_count=alert_count,
        last_severity=last_severity,
    )


def a_state_manager(tmp_path: Path, resend_hours: int = 24) -> AlertStateManager:
    """Create an alert state manager with temporary storage."""
    state_file = tmp_path / "alert_state.json"
    return AlertStateManager(state_file, resend_interval_hours=resend_hours)


# ============================================================================
# Tests: AlertState Value Object
# ============================================================================


class TestAlertStateCreation:
    """AlertState objects preserve all their attributes."""

    @pytest.mark.os_agnostic
    def test_alert_state_remembers_pool_name(self) -> None:
        """When creating an alert state with a pool name,
        it faithfully preserves that name."""
        state = an_alert_state("rpool", "capacity")

        assert state.pool_name == "rpool"

    @pytest.mark.os_agnostic
    def test_alert_state_remembers_issue_category(self) -> None:
        """When creating an alert state with a category,
        it faithfully preserves that category."""
        state = an_alert_state("rpool", "capacity")

        assert state.issue_category == "capacity"

    @pytest.mark.os_agnostic
    def test_alert_state_remembers_timestamps(self) -> None:
        """When creating an alert state with timestamps,
        it preserves both first_seen and last_alerted."""
        now = datetime.now(UTC)
        state = AlertState(
            pool_name="rpool",
            issue_category="capacity",
            first_seen=now,
            last_alerted=now,
            alert_count=1,
            last_severity="WARNING",
        )

        assert state.first_seen == now
        assert state.last_alerted == now

    @pytest.mark.os_agnostic
    def test_alert_state_remembers_alert_count(self) -> None:
        """When creating an alert state with a count,
        it preserves that count accurately."""
        state = an_alert_state("rpool", "capacity", alert_count=5)

        assert state.alert_count == 5


# ============================================================================
# Tests: AlertStateManager Initialization
# ============================================================================


class TestStateManagerInitialization:
    """State manager initializes correctly with filesystem storage."""

    @pytest.mark.os_agnostic
    def test_manager_creates_parent_directory_if_missing(self, tmp_path: Path) -> None:
        """When creating a state manager with a non-existent directory,
        the manager creates the directory automatically."""
        state_file = tmp_path / "subdir" / "alert_state.json"

        AlertStateManager(state_file, resend_interval_hours=24)

        assert state_file.parent.exists()

    @pytest.mark.os_agnostic
    def test_new_manager_starts_with_empty_state(self, tmp_path: Path) -> None:
        """When creating a new state manager with no existing state file,
        it has no tracked alert states."""
        manager = a_state_manager(tmp_path)

        assert len(manager.states) == 0


# ============================================================================
# Tests: Alert Deduplication Logic
# ============================================================================


class TestNewIssueDetection:
    """New issues always trigger alerts."""

    @pytest.mark.os_agnostic
    def test_brand_new_issue_should_alert(self, tmp_path: Path) -> None:
        """When checking an issue never seen before,
        should_alert returns True."""
        manager = a_state_manager(tmp_path)
        issue = a_capacity_issue_for("rpool")

        result = manager.should_alert(issue)

        assert result is True


class TestAlertSuppressionWithinInterval:
    """Duplicate alerts within resend interval are suppressed."""

    @pytest.mark.os_agnostic
    def test_immediate_duplicate_is_suppressed(self, tmp_path: Path) -> None:
        """When checking the same issue immediately after alerting,
        should_alert returns False."""
        manager = a_state_manager(tmp_path, resend_hours=24)
        issue = a_capacity_issue_for("rpool")

        manager.record_alert(issue)
        result = manager.should_alert(issue)

        assert result is False

    @pytest.mark.os_agnostic
    def test_duplicate_after_one_hour_is_suppressed(self, tmp_path: Path) -> None:
        """When checking an issue 1 hour after alerting (interval=24h),
        should_alert returns False."""
        manager = a_state_manager(tmp_path, resend_hours=24)
        issue = a_capacity_issue_for("rpool")

        # Simulate alert 1 hour ago
        manager.states["rpool:capacity"] = an_alert_state("rpool", "capacity", hours_ago=1)

        result = manager.should_alert(issue)

        assert result is False


class TestAlertResendAfterInterval:
    """Alerts resend after the configured interval expires."""

    @pytest.mark.os_agnostic
    def test_resend_after_exact_interval_boundary(self, tmp_path: Path) -> None:
        """When checking an issue exactly 24 hours after last alert (interval=24h),
        should_alert returns True."""
        manager = a_state_manager(tmp_path, resend_hours=24)
        issue = a_capacity_issue_for("rpool")

        # Simulate alert exactly 24 hours ago
        manager.states["rpool:capacity"] = an_alert_state("rpool", "capacity", hours_ago=24)

        result = manager.should_alert(issue)

        assert result is True

    @pytest.mark.os_agnostic
    def test_resend_after_interval_plus_one_hour(self, tmp_path: Path) -> None:
        """When checking an issue 25 hours after last alert (interval=24h),
        should_alert returns True."""
        manager = a_state_manager(tmp_path, resend_hours=24)
        issue = a_capacity_issue_for("rpool")

        # Simulate alert 25 hours ago
        manager.states["rpool:capacity"] = an_alert_state("rpool", "capacity", hours_ago=25)

        result = manager.should_alert(issue)

        assert result is True

    @pytest.mark.os_agnostic
    def test_short_interval_allows_faster_resends(self, tmp_path: Path) -> None:
        """When using a 1-hour resend interval,
        alerts resend after 1 hour has passed."""
        manager = a_state_manager(tmp_path, resend_hours=1)
        issue = a_capacity_issue_for("rpool")

        # Simulate alert 2 hours ago
        manager.states["rpool:capacity"] = an_alert_state("rpool", "capacity", hours_ago=2)

        result = manager.should_alert(issue)

        assert result is True


# ============================================================================
# Tests: Recording Alerts
# ============================================================================


class TestRecordingNewAlerts:
    """Recording alerts for new issues creates state entries."""

    @pytest.mark.os_agnostic
    def test_recording_creates_state_entry(self, tmp_path: Path) -> None:
        """When recording an alert for a new issue,
        a state entry is created with the correct key."""
        manager = a_state_manager(tmp_path)
        issue = a_capacity_issue_for("rpool")

        manager.record_alert(issue)

        assert "rpool:capacity" in manager.states

    @pytest.mark.os_agnostic
    def test_recorded_state_has_correct_pool_name(self, tmp_path: Path) -> None:
        """When recording an alert,
        the created state preserves the pool name."""
        manager = a_state_manager(tmp_path)
        issue = a_capacity_issue_for("rpool")

        manager.record_alert(issue)
        state = manager.states["rpool:capacity"]

        assert state.pool_name == "rpool"

    @pytest.mark.os_agnostic
    def test_recorded_state_has_correct_category(self, tmp_path: Path) -> None:
        """When recording an alert,
        the created state preserves the issue category."""
        manager = a_state_manager(tmp_path)
        issue = a_capacity_issue_for("rpool")

        manager.record_alert(issue)
        state = manager.states["rpool:capacity"]

        assert state.issue_category == "capacity"

    @pytest.mark.os_agnostic
    def test_new_alert_starts_with_count_one(self, tmp_path: Path) -> None:
        """When recording an alert for a new issue,
        the alert count starts at 1."""
        manager = a_state_manager(tmp_path)
        issue = a_capacity_issue_for("rpool")

        manager.record_alert(issue)
        state = manager.states["rpool:capacity"]

        assert state.alert_count == 1


class TestRecordingRepeatedAlerts:
    """Recording alerts for existing issues increments the count."""

    @pytest.mark.os_agnostic
    def test_second_alert_increments_count_to_two(self, tmp_path: Path) -> None:
        """When recording a second alert for the same issue,
        the alert count increases to 2."""
        manager = a_state_manager(tmp_path)
        issue = a_capacity_issue_for("rpool")

        manager.record_alert(issue)
        manager.record_alert(issue)

        state = manager.states["rpool:capacity"]
        assert state.alert_count == 2

    @pytest.mark.os_agnostic
    def test_third_alert_increments_count_to_three(self, tmp_path: Path) -> None:
        """When recording a third alert for the same issue,
        the alert count increases to 3."""
        manager = a_state_manager(tmp_path)
        issue = a_capacity_issue_for("rpool")

        manager.record_alert(issue)
        manager.record_alert(issue)
        manager.record_alert(issue)

        state = manager.states["rpool:capacity"]
        assert state.alert_count == 3


# ============================================================================
# Tests: Clearing Issues (Recovery Detection)
# ============================================================================


class TestClearingExistingIssues:
    """Clearing issues removes their state entries."""

    @pytest.mark.os_agnostic
    def test_clearing_removes_state_entry(self, tmp_path: Path) -> None:
        """When clearing an issue that has state,
        the state entry is removed."""
        manager = a_state_manager(tmp_path)
        issue = a_capacity_issue_for("rpool")
        manager.record_alert(issue)

        manager.clear_issue("rpool", "capacity")

        assert "rpool:capacity" not in manager.states

    @pytest.mark.os_agnostic
    def test_clearing_returns_true_when_found(self, tmp_path: Path) -> None:
        """When clearing an issue that exists,
        clear_issue returns True."""
        manager = a_state_manager(tmp_path)
        issue = a_capacity_issue_for("rpool")
        manager.record_alert(issue)

        result = manager.clear_issue("rpool", "capacity")

        assert result is True


class TestClearingNonexistentIssues:
    """Clearing issues that don't exist returns False gracefully."""

    @pytest.mark.os_agnostic
    def test_clearing_nonexistent_returns_false(self, tmp_path: Path) -> None:
        """When clearing an issue that doesn't exist,
        clear_issue returns False."""
        manager = a_state_manager(tmp_path)

        result = manager.clear_issue("nonexistent", "capacity")

        assert result is False


# ============================================================================
# Tests: State Persistence (Save/Load)
# ============================================================================


class TestSavingState:
    """Saving state writes JSON to filesystem."""

    @pytest.mark.os_agnostic
    def test_save_creates_json_file(self, tmp_path: Path) -> None:
        """When saving state,
        a JSON file is created at the configured path."""
        manager = a_state_manager(tmp_path)
        issue = a_capacity_issue_for("rpool")
        manager.record_alert(issue)

        manager.save_state()

        assert manager.state_file.exists()

    @pytest.mark.os_agnostic
    def test_saved_json_has_version_field(self, tmp_path: Path) -> None:
        """When saving state,
        the JSON includes a version field."""
        manager = a_state_manager(tmp_path)
        issue = a_capacity_issue_for("rpool")
        manager.record_alert(issue)

        manager.save_state()

        with manager.state_file.open("r") as f:
            data = json.load(f)

        assert data["version"] == 1

    @pytest.mark.os_agnostic
    def test_saved_json_includes_alert_states(self, tmp_path: Path) -> None:
        """When saving state,
        the JSON includes all recorded alert states."""
        manager = a_state_manager(tmp_path)
        issue = a_capacity_issue_for("rpool")
        manager.record_alert(issue)

        manager.save_state()

        with manager.state_file.open("r") as f:
            data = json.load(f)

        assert "alerts" in data
        assert "rpool:capacity" in data["alerts"]


class TestLoadingValidState:
    """Loading state restores entries from JSON."""

    @pytest.mark.os_agnostic
    def test_load_restores_state_from_file(self, tmp_path: Path) -> None:
        """When loading from a valid state file,
        all alert states are restored."""
        state_file = tmp_path / "alert_state.json"
        now = datetime.now(UTC)
        data = {
            "version": 1,
            "alerts": {
                "rpool:capacity": {
                    "pool_name": "rpool",
                    "issue_category": "capacity",
                    "first_seen": now.isoformat(),
                    "last_alerted": now.isoformat(),
                    "alert_count": 3,
                    "last_severity": "WARNING",
                }
            },
        }

        with state_file.open("w") as f:
            json.dump(data, f)

        manager = AlertStateManager(state_file, resend_interval_hours=24)

        assert "rpool:capacity" in manager.states
        state = manager.states["rpool:capacity"]
        assert state.pool_name == "rpool"
        assert state.alert_count == 3


class TestLoadingWithMissingFile:
    """Loading with missing state file starts empty gracefully."""

    @pytest.mark.os_agnostic
    def test_missing_file_starts_empty(self, tmp_path: Path) -> None:
        """When the state file doesn't exist,
        the manager starts with empty state."""
        state_file = tmp_path / "nonexistent.json"

        manager = AlertStateManager(state_file, resend_interval_hours=24)

        assert len(manager.states) == 0


class TestLoadingWithCorruptData:
    """Loading with corrupt data handles errors gracefully."""

    @pytest.mark.os_agnostic
    def test_corrupt_json_starts_empty(self, tmp_path: Path) -> None:
        """When the state file contains invalid JSON,
        the manager starts with empty state."""
        state_file = tmp_path / "alert_state.json"

        with state_file.open("w") as f:
            f.write("{ invalid json }")

        manager = AlertStateManager(state_file, resend_interval_hours=24)

        assert len(manager.states) == 0

    @pytest.mark.os_agnostic
    def test_wrong_version_starts_empty(self, tmp_path: Path) -> None:
        """When the state file has an unknown version,
        the manager starts with empty state."""
        state_file = tmp_path / "alert_state.json"
        data = {"version": 999, "alerts": {}}

        with state_file.open("w") as f:
            json.dump(data, f)

        manager = AlertStateManager(state_file, resend_interval_hours=24)

        assert len(manager.states) == 0

    @pytest.mark.os_agnostic
    def test_corrupt_entries_are_skipped_but_valid_loaded(self, tmp_path: Path) -> None:
        """When some alert entries are corrupt,
        valid entries are loaded and corrupt ones are skipped."""
        state_file = tmp_path / "alert_state.json"
        now = datetime.now(UTC)
        data = {
            "version": 1,
            "alerts": {
                "rpool:capacity": {
                    "pool_name": "rpool",
                    "issue_category": "capacity",
                    "first_seen": now.isoformat(),
                    "last_alerted": now.isoformat(),
                    "alert_count": 1,
                    "last_severity": "WARNING",
                },
                "bad:entry": {
                    # Missing required fields
                    "pool_name": "bad",
                },
            },
        }

        with state_file.open("w") as f:
            json.dump(data, f)

        manager = AlertStateManager(state_file, resend_interval_hours=24)

        assert "rpool:capacity" in manager.states
        assert "bad:entry" not in manager.states


# ============================================================================
# Tests: State Persistence Across Instances
# ============================================================================


class TestStatePersistenceAcrossRestarts:
    """State persists when manager instances are recreated."""

    @pytest.mark.os_agnostic
    def test_state_survives_manager_recreation(self, tmp_path: Path) -> None:
        """When a manager records state and a new manager is created,
        the new manager loads the previous state."""
        state_file = tmp_path / "alert_state.json"
        issue = a_capacity_issue_for("rpool")

        # Create first manager and record alert
        manager1 = AlertStateManager(state_file, resend_interval_hours=24)
        manager1.record_alert(issue)

        # Create second manager instance
        manager2 = AlertStateManager(state_file, resend_interval_hours=24)

        assert "rpool:capacity" in manager2.states
        assert manager2.states["rpool:capacity"].alert_count == 1


# ============================================================================
# Tests: Multiple Issues Tracking
# ============================================================================


class TestTrackingMultipleIssues:
    """Multiple issues are tracked independently."""

    @pytest.mark.os_agnostic
    def test_different_categories_on_same_pool_tracked_separately(self, tmp_path: Path) -> None:
        """When recording alerts for different categories on the same pool,
        each category is tracked independently."""
        manager = a_state_manager(tmp_path)
        capacity_issue = a_capacity_issue_for("rpool")
        error_issue = an_error_issue_for("rpool")

        manager.record_alert(capacity_issue)
        manager.record_alert(error_issue)

        assert "rpool:capacity" in manager.states
        assert "rpool:errors" in manager.states
        assert len(manager.states) == 2

    @pytest.mark.os_agnostic
    def test_same_category_on_different_pools_tracked_separately(self, tmp_path: Path) -> None:
        """When recording alerts for the same category on different pools,
        each pool is tracked independently."""
        manager = a_state_manager(tmp_path)
        rpool_issue = a_capacity_issue_for("rpool")
        data_issue = a_capacity_issue_for("data")

        manager.record_alert(rpool_issue)
        manager.record_alert(data_issue)

        assert "rpool:capacity" in manager.states
        assert "data:capacity" in manager.states
        assert len(manager.states) == 2

    @pytest.mark.os_agnostic
    def test_three_different_issues_all_tracked(self, tmp_path: Path) -> None:
        """When recording alerts for three different issues,
        all three are tracked independently."""
        manager = a_state_manager(tmp_path)

        manager.record_alert(a_capacity_issue_for("rpool"))
        manager.record_alert(an_error_issue_for("rpool"))
        manager.record_alert(a_health_issue_for("data"))

        assert len(manager.states) == 3
        assert "rpool:capacity" in manager.states
        assert "rpool:errors" in manager.states
        assert "data:health" in manager.states


# ============================================================================
# Tests: State Change Detection
# ============================================================================


class TestStateChangeDetection:
    """State changes trigger immediate alerts regardless of resend interval."""

    @pytest.mark.os_agnostic
    def test_severity_change_triggers_immediate_alert(self, tmp_path: Path) -> None:
        """When an issue's severity changes from WARNING to CRITICAL,
        should_alert returns True even if resend interval hasn't passed."""
        manager = a_state_manager(tmp_path, resend_hours=24)

        # Record initial WARNING alert
        warning_issue = PoolIssue(
            pool_name="rpool",
            severity=Severity.WARNING,
            category="health",
            message="Pool degraded",
            details={},
        )
        manager.record_alert(warning_issue)

        # Immediately check with CRITICAL severity (no time has passed)
        critical_issue = PoolIssue(
            pool_name="rpool",
            severity=Severity.CRITICAL,
            category="health",
            message="Pool faulted",
            details={},
        )

        result = manager.should_alert(critical_issue)

        assert result is True

    @pytest.mark.os_agnostic
    def test_severity_downgrade_triggers_immediate_alert(self, tmp_path: Path) -> None:
        """When an issue's severity improves from CRITICAL to WARNING,
        should_alert returns True even if resend interval hasn't passed."""
        manager = a_state_manager(tmp_path, resend_hours=24)

        # Record initial CRITICAL alert
        critical_issue = PoolIssue(
            pool_name="rpool",
            severity=Severity.CRITICAL,
            category="health",
            message="Pool faulted",
            details={},
        )
        manager.record_alert(critical_issue)

        # Immediately check with WARNING severity (state improved)
        warning_issue = PoolIssue(
            pool_name="rpool",
            severity=Severity.WARNING,
            category="health",
            message="Pool degraded",
            details={},
        )

        result = manager.should_alert(warning_issue)

        assert result is True

    @pytest.mark.os_agnostic
    def test_unchanged_severity_respects_resend_interval(self, tmp_path: Path) -> None:
        """When an issue's severity remains unchanged,
        should_alert respects the resend interval."""
        manager = a_state_manager(tmp_path, resend_hours=24)

        # Record initial WARNING alert
        warning_issue = PoolIssue(
            pool_name="rpool",
            severity=Severity.WARNING,
            category="capacity",
            message="Pool at 85%",
            details={},
        )
        manager.record_alert(warning_issue)

        # Immediately check with same severity
        same_issue = PoolIssue(
            pool_name="rpool",
            severity=Severity.WARNING,
            category="capacity",
            message="Pool at 86%",  # Message changed but severity same
            details={},
        )

        result = manager.should_alert(same_issue)

        assert result is False

    @pytest.mark.os_agnostic
    def test_record_alert_stores_severity(self, tmp_path: Path) -> None:
        """When recording an alert,
        the severity is stored in the state."""
        manager = a_state_manager(tmp_path)

        issue = PoolIssue(
            pool_name="rpool",
            severity=Severity.CRITICAL,
            category="health",
            message="Pool faulted",
            details={},
        )

        manager.record_alert(issue)
        state = manager.states["rpool:health"]

        assert state.last_severity == "CRITICAL"

    @pytest.mark.os_agnostic
    def test_state_change_after_24_hours_still_alerts(self, tmp_path: Path) -> None:
        """When severity changes after the resend interval,
        should_alert returns True (state change takes precedence)."""
        manager = a_state_manager(tmp_path, resend_hours=24)

        # Simulate alert 25 hours ago with WARNING
        manager.states["rpool:health"] = an_alert_state("rpool", "health", hours_ago=25, last_severity="WARNING")

        # Check with CRITICAL severity
        critical_issue = PoolIssue(
            pool_name="rpool",
            severity=Severity.CRITICAL,
            category="health",
            message="Pool faulted",
            details={},
        )

        result = manager.should_alert(critical_issue)

        assert result is True


# ============================================================================
# Tests: Device-Specific Alert Tracking
# ============================================================================


def a_device_issue_for(pool_name: str, device_name: str, severity: Severity = Severity.CRITICAL) -> PoolIssue:
    """Create a device issue for a specific device in a pool."""
    return PoolIssue(
        pool_name=pool_name,
        severity=severity,
        category="device",
        message=f"Device {device_name} is FAULTED",
        details={"device_name": device_name, "device_state": "FAULTED"},
    )


class TestDeviceSpecificAlertTracking:
    """Device issues are tracked per-device, not just per-pool."""

    @pytest.mark.os_agnostic
    def test_different_devices_in_same_pool_tracked_separately(self, tmp_path: Path) -> None:
        """When recording alerts for different devices in the same pool,
        each device is tracked independently."""
        manager = a_state_manager(tmp_path)
        device1_issue = a_device_issue_for("rpool", "sda1")
        device2_issue = a_device_issue_for("rpool", "sdb1")

        manager.record_alert(device1_issue)
        manager.record_alert(device2_issue)

        assert "rpool:device:sda1" in manager.states
        assert "rpool:device:sdb1" in manager.states
        assert len(manager.states) == 2

    @pytest.mark.os_agnostic
    def test_second_device_alerts_even_if_first_device_suppressed(self, tmp_path: Path) -> None:
        """When one device alert is suppressed (within interval),
        a different device in the same pool should still alert."""
        manager = a_state_manager(tmp_path, resend_hours=24)
        device1_issue = a_device_issue_for("rpool", "sda1")
        device2_issue = a_device_issue_for("rpool", "sdb1")

        # Alert for first device
        manager.record_alert(device1_issue)

        # First device should be suppressed
        assert manager.should_alert(device1_issue) is False

        # Second device should still alert (new device)
        assert manager.should_alert(device2_issue) is True

    @pytest.mark.os_agnostic
    def test_device_alert_resends_after_interval(self, tmp_path: Path) -> None:
        """When a device alert's resend interval passes,
        should_alert returns True for that specific device."""
        manager = a_state_manager(tmp_path, resend_hours=2)

        # Simulate device alert 3 hours ago
        manager.states["rpool:device:sda1"] = an_alert_state("rpool", "device", hours_ago=3, last_severity="CRITICAL")

        device_issue = a_device_issue_for("rpool", "sda1")
        result = manager.should_alert(device_issue)

        assert result is True

    @pytest.mark.os_agnostic
    def test_same_device_different_pools_tracked_separately(self, tmp_path: Path) -> None:
        """When the same device name exists in different pools,
        each is tracked independently."""
        manager = a_state_manager(tmp_path)
        rpool_device = a_device_issue_for("rpool", "sda1")
        data_device = a_device_issue_for("data", "sda1")

        manager.record_alert(rpool_device)
        manager.record_alert(data_device)

        assert "rpool:device:sda1" in manager.states
        assert "data:device:sda1" in manager.states
        assert len(manager.states) == 2


class TestClearingDeviceIssues:
    """Clearing device issues can clear all devices or specific ones."""

    @pytest.mark.os_agnostic
    def test_clear_all_device_issues_for_pool(self, tmp_path: Path) -> None:
        """When clearing device category without device_name,
        all device issues for that pool are cleared."""
        manager = a_state_manager(tmp_path)
        manager.record_alert(a_device_issue_for("rpool", "sda1"))
        manager.record_alert(a_device_issue_for("rpool", "sdb1"))
        manager.record_alert(a_device_issue_for("rpool", "sdc1"))

        result = manager.clear_issue("rpool", "device")

        assert result is True
        assert "rpool:device:sda1" not in manager.states
        assert "rpool:device:sdb1" not in manager.states
        assert "rpool:device:sdc1" not in manager.states

    @pytest.mark.os_agnostic
    def test_clear_specific_device_issue(self, tmp_path: Path) -> None:
        """When clearing with device_name specified,
        only that specific device issue is cleared."""
        manager = a_state_manager(tmp_path)
        manager.record_alert(a_device_issue_for("rpool", "sda1"))
        manager.record_alert(a_device_issue_for("rpool", "sdb1"))

        result = manager.clear_issue("rpool", "device", device_name="sda1")

        assert result is True
        assert "rpool:device:sda1" not in manager.states
        assert "rpool:device:sdb1" in manager.states

    @pytest.mark.os_agnostic
    def test_clear_device_issues_does_not_affect_other_pools(self, tmp_path: Path) -> None:
        """When clearing device issues for one pool,
        device issues for other pools are preserved."""
        manager = a_state_manager(tmp_path)
        manager.record_alert(a_device_issue_for("rpool", "sda1"))
        manager.record_alert(a_device_issue_for("data", "sdb1"))

        manager.clear_issue("rpool", "device")

        assert "rpool:device:sda1" not in manager.states
        assert "data:device:sdb1" in manager.states

    @pytest.mark.os_agnostic
    def test_clear_device_issues_does_not_affect_other_categories(self, tmp_path: Path) -> None:
        """When clearing device issues,
        other category issues are preserved."""
        manager = a_state_manager(tmp_path)
        manager.record_alert(a_device_issue_for("rpool", "sda1"))
        manager.record_alert(a_capacity_issue_for("rpool"))

        manager.clear_issue("rpool", "device")

        assert "rpool:device:sda1" not in manager.states
        assert "rpool:capacity" in manager.states

    @pytest.mark.os_agnostic
    def test_clear_nonexistent_device_returns_false(self, tmp_path: Path) -> None:
        """When clearing device issues that don't exist,
        clear_issue returns False."""
        manager = a_state_manager(tmp_path)

        result = manager.clear_issue("rpool", "device")

        assert result is False


class TestDeviceIssuePersistence:
    """Device-specific state persists correctly across saves/loads."""

    @pytest.mark.os_agnostic
    def test_device_issues_survive_save_load_cycle(self, tmp_path: Path) -> None:
        """When saving and loading state with device issues,
        the device-specific keys are preserved."""
        state_file = tmp_path / "alert_state.json"

        # Create manager and record device issues
        manager1 = AlertStateManager(state_file, resend_interval_hours=24)
        manager1.record_alert(a_device_issue_for("rpool", "sda1"))
        manager1.record_alert(a_device_issue_for("rpool", "sdb1"))

        # Create new manager instance (loads from file)
        manager2 = AlertStateManager(state_file, resend_interval_hours=24)

        assert "rpool:device:sda1" in manager2.states
        assert "rpool:device:sdb1" in manager2.states
        assert len(manager2.states) == 2
