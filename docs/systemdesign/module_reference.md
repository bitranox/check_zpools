# ZFS Monitoring System - Module Reference

## Status

Production Ready (v2.4.0) - Last Updated: 2025-11-24

## Links & References

**Feature Requirements:** ZFS pool health monitoring and alerting
**Repository:** https://github.com/bitranox/check_zpools
**PyPI Package:** https://pypi.org/project/check-zpools/
**Related Files:**

* Core: zfs_client.py, zfs_parser.py, monitor.py, alerting.py, daemon.py
* Models: models.py
* Config: config.py, config_deploy.py, config_show.py
* CLI: cli.py, __main__.py, cli_errors.py
* Utilities: formatters.py, mail.py, alert_state.py, logging_setup.py, service_install.py

---

## Problem Statement

ZFS administrators need proactive monitoring of pool health, capacity, scrub status, and hardware errors. Manual checking is error-prone and reactive. The system must:

1. Monitor multiple pools continuously or on-demand
2. Alert on capacity thresholds, health degradation, and scrub age
3. Support daemon mode for background monitoring
4. Deduplicate alerts to avoid notification fatigue
5. Provide flexible output formats (text, JSON, HTML)
6. Support email notifications via multiple backends (SMTP, sendmail)
7. Maintain state across daemon restarts

---

## Solution Overview

A layered architecture implementing ZFS pool monitoring with:

* **CLI Layer:** Rich-click commands for all user interactions
* **Behaviors Layer:** High-level orchestration (daemon, check, watch)
* **Domain Layer:** Core monitoring logic (threshold checks, health states)
* **Integration Layer:** ZFS command execution and JSON parsing
* **Infrastructure Layer:** Email, state persistence, logging, formatting

Key design decisions:
* Frozen dataclasses for immutable data structures
* LRU caching for performance-critical enum comparisons
* JSON parsing with robust error handling
* Configurable alert deduplication
* Systemd service integration

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                         CLI Layer                        │
│                  (cli.py, __main__.py)                   │
│  Commands: check, daemon, watch, alert, config           │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│                    Behaviors Layer                       │
│                    (behaviors.py)                        │
│  • run_daemon()     • check_pools_once()                │
│  • check_alerts()   • run_watch()                       │
└────────────────────┬────────────────────────────────────┘
                     │
         ┌───────────┼───────────┬───────────────┐
         │           │           │               │
         ▼           ▼           ▼               ▼
┌─────────────┐ ┌──────────┐ ┌────────────┐ ┌──────────┐
│   Daemon    │ │ Monitor  │ │ Alerting   │ │ Config   │
│ (daemon.py) │ │(monitor) │ │(alerting)  │ │ (config) │
└─────────────┘ └──────────┘ └────────────┘ └──────────┘
         │           │           │               │
         │           ▼           ▼               │
         │     ┌──────────┐ ┌──────────┐        │
         │     │ZFS Parser│ │   Mail   │        │
         │     │(parser)  │ │  (mail)  │        │
         │     └──────────┘ └──────────┘        │
         │           │                           │
         ▼           ▼                           ▼
    ┌──────────┐ ┌──────────┐           ┌──────────────┐
    │  State   │ │  Models  │           │ Formatters   │
    │(alert_   │ │(models)  │           │(formatters)  │
    │ state)   │ │          │           │              │
    └──────────┘ └──────────┘           └──────────────┘
         │           │
         └───────────┴─────────────┐
                                   ▼
                            ┌──────────────┐
                            │  ZFS Client  │
                            │(zfs_client)  │
                            └──────────────┘
                                   │
                                   ▼
                            ┌──────────────┐
                            │ ZFS Commands │
                            │ (zpool list) │
                            │(zpool status)│
                            └──────────────┘
