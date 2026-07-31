"""Data models for ZFS pool monitoring.

Purpose
-------
Define immutable data structures representing ZFS pool state, issues, and check
results. These models serve as the foundation for all monitoring logic, providing
type-safe containers for ZFS data.

Contents
--------
* :class:`PoolHealth` - Enumeration of possible ZFS pool health states
* :class:`Severity` - Enumeration of issue severity levels
* :class:`PoolStatus` - Complete status snapshot of a single ZFS pool
* :class:`PoolIssue` - Detected issue with a pool
* :class:`CheckResult` - Aggregated result of checking all pools
* :class:`ScanRun` - One scrub/resilver run of a pool, from `scan_stats`
* :class:`ScrubCycleResult` - Aggregated result of one scrub invocation

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
from datetime import datetime, timedelta, timezone  # noqa: F401 - timezone used in doctests  # pyright: ignore[reportUnusedImport]
from enum import Enum
from functools import lru_cache
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, TypeAdapter, ValidationError, field_validator, model_validator

logger = logging.getLogger(__name__)

#: Upper bound for capacity threshold percentages (0-100 inclusive).
CAPACITY_PERCENT_MAX = 100

#: Highest valid TCP port number.
MAX_PORT_NUMBER = 65535

#: Expected number of parts when splitting a "host:port" string.
HOST_PORT_PARTS_COUNT = 2


# ============================================================================
# Enums (declared first: the boundary models below carry them)
# ============================================================================


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
    def from_string(cls, value: str | None) -> ScanState:
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


class ScanFunction(str, Enum):
    """Which kind of scan `scan_stats` describes.

    Why
        `ScanState.SCANNING` alone does not say WHAT is running. A resilver and
        an error scrub occupy the same scan slot as a scrub, so a caller that
        wants to start a scrub must be able to tell them apart - starting a
        scrub while another scan owns the slot fails.

    Values
        NONE: No scan recorded
        SCRUB: Regular data scrub
        RESILVER: Device resilver after a replacement or a reattached device
        ERRORSCRUB: Error-log scrub (OpenZFS 2.2+)
        REBUILD: Sequential resilver / rebuild
        UNKNOWN: A scan function this version does not model

    Examples
    --------
    >>> ScanFunction.from_string("SCRUB")
    <ScanFunction.SCRUB: 'SCRUB'>
    >>> ScanFunction.from_string(None)
    <ScanFunction.NONE: 'NONE'>
    """

    NONE = "NONE"
    SCRUB = "SCRUB"
    RESILVER = "RESILVER"
    ERRORSCRUB = "ERRORSCRUB"
    REBUILD = "REBUILD"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def from_string(cls, value: str | None) -> ScanFunction:
        """Parse a string to ScanFunction.

        Why UNKNOWN rather than NONE for an unrecognised value
            NONE means "nothing is running". Mapping an unmodelled function to
            it would let a caller start a scrub while some other scan already
            owns the slot. UNKNOWN keeps "something is running" true.

        Parameters
        ----------
        value:
            String representation of the scan function.

        Returns
        -------
        ScanFunction:
            The corresponding enum value.

        Examples
        --------
        >>> ScanFunction.from_string("resilver")
        <ScanFunction.RESILVER: 'RESILVER'>
        >>> ScanFunction.from_string("SOMETHING_NEW")
        <ScanFunction.UNKNOWN: 'UNKNOWN'>
        """
        if value is None:
            return cls.NONE
        try:
            return cls(value.upper())
        except ValueError:
            logger.debug("Unknown scan function '%s', treating as UNKNOWN", value)
            return cls.UNKNOWN


class OutputFormat(str, Enum):
    """How a command renders its result.

    Why
        The choice appears in three commands and in each Click declaration; as
        a bare string it had to be spelled correctly in six places.

    Examples
    --------
    >>> OutputFormat("json")
    <OutputFormat.JSON: 'json'>
    """

    TEXT = "text"
    JSON = "json"


class ConfigOutputFormat(str, Enum):
    """How the config command renders the merged configuration.

    Why a second enum rather than reusing OutputFormat
        This command offers human or json; the check and scrub commands offer
        text or json. Merging them into one vocabulary would let
        `check --format human` past the Click choice and fail later.

    Examples
    --------
    >>> ConfigOutputFormat("human")
    <ConfigOutputFormat.HUMAN: 'human'>
    """

    HUMAN = "human"
    JSON = "json"


class ErrorKind(str, Enum):
    """Which ZFS error counter an issue is about.

    Values
        READ / WRITE: I/O errors on the vdev
        CHECKSUM: silent corruption caught by ZFS

    Examples
    --------
    >>> ErrorKind.CHECKSUM.value
    'checksum'
    """

    READ = "read"
    WRITE = "write"
    CHECKSUM = "checksum"


class InstallMethod(str, Enum):
    """How this copy of check_zpools was installed.

    Why
        Decides whether the systemd unit needs the uvx cache directory and a
        version pin, so it is a branch condition in three modules.

    Examples
    --------
    >>> InstallMethod.UVX.value
    'uvx'
    """

    UVX = "uvx"
    DIRECT = "direct"


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
    alert_resend_interval_hours:
        Hours before re-sending an alert whose severity has not changed.
    state_file:
        Path to the alert-state file; empty means the platform cache dir.
    pools_to_monitor:
        List of pool names to monitor. Empty means all pools.
    send_ok_emails:
        Whether to send emails when all pools are OK (default: False).
    send_recovery_emails:
        Whether to send emails when issues are resolved (default: True).
    """

    check_interval_seconds: int = 300
    alert_resend_interval_hours: int = 2
    state_file: str = ""
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
        Parsed from the config file's strings by pydantic, so the wire format
        is unchanged.
    """

    subject_prefix: str = "[ZFS Alert]"
    alert_recipients: list[str] = []
    send_ok_emails: bool = False
    send_recovery_emails: bool = True
    alert_on_severities: list[Severity] = [Severity.CRITICAL, Severity.WARNING]

    model_config = ConfigDict(extra="ignore")

    @field_validator("alert_on_severities", mode="before")
    @classmethod
    def _accept_any_case(cls, value: Any) -> Any:
        """Accept severities in any case, as this setting always has.

        Why
            Severity names are upper case, but the config file is written by
            hand and `alert_on_severities = ["critical"]` used to work - the
            alerter upper-cased them before comparing. Folding case here keeps
            that true while the field itself stays typed.

        Examples
        --------
        >>> AlertConfig.model_validate({"alert_on_severities": ["critical"]}).alert_on_severities
        [<Severity.CRITICAL: 'CRITICAL'>]
        """
        if isinstance(value, list):
            return [item.upper() if isinstance(item, str) else item for item in value]
        return value


class ScrubSettings(BaseModel):
    """Typed configuration for the scrub command.

    Why
        Replaces dict access with a validated model at the config boundary.

    Attributes
    ----------
    poll_interval_seconds:
        How often to re-read pool status while waiting for a scrub to finish.
        This is a polling cadence, never a deadline - the wait ends when ZFS
        reports no scan running, and at no other point.
    pools:
        Pools to scrub. Empty means every pool on the host.
    send_email:
        Whether to email a summary at the end of a cycle.
    email_on_success:
        When False, only cycles with problems are emailed.
    skip_if_other_scan_running:
        Leave a pool alone when a resilver (or any non-scrub scan) already owns
        its scan slot. When False, the start is attempted and ZFS decides.
    """

    poll_interval_seconds: float = 60.0
    pools: list[str] = []
    send_email: bool = True
    email_on_success: bool = True
    skip_if_other_scan_running: bool = True

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

    Attributes
    ----------
    last_scrub:
        Timestamp of the last completed scan, or None if never scanned.
    scrub_errors:
        Errors the scan reported.
    scrub_in_progress:
        Whether a SCRUB specifically is running. A resilver occupies the same
        scan slot but is not a scrub, so it does not set this flag.
    scan_function:
        Which kind of scan the fields above describe.
    scan_state:
        The state of that scan.
    """

    last_scrub: datetime | None
    scrub_errors: int
    scrub_in_progress: bool
    scan_function: ScanFunction = ScanFunction.NONE
    scan_state: ScanState = ScanState.NONE


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
    def from_string(cls, value: str) -> DeviceState:
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
    ...     last_scrub=datetime.now(timezone.utc),
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
    scan_function: ScanFunction = ScanFunction.NONE
    scan_state: ScanState = ScanState.NONE

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

    @property
    def resilver_in_progress(self) -> bool:
        """Return True while this pool is resilvering.

        Why
            A resilver and a scrub share one scan slot in ZFS, so before this
            existed the only signal, `scrub_in_progress`, was set by both and a
            rebuilding pool was reported as "scrub in progress". They need
            different words: a scrub is routine, a resilver means the pool is
            rebuilding redundancy after a device failure or replacement.

        Examples
        --------
        >>> pool = PoolStatus(
        ...     name="test", health=PoolHealth.DEGRADED, capacity_percent=50.0,
        ...     size_bytes=1000, allocated_bytes=500, free_bytes=500,
        ...     read_errors=0, write_errors=0, checksum_errors=0,
        ...     last_scrub=None, scrub_errors=0, scrub_in_progress=False,
        ...     scan_function=ScanFunction.RESILVER, scan_state=ScanState.SCANNING,
        ... )
        >>> pool.resilver_in_progress
        True
        >>> pool.scrub_in_progress
        False

        A resilver that has already finished is not in progress:

        >>> import dataclasses
        >>> dataclasses.replace(pool, scan_state=ScanState.FINISHED).resilver_in_progress
        False
        """
        return self.scan_function == ScanFunction.RESILVER and self.scan_state == ScanState.SCANNING


