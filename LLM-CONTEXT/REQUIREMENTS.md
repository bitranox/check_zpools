# check_zpools - Requirements Specification

## Overview

`check_zpools` is a ZFS pool monitoring daemon and CLI tool that monitors pool health, capacity, errors, and scrub status, sending email alerts when issues are detected.

## Use Cases

### Primary: Continuous Monitoring Daemon
- Run as a systemd service or background process
- Periodically check all ZFS pools on the system
- Send email alerts when problems are detected
- Log status to journald/syslog/Graylog for centralized monitoring
- Suppress repeated alerts for the same ongoing issue

### Secondary: One-Shot CLI Check
- Manually check pool status and display results
- Useful for testing configuration and troubleshooting
- Rich console output showing pool health

## ZFS Properties to Monitor

### 1. Health Status (CRITICAL)
- **States**: ONLINE, DEGRADED, FAULTED, UNAVAIL, REMOVED, OFFLINE
- **Alert Conditions**:
  - CRITICAL: FAULTED, UNAVAIL, REMOVED
  - WARNING: DEGRADED, OFFLINE
  - OK: ONLINE

### 2. Capacity Usage (WARNING/CRITICAL)
- **Metrics**: Used space percentage
- **Alert Thresholds** (configurable):
  - WARNING: Default 80%
  - CRITICAL: Default 90%
- **Note**: ZFS performance degrades significantly above 80% capacity

### 3. Read/Write/Checksum Errors (WARNING)
- **Metrics**: Error counts from `zpool status`
- **Alert Conditions**:
  - WARNING: Any non-zero error count
  - Include error details (which vdev, count)

### 4. Scrub Status (INFO/WARNING)
- **Metrics**:
  - Last scrub timestamp
  - Scrub errors found
  - Scrub in progress
- **Alert Conditions**:
  - WARNING: Scrub errors found > 0
  - INFO: No scrub in last 30 days (configurable)
  - INFO: Scrub in progress

## ZFS Command Interface