```

---

## Core Modules

### zfs_client.py

**Purpose:** Interface to ZFS command-line tools

**Responsibilities:**
- Execute `zpool list` and `zpool status` commands with JSON output
- Handle ZFS-specific errors and command not found scenarios
- Provide type-safe wrappers around subprocess execution
- Parse command-line options for pool names and flags

**Key Functions:**
- `get_all_pools_status()` - Fetch all pool statuses using `zpool list -j`
- `get_pool_status()` - Get single pool status using `zpool status -j`
- `run_zpool_command()` - Low-level command execution with error handling

**Dependencies:** subprocess, typing, pathlib
**Tests:** test_zfs_client.py (25% coverage - requires actual ZFS system)
**Design Pattern:** Facade pattern wrapping system commands

---

### zfs_parser.py

**Purpose:** Parse ZFS JSON output into typed models

**Responsibilities:**
- Parse `zpool list -j` output into PoolStatus objects
- Parse `zpool status -j` output for detailed vdev information
- Convert size strings (1.5T, 500G) to bytes with LRU caching
- Parse health states into PoolHealth enum with LRU caching
- Extract error counts from vdev trees
- Parse scrub timestamps and states

**Key Functions:**
- `parse_pool_list()` - Parse `zpool list -j` JSON into PoolStatus list
- `parse_pool_status()` - Parse `zpool status -j` JSON into PoolStatus
- `_parse_size()` - Convert size string to bytes (LRU cached, 128 entries)
- `_parse_health()` - Convert health string to enum (LRU cached, 8 entries)
- `_extract_error_counts_from_vdev_tree()` - Recursively parse vdev errors

**Dependencies:** models, typing, functools, json, re, datetime
**Tests:** test_zfs_parser.py (97% coverage)
**Design Patterns:**
- Factory pattern for model construction
- LRU caching for performance (16-28x speedup measured)
- Recursive tree traversal for vdev parsing

**Performance Optimizations:**
- `_parse_size()`: Called 1000s of times → cached (maxsize=128)
- `_parse_health()`: Called per pool check → cached (maxsize=8)
- Size regex compiled once at module load

---

### monitor.py

**Purpose:** Pool health monitoring and threshold checking

**Responsibilities:**
- Check pool capacity against thresholds (warning, critical)
- Check pool health states (ONLINE, DEGRADED, FAULTED)
- Check scrub age and status
- Check vdev read/write/checksum errors
- Generate CheckResult objects with severity levels
- Aggregate multiple check results

**Key Functions:**
- `check_pool()` - Run all checks on a single pool
- `check_capacity()` - Threshold-based capacity check
- `check_health()` - Health state validation
- `check_scrub_age()` - Scrub recency check
- `check_errors()` - Vdev error threshold check

**Dependencies:** models, zfs_parser, config
**Tests:** test_monitor.py (100% coverage, 41 tests)
**Design Patterns:**
- Strategy pattern for different check types
- Builder pattern for CheckResult creation
- Aggregation pattern for combining results

**Severity Mapping:**
- OK: Pool healthy, under thresholds
- WARNING: Approaching limits (80-90% capacity)
- CRITICAL: Over limits (>90% capacity, DEGRADED health)
- ERROR: FAULTED health, vdev errors

---

### alerting.py

**Purpose:** Alert generation and notification

**Responsibilities:**
- Format alert messages (plain text, HTML, JSON)
- Send email notifications via SMTP or sendmail
- Integrate with alert state tracking for deduplication
- Support multiple recipients and custom subjects
- Handle email configuration from environment/config

**Key Functions:**
- `send_alert()` - High-level alert sending with state tracking
- `format_alert_text()` - Plain text alert formatting
- `format_alert_html()` - HTML email alert formatting
- `should_send_alert()` - Check if alert should be sent (deduplication)
- `send_email_alert()` - Low-level email sending

**Dependencies:** models, mail, alert_state, config, formatters
**Tests:** test_alerting.py (91% coverage, 31 tests across 11 focused test classes)
**Design Patterns:**
- Template method for alert formatting
- Adapter pattern for email backends
- State pattern for alert deduplication

**Email Backends:**
1. SMTP (default): Direct SMTP connection
2. Sendmail: Shell out to sendmail binary
3. Mock: Testing backend (no actual send)

---

### daemon.py

**Purpose:** Background monitoring service

**Responsibilities:**
- Periodic pool checking at configurable intervals
- Signal handling (SIGTERM, SIGINT) for graceful shutdown
- State persistence between runs (alert history)
- Alert deduplication across daemon restarts
- Thread-safe stop mechanism
- Log rotation integration

**Key Functions:**
- `run_daemon()` - Main daemon loop
- `check_once()` - Single check iteration
- `signal_handler()` - Handle shutdown signals
- `load_state()` - Restore alert state from disk
- `save_state()` - Persist alert state to disk

**Dependencies:** behaviors, alert_state, config, logging, signal, threading, time
**Tests:** test_daemon.py (100% coverage, 31 tests across 15 focused test classes)
**Design Patterns:**
- Event loop pattern for periodic checking
- Observer pattern for signal handling
- Memento pattern for state persistence

**Systemd Integration:**
- Type=simple service
- KillMode=mixed for graceful shutdown
- Restart=on-failure with backoff
- State file: /var/lib/check-zpools/alert_state.json

---

### models.py

**Purpose:** Type-safe data structures

**Responsibilities:**
- Define PoolStatus frozen dataclass (immutable pool state)
- Define CheckResult frozen dataclass (immutable check outcome)
- Define PoolHealth enum vocabulary (ONLINE, DEGRADED, etc.)
- Define Severity enum vocabulary (OK, WARNING, CRITICAL, ERROR)
- Provide LRU-cached enum comparison methods

**Key Data Structures:**

```python
@dataclass(frozen=True)
class PoolStatus:
    name: str
    health: PoolHealth
    size: int                    # bytes
    allocated: int               # bytes
    free: int                    # bytes
    capacity: int                # 0-100
    fragmentation: int           # 0-100
    # ... additional fields