@dataclass(frozen=True)
class ScanRun:
    """One scrub/resilver run of a single pool, as reported by `scan_stats`.

    Why
        `PoolStatus` carries a boolean `scrub_in_progress`, which is enough to
        raise an alert but not enough to DRIVE a scrub: a caller waiting for a
        scrub to finish needs to know what kind of scan is running, how far it
        has come, and how it ended. This model carries the whole `scan_stats`
        block in typed form.

    Attributes
    ----------
    pool_name:
        Name of the pool this scan belongs to
    function:
        Which kind of scan this is (SCRUB, RESILVER, ...)
    state:
        Current state of the scan (SCANNING, FINISHED, CANCELED, NONE)
    start_time:
        When the scan started, or None if it never ran
    end_time:
        When the scan ended, or None while it is still running
    to_examine_bytes:
        Total bytes the scan intends to walk
    examined_bytes:
        Bytes walked so far
    issued_bytes:
        Bytes actually issued to the vdevs so far. This - not examined_bytes -
        is what `zpool status` reports as the progress percentage, and it is
        the smaller, honest number on a pool with skipped ranges.
    errors:
        Errors this scan found
    paused_seconds:
        Seconds the scan spent paused

    Examples
    --------
    >>> run = ScanRun(
    ...     pool_name="rpool",
    ...     function=ScanFunction.SCRUB,
    ...     state=ScanState.SCANNING,
    ...     start_time=None,
    ...     end_time=None,
    ...     to_examine_bytes=1000,
    ...     examined_bytes=500,
    ...     issued_bytes=250,
    ...     errors=0,
    ...     paused_seconds=0,
    ... )
    >>> run.is_running
    True
    >>> run.is_scrub
    True
    >>> run.progress_percent
    25.0
    """

    pool_name: str
    function: ScanFunction
    state: ScanState
    start_time: datetime | None
    end_time: datetime | None
    to_examine_bytes: int
    examined_bytes: int
    issued_bytes: int
    errors: int
    paused_seconds: int = 0

    @property
    def is_running(self) -> bool:
        """Return True while this scan is still scanning.

        Examples
        --------
        >>> ScanRun("p", ScanFunction.SCRUB, ScanState.FINISHED, None, None, 0, 0, 0, 0).is_running
        False
        """
        return self.state == ScanState.SCANNING

    @property
    def is_scrub(self) -> bool:
        """Return True when this scan is a regular data scrub.

        Examples
        --------
        >>> ScanRun("p", ScanFunction.RESILVER, ScanState.SCANNING, None, None, 0, 0, 0, 0).is_scrub
        False
        """
        return self.function == ScanFunction.SCRUB

    @property
    def progress_percent(self) -> float:
        """Return scan progress in percent, 0.0 when nothing is known yet.

        Examples
        --------
        >>> ScanRun("p", ScanFunction.SCRUB, ScanState.SCANNING, None, None, 0, 0, 0, 0).progress_percent
        0.0
        >>> ScanRun("p", ScanFunction.SCRUB, ScanState.FINISHED, None, None, 200, 200, 300, 0).progress_percent
        100.0
        """
        if self.to_examine_bytes <= 0:
            return 0.0
        # ZFS can issue slightly more than it planned to examine; clamp so the
        # progress line never reads "103.4% done".
        return min(self.issued_bytes / self.to_examine_bytes * 100, 100.0)

    @property
    def duration(self) -> timedelta | None:
        """Return how long a finished scan took, or None if it has not ended.

        Examples
        --------
        >>> from datetime import datetime, timezone
        >>> start = datetime(2026, 7, 31, 7, 0, tzinfo=timezone.utc)
        >>> end = datetime(2026, 7, 31, 7, 5, tzinfo=timezone.utc)
        >>> ScanRun("p", ScanFunction.SCRUB, ScanState.FINISHED, start, end, 0, 0, 0, 0).duration
        datetime.timedelta(seconds=300)
        """
        if self.start_time is None or self.end_time is None:
            return None
        return self.end_time - self.start_time