### Command Execution
- Execute `zpool list -j -o name,health,size,allocated,free,capacity` for capacity data
- Execute `zpool status -j` for detailed health, errors, and scrub status
- Parse JSON output (ZFS native JSON format, introduced in OpenZFS 2.2+)
- Handle command failures gracefully (log errors, don't crash)

### Error Handling
- Check if `zpool` command exists
- Handle pools with no errors vs. pools with issues
- Gracefully handle permission errors (requires root or delegation)

## Configuration Schema

### Monitoring Thresholds
```toml
[check_zpools]
# Capacity thresholds (percentage)
capacity_warning_percent = 80
capacity_critical_percent = 90

# Scrub age warning (days)
scrub_max_age_days = 30

# Error thresholds
read_errors_warning = 1
write_errors_warning = 1
checksum_errors_warning = 1
```

### Daemon Configuration
```toml
[check_zpools.daemon]
# Check interval (seconds)
check_interval_seconds = 300  # 5 minutes

# Alert suppression
alert_resend_interval_hours = 24  # Re-alert after 24 hours if issue persists

# Pools to monitor (empty = all pools)
pools_to_monitor = []  # Example: ["rpool", "zpool-data"]
```

### Email Configuration
```toml
[email]
# Email recipients for alerts
alert_recipients = ["admin@example.com"]

# Email subject prefix
subject_prefix = "[ZFS Alert]"

# Send email for these severities
alert_on_severities = ["CRITICAL", "WARNING"]  # Options: CRITICAL, WARNING, INFO
```

## Daemon Behavior

### Startup
1. Load configuration from layered sources
2. Validate ZFS commands available
3. Perform initial pool check
4. Enter monitoring loop

### Monitoring Loop
1. Execute ZFS commands and parse output
2. Check each pool against thresholds
3. Determine alert severity (OK, INFO, WARNING, CRITICAL)
4. Check alert suppression state
5. Send emails if needed (and not suppressed)
6. Log results to structured logging
7. Sleep until next check interval

### Alert Suppression/Deduplication
- **State File**: `~/.cache/check_zpools/alert_state.json`
- **Behavior**:
  - First alert: Send immediately, record timestamp
  - Subsequent alerts: Only send if `alert_resend_interval_hours` has passed
  - When issue resolves: Send "RESOLVED" email, clear suppression state
  - Track suppression per pool+issue combination

### Graceful Shutdown
- Handle SIGTERM/SIGINT
- Complete current check cycle
- Clean up resources
- Log shutdown

## CLI Commands

### `check_zpools check`
- Perform one-shot check of all pools
- Display rich formatted output to console
- Exit with appropriate code:
  - 0: All pools OK
  - 1: Warnings detected
  - 2: Critical issues detected

### `check_zpools daemon`
- Start daemon mode
- Options:
  - `--foreground`: Don't daemonize, run in foreground
  - `--check-interval SECONDS`: Override config check interval
  - `--no-email`: Disable email alerts (logging only)

### `check_zpools show-status`
- Display current pool status in various formats
- Options:
  - `--format json|table|text`: Output format
  - `--pool NAME`: Show specific pool only

### Existing Commands (from template)
- `check_zpools info`: Show package metadata
- `check_zpools config`: Show merged configuration
- `check_zpools config-deploy`: Deploy config files

## Data Models

### PoolHealth (Enum)
```python
class PoolHealth(str, Enum):
    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    FAULTED = "FAULTED"
    OFFLINE = "OFFLINE"
    UNAVAIL = "UNAVAIL"
    REMOVED = "REMOVED"
```

### PoolStatus
```python
@dataclass
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

### CheckResult
```python
@dataclass
class CheckResult:
    timestamp: datetime
    pools: list[PoolStatus]
    issues: list[PoolIssue]
    overall_severity: Severity
```

### PoolIssue
```python
@dataclass
class PoolIssue:
    pool_name: str
    severity: Severity  # INFO, WARNING, CRITICAL
    category: str  # "health", "capacity", "errors", "scrub"
    message: str
    details: dict[str, Any]
```

## Email Alert Format

### Subject Line
```
[ZFS Alert] CRITICAL: Pool 'rpool' on host <hostname> is DEGRADED
[ZFS Alert] WARNING: Pool 'zpool-data' on host <hostname> at 85% capacity
[ZFS Alert] RESOLVED: Pool 'rpool' on host <hostname> is now ONLINE
```

### Body (Plain Text)
```
ZFS Pool Alert - CRITICAL

Host: <hostname>
Pool: rpool
Status: DEGRADED
Timestamp: 2025-11-16 14:30:45 UTC

Issues:
  • Health: Pool is DEGRADED (expected: ONLINE)
  • Capacity: 45% used (12.5 TB / 27.3 TB)
  • Errors: 0 read, 0 write, 0 checksum
  • Last Scrub: 2025-11-10 (6 days ago, 0 errors)

Action Required:
  Run 'zpool status rpool' to investigate degraded state.

---
Generated by check_zpools v0.0.1
```

### Body (HTML - Optional Enhancement)
- Rich formatting with color-coded severity
- Table showing all pools
- Highlighted issues

## Logging Strategy

### Structured Logging (via lib_log_rich)
- **Console**: Rich formatted output with colors
- **Journald**: Structured fields for systemd journal
- **Graylog**: GELF format with custom fields

### Log Levels
- **DEBUG**: Detailed command output, parsing steps
- **INFO**: Check cycle started/completed, pool status OK
- **WARNING**: Pool issues detected, emails sent
- **ERROR**: Command failures, configuration errors
- **CRITICAL**: Fatal errors preventing monitoring

### Structured Fields
```python
logger.info(
    "Pool check completed",
    extra={
        "pool_name": "rpool",
        "health": "ONLINE",
        "capacity_percent": 45.2,
        "issues_found": 0,
        "check_duration_ms": 123,
    }
)
```

## Testing Strategy

### Unit Tests
- ZFS JSON parsing (use sample data from `tests/`)
- Threshold checking logic
- Alert suppression state machine
- Email formatting

### Integration Tests
- Mock `zpool` commands with sample output
- Test full check cycle with various pool states
- Verify email sending with test SMTP server

### Test Data
- `tests/zpool_list_ok_sample.json`: All pools healthy
- `tests/zpool_list_degraded_sample.json`: Pool degraded (to create)
- `tests/zpool_status_errors_sample.json`: Pools with errors (to create)
- `tests/zpool_status_scrub_sample.json`: Scrub in progress (to create)

## Dependencies

### Runtime
- Python 3.13+
- OpenZFS with JSON output support (OpenZFS 2.2+)
- Existing template dependencies (rich-click, lib_log_rich, etc.)

### System
- `zpool` command available in PATH
- Appropriate permissions (root or ZFS delegation)

## Security Considerations

- Run as dedicated user with minimal ZFS read permissions
- Sanitize all command output before logging
- Protect alert state file (may contain pool names)
- Email credentials stored securely (environment variables or protected config)

## Future Enhancements (Out of Scope for v0.1.0)

- Web dashboard for status visualization
- Metrics export (Prometheus format)
- Support for remote ZFS pools (SSH)
- Integration with monitoring systems (Nagios, Zabbix)
- Snapshot monitoring and management
- Dataset-level monitoring (in addition to pools)
