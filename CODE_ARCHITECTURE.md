# Code Architecture Documentation

## Email Alerting Module (`alerting.py`)

### Design Principles

The email alerting system follows clean code principles with:
- **Single Responsibility Principle**: Each method handles one specific formatting concern
- **DRY (Don't Repeat Yourself)**: Shared logic extracted into reusable helper methods
- **Self-Documenting Code**: Named constants instead of magic numbers
- **Configuration-Driven**: Thresholds passed as parameters, not hardcoded

### Module-Level Constants

```python
# Binary unit multipliers (powers of 1024)
_BYTES_PER_KB = 1024
_BYTES_PER_MB = 1024 ** 2
_BYTES_PER_GB = 1024 ** 3
_BYTES_PER_TB = 1024 ** 4
_BYTES_PER_PB = 1024 ** 5
```

These constants provide self-documenting byte conversions and eliminate magic numbers throughout the codebase.

### Configuration-Driven Thresholds

The `EmailAlerter` class accepts threshold parameters in its constructor:

```python
def __init__(
    self,
    email_config: EmailConfig,
    alert_config: dict[str, Any],
    capacity_warning_percent: int = 80,
    capacity_critical_percent: int = 90,
    scrub_max_age_days: int = 30,
):
```

These thresholds are:
- Passed from `MonitorConfig` during daemon initialization
- Used in `_format_notes_section()` for dynamic warning messages
- Displayed in user-facing warning messages (e.g., "≥90%" shows actual threshold)

**Why**: Eliminates hardcoded threshold values (previously 90, 80, 30) and ensures
email alerts use the same thresholds as pool monitoring, maintaining consistency
across the entire system.

### Email Formatting Architecture

#### Return Pattern

All email formatting helper methods follow a consistent pattern:
- **Helper methods** return `list[str]` (individual lines)
- **Parent methods** perform single `"\n".join()` operation
- This prevents double-joining and ensures correct spacing

#### Alert Email Structure

**Main method:** `_format_body(issue, pool) -> str`

Delegates to specialized formatters:
1. `_format_alert_header()` → Alert header with issue details
2. `_format_pool_details_section()` → Pool capacity and scrub summary
3. `_format_recommended_actions_section()` → Context-specific actions
4. `_format_alert_footer()` → Version and hostname
5. `_format_complete_pool_status()` → Full pool status details

#### Pool Status Formatting

**Main method:** `_format_complete_pool_status(pool) -> str`

Delegates to specialized formatters:
1. `_format_capacity_section()` → Capacity in TB/GB/bytes
2. `_format_error_statistics_section()` → Error counts
3. `_format_scrub_status_section()` → Scrub timing and results
4. `_format_health_assessment_section()` → Health status
5. `_format_notes_section()` → Warnings (empty list if none)

### Helper Methods

#### `_calculate_scrub_age_days(pool) -> int | None`

Calculates days since last scrub. Returns `None` if pool has never been scrubbed.

**Used by:**
- `_format_pool_details_section()` - For alert email summary
- `_format_scrub_status_section()` - For detailed scrub status
- `_format_notes_section()` - For scrub age warnings

This eliminates code duplication across three locations.

### Binary Unit Conversions

All capacity calculations use named constants:

```python
used_tb = pool.allocated_bytes / _BYTES_PER_TB
used_gb = pool.allocated_bytes / _BYTES_PER_GB
```

This provides:
- Clear intent (what unit we're converting to)
- Easy maintenance (change definition in one place)
- Consistency across all calculations

## Behaviors Module (`behaviors.py`)

### Configuration-Driven Display

The `show_pool_status()` function loads capacity thresholds from configuration
to color-code pool capacity display:

```python
# Load config to get capacity thresholds for color-coding
config_dict = get_config().as_dict()
capacity = config_dict.get("zfs", {}).get("capacity", {})
capacity_warning = capacity.get("warning_percent", 80)
capacity_critical = capacity.get("critical_percent", 90)

# Apply thresholds
if pool.capacity_percent >= capacity_critical:
    cap_style = "red"
elif pool.capacity_percent >= capacity_warning:
    cap_style = "yellow"
```

**Why**: Eliminates hardcoded threshold values (previously 90 and 80) and ensures
status display uses the same thresholds as monitoring and alerting.

### Daemon Initialization

When initializing `EmailAlerter`, threshold values are passed from `MonitorConfig`:

```python
alerter = EmailAlerter(
    email_config,
    alert_config,
    capacity_warning_percent=monitor_config.capacity_warning_percent,
    capacity_critical_percent=monitor_config.capacity_critical_percent,
    scrub_max_age_days=monitor_config.scrub_max_age_days,
)
```

This ensures alert formatting uses the same thresholds as pool monitoring.

## Daemon Module (`daemon.py`)

### Alert Processing Architecture

**Main method:** `_handle_check_result(result, pools) -> dict[str, set[str]]`

Delegates to specialized methods:
1. `_should_send_alert(issue)` → Filtering logic
2. `_send_alert_for_issue(issue, pool)` → Alert delivery

#### `_should_send_alert(issue) -> bool`

Determines if an alert should be sent based on:
- Severity filtering (skip OK issues if configured)
- Alert state management (prevent duplicates within resend interval)

#### `_send_alert_for_issue(issue, pool) -> None`

Handles alert delivery and state recording:
- Sends email via alerter
- Records successful delivery in state manager
- Logs result for monitoring

### Benefits

- **Testability**: Each concern can be tested independently
- **Maintainability**: Clear boundaries between filtering, sending, and recording
- **Readability**: Method names clearly describe intent

## Parser Module (`zfs_parser.py`)

### Regex Optimization

Pre-compiled regex pattern for performance:

```python
# Module-level constant
_SIZE_PATTERN = re.compile(r'^([0-9.]+)\s*([KMGTP])$')
```

**Used in:** `_parse_size_to_bytes(size_str) -> int`

Benefits:
- Pattern compiled once at module import
- Eliminates repeated compilation overhead
- Critical for daemon mode (continuous parsing)

### Helper Methods

#### `_parse_health_state(health_value, pool_name) -> PoolHealth`

Parses health state strings into enum values with fallback to OFFLINE for unknown states.

#### `_extract_capacity_metrics(props) -> dict`

Extracts and converts capacity metrics from pool properties:
- `capacity_percent` (float)
- `size_bytes`, `allocated_bytes`, `free_bytes` (int)

#### `_extract_scrub_info(pool_data) -> dict`

Extracts scrub information from pool status data:
- `last_scrub` (datetime | None)
- `scrub_errors` (int)
- `scrub_in_progress` (bool)

These helpers eliminate duplication between `_parse_pool_from_list()` and `_parse_pool_from_status()`.

## CLI Errors Module (`cli_errors.py`)

### Purpose

Provides shared error handling utilities to eliminate code duplication across CLI
commands.

### Design Principle

**DRY (Don't Repeat Yourself)**: Identical exception handling patterns appeared in
multiple CLI commands. Extracting to shared utilities ensures consistency and
reduces maintenance burden.

### Functions

#### `handle_zfs_not_available(exc, operation) -> NoReturn`

Handles `ZFSNotAvailableError` exceptions with consistent logging and messaging.

**Benefits:**
- Single source of truth for ZFS unavailability errors
- Consistent error messages across all commands
- Centralized logging format

#### `handle_generic_error(exc, operation) -> NoReturn`

Handles unexpected exceptions with full traceback logging and user-friendly messaging.

**Benefits:**
- Consistent error handling across all commands
- Full traceback capture for debugging
- Operation-specific context in error messages

### Usage

```python
try:
    result = check_pools_once()
except ZFSNotAvailableError as exc:
    handle_zfs_not_available(exc, operation="Check")
except Exception as exc:
    handle_generic_error(exc, operation="Check")
```

**Refactoring Impact**: Reduced each exception handler from 6-8 lines to 2 lines,
eliminating 18-24 lines of duplicated code across 3 commands.

## Formatters Module (`formatters.py`)

### Purpose

Centralizes all output formatting logic to keep the CLI module minimal and focused
on command wiring.

### Design Principle

**Separation of Concerns**: The CLI module handles command routing and option parsing,
while formatters handle output generation. This keeps each module focused on a single
responsibility.

### Functions

#### `format_check_result_json(result) -> str`

Formats check results as JSON with proper indentation.

**Returns:**
- timestamp (ISO format)
- pools (name, health, capacity)
- issues (pool_name, severity, category, message, details)
- overall_severity

#### `format_check_result_text(result) -> str`

Formats check results as human-readable text with:
- Timestamp header
- Overall status
- Color-coded issue list (red/yellow/green)
- Summary (pools checked count)

#### `get_exit_code_for_severity(severity) -> int`

Maps severity levels to standard exit codes:
- OK → 0
- WARNING → 1
- CRITICAL → 2

#### `_get_severity_color(severity) -> str` (private)

Maps severity to rich console color markup (red/yellow/green).

### Benefits

- **Testability**: Format functions can be unit tested independently
- **Reusability**: Formatters can be used by multiple CLI commands
- **Maintainability**: Changes to output format isolated to one module
- **CLI Simplicity**: CLI commands reduced from 60+ lines to ~25 lines

## Data Models Module (`models.py`)

### Purpose

Defines immutable data structures representing ZFS pool state, issues, and check
results. These models serve as the domain model layer, providing type-safe
containers for all ZFS data flowing through the system.

### Design Principles

**Immutability**: All models are frozen dataclasses (`@dataclass(frozen=True)`)
- Prevents accidental state modification
- Enables safe concurrent access in daemon mode
- Makes data flow predictable and testable

**Type Safety**: Comprehensive type hints and enums
- All fields have explicit type annotations
- Enums for fixed vocabularies (health states, severities)
- Union types for optional values (`datetime | None`)

**Single Responsibility**: Models contain only data, no business logic
- Parsing logic lives in `zfs_parser.py`
- Monitoring logic lives in `monitor.py`
- Alerting logic lives in `alerting.py`

### Core Data Structures

#### `PoolHealth` Enum

Represents ZFS pool health states:

```python
class PoolHealth(str, Enum):
    ONLINE = "ONLINE"      # Fully operational
    DEGRADED = "DEGRADED"  # Operational but degraded
    FAULTED = "FAULTED"    # Cannot provide data
    OFFLINE = "OFFLINE"    # Manually offline
    UNAVAIL = "UNAVAIL"    # Insufficient devices
    REMOVED = "REMOVED"    # Removed from system
```

**Methods:**
- `is_healthy() -> bool`: Returns True only for ONLINE
- `is_critical() -> bool`: Returns True for FAULTED, UNAVAIL, REMOVED

**Caching**: Both methods use `@lru_cache(maxsize=6)` for performance
(only 6 enum values possible)

#### `Severity` Enum

Represents issue severity levels with ordering:

```python
class Severity(str, Enum):
    OK = "OK"              # No issues
    WARNING = "WARNING"    # Attention needed
    CRITICAL = "CRITICAL"  # Urgent action required
```

**Methods:**
- `is_critical() -> bool`: Returns True for CRITICAL severity
- `__lt__(other) -> bool`: Enables severity comparison (OK < WARNING < CRITICAL)

**Ordering**: Implements `__lt__` for severity comparison logic used by
`CheckResult.overall_severity` aggregation.

#### `PoolStatus` Dataclass

Complete snapshot of a single ZFS pool:

```python
@dataclass(frozen=True)
class PoolStatus:
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
```

**Properties:**
- `has_errors() -> bool`: Returns True if any error count > 0

**Usage**: Created by `ZFSParser`, consumed by `PoolMonitor` and `EmailAlerter`.

#### `PoolIssue` Dataclass

Represents a detected issue with a pool:

```python
@dataclass(frozen=True)
class PoolIssue:
    pool_name: str
    severity: Severity
    category: str          # 'capacity', 'health', 'errors', 'scrub'
    message: str           # Human-readable description
    details: dict[str, Any]  # Additional context
```

**Methods:**
- `__str__() -> str`: Formats as `[SEVERITY] pool_name: message`

**Category Values:**
- `capacity`: Pool capacity threshold exceeded
- `health`: Pool health degraded/faulted
- `errors`: Read/write/checksum errors detected
- `scrub`: Scrub overdue or errors found

**Usage**: Created by `PoolMonitor.check_pool()`, consumed by `EmailAlerter`
and `AlertStateManager`.

#### `CheckResult` Dataclass

Aggregated result of checking all pools:

```python
@dataclass(frozen=True)
class CheckResult:
    timestamp: datetime
    pools: list[PoolStatus]
    issues: list[PoolIssue]
    overall_severity: Severity
```

**Properties:**
- `has_issues() -> bool`: Returns True if any issues exist
- `critical_issues() -> list[PoolIssue]`: Filters to CRITICAL issues only
- `warning_issues() -> list[PoolIssue]`: Filters to WARNING issues only

**Overall Severity Calculation**: Set to highest severity found among all
issues, defaults to OK if no issues.

**Usage**: Returned by `PoolMonitor.check_all_pools()`, consumed by CLI
commands and daemon monitoring loop.

### Performance Optimizations

**LRU Caching**: `PoolHealth.is_healthy()` and `PoolHealth.is_critical()`
use `@lru_cache(maxsize=6)` since:
- Only 6 possible enum values
- Called frequently during monitoring
- Eliminates repeated enum comparisons

**Frozen Dataclasses**: Immutability enables:
- Safe sharing across threads in daemon mode
- Hashable types for caching
- Predictable behavior in concurrent scenarios

### Serialization

All models are designed for easy serialization:

**JSON Export**: Used by `format_check_result_json()` for CLI output
```python
{
  "timestamp": "2025-11-19T22:00:00Z",
  "pools": [...],
  "issues": [...],
  "overall_severity": "WARNING"
}
```

**State Persistence**: Used by `AlertStateManager` for alert deduplication
state storage.

### Integration Points

**Parsers → Models**: `ZFSParser` creates `PoolStatus` from raw ZFS output
- `parse_pool_list()` → list of `PoolStatus`
- `parse_pool_status()` → dict of `PoolStatus`
- `merge_pool_data()` → combined `PoolStatus`

**Models → Monitor**: `PoolMonitor` consumes `PoolStatus`, produces `CheckResult`
- `check_pool(PoolStatus)` → list of `PoolIssue`
- `check_all_pools(dict[str, PoolStatus])` → `CheckResult`

**Models → Alerting**: `EmailAlerter` consumes `PoolIssue` and `PoolStatus`
- `send_alert(issue, pool)` → formats email from issue + pool data
- `send_recovery(pool_name, category, pool)` → recovery notification

**Models → State**: `AlertStateManager` tracks `PoolIssue` for deduplication
- `should_alert(issue)` → checks if issue should trigger alert
- `record_alert(issue)` → records alert sent timestamp

### Testing Recommendations

**Unit Tests:**
- Enum method behavior (`is_healthy()`, `is_critical()`)
- Property calculations (`has_errors()`, `critical_issues()`)
- String formatting (`PoolIssue.__str__()`)
- Severity ordering (`Severity.__lt__()`)

**Integration Tests:**
- Round-trip serialization (model → JSON → model)
- Parser output validation (ensure all fields populated)
- State persistence (AlertStateManager with real PoolIssue)

**Fixtures:**
Create factory functions for common test scenarios:
```python
def create_healthy_pool(name="tank") -> PoolStatus:
    """Factory for healthy pool test data."""
    return PoolStatus(
        name=name,
        health=PoolHealth.ONLINE,
        capacity_percent=45.0,
        # ... other fields
    )
```

## Code Quality Standards

### Type Hints

All methods include complete type hints:
- Parameter types
- Return types
- Union types where applicable (`int | None`)

### Documentation

Methods include structured docstrings:
- Purpose statement (Why)
- Implementation details (What)
- Parameter descriptions
- Return value descriptions

### Testing Recommendations

1. **Snapshot tests** for email formatting to catch spacing regressions
2. **Unit tests** for helper methods (scrub age, capacity calculations)
3. **Integration tests** for complete alert flow

### Performance Considerations

1. **Pre-compiled regex** for size parsing (daemon mode optimization)
2. **LRU cache** on size parsing method (existing optimization)
3. **Single join operation** for string formatting (memory efficiency)

## Future Enhancements

Potential improvements to consider:
1. Pass timestamp as parameter to eliminate multiple `datetime.now()` calls
2. Add examples in docstrings showing expected output
3. Implement snapshot/golden file tests for email formatting