@dataclass(frozen=True)
class ScrubRunOptions:
    """Per-invocation knobs for one scrub cycle.

    Why
        Separates WHAT to do from the collaborators that do it, and keeps the
        runner's signature to the objects it acts through. Built from
        :class:`ScrubSettings` plus any command-line overrides.

    Attributes
    ----------
    pools:
        Pools to scrub. Empty means every pool on the host.
    wait:
        Wait for the scrubs to finish. There is no timeout on that wait.
    poll_interval_seconds:
        Seconds between status reads while waiting.
    skip_if_other_scan_running:
        Leave a pool alone while a non-scrub scan holds its scan slot.
    dry_run:
        Report what would happen without starting anything.

    Examples
    --------
    >>> ScrubRunOptions(pools=("rpool",), wait=False).pools
    ('rpool',)
    >>> ScrubRunOptions().poll_interval_seconds
    60.0
    """

    pools: tuple[str, ...] = ()
    wait: bool = True
    poll_interval_seconds: float = 60.0
    skip_if_other_scan_running: bool = True
    dry_run: bool = False


class ScrubAction(str, Enum):
    """What the scrub runner did with one pool.

    Why
        A scrub cycle does not simply "run": a pool may already be scrubbing
        (adopt it), may be busy resilvering (leave it alone), or may refuse the
        start. Reporting needs to distinguish those rather than collapse them
        into success or failure.

    Values
        STARTED: A scrub was issued for this pool
        ADOPTED: A scrub was already running; the runner waited on it instead
        SKIPPED: Another scan owns the scan slot, no scrub was issued
        FAILED_TO_START: `zpool scrub` was issued and refused
        DRY_RUN: A scrub would have been issued, but --dry-run was in effect
    """

    STARTED = "started"
    ADOPTED = "adopted"
    SKIPPED = "skipped"
    FAILED_TO_START = "failed_to_start"
    DRY_RUN = "dry_run"