@dataclass(frozen=True)
class CheckResult:
    severity: Severity
    message: str
    details: dict[str, Any]
    timestamp: str | None = None
```

**Enum Methods (LRU Cached):**
- `PoolHealth.is_healthy()` - Check if ONLINE
- `PoolHealth.is_degraded_or_worse()` - Check if degraded/faulted
- `Severity.is_error()` - Check if ERROR level
- `Severity.max()` - Find worst severity in list

**Dependencies:** dataclasses, enum, functools, typing
**Tests:** test_models.py (85% coverage)
**Design Patterns:**
- Value Object pattern (frozen dataclasses)
- Enum pattern for type-safe vocabularies
- Memoization pattern (LRU cache)

**Rationale for Frozen:**
- Thread-safe by default
- Hashable (can use as dict keys)
- Prevents accidental mutation
- Signals intent: "this is data, not behavior"

**Performance:**
- Enum methods called 1000s of times per monitoring cycle
- LRU cache provides 16-28x speedup (profiling data)
- Cache size matches enum cardinality

---

### behaviors.py

**Purpose:** High-level behavior orchestration

**Responsibilities:**
- Orchestrate daemon mode (periodic checks + state management)
- Orchestrate single-shot checks (check once, optional email)
- Orchestrate watch mode (continuous display updates)
- Orchestrate alert checks (manual alert sending)
- Provide re-usable behavior primitives for CLI

**Key Functions:**
- `run_daemon()` - Daemon behavior (108 lines, CC=12)
- `check_pools_once()` - Single check behavior
- `run_watch()` - Live monitoring behavior
- `check_alerts()` - Manual alert trigger

**Dependencies:** daemon, monitor, alerting, config, formatters, time
**Tests:** test_behaviors.py (96% coverage, 40 tests across focused test classes)
**Design Patterns:**
- Facade pattern for CLI simplification
- Command pattern for behavior encapsulation

---

### cli.py

**Purpose:** Command-line interface implementation

**Responsibilities:**
- Define all CLI commands (check, daemon, watch, alert, etc.)
- Parse command-line arguments with rich-click
- Apply configuration from files and environment
- Delegate to behaviors layer for execution
- Handle CLI errors and exit codes

**Commands:**
- `check` - Check pools once
- `daemon` - Run background service
- `watch` - Live monitoring display
- `alert` - Send test alerts
- `config` - Configuration management
- `service` - Systemd service installation (Linux only)

**Dependencies:** behaviors, config, formatters, rich_click, typer
**Tests:** test_cli_commands_integration.py (24 tests across 6 focused test classes following clean architecture)
**Design Pattern:** Command pattern with rich-click decorators

---

### Utility Modules

**formatters.py** (99% coverage):
- Format pool status as text tables
- Format check results with color coding
- Format scrub age in human-readable format
- Format size with units (TB, GB, MB)

**mail.py** (100% coverage):
- Send email via SMTP or sendmail
- Support TLS, authentication
- Handle connection errors gracefully
- Validate email addresses

**alert_state.py** (97% coverage):
- Track sent alerts with timestamps and severity changes
- Implement deduplication logic with resend intervals
- Detect severity changes for immediate alerts
- Persist state to JSON file with Pydantic validation
- Load state on daemon start with error recovery

**logging_setup.py** (100% coverage):
- Configure rich logging with colors
- Set log levels from config
- Support multiple log backends (journald, file, console)

**config.py** (100% coverage):
- Load configuration from TOML files
- Merge config from multiple sources
- Apply environment variable overrides
- Validate configuration schema

**config_deploy.py** (100% coverage):
- Deploy default configuration to system
- Handle permissions and paths

**config_show.py** (97% coverage):
- Display current configuration
- Show effective settings after merges

**cli_errors.py** (100% coverage):
- Custom exception types for CLI
- Error message formatting

**service_install.py** (10% coverage - requires systemd):
- Install systemd service unit
- Configure service user and permissions
- Handle platform differences

---

## Implementation Details

**Dependencies:**

**External:**
- rich-click: Enhanced CLI with colors and help
- lib-log-rich: Structured logging with rich formatting
- pydantic: Configuration validation (optional)

**Internal:**
- All modules depend on models.py for type safety
- Parser → Client → Models (data flow)
- Monitor → Parser → Models (check flow)
- Daemon → Behaviors → Monitor → Alerting (orchestration flow)

**Key Configuration (defaultconfig.toml):**

```toml
[monitor]
capacity_warning_threshold = 80   # percent
capacity_critical_threshold = 90  # percent
scrub_age_days_threshold = 30     # days

