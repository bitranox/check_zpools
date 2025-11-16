"""Tests for alert state management module.

Tests cover:
- Alert state creation and tracking
- Deduplication logic (should_alert)
- State persistence (load/save)
- Recovery detection (clear_issue)
- Error handling (corrupt files, missing data)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from check_zpools.alert_state import AlertState, AlertStateManager
from check_zpools.models import PoolIssue, Severity


@pytest.fixture
def temp_state_file(tmp_path: Path) -> Path:
    """Create a temporary state file path."""
    return tmp_path / "alert_state.json"


@pytest.fixture
def state_manager(temp_state_file: Path) -> AlertStateManager:
    """Create a state manager with temporary file."""
    return AlertStateManager(temp_state_file, resend_interval_hours=24)


@pytest.fixture
def sample_issue() -> PoolIssue:
    """Create a sample pool issue for testing."""
    return PoolIssue(
        pool_name="rpool",
        severity=Severity.WARNING,
        category="capacity",
        message="Pool capacity at 85%",
        details={"capacity_percent": 85},
    )


class TestAlertState:
    """Test AlertState dataclass."""

    def test_alert_state_creation(self) -> None:
        """AlertState should be created with all required fields."""
        now = datetime.now(UTC)
        state = AlertState(
            pool_name="rpool",
            issue_category="capacity",
            first_seen=now,
            last_alerted=now,
            alert_count=1,
        )

        assert state.pool_name == "rpool"
        assert state.issue_category == "capacity"
        assert state.first_seen == now
        assert state.last_alerted == now
        assert state.alert_count == 1


class TestAlertStateManager:
    """Test AlertStateManager functionality."""

    def test_manager_creates_state_directory(self, temp_state_file: Path) -> None:
        """Manager should create state directory if it doesn't exist."""
        AlertStateManager(temp_state_file, resend_interval_hours=24)
        assert temp_state_file.parent.exists()

    def test_manager_starts_with_empty_state(self, state_manager: AlertStateManager) -> None:
        """New manager should have no tracked states."""
        assert len(state_manager.states) == 0

    def test_should_alert_returns_true_for_new_issue(self, state_manager: AlertStateManager, sample_issue: PoolIssue) -> None:
        """New issues should always trigger alerts."""
        result = state_manager.should_alert(sample_issue)
        assert result is True

    def test_should_alert_returns_false_within_interval(self, state_manager: AlertStateManager, sample_issue: PoolIssue) -> None:
        """Duplicate alerts within resend interval should be suppressed."""
        # Record initial alert
        state_manager.record_alert(sample_issue)

        # Immediate recheck should suppress
        result = state_manager.should_alert(sample_issue)
        assert result is False

    def test_should_alert_returns_true_after_interval(self, temp_state_file: Path, sample_issue: PoolIssue) -> None:
        """Alerts should resend after configured interval."""
        manager = AlertStateManager(temp_state_file, resend_interval_hours=1)

        # Record alert with timestamp 2 hours ago
        past_time = datetime.now(UTC) - timedelta(hours=2)
        manager.states["rpool:capacity"] = AlertState(
            pool_name="rpool",
            issue_category="capacity",
            first_seen=past_time,
            last_alerted=past_time,
            alert_count=1,
        )

        # Should allow resend
        result = manager.should_alert(sample_issue)
        assert result is True

    def test_record_alert_creates_new_state(self, state_manager: AlertStateManager, sample_issue: PoolIssue) -> None:
        """Recording alert for new issue should create state."""
        state_manager.record_alert(sample_issue)

        assert "rpool:capacity" in state_manager.states
        state = state_manager.states["rpool:capacity"]
        assert state.pool_name == "rpool"
        assert state.issue_category == "capacity"
        assert state.alert_count == 1

    def test_record_alert_increments_count(self, state_manager: AlertStateManager, sample_issue: PoolIssue) -> None:
        """Recording alert for existing issue should increment count."""
        state_manager.record_alert(sample_issue)
        state_manager.record_alert(sample_issue)

        state = state_manager.states["rpool:capacity"]
        assert state.alert_count == 2

    def test_clear_issue_removes_state(self, state_manager: AlertStateManager, sample_issue: PoolIssue) -> None:
        """Clearing an issue should remove its state."""
        state_manager.record_alert(sample_issue)
        assert "rpool:capacity" in state_manager.states

        result = state_manager.clear_issue("rpool", "capacity")
        assert result is True
        assert "rpool:capacity" not in state_manager.states

    def test_clear_issue_returns_false_if_not_exists(self, state_manager: AlertStateManager) -> None:
        """Clearing non-existent issue should return False."""
        result = state_manager.clear_issue("nonexistent", "capacity")
        assert result is False

    def test_save_state_creates_json_file(self, state_manager: AlertStateManager, sample_issue: PoolIssue) -> None:
        """Saving state should create JSON file."""
        state_manager.record_alert(sample_issue)
        state_manager.save_state()

        assert state_manager.state_file.exists()

        # Verify JSON structure
        with state_manager.state_file.open("r") as f:
            data = json.load(f)

        assert data["version"] == 1
        assert "alerts" in data
        assert "rpool:capacity" in data["alerts"]

    def test_load_state_restores_from_file(self, temp_state_file: Path) -> None:
        """Loading state should restore from JSON file."""
        # Create state file manually
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
                }
            },
        }

        with temp_state_file.open("w") as f:
            json.dump(data, f)

        # Load into new manager
        manager = AlertStateManager(temp_state_file, resend_interval_hours=24)

        assert "rpool:capacity" in manager.states
        state = manager.states["rpool:capacity"]
        assert state.pool_name == "rpool"
        assert state.alert_count == 3

    def test_load_state_handles_missing_file(self, temp_state_file: Path) -> None:
        """Loading state with missing file should start empty."""
        manager = AlertStateManager(temp_state_file, resend_interval_hours=24)
        assert len(manager.states) == 0

    def test_load_state_handles_corrupt_json(self, temp_state_file: Path) -> None:
        """Loading state with corrupt JSON should start empty."""
        # Write invalid JSON
        temp_state_file.parent.mkdir(parents=True, exist_ok=True)
        with temp_state_file.open("w") as f:
            f.write("{ invalid json }")

        manager = AlertStateManager(temp_state_file, resend_interval_hours=24)
        assert len(manager.states) == 0

    def test_load_state_handles_wrong_version(self, temp_state_file: Path) -> None:
        """Loading state with unknown version should start empty."""
        data = {"version": 999, "alerts": {}}

        with temp_state_file.open("w") as f:
            json.dump(data, f)

        manager = AlertStateManager(temp_state_file, resend_interval_hours=24)
        assert len(manager.states) == 0

    def test_load_state_skips_corrupt_entries(self, temp_state_file: Path) -> None:
        """Loading state should skip corrupt entries but load valid ones."""
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
                },
                "bad:entry": {
                    # Missing required fields
                    "pool_name": "bad",
                },
            },
        }

        with temp_state_file.open("w") as f:
            json.dump(data, f)

        manager = AlertStateManager(temp_state_file, resend_interval_hours=24)

        # Should load valid entry, skip corrupt one
        assert "rpool:capacity" in manager.states
        assert "bad:entry" not in manager.states

    def test_state_persists_across_instances(self, temp_state_file: Path, sample_issue: PoolIssue) -> None:
        """State should persist when manager is recreated."""
        # Create manager and record alert
        manager1 = AlertStateManager(temp_state_file, resend_interval_hours=24)
        manager1.record_alert(sample_issue)

        # Create new manager instance
        manager2 = AlertStateManager(temp_state_file, resend_interval_hours=24)

        # Should have loaded state
        assert "rpool:capacity" in manager2.states
        assert manager2.states["rpool:capacity"].alert_count == 1

    def test_multiple_issues_tracked_separately(self, state_manager: AlertStateManager) -> None:
        """Multiple issues should be tracked independently."""
        issue1 = PoolIssue(
            pool_name="rpool",
            severity=Severity.WARNING,
            category="capacity",
            message="High capacity",
            details={},
        )
        issue2 = PoolIssue(
            pool_name="rpool",
            severity=Severity.WARNING,
            category="errors",
            message="Read errors detected",
            details={},
        )

        state_manager.record_alert(issue1)
        state_manager.record_alert(issue2)

        assert "rpool:capacity" in state_manager.states
        assert "rpool:errors" in state_manager.states
        assert len(state_manager.states) == 2

    def test_different_pools_same_category(self, state_manager: AlertStateManager) -> None:
        """Same category on different pools should be tracked separately."""
        issue1 = PoolIssue(
            pool_name="rpool",
            severity=Severity.WARNING,
            category="capacity",
            message="High capacity",
            details={},
        )
        issue2 = PoolIssue(
            pool_name="data",
            severity=Severity.WARNING,
            category="capacity",
            message="High capacity",
            details={},
        )

        state_manager.record_alert(issue1)
        state_manager.record_alert(issue2)

        assert "rpool:capacity" in state_manager.states
        assert "data:capacity" in state_manager.states