@dataclass(frozen=True)
class PoolDecision:
    """What the runner decided to do with one pool, before it is known how it ended.

    Why
        The decision is a named triple, not a positional pair: carrying it as
        `tuple[ScrubAction, str]` forced every reader to remember which slot
        held the reason and left the pool name implicit in a surrounding dict
        key.

    Examples
    --------
    >>> PoolDecision(pool_name="rpool", action=ScrubAction.ADOPTED).reason
    ''
    """

    pool_name: str
    action: ScrubAction
    reason: str = ""


@dataclass(frozen=True)
class PoolScrubOutcome:
    """Result of one pool's participation in a scrub cycle.

    Attributes
    ----------
    pool_name:
        Name of the pool
    action:
        What the runner did with this pool
    reason:
        Why it was skipped or failed; empty when nothing went wrong
    final_scan:
        The pool's scan record as of the last status read, or None if the pool
        could not be read at all

    Examples
    --------
    >>> outcome = PoolScrubOutcome("rpool", ScrubAction.SKIPPED, reason="resilver running")
    >>> outcome.is_problem
    True
    """

    pool_name: str
    action: ScrubAction
    reason: str = ""
    final_scan: ScanRun | None = None

    @property
    def is_problem(self) -> bool:
        """Return True when this pool needs a human to look at it.

        Why
            A scrub that could not be started, was skipped, was canceled, or
            found errors is a problem. A scrub that is merely still running
            (--no-wait) is not.

        Examples
        --------
        >>> ok = ScanRun("p", ScanFunction.SCRUB, ScanState.FINISHED, None, None, 0, 0, 0, 0)
        >>> PoolScrubOutcome("p", ScrubAction.STARTED, final_scan=ok).is_problem
        False
        >>> bad = ScanRun("p", ScanFunction.SCRUB, ScanState.FINISHED, None, None, 0, 0, 0, 3)
        >>> PoolScrubOutcome("p", ScrubAction.STARTED, final_scan=bad).is_problem
        True
        """
        if self.action in (ScrubAction.SKIPPED, ScrubAction.FAILED_TO_START):
            return True
        if self.final_scan is None:
            # A pool we started or adopted that is no longer readable (exported
            # or destroyed mid-scrub) is a problem; a pool we never touched is not.
            return self.action in (ScrubAction.STARTED, ScrubAction.ADOPTED)
        return self.final_scan.errors > 0 or self.final_scan.state == ScanState.CANCELED