[alerting]
enabled = true
deduplication_window_hours = 24   # hours

[email]
smtp_hosts = "localhost:25"
from_address = "zfs@localhost"
```

**Environment Variables:**
- `CHECK_ZPOOLS_CONFIG` - Config file path
- `CHECK_ZPOOLS_EMAIL_*` - Email settings override
- `CHECK_ZPOOLS_LOG_LEVEL` - Logging level

**Error Handling Strategy:**
- ZFS commands: Graceful degradation with error messages
- Email failures: Log error, continue monitoring
- Config errors: Fail fast with clear messages
- JSON parsing: Validate and provide helpful errors

---

## Testing Approach

**Manual Testing Steps:**

1. `check-zpools check` → Shows all pool statuses
2. `check-zpools check --email user@example.com` → Sends email report
3. `check-zpools daemon` → Runs background monitoring
4. `check-zpools watch` → Live pool status display
5. `check-zpools config show` → Display configuration

**Automated Tests:**

**Unit Tests:**
- test_models.py: Frozen dataclasses, enum methods, serialization
- test_zfs_parser.py: JSON parsing, size conversion, health parsing
- test_monitor.py: Threshold checks, health validation, scrub checks
- test_alerting.py: Alert formatting, deduplication, email integration
- test_formatters.py: Output formatting, color codes, size display

**Integration Tests:**
- test_behaviors.py: Behavior orchestration, state management
- test_daemon.py: Daemon lifecycle, signal handling
- test_cli.py: CLI command execution, argument parsing

**Mock Strategies:**
- Mock ZFS commands with JSON fixtures
- Mock SMTP with fake server
- Mock file system for state persistence
- Monkeypatch environment variables

**Coverage Requirements:**
- Local minimum: 60% (enforced by `make test`)
- CI target: 70% (Codecov PR checks)
- Current: 77% (exceeds both thresholds)
- Test count: 519 passing tests

**Test Data:**
- Shared fixtures in conftest.py:
  - `healthy_pool_status` - Standard healthy pool for happy-path tests
  - `ok_check_result` - Successful check result fixture
  - `configurable_pool_status` - Factory pattern fixture for customizable pools
- JSON fixtures for zpool output
- Sample configuration files

**Test Architecture (v2.4.0):**
All major test files have been refactored following clean architecture principles:
- Test names read like plain English sentences
- Each test validates ONE specific behavior
- Given-When-Then docstrings throughout
- Tests organized into focused classes by behavior domain
- Real behavior testing over excessive mocking
- Comprehensive coverage of edge cases and error paths

---

## Known Issues & Future Improvements

**Current Limitations:**
- ZFS client requires actual ZFS installation (25% coverage)
- Service installation requires systemd (10% coverage)
- No Windows support (Linux/macOS only)
- Email retry logic is basic

**Future Enhancements:**
See README.md for comprehensive roadmap (35+ features across 6 categories):
- Monitoring: Remote SSH, device-level health, SMART integration, I/O stats
- Alerting: Multiple channels (Slack, Discord, Teams, PagerDuty), escalation, quiet hours
- Reporting: TUI dashboard, historical trending, capacity prediction, Prometheus/Grafana
- Daemon: Adaptive intervals, self-healing actions, pool-specific configs
- CLI: Historical query, pool comparison, threshold testing, dry-run mode
- Security: Audit logging, read-only mode, encrypted state, role-based access

---

## Risks & Considerations

**Technical Risks:**
- ZFS JSON format changes (mitigated by parser abstraction)
- Email delivery failures (logged, not fatal)
- State file corruption (validated on load)
- Daemon stop during check (graceful shutdown)

**Performance Considerations:**
- LRU caching reduces CPU by 16-28x
- Frozen dataclasses are thread-safe
- JSON parsing is I/O bound (ZFS command execution)
- Daemon check interval: 300s default (configurable)

**User Impact:**
- Requires ZFS installation
- Email requires SMTP or sendmail
- Daemon requires systemd (or manual process management)
- Configuration changes require daemon restart

---

## Documentation & Resources

**Internal References:**
- README.md - Usage examples, quick start, and comprehensive feature roadmap
- INSTALL.md - Installation instructions
- DEVELOPMENT.md - Developer workflow and testing
- CONTRIBUTING.md - Contribution guidelines
- CHANGELOG.md - Version history and detailed change documentation
- docs/TEST_REFACTORING_GUIDE.md - Clean architecture test patterns and examples

**External References:**
- OpenZFS Documentation: https://openzfs.github.io/openzfs-docs/
- ZFS JSON Output Format: `man zpool` (JSON OUTPUT section)
- Systemd Service Units: https://www.freedesktop.org/software/systemd/man/systemd.service.html

---

**Created:** 2025-11-19 by Claude Code (comprehensive update)
**Last Updated:** 2025-11-24 by Claude Code (v2.4.0 test refactoring and coverage improvements)
**Review Cycle:** Update when new modules added or architecture changes

---

## Instructions for Use

1. **Update this document** whenever new modules are added
2. **Keep module descriptions in sync** with actual code during refactors
3. **Document design decisions** for future maintainers
4. **Update coverage percentages** after significant test improvements
5. **Add new sections** for new architectural layers or patterns
