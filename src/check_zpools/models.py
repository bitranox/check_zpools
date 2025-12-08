"""Data models for ZFS pool monitoring.

Purpose
-------
Define immutable data structures representing ZFS pool state, issues, and check
results. These models serve as the foundation for all monitoring logic, providing
type-safe containers for ZFS data.

Contents
--------
* :class:`PoolHealth` – Enumeration of possible ZFS pool health states
* :class:`Severity` – Enumeration of issue severity levels
* :class:`PoolStatus` – Complete status snapshot of a single ZFS pool
* :class:`PoolIssue` – Detected issue with a pool
* :class:`CheckResult` – Aggregated result of checking all pools

System Role
-----------
Serves as the domain model layer, keeping data structures pure and free of
business logic. All ZFS data flows through these models, ensuring consistent
type safety across parsers, monitors, and alerting systems.

Architecture Notes
------------------
- All models are immutable (frozen dataclasses)
- Use enums for fixed vocabularies (health states, severities)
- Comprehensive type hints for strict type checking
- No business logic in models (Single Responsibility Principle)
- Models are serializable for logging and state persistence
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime  # noqa: F401 - UTC used in doctests  # pyright: ignore[reportUnusedImport]
from enum import Enum
from functools import lru_cache

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)


# ============================================================================
# Configuration Models (Pydantic for external boundary parsing)
# ============================================================================


class DaemonConfig(BaseModel):
    """Typed configuration for daemon mode.

    Why
        Replaces dict[str, Any] with a typed Pydantic model for daemon config.
        Provides validation at the boundary when config is loaded.

    Attributes
    ----------
    check_interval_seconds:
        How often to check pools (default: 300 seconds = 5 minutes).
    pools_to_monitor:
        List of pool names to monitor. Empty means all pools.
    send_ok_emails:
        Whether to send emails when all pools are OK (default: False).
    send_recovery_emails:
        Whether to send emails when issues are resolved (default: True).
    """

    check_interval_seconds: int = 300
    pools_to_monitor: list[str] = []
    send_ok_emails: bool = False
    send_recovery_emails: bool = True

    model_config = ConfigDict(extra="ignore")


class AlertConfig(BaseModel):
    """Typed configuration for alerting.

    Why
        Replaces dict[str, Any] with a typed Pydantic model for alert config.
        Provides validation at the boundary when config is loaded.

    Attributes
    ----------
    subject_prefix:
        Prefix for email subject lines (default: "[ZFS Alert]").
    alert_recipients:
        List of email addresses to receive alerts.
    send_ok_emails:
        Whether to send emails when all pools are OK (default: False).
    send_recovery_emails:
        Whether to send emails when issues are resolved (default: True).
    alert_on_severities:
        Which severity levels trigger alerts (default: CRITICAL, WARNING).
    """

    subject_prefix: str = "[ZFS Alert]"
    alert_recipients: list[str] = []
    send_ok_emails: bool = False
    send_recovery_emails: bool = True
    alert_on_severities: list[str] = ["CRITICAL", "WARNING"]

    model_config = ConfigDict(extra="ignore")


class CapacityInfo(BaseModel):
    """Capacity metrics extracted from ZFS vdev.

    Why
        Replaces dict[str, Any] returned by _extract_capacity_from_vdev.
        Provides type-safe container for capacity values.
    """

    capacity_percent: float
    size_bytes: int
    allocated_bytes: int
    free_bytes: int


class ScrubInfo(BaseModel):
    """Scrub status information extracted from ZFS pool.

    Why
        Replaces dict[str, Any] returned by _extract_scrub_info.
        Provides type-safe container for scrub values.
    """

    last_scrub: datetime | None
    scrub_errors: int
    scrub_in_progress: bool


# ============================================================================
# Domain Models (Enums and Dataclasses)
# ============================================================================


class PoolHealth(str, Enum):
    """ZFS pool health states as reported by zpool status/list.

    Why
        ZFS pools have well-defined health states that determine monitoring
        severity. Enumerating these states provides type safety and prevents
        typos in health comparisons.

    Values
        ONLINE: Pool is fully operational, all devices working
        DEGRADED: Pool is operational but one or more devices have failed
        FAULTED: Pool cannot provide data due to device failures
        OFFLINE: Pool has been manually taken offline
        UNAVAIL: Pool is unavailable (insufficient devices)
        REMOVED: Pool has been removed from the system

    Examples
    --------
    >>> PoolHealth.ONLINE
    <PoolHealth.ONLINE: 'ONLINE'>
    >>> PoolHealth('DEGRADED')
    <PoolHealth.DEGRADED: 'DEGRADED'>
    >>> PoolHealth.FAULTED.value
    'FAULTED'
    """

    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    FAULTED = "FAULTED"
    OFFLINE = "OFFLINE"
    UNAVAIL = "UNAVAIL"
    REMOVED = "REMOVED"

    @lru_cache(maxsize=6)
    def is_healthy(self) -> bool:
        """Return True if this health state is considered healthy.

        Why
            Simplifies conditional logic when checking if pool is OK.

        Why Cached
            Called frequently during monitoring. Only 6 possible enum values,
            perfect for caching. Eliminates repeated enum comparisons.

        Returns
            True for ONLINE, False for all other states.

        Examples
        --------
        >>> PoolHealth.ONLINE.is_healthy()
        True
        >>> PoolHealth.DEGRADED.is_healthy()
        False
        """
        return self == PoolHealth.ONLINE

    @lru_cache(maxsize=6)
    def is_critical(self) -> bool:
        """Return True if this health state is critical.

        Why
            Determines if immediate action is required.

        Why Cached
            Called frequently during monitoring. Only 6 possible enum values,
            perfect for caching. Eliminates repeated tuple membership checks.

        Returns
            True for FAULTED, UNAVAIL, or REMOVED states.

        Examples
        --------
        >>> PoolHealth.FAULTED.is_critical()
        True
        >>> PoolHealth.DEGRADED.is_critical()
        False
        """
        return self in (PoolHealth.FAULTED, PoolHealth.UNAVAIL, PoolHealth.REMOVED)


class Severity(str, Enum):
    """Issue severity levels for monitoring alerts.

    Why
        Different issues require different response urgency. Severity levels
        enable filtering, routing, and prioritization of alerts.

    Values
        OK: No issues detected
        INFO: Informational message, no action required
        WARNING: Issue detected, should be addressed soon
        CRITICAL: Serious issue requiring immediate attention

    Examples
    --------
    >>> Severity.CRITICAL
    <Severity.CRITICAL: 'CRITICAL'>
    >>> Severity.WARNING.value
    'WARNING'
    """

    OK = "OK"
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"

    @lru_cache(maxsize=4)
    def _order_value(self) -> int:
        """Return numeric value for ordering comparisons.

        Why Cached
        ----------
        Called frequently during severity comparisons (e.g., max() to find highest severity).
        Only 4 possible enum values, perfect for caching with maxsize=4.
        Eliminates repeated dict construction and lookup.
        """
        order = {
            Severity.OK: 0,
            Severity.INFO: 1,
            Severity.WARNING: 2,
            Severity.CRITICAL: 3,
        }
        return order[self]

    def __lt__(self, other: object) -> bool:
        """Compare severity levels for ordering.

        Why
            Enables finding the highest severity in a collection.

        Examples
        --------
        >>> Severity.WARNING < Severity.CRITICAL
        True
        >>> max([Severity.INFO, Severity.CRITICAL, Severity.WARNING])
        <Severity.CRITICAL: 'CRITICAL'>
        """
        if not isinstance(other, Severity):
            return NotImplemented
        return self._order_value() < other._order_value()

    def __le__(self, other: object) -> bool:
        """Less than or equal comparison."""
        if not isinstance(other, Severity):
            return NotImplemented
        return self._order_value() <= other._order_value()

    def __gt__(self, other: object) -> bool:
        """Greater than comparison."""
        if not isinstance(other, Severity):
            return NotImplemented
        return self._order_value() > other._order_value()

    def __ge__(self, other: object) -> bool:
        """Greater than or equal comparison."""
        if not isinstance(other, Severity):
            return NotImplemented
        return self._order_value() >= other._order_value()

    @lru_cache(maxsize=4)
    def is_critical(self) -> bool:
        """Return True if this severity level is critical.

        Why
        ----
        Determines if immediate action is required based on severity.

        Why Cached
        ----------
        Called frequently during alert processing. Only 4 possible enum values,
        perfect for caching. Eliminates repeated comparisons.

        Returns
        -------
        bool
            True if severity is CRITICAL, False otherwise.

        Examples
        --------
        >>> Severity.CRITICAL.is_critical()
        True
        >>> Severity.WARNING.is_critical()
        False
        """
        return self == Severity.CRITICAL

    def is_warning(self) -> bool:
        """Return True if this severity level is warning.

        Returns
        -------
        bool
            True if severity is WARNING, False otherwise.

        Examples
        --------
        >>> Severity.WARNING.is_warning()
        True
        >>> Severity.CRITICAL.is_warning()
        False
        """
        return self == Severity.WARNING


class DeviceState(str, Enum):
    """ZFS device (vdev) states as reported by zpool status.

    Why
        ZFS devices have well-defined states that determine device health.
        Enumerating these states provides type safety and prevents typos
        in state comparisons.

    Values
        ONLINE: Device is operational
        DEGRADED: Device is operational but in a degraded state
        FAULTED: Device has failed and cannot be used
        OFFLINE: Device has been manually taken offline
        UNAVAIL: Device is unavailable (removed or failed to open)
        REMOVED: Device has been physically removed

    Examples
    --------
    >>> DeviceState.ONLINE
    <DeviceState.ONLINE: 'ONLINE'>
    >>> DeviceState('FAULTED')
    <DeviceState.FAULTED: 'FAULTED'>
    """

    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    FAULTED = "FAULTED"
    OFFLINE = "OFFLINE"
    UNAVAIL = "UNAVAIL"
    REMOVED = "REMOVED"

    @classmethod
    def from_string(cls, value: str) -> "DeviceState":
        """Parse a string to DeviceState, defaulting to UNAVAIL for unknown values.

        Parameters
        ----------
        value:
            String representation of the device state.

        Returns
        -------
        DeviceState:
            The corresponding enum value.

        Examples
        --------
        >>> DeviceState.from_string("ONLINE")
        <DeviceState.ONLINE: 'ONLINE'>
        >>> DeviceState.from_string("UNKNOWN")
        <DeviceState.UNAVAIL: 'UNAVAIL'>
        """
        try:
            return cls(value.upper())
        except ValueError:
            return cls.UNAVAIL

    def is_problematic(self) -> bool:
        """Return True if this state indicates a problem.

        Returns
        -------
        bool:
            True for FAULTED, DEGRADED, OFFLINE, UNAVAIL, REMOVED.

        Examples
        --------
        >>> DeviceState.FAULTED.is_problematic()
        True
        >>> DeviceState.ONLINE.is_problematic()
        False
        """
        return self in (
            DeviceState.FAULTED,
            DeviceState.DEGRADED,
            DeviceState.OFFLINE,
            DeviceState.UNAVAIL,
            DeviceState.REMOVED,
        )


class IssueCategory(str, Enum):
    """Categories of ZFS pool issues.

    Why
        Issue categories provide type safety and enable filtering of issues
        by type. Using an enum prevents typos and ensures consistent naming.

    Values
        HEALTH: Pool health state issues (DEGRADED, FAULTED, etc.)
        CAPACITY: Disk space usage issues
        ERRORS: Read/write/checksum error issues
        SCRUB: Scrub-related issues (old scrub, scrub errors)
        DEVICE: Individual device issues within a pool

    Examples
    --------
    >>> IssueCategory.HEALTH
    <IssueCategory.HEALTH: 'health'>
    >>> IssueCategory.CAPACITY.value
    'capacity'
    """

    HEALTH = "health"
    CAPACITY = "capacity"
    ERRORS = "errors"
    SCRUB = "scrub"
    DEVICE = "device"


class ScanState(str, Enum):
    """ZFS scan (scrub/resilver) states.

    Why
        Scan states indicate the current scrub/resilver activity status.
        Using an enum provides type safety for state comparisons.

    Values
        NONE: No scan has ever been run
        SCANNING: Scan is currently in progress
        FINISHED: Last scan completed successfully
        CANCELED: Last scan was canceled
    """

    NONE = "NONE"
    SCANNING = "SCANNING"
    FINISHED = "FINISHED"
    CANCELED = "CANCELED"

    @classmethod
    def from_string(cls, value: str | None) -> "ScanState":
        """Parse a string to ScanState.

        Parameters
        ----------
        value:
            String representation of the scan state.

        Returns
        -------
        ScanState:
            The corresponding enum value.
        """
        if value is None:
            return cls.NONE
        try:
            return cls(value.upper())
        except ValueError:
            return cls.NONE


class IssueDetails(BaseModel):
    """Structured details for a pool issue.

    Why
        Replaces dict[str, Any] with a typed Pydantic model for issue details.
        Provides type safety for known fields while allowing flexible additional
        fields via extra="allow".

    Attributes
    ----------
    device_name:
        For device issues, the name of the affected device.
    device_state:
        Device state string (e.g., "FAULTED", "DEGRADED").
    device_type:
        Type of vdev (disk, mirror, raidz, etc.).
    current_state:
        Current pool state for health issues.
    expected_state:
        Expected pool state for health issues.
    capacity_percent:
        Pool capacity percentage for capacity issues.
    threshold:
        Threshold value that was exceeded.
    size_bytes:
        Total pool size in bytes.
    allocated_bytes:
        Allocated space in bytes.
    free_bytes:
        Free space in bytes.
    read_errors:
        Read error count.
    write_errors:
        Write error count.
    checksum_errors:
        Checksum error count.
    scrub_errors:
        Scrub error count.
    last_scrub:
        Last scrub timestamp as ISO string or None.
    age_days:
        Age in days (for scrub age issues).
    max_age_days:
        Maximum allowed age in days.
    expected:
        Expected value for comparison.
    actual:
        Actual value for comparison.
    """

    # Device issue fields
    device_name: str | None = None
    device_state: str | None = None
    device_type: str | None = None

    # Health issue fields
    current_state: str | None = None
    expected_state: str | None = None
    expected: str | None = None
    actual: str | None = None

    # Capacity issue fields
    capacity_percent: float | None = None
    threshold: float | int | None = None
    size_bytes: int | None = None
    allocated_bytes: int | None = None
    free_bytes: int | None = None

    # Error count fields
    read_errors: int | None = None
    write_errors: int | None = None
    checksum_errors: int | None = None

    # Scrub issue fields
    scrub_errors: int | None = None
    last_scrub: str | None = None
    age_days: int | None = None
    max_age_days: int | None = None

    model_config = ConfigDict(extra="allow")


@dataclass(frozen=True)
class DeviceStatus:
    """Status of a single device (vdev) within a ZFS pool.

    Why
        Tracks individual device health separately from pool health.
        A pool can be ONLINE while containing FAULTED devices if redundancy
        exists (e.g., mirror with one working device).

    Attributes
    ----------
    name:
        Device name or path (e.g., "wwn-0x5002538f55117008-part3")
    state:
        Device state as DeviceState enum
    read_errors:
        Count of read I/O errors on this device
    write_errors:
        Count of write I/O errors on this device
    checksum_errors:
        Count of checksum errors on this device
    vdev_type:
        Type of vdev (disk, mirror, raidz, draid, etc.)

    Examples
    --------
    >>> device = DeviceStatus(
    ...     name="wwn-0x5002538f55117008-part3",
    ...     state=DeviceState.FAULTED,
    ...     read_errors=3,
    ...     write_errors=220,
    ...     checksum_errors=0,
    ...     vdev_type="disk",
    ... )
    >>> device.is_faulted()
    True
    """

    name: str
    state: DeviceState
    read_errors: int
    write_errors: int
    checksum_errors: int
    vdev_type: str

    def is_faulted(self) -> bool:
        """Return True if device is in a faulted state."""
        return self.state == DeviceState.FAULTED

    def is_degraded(self) -> bool:
        """Return True if device is in a degraded state."""
        return self.state == DeviceState.DEGRADED

    def is_offline(self) -> bool:
        """Return True if device is offline."""
        return self.state == DeviceState.OFFLINE

    def is_healthy(self) -> bool:
        """Return True if device is healthy (ONLINE)."""
        return self.state == DeviceState.ONLINE

    def has_errors(self) -> bool:
        """Return True if device has any errors."""
        return self.read_errors > 0 or self.write_errors > 0 or self.checksum_errors > 0

    def is_problematic(self) -> bool:
        """Return True if device state indicates a problem."""
        return self.state.is_problematic()


@dataclass(frozen=True)
class PoolStatus:
    """Complete status snapshot of a single ZFS pool.

    Why
        Consolidates all relevant pool metrics into a single immutable
        structure. Parsers populate these from ZFS commands; monitors
        read them to detect issues.

    Attributes
    ----------
    name:
        Pool name as shown in `zpool list`
    health:
        Current health state (ONLINE, DEGRADED, etc.)
    capacity_percent:
        Percentage of pool capacity used (0.0-100.0)
    size_bytes:
        Total pool size in bytes
    allocated_bytes:
        Bytes allocated/used
    free_bytes:
        Bytes available for new data
    read_errors:
        Count of read I/O errors
    write_errors:
        Count of write I/O errors
    checksum_errors:
        Count of checksum errors (data corruption)
    last_scrub:
        Timestamp of last completed scrub, or None if never scrubbed
    scrub_errors:
        Number of errors found during last scrub
    scrub_in_progress:
        Whether a scrub is currently running
    faulted_devices:
        List of devices that are FAULTED, DEGRADED, or have errors.
        Empty list if all devices are healthy.

    Examples
    --------
    >>> from datetime import datetime, timezone
    >>> pool = PoolStatus(
    ...     name="rpool",
    ...     health=PoolHealth.ONLINE,
    ...     capacity_percent=45.2,
    ...     size_bytes=1_000_000_000_000,
    ...     allocated_bytes=452_000_000_000,
    ...     free_bytes=548_000_000_000,
    ...     read_errors=0,
    ...     write_errors=0,
    ...     checksum_errors=0,
    ...     last_scrub=datetime.now(UTC),
    ...     scrub_errors=0,
    ...     scrub_in_progress=False,
    ...     faulted_devices=[],
    ... )
    >>> pool.name
    'rpool'
    >>> pool.health.is_healthy()
    True
    """

    name: str
    health: PoolHealth
    capacity_percent: float
    size_bytes: int
    allocated_bytes: int
    free_bytes: int
    read_errors: int
    write_errors: int
    checksum_errors: int
    last_scrub: datetime | None
    scrub_errors: int
    scrub_in_progress: bool
    faulted_devices: tuple[DeviceStatus, ...] = ()

    def has_errors(self) -> bool:
        """Return True if pool has any I/O or checksum errors.

        Why
            Convenience method for quick error detection.

        Examples
        --------
        >>> pool = PoolStatus(
        ...     name="test", health=PoolHealth.ONLINE, capacity_percent=50.0,
        ...     size_bytes=1000, allocated_bytes=500, free_bytes=500,
        ...     read_errors=1, write_errors=0, checksum_errors=0,
        ...     last_scrub=None, scrub_errors=0, scrub_in_progress=False
        ... )
        >>> pool.has_errors()
        True
        """
        return self.read_errors > 0 or self.write_errors > 0 or self.checksum_errors > 0


@dataclass(frozen=True)
class PoolIssue:
    """Detected issue with a ZFS pool.

    Why
        Represents a single problem requiring attention. Issues are generated
        by monitoring logic and consumed by alerting systems.

    Attributes
    ----------
    pool_name:
        Name of affected pool
    severity:
        How urgent this issue is (INFO, WARNING, CRITICAL)
    category:
        Type of issue as IssueCategory enum
    message:
        Human-readable description of the issue
    details:
        Additional structured data about the issue as IssueDetails model.

    Examples
    --------
    >>> issue = PoolIssue(
    ...     pool_name="rpool",
    ...     severity=Severity.CRITICAL,
    ...     category=IssueCategory.HEALTH,
    ...     message="Pool is DEGRADED",
    ...     details=IssueDetails(expected="ONLINE", actual="DEGRADED"),
    ... )
    >>> issue.severity == Severity.CRITICAL
    True
    """

    pool_name: str
    severity: Severity
    category: IssueCategory
    message: str
    details: IssueDetails

    def __str__(self) -> str:
        """Return user-friendly string representation.

        Examples
        --------
        >>> issue = PoolIssue(
        ...     pool_name="rpool", severity=Severity.WARNING,
        ...     category=IssueCategory.CAPACITY, message="Pool at 85% capacity",
        ...     details=IssueDetails()
        ... )
        >>> str(issue)
        '[WARNING] rpool: Pool at 85% capacity'
        """
        return f"[{self.severity.value}] {self.pool_name}: {self.message}"


@dataclass(frozen=True)
class CheckResult:
    """Aggregated result of checking all ZFS pools.

    Why
        Consolidates monitoring results into a single structure. Represents
        the complete state of all pools at a point in time.

    Attributes
    ----------
    timestamp:
        When this check was performed
    pools:
        Status of all checked pools
    issues:
        All detected issues across all pools
    overall_severity:
        Highest severity among all issues

    Examples
    --------
    >>> from datetime import datetime, timezone
    >>> pool = PoolStatus(
    ...     name="rpool", health=PoolHealth.ONLINE, capacity_percent=45.0,
    ...     size_bytes=1000, allocated_bytes=450, free_bytes=550,
    ...     read_errors=0, write_errors=0, checksum_errors=0,
    ...     last_scrub=None, scrub_errors=0, scrub_in_progress=False
    ... )
    >>> result = CheckResult(
    ...     timestamp=datetime.now(UTC),
    ...     pools=[pool],
    ...     issues=[],
    ...     overall_severity=Severity.OK,
    ... )
    >>> result.overall_severity == Severity.OK
    True
    >>> len(result.pools)
    1
    """

    timestamp: datetime
    pools: list[PoolStatus]
    issues: list[PoolIssue]
    overall_severity: Severity

    def has_issues(self) -> bool:
        """Return True if any issues were detected.

        Examples
        --------
        >>> result = CheckResult(
        ...     timestamp=datetime.now(UTC),
        ...     pools=[],
        ...     issues=[],
        ...     overall_severity=Severity.OK
        ... )
        >>> result.has_issues()
        False
        """
        return len(self.issues) > 0

    def critical_issues(self) -> list[PoolIssue]:
        """Return only CRITICAL severity issues.

        Examples
        --------
        >>> issue1 = PoolIssue("pool1", Severity.WARNING, "capacity", "High", {})
        >>> issue2 = PoolIssue("pool2", Severity.CRITICAL, "health", "Faulted", {})
        >>> result = CheckResult(
        ...     timestamp=datetime.now(UTC),
        ...     pools=[],
        ...     issues=[issue1, issue2],
        ...     overall_severity=Severity.CRITICAL
        ... )
        >>> len(result.critical_issues())
        1
        >>> result.critical_issues()[0].severity == Severity.CRITICAL
        True
        """
        return [issue for issue in self.issues if issue.severity == Severity.CRITICAL]

    def warning_issues(self) -> list[PoolIssue]:
        """Return only WARNING severity issues.

        Examples
        --------
        >>> issue1 = PoolIssue("pool1", Severity.WARNING, "capacity", "High", {})
        >>> issue2 = PoolIssue("pool2", Severity.CRITICAL, "health", "Faulted", {})
        >>> result = CheckResult(
        ...     timestamp=datetime.now(UTC),
        ...     pools=[],
        ...     issues=[issue1, issue2],
        ...     overall_severity=Severity.CRITICAL
        ... )
        >>> len(result.warning_issues())
        1
        """
        return [issue for issue in self.issues if issue.severity == Severity.WARNING]


__all__ = [
    "CheckResult",
    "DeviceState",
    "DeviceStatus",
    "IssueCategory",
    "IssueDetails",
    "PoolHealth",
    "PoolIssue",
    "PoolStatus",
    "ScanState",
    "Severity",
]