@dataclass(frozen=True)
class ScrubCycleResult:
    """Aggregated result of one `check_zpools scrub` invocation.

    Attributes
    ----------
    started_at:
        When the cycle began
    finished_at:
        When the cycle ended (after waiting, when waiting was requested)
    outcomes:
        Per-pool outcome, in the order the pools were processed
    waited:
        Whether the runner waited for the scrubs to finish
    dry_run:
        Whether this was a dry run (nothing was started)

    Examples
    --------
    >>> from datetime import datetime, timezone
    >>> now = datetime.now(timezone.utc)
    >>> result = ScrubCycleResult(now, now, [], waited=True, dry_run=False)
    >>> result.has_problems()
    False
    """

    started_at: datetime
    finished_at: datetime
    outcomes: list[PoolScrubOutcome]
    waited: bool
    dry_run: bool

    def has_problems(self) -> bool:
        """Return True when any pool needs attention."""
        return any(outcome.is_problem for outcome in self.outcomes)

    def problems(self) -> list[PoolScrubOutcome]:
        """Return only the outcomes that need attention."""
        return [outcome for outcome in self.outcomes if outcome.is_problem]

    @property
    def duration(self) -> timedelta:
        """Return how long the whole cycle took."""
        return self.finished_at - self.started_at


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
    ...     timestamp=datetime.now(timezone.utc),
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
        ...     timestamp=datetime.now(timezone.utc),
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
        ...     timestamp=datetime.now(timezone.utc),
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
        ...     timestamp=datetime.now(timezone.utc),
        ...     pools=[],
        ...     issues=[issue1, issue2],
        ...     overall_severity=Severity.CRITICAL
        ... )
        >>> len(result.warning_issues())
        1
        """
        return [issue for issue in self.issues if issue.severity == Severity.WARNING]


# ============================================================================
# Application Configuration (bottom layer: every consumer may import these)
# ============================================================================


def _default_smtp_hosts() -> list[str]:
    """Factory function for default SMTP hosts list."""
    return []


class EmailConfig(BaseModel):
    """Email configuration container.

    Why
        Provides a domain-appropriate configuration object that maps cleanly
        to lib_layered_config while remaining independent of btx_lib_mail's
        internal structure.

    Fields
    ------
    smtp_hosts:
        List of SMTP servers in 'host[:port]' format. Tried in order until
        one succeeds.
    from_address:
        Default sender address for outgoing emails.
    smtp_username:
        Optional SMTP authentication username.
    smtp_password:
        Optional SMTP authentication password.
    use_starttls:
        Enable STARTTLS negotiation.
    timeout:
        Socket timeout in seconds for SMTP operations.
    raise_on_missing_attachments:
        When True, missing attachment files raise FileNotFoundError.
    raise_on_invalid_recipient:
        When True, invalid email addresses raise ValueError.

    Examples
    --------
    >>> config = EmailConfig(
    ...     smtp_hosts=["smtp.example.com:587"],
    ...     from_address="noreply@example.com"
    ... )
    >>> config.smtp_hosts
    ['smtp.example.com:587']
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _drop_uncoercible_values(cls, data: Any) -> Any:
        """Drop config values that cannot become their declared type, so the default applies.

        Why
            This model parses an operator-edited config file that a monitoring
            daemon loads at startup on every node. A single typo (`timeout =
            "abc"`) must not turn that daemon into a crash loop, so an
            unusable value falls back to the field default - the long-standing
            behaviour of this loader. Unlike the silent fallback it replaces,
            each dropped value is logged, so the typo is still discoverable.

        Examples
        --------
        >>> EmailConfig.model_validate({"timeout": "not_a_number"}).timeout
        30.0
        >>> EmailConfig.model_validate({"timeout": 5.0}).timeout
        5.0
        """
        if not isinstance(data, dict):
            return data
        usable: dict[str, Any] = {}
        for name, field_info in cls.model_fields.items():
            if name not in data:
                continue
            value = data[name]
            try:
                TypeAdapter(field_info.annotation).validate_python(value)
            except ValidationError:
                logger.warning(
                    "Ignoring unusable value for email.%s, using default",
                    name,
                    extra={"field": name, "value_type": type(value).__name__},
                )
                continue
            usable[name] = value
        return usable

    smtp_hosts: list[str] = Field(default_factory=_default_smtp_hosts)
    from_address: str = "noreply@localhost"
    smtp_username: str | None = None
    smtp_password: str | None = None
    use_starttls: bool = True
    timeout: float = 30.0
    raise_on_missing_attachments: bool = True
    raise_on_invalid_recipient: bool = True

    def _validate_timeout(self) -> None:
        """Validate timeout is positive.

        Raises
        ------
        ValueError: If timeout is not positive.
        """
        if self.timeout <= 0:
            raise ValueError(f"timeout must be positive, got {self.timeout}")

    def _validate_from_address(self) -> None:
        """Validate from_address contains @.

        Raises
        ------
        ValueError: If from_address doesn't contain @.
        """
        if "@" not in self.from_address:
            raise ValueError(f"from_address must contain @, got {self.from_address!r}")

    def _validate_smtp_host_port(self, host: str, port_str: str) -> None:
        """Validate SMTP host port is numeric and in valid range.

        Parameters
        ----------
        host:
            Full host string (for error messages).
        port_str:
            Port string to validate.

        Raises
        ------
        ValueError: If port is invalid.
        """
        try:
            port = int(port_str)
            if not (1 <= port <= MAX_PORT_NUMBER):
                raise ValueError(f"Port must be 1-65535 in {host!r}")
        except ValueError as e:
            if "invalid literal" in str(e):
                raise ValueError(f"Port must be numeric in {host!r}") from e
            raise

    def _validate_smtp_host(self, host: str) -> None:
        """Validate single SMTP host format.

        Parameters
        ----------
        host:
            SMTP host string, optionally with :port.

        Raises
        ------
        ValueError: If host format is invalid.
        """
        if ":" not in host:
            return

        parts = host.split(":")
        if len(parts) != HOST_PORT_PARTS_COUNT:
            raise ValueError(f"Invalid SMTP host format (expected 'host:port'): {host!r}")

        self._validate_smtp_host_port(host, parts[1])

    @model_validator(mode="after")
    def _validate(self) -> EmailConfig:
        """Validate configuration values.

        Why
            Catch common configuration mistakes early with clear error messages
            rather than allowing invalid values to cause obscure failures later.

        Raises
            ValueError: When configuration values are invalid.

        Examples
        --------
        Pydantic wraps the failure, and its ValidationError is a ValueError, so
        callers catching ValueError keep working:

        >>> EmailConfig(timeout=-5.0)  # doctest: +IGNORE_EXCEPTION_DETAIL
        Traceback (most recent call last):
        ...
        pydantic_core._pydantic_core.ValidationError: timeout must be positive

        >>> try:
        ...     EmailConfig(from_address="not-an-email")
        ... except ValueError as exc:
        ...     "from_address must contain @" in str(exc)
        True
        """
        self._validate_timeout()
        self._validate_from_address()
        for host in self.smtp_hosts:
            self._validate_smtp_host(host)
        return self


