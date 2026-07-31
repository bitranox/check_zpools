"""Alert state management for deduplication and suppression.

Purpose
-------
Track which alerts have been sent and when, to prevent alert fatigue through
intelligent deduplication and resend throttling. State persists across daemon
restarts in a JSON file.

Contents
--------
* :class:`AlertState` - dataclass representing the state of a single alert
* :class:`AlertStateManager` - manages alert suppression and persistence

Architecture
------------
The manager maintains a dictionary of alert states keyed by pool name and
issue category. It determines whether an alert should be sent based on:
1. Whether this is a new issue (never seen before)
2. Whether enough time has passed since the last alert (resend interval)
3. Whether the issue has been resolved

State is persisted to a JSON file in a platform-specific cache directory.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, cast

from pydantic import BaseModel, ConfigDict, field_serializer

from .models import IssueCategory, PoolIssue, Severity

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


class AlertState(BaseModel):
    """One tracked pool issue, both in memory and on disk.

    Why
        This used to be a Pydantic model for the file and an identical
        dataclass for memory, converted field by field in each direction. One
        model removes that round trip and makes the persisted shape and the
        in-memory shape the same thing by construction.

    Attributes
    ----------
    pool_name:
        Name of the ZFS pool this alert concerns.
    issue_category:
        Category of the issue.
    first_seen:
        When this issue was first detected.
    last_alerted:
        When an alert was last sent, or None if never.
    alert_count:
        How many alerts have been sent for this issue.
    last_severity:
        Severity of the last alert, used to detect a change such as
        DEGRADED to ONLINE. None if never alerted.

    Examples
    --------
    >>> from datetime import datetime, timezone
    >>> state = AlertState(
    ...     pool_name="rpool",
    ...     issue_category=IssueCategory.CAPACITY,
    ...     first_seen=datetime.now(timezone.utc),
    ...     last_alerted=None,
    ...     alert_count=0,
    ...     last_severity=None,
    ... )
    >>> state.issue_category
    <IssueCategory.CAPACITY: 'capacity'>
    """

    model_config = ConfigDict(validate_assignment=True)

    pool_name: str
    issue_category: IssueCategory
    first_seen: datetime
    last_alerted: datetime | None = None
    alert_count: int = 0
    last_severity: Severity | None = None

    @field_serializer("first_seen", "last_alerted")
    @classmethod
    def serialize_datetime(cls, value: datetime | None) -> str | None:
        """Serialize datetime to ISO format string."""
        return value.isoformat() if value else None


class AlertStateFile(BaseModel):
    """The persisted alert-state document.

    Why
        The file layout (a version plus a map of entries) was previously
        assembled and unpacked as raw dicts at both ends. Declaring it means
        the reader and the writer cannot disagree about it.
    """

    model_config = ConfigDict(extra="ignore")

    version: int = 1
    alerts: dict[str, AlertState] = {}


def _parse_alert_state_entry(key: str, state_dict: Any) -> AlertState | None:
    """Parse one persisted entry, tolerating a corrupt record.

    Why
        One malformed entry must not cost the whole file: losing all state
        means re-alerting every issue that is currently open.

    Returns
    -------
    AlertState | None:
        The parsed state, or None if the entry is corrupt (already logged).
    """
    try:
        return AlertState.model_validate(state_dict)
    except Exception as exc:  # Catches ValidationError + KeyError + ValueError
        logger.warning("Skipping corrupt state entry", extra={"key": key, "error": str(exc)})
        return None


class AlertStateManager:
    """Manage alert suppression and deduplication across daemon runs.

    Why
    ---
    Without state management, the daemon would send the same alert every
    check cycle, causing alert fatigue. This manager tracks which issues
    have been alerted and throttles resends based on a configured interval.

    What
    ----
    Maintains a dict of AlertState objects keyed by "{pool_name}:{category}".
    State persists to JSON file so alerts aren't duplicated after restarts.

    Parameters
    ----------
    state_file:
        Path to JSON file for persisting alert state.
    resend_interval_hours:
        Minimum hours between resending alerts for the same issue.
    """

    def __init__(self, state_file: Path, resend_interval_hours: int):
        self.state_file = state_file
        self.resend_interval_hours = resend_interval_hours
        self.states: dict[str, AlertState] = {}
        self._ensure_state_dir()
        self.load_state()

    def _ensure_state_dir(self) -> None:
        """Create state file directory if it doesn't exist with restricted permissions."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True, mode=0o750)

        # Restrict state file to owner-only read/write if it exists
        if self.state_file.exists():
            self.state_file.chmod(0o600)

    def _make_key(self, pool_name: str, category: IssueCategory | str, device_name: str | None = None) -> str:
        """Generate unique key for a pool+category+device combination.

        Why the explicit .value
            The key is written into the state file, so its format is a
            persisted contract. An IssueCategory is a str-Enum, and
            interpolating one directly yields "IssueCategory.CAPACITY" rather
            than "capacity" - which would orphan every existing entry on the
            first run after an upgrade.

        Parameters
        ----------
        pool_name:
            Name of the ZFS pool.
        category:
            Issue category, as the enum or its value.
        device_name:
            For device issues, the specific device name. None for pool-level issues.

        Returns
        -------
        str:
            Unique key for this alert state.

        Examples
        --------
        >>> AlertStateManager._make_key(None, "rpool", IssueCategory.CAPACITY)
        'rpool:capacity'
        >>> AlertStateManager._make_key(None, "rpool", IssueCategory.DEVICE, "sda")
        'rpool:device:sda'
        """
        category_key = category.value if isinstance(category, IssueCategory) else category
        if device_name:
            return f"{pool_name}:{category_key}:{device_name}"
        return f"{pool_name}:{category_key}"

    def _extract_device_name(self, issue: PoolIssue) -> str | None:
        """Extract device name from issue details if this is a device issue.

        Parameters
        ----------
        issue:
            The pool issue to extract device name from.

        Returns
        -------
        str | None:
            Device name if this is a device issue with device_name in details, else None.
        """
        if issue.category == IssueCategory.DEVICE and issue.details:
            # issue.details is always IssueDetails (typed field in PoolIssue)
            return issue.details.device_name
        return None

    def should_alert(self, issue: PoolIssue) -> bool:
        """Determine whether to send an alert for this issue.

        Why
        ---
        Prevents alert fatigue by suppressing duplicate alerts and
        respecting the resend interval. However, state changes always
        trigger immediate alerts regardless of the resend interval.

        What
        ---
        Returns True if:
        1. This is a new issue (never seen before), OR
        2. The severity has changed from the last alert (state change), OR
        3. Enough time has passed since the last alert (resend interval)

        Parameters
        ----------
        issue:
            The pool issue to evaluate.

        Returns
        -------
        bool
            True if alert should be sent, False to suppress.
        """
        device_name = self._extract_device_name(issue)
        category_value = issue.category
        key = self._make_key(issue.pool_name, category_value, device_name)
        state = self.states.get(key)

        if state is None:
            # New issue, should alert
            logger.debug(
                "New issue detected",
                extra={"pool": issue.pool_name, "category": category_value},
            )
            return True

        if state.last_alerted is None:
            # Issue exists but never alerted (shouldn't happen, but safe)
            logger.warning(
                "Issue has state but no alert timestamp",
                extra={"pool": issue.pool_name, "category": category_value},
            )
            return True

        # Check if severity/state has changed - always alert on state changes
        current_severity = issue.severity
        if state.last_severity is not None and current_severity != state.last_severity:
            logger.info(
                "State change detected - sending immediate alert",
                extra={
                    "pool": issue.pool_name,
                    "category": category_value,
                    "old_severity": state.last_severity,
                    "new_severity": current_severity,
                },
            )
            return True

        # Check if resend interval has passed for unchanged state
        now = datetime.now(timezone.utc)
        elapsed = now - state.last_alerted
        should_resend = elapsed >= timedelta(hours=self.resend_interval_hours)

        if should_resend:
            logger.info(
                "Resending alert after interval",
                extra={
                    "pool": issue.pool_name,
                    "category": category_value,
                    "hours_since_last": elapsed.total_seconds() / 3600,
                },
            )
        else:
            logger.debug(
                "Suppressing duplicate alert",
                extra={
                    "pool": issue.pool_name,
                    "category": category_value,
                    "hours_since_last": elapsed.total_seconds() / 3600,
                },
            )

        return should_resend

    def record_alert(self, issue: PoolIssue) -> None:
        """Record that an alert was sent for this issue.

        Why
        ---
        Updates state so future checks can determine whether to suppress
        duplicate alerts or detect state changes.

        What
        ---
        Creates or updates the AlertState for this issue, storing the
        current severity level for state change detection, and persists
        to disk.

        Parameters
        ----------
        issue:
            The issue for which an alert was sent.
        """
        device_name = self._extract_device_name(issue)
        category_value = issue.category
        key = self._make_key(issue.pool_name, category_value, device_name)
        now = datetime.now(timezone.utc)
        current_severity = issue.severity

        if key in self.states:
            # Existing issue - update last alerted time, severity, and increment count
            state = self.states[key]
            state.last_alerted = now
            state.last_severity = current_severity
            state.alert_count += 1
            logger.debug(
                "Updated alert state",
                extra={
                    "pool": issue.pool_name,
                    "category": category_value,
                    "severity": current_severity,
                    "count": state.alert_count,
                },
            )
        else:
            # New issue - create state
            self.states[key] = AlertState(
                pool_name=issue.pool_name,
                issue_category=category_value,
                first_seen=now,
                last_alerted=now,
                alert_count=1,
                last_severity=current_severity,
            )
            logger.debug(
                "Created alert state",
                extra={
                    "pool": issue.pool_name,
                    "category": category_value,
                    "severity": current_severity,
                },
            )

        self.save_state()

    def clear_issue(self, pool_name: str, category: str | IssueCategory, device_name: str | None = None) -> bool:
        """Clear state when an issue is resolved.

        Why
        ---
        When an issue is resolved, we want to forget about it so that if
        it recurs in the future, we'll send a fresh alert immediately.

        What
        ---
        For device issues without a specific device_name, clears ALL device
        issues for the pool. For other issues or specific devices, clears
        only the matching state entry.

        Parameters
        ----------
        pool_name:
            Name of the pool.
        category:
            Issue category to clear.
        device_name:
            For device issues, the specific device. If None and category is
            "device", clears all device issues for the pool.

        Returns
        -------
        bool
            True if any state was cleared, False if no state existed.
        """
        # Callers pass either the enum or its value; normalise once, at the
        # edge, then compare enums rather than strings.
        issue_category = category if isinstance(category, IssueCategory) else IssueCategory(category)
        if issue_category is IssueCategory.DEVICE and device_name is None:
            return self._clear_all_device_issues(pool_name)

        key = self._make_key(pool_name, issue_category, device_name)
        if key in self.states:
            del self.states[key]
            self.save_state()
            logger.info(
                "Cleared resolved issue",
                extra={"pool": pool_name, "category": issue_category.value, "device": device_name},
            )
            return True
        return False

    def _clear_all_device_issues(self, pool_name: str) -> bool:
        """Clear all device issues for a specific pool.

        Parameters
        ----------
        pool_name:
            Name of the pool.

        Returns
        -------
        bool:
            True if any device issues were cleared.
        """
        prefix = f"{pool_name}:device:"
        keys_to_remove = [key for key in self.states if key.startswith(prefix)]

        if not keys_to_remove:
            return False

        for key in keys_to_remove:
            del self.states[key]
            logger.info(
                "Cleared resolved device issue",
                extra={"pool": pool_name, "key": key},
            )

        self.save_state()
        return True

    def load_state(self) -> None:
        """Load alert state from JSON file.

        Why
        ---
        State must persist across daemon restarts to prevent duplicate
        alerts when the service is restarted.

        What
        ---
        Reads and parses the JSON state file. Handles missing or corrupt
        files gracefully by starting with empty state.
        """
        if not self.state_file.exists():
            logger.info("No state file found, starting with empty state")
            return

        try:
            with self.state_file.open("r") as f:
                raw: object = json.load(f)

            document = cast("dict[str, Any]", raw) if isinstance(raw, dict) else {}
            version = document.get("version", 1)
            if version != 1:
                logger.warning(
                    "Unknown state file version, starting fresh",
                    extra={"version": version},
                )
                return

            # Entry by entry, so one corrupt record cannot cost us the rest of
            # the file - losing all state means re-alerting every open issue.
            entries: dict[str, Any] = document.get("alerts", {})
            for key, entry in entries.items():
                state = _parse_alert_state_entry(key, entry)
                if state is not None:
                    self.states[key] = state

            logger.info(
                "Loaded alert state",
                extra={"count": len(self.states), "file": str(self.state_file)},
            )

        except json.JSONDecodeError as exc:
            logger.error(
                "Corrupt state file, starting fresh",
                extra={"file": str(self.state_file), "error": str(exc)},
            )
        except OSError as exc:
            logger.error(
                "Failed to read state file",
                extra={"file": str(self.state_file), "error": str(exc)},
            )

    def save_state(self) -> None:
        """Persist alert state to JSON file.

        Why
        ---
        State must survive daemon restarts to prevent duplicate alerts.

        What
        ---
        Serializes current state to JSON with ISO-formatted timestamps using
        Pydantic for type-safe serialization. Handles write errors gracefully.
        """
        try:
            document = AlertStateFile(version=1, alerts=self.states)

            # Write atomically via temp file
            temp_file = self.state_file.with_suffix(".tmp")
            temp_file.write_text(document.model_dump_json(indent=2))

            # Atomic rename
            temp_file.replace(self.state_file)

            # Set secure permissions on new file
            self.state_file.chmod(0o600)

            logger.debug(
                "Saved alert state",
                extra={"count": len(self.states), "file": str(self.state_file)},
            )

        except OSError as exc:
            logger.error(
                "Failed to save state file",
                extra={"file": str(self.state_file), "error": str(exc)},
            )