class MonitorConfig(BaseModel):
    """Configuration for pool monitoring thresholds.

    Why
        Centralizes threshold configuration, making it easy to override
        via config files or environment variables.

    Attributes
    ----------
    capacity_warning_percent:
        Capacity percentage triggering WARNING (default: 80)
    capacity_critical_percent:
        Capacity percentage triggering CRITICAL (default: 90)
    scrub_max_age_days:
        Maximum days since last scrub before WARNING (default: 30)
    read_errors_warning:
        Read error count triggering WARNING (default: 1)
    write_errors_warning:
        Write error count triggering WARNING (default: 1)
    checksum_errors_warning:
        Checksum error count triggering WARNING (default: 1)

    Examples
    --------
    >>> config = MonitorConfig(
    ...     capacity_warning_percent=75,
    ...     capacity_critical_percent=85,
    ...     scrub_max_age_days=7,
    ... )
    >>> config.capacity_warning_percent
    75
    """

    model_config = ConfigDict(extra="ignore")

    capacity_warning_percent: int = 80
    capacity_critical_percent: int = 90
    scrub_max_age_days: int = 30
    read_errors_warning: int = 1
    write_errors_warning: int = 1
    checksum_errors_warning: int = 1

    @model_validator(mode="after")
    def _validate_thresholds(self) -> MonitorConfig:
        """Validate thresholds are in range and correctly ordered.

        Why
            These bounds used to be re-checked by hand wherever the config
            dict was unpacked. Declaring them on the model means the section
            cannot be constructed invalid - from a config file or from code -
            and there is one copy of the rule rather than one per call site.

        Raises
        ------
        ValueError:
            When a threshold is out of range or the two capacity thresholds
            are not strictly ordered.
        """
        if not 0 < self.capacity_warning_percent < CAPACITY_PERCENT_MAX:
            raise ValueError(f"zfs.capacity_warning_percent must be between 0 and 100, got {self.capacity_warning_percent}")
        if not 0 < self.capacity_critical_percent <= CAPACITY_PERCENT_MAX:
            raise ValueError(f"zfs.capacity_critical_percent must be between 0 and 100, got {self.capacity_critical_percent}")
        if self.capacity_warning_percent >= self.capacity_critical_percent:
            raise ValueError(
                f"zfs.capacity_warning_percent ({self.capacity_warning_percent}%) "
                f"must be less than capacity_critical_percent ({self.capacity_critical_percent}%)"
            )
        for name in ("scrub_max_age_days", "read_errors_warning", "write_errors_warning", "checksum_errors_warning"):
            if getattr(self, name) < 0:
                raise ValueError(f"zfs.{name} must be non-negative, got {getattr(self, name)}")
        return self


class CheckZpoolsConfig(BaseModel):
    """The whole application configuration, parsed once at the boundary.

    Why
        `lib_layered_config` hands back an untyped mapping. Before this model
        existed that mapping travelled into the behaviour layer and every
        consumer re-parsed its own section, so the same file was parsed five
        times with five sets of defaults, and a section nobody happened to read
        was never validated at all. Parsing once means a misconfiguration is
        caught at startup rather than on the first code path that looks.

    Examples
    --------
    >>> settings = CheckZpoolsConfig()
    >>> settings.zfs.capacity_warning_percent, settings.scrub.poll_interval_seconds
    (80, 60.0)
    >>> CheckZpoolsConfig.model_validate({"zfs": {"capacity_warning_percent": 70}}).zfs.capacity_warning_percent
    70
    """

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _drop_non_mapping_sections(cls, data: Any) -> Any:
        """Ignore a section that is not a table, so its defaults apply.

        Why
            Same reason the individual values tolerate junk: this is parsed at
            startup on every node from a file a human edits. A section written
            as a scalar (`email = "smtp.example.com"`) is a mistake, but it
            must not stop the daemon starting - it is logged, and the section
            falls back to defaults.

        Examples
        --------
        >>> CheckZpoolsConfig.model_validate({"email": "oops"}).email.timeout
        30.0
        """
        if not isinstance(data, dict):
            return data
        cleaned: dict[str, Any] = {}
        for key, value in data.items():
            if key in cls.model_fields and not isinstance(value, dict):
                logger.warning("Ignoring malformed config section %r, using defaults", key)
                continue
            cleaned[key] = value
        return cleaned

    zfs: MonitorConfig = MonitorConfig()
    daemon: DaemonConfig = DaemonConfig()
    alerts: AlertConfig = AlertConfig()
    email: EmailConfig = EmailConfig()
    scrub: ScrubSettings = ScrubSettings()


# ============================================================================
# ZFS Wire Payload (the shape `zpool status -j --json-int` actually emits)
# ============================================================================


def _tolerant_int(value: Any) -> Any:
    """Coerce a numeric field, falling back to 0 when ZFS emits something odd.

    Why
        The parser has always degraded a malformed numeric field to 0 rather
        than aborting the whole status read: one strange value on one vdev must
        not blind the monitor to every other pool. Declaring that here keeps
        the behaviour while letting the models describe the payload.

    Examples
    --------
    >>> _tolerant_int(42), _tolerant_int("42")
    (42, 42)
    >>> _tolerant_int("not-a-number")
    0
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        logger.warning("Ignoring non-numeric value %r in zpool status output, using 0", value)
        return 0


#: An integer field that degrades to 0 instead of failing the whole parse.
TolerantInt = Annotated[int, BeforeValidator(_tolerant_int)]


class ScanStatsPayload(BaseModel):
    """The `scan_stats` block of one pool, as ZFS emits it."""

    model_config = ConfigDict(extra="ignore")

    function: str | None = None
    state: str | None = None
    start_time: TolerantInt = 0
    end_time: TolerantInt = 0
    to_examine: TolerantInt = 0
    examined: TolerantInt = 0
    issued: TolerantInt = 0
    skipped: TolerantInt = 0
    processed: TolerantInt = 0
    errors: TolerantInt = 0
    pass_start: TolerantInt = 0
    scrub_spent_paused: TolerantInt = 0


class VdevPayload(BaseModel):
    """One vdev in the tree: the root, a mirror/raidz container, or a leaf device."""

    model_config = ConfigDict(extra="ignore")

    name: str = "unknown"
    vdev_type: str = ""
    state: str = "UNAVAIL"
    alloc_space: TolerantInt = 0
    total_space: TolerantInt = 0
    read_errors: TolerantInt = 0
    write_errors: TolerantInt = 0
    checksum_errors: TolerantInt = 0
    vdevs: dict[str, VdevPayload] = {}

    @property
    def is_leaf_device(self) -> bool:
        """Return True for a device that holds data, not a container vdev.

        Why
            Only leaves are worth reporting individually: a mirror showing
            DEGRADED is a summary of the disk underneath it, and reporting both
            would double-count one failure.

        Examples
        --------
        >>> VdevPayload(vdev_type="disk").is_leaf_device
        True
        >>> VdevPayload(vdev_type="mirror").is_leaf_device
        False
        """
        return self.vdev_type.lower() in ("disk", "file", "spare", "cache", "log")

    @property
    def has_errors(self) -> bool:
        """Return True when this vdev reports any I/O or checksum error."""
        return self.read_errors > 0 or self.write_errors > 0 or self.checksum_errors > 0


class PoolPayload(BaseModel):
    """One pool as reported by `zpool status -j`."""

    model_config = ConfigDict(extra="ignore")

    name: str = ""
    state: str = "UNKNOWN"
    vdevs: dict[str, VdevPayload] = {}
    scan_stats: ScanStatsPayload | None = None
    #: Older ZFS builds name the same block `scan`.
    scan: ScanStatsPayload | None = None

    @property
    def scan_block(self) -> ScanStatsPayload:
        """Return the scan block under whichever key this ZFS version used."""
        return self.scan_stats or self.scan or ScanStatsPayload()

    def root_vdev(self) -> VdevPayload:
        """Return the pool's root vdev, or an empty one when absent.

        Why
            The root vdev carries the pool-wide capacity and error counters;
            an absent one means a malformed payload, and an empty vdev keeps
            the caller on the degraded path rather than raising.
        """
        return self.vdevs.get(self.name, VdevPayload())


class ZpoolStatusPayload(BaseModel):
    """The whole `zpool status -j --json-int` document."""

    model_config = ConfigDict(extra="ignore")

    pools: dict[str, PoolPayload] = {}


__all__ = [
    "CheckResult",
    "CheckZpoolsConfig",
    "ConfigOutputFormat",
    "DeviceState",
    "DeviceStatus",
    "EmailConfig",
    "ErrorKind",
    "InstallMethod",
    "IssueCategory",
    "IssueDetails",
    "MonitorConfig",
    "OutputFormat",
    "PoolDecision",
    "PoolHealth",
    "PoolIssue",
    "PoolPayload",
    "PoolScrubOutcome",
    "PoolStatus",
    "ScanFunction",
    "ScanRun",
    "ScanState",
    "ScanStatsPayload",
    "ScrubAction",
    "ScrubCycleResult",
    "ScrubRunOptions",
    "ScrubSettings",
    "Severity",
    "VdevPayload",
    "ZpoolStatusPayload",
]
