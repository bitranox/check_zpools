# check_zpools - Implementation Plan

## Project Overview

Transform the template CLI application into a production-ready ZFS pool monitoring daemon with the following capabilities:

- **Continuous Monitoring**: Daemon mode with configurable check intervals
- **Multi-Property Monitoring**: Health status, capacity, errors, scrub status
- **Smart Alerting**: Email notifications with deduplication/suppression
- **Rich Logging**: Console, journald, and Graylog integration
- **Flexible Configuration**: Layered config with environment variable overrides

## Implementation Status

### ✅ Completed
1. **Requirements Documentation** (`REQUIREMENTS.md`)
   - Comprehensive use cases and functional requirements
   - Data model definitions
   - Email alert format specifications
   - Testing strategy

2. **Configuration Schema** (`defaultconfig.toml`)
   - ZFS monitoring thresholds (capacity, errors, scrub age)
   - Daemon configuration (interval, alert suppression)
   - Alert configuration (recipients, severities)
   - Full documentation with examples

### 🔨 In Progress
None currently

### 📋 Planned Implementation Phases

## Phase 1: Foundation & Cleanup (Priority: HIGH)

### Task 1.1: Commit Current Changes
**Files**: `.env.example`, `AGENTS.md`, `pyproject.toml`, `tests/test_scripts.py`
**Status**: Unstaged changes exist
**Action**:
```bash
git add .env.example AGENTS.md pyproject.toml tests/test_scripts.py
git commit -m "fix: correct module paths and remove duplicate CLI entry point"
```

### Task 1.2: Run Quality Checks
**Command**: `make test`
**Purpose**: Ensure baseline code quality before implementation
**Expected**: All tests pass, no lint errors, type checks succeed

## Phase 2: Core Data Models (Priority: HIGH)

### Task 2.1: Create ZFS Data Models
**File**: `src/check_zpools/models.py` (new)
**Components**:
```python
# Enumerations
class PoolHealth(str, Enum)
class Severity(str, Enum)

# Data Classes
@dataclass
class PoolStatus:
    """Represents the status of a single ZFS pool"""
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

@dataclass
class PoolIssue:
    """Represents a detected issue with a pool"""
    pool_name: str
    severity: Severity
    category: str  # "health", "capacity", "errors", "scrub"
    message: str
    details: dict[str, Any]

@dataclass
class CheckResult:
    """Aggregated result of checking all pools"""
    timestamp: datetime
    pools: list[PoolStatus]
    issues: list[PoolIssue]
    overall_severity: Severity
```

**Architecture Notes**:
- Keep models simple and immutable
- Use `@dataclass` for automatic `__init__`, `__repr__`
- Type hints for all fields (PEP 484)
- No business logic in models (pure data)

### Task 2.2: Add Model Tests
**File**: `tests/test_models.py` (new)
**Coverage**:
- Enum validation
- Dataclass instantiation
- JSON serialization/deserialization (if needed)
- Edge cases (None values, extreme numbers)

## Phase 3: ZFS Command Interface (Priority: HIGH)

### Task 3.1: Implement ZFS Command Execution
**File**: `src/check_zpools/zfs_client.py` (new)
**Components**:
```python
class ZFSClient:
    """Execute ZFS commands and parse JSON output"""

    def get_pool_list(self) -> dict[str, Any]:
        """Execute 'zpool list -j' and return parsed JSON"""

    def get_pool_status(self, pool_name: str | None = None) -> dict[str, Any]:
        """Execute 'zpool status -j' and return parsed JSON"""

    def check_zpool_available(self) -> bool:
        """Verify zpool command is available"""
```

**Implementation Details**:
- Use `subprocess.run()` with timeout
- Capture both stdout and stderr
- Handle `FileNotFoundError` (zpool not found)
- Handle `subprocess.TimeoutExpired`
- Handle non-zero exit codes
- Validate JSON parsing

**Error Handling**:
- Log all command executions (DEBUG level)
- Raise custom exceptions: `ZFSCommandError`, `ZFSNotAvailableError`
- Include stderr output in exceptions

### Task 3.2: Implement JSON Parsing
**File**: `src/check_zpools/zfs_parser.py` (new)
**Components**:
```python
class ZFSParser:
    """Parse ZFS JSON output into PoolStatus objects"""

    def parse_pool_list(self, json_data: dict) -> dict[str, PoolStatus]:
        """Parse 'zpool list -j' output"""

    def parse_pool_status(self, json_data: dict) -> dict[str, PoolStatus]:
        """Parse 'zpool status -j' output"""

    def merge_pool_data(
        self,
        list_data: dict[str, PoolStatus],
        status_data: dict[str, PoolStatus]
    ) -> dict[str, PoolStatus]:
        """Merge data from list and status commands"""
```

**Architecture Notes**:
- Separate command execution from parsing (SRP)
- Parser is pure function (testable without ZFS)
- Handle missing fields gracefully
- Use sample JSON files for tests

### Task 3.3: Add ZFS Client Tests
**Files**:
- `tests/test_zfs_client.py` (new)
- `tests/test_zfs_parser.py` (new)

**Test Data**:
- `tests/zpool_list_ok_sample.json` (exists)
- `tests/zpool_list_degraded_sample.json` (create)
- `tests/zpool_status_with_errors.json` (create)
- `tests/zpool_status_scrub_in_progress.json` (create)

**Coverage**:
- Mock subprocess calls (no actual ZFS commands in tests)
- Test all health states (ONLINE, DEGRADED, FAULTED, etc.)
- Test error conditions (command not found, timeout, parse errors)
- Test parser with real sample data

## Phase 4: Monitoring Logic (Priority: HIGH)

### Task 4.1: Implement Threshold Checker
**File**: `src/check_zpools/monitor.py` (new)
**Components**:
```python
@dataclass
class MonitorConfig:
    """Configuration for monitoring thresholds"""
    capacity_warning_percent: int
    capacity_critical_percent: int
    scrub_max_age_days: int
    read_errors_warning: int
    write_errors_warning: int
    checksum_errors_warning: int

class PoolMonitor:
    """Check pools against configured thresholds"""

    def __init__(self, config: MonitorConfig):
        self.config = config

    def check_pool(self, pool: PoolStatus) -> list[PoolIssue]:
        """Check single pool and return list of issues"""

    def check_all_pools(self, pools: dict[str, PoolStatus]) -> CheckResult:
        """Check all pools and return aggregated result"""

    def _check_health(self, pool: PoolStatus) -> PoolIssue | None:
        """Check pool health status"""

    def _check_capacity(self, pool: PoolStatus) -> PoolIssue | None:
        """Check pool capacity against thresholds"""

    def _check_errors(self, pool: PoolStatus) -> list[PoolIssue]:
        """Check for read/write/checksum errors"""

    def _check_scrub(self, pool: PoolStatus) -> PoolIssue | None:
        """Check scrub status and age"""
```

**Architecture Notes**:
- Keep threshold checking logic separate from data collection
- Each check method returns issues or None
- Severity determination is centralized
- Configuration injected via constructor (testable)

### Task 4.2: Add Monitor Tests
**File**: `tests/test_monitor.py` (new)
**Coverage**:
- Test each threshold independently
- Test boundary conditions (79%, 80%, 81% capacity)
- Test combinations (multiple issues on one pool)
- Test severity aggregation (CRITICAL > WARNING > INFO > OK)

## Phase 5: Alert Management (Priority: MEDIUM)

### Task 5.1: Implement Alert State Manager
**File**: `src/check_zpools/alert_state.py` (new)
**Components**:
```python
@dataclass
class AlertState:
    """State of alerts for a specific pool+issue"""
    pool_name: str
    issue_category: str
    first_seen: datetime
    last_alerted: datetime | None
    alert_count: int

class AlertStateManager:
    """Manage alert suppression/deduplication"""

    def __init__(self, state_file: Path, resend_interval_hours: int):
        self.state_file = state_file
        self.resend_interval_hours = resend_interval_hours

    def should_alert(self, issue: PoolIssue) -> bool:
        """Determine if alert should be sent for this issue"""

    def record_alert(self, issue: PoolIssue) -> None:
        """Record that alert was sent"""

    def clear_issue(self, pool_name: str, category: str) -> None:
        """Clear state when issue is resolved"""

    def load_state(self) -> dict[str, AlertState]:
        """Load state from JSON file"""

    def save_state(self) -> None:
        """Save state to JSON file"""
```

**State File Format**:
```json
{
  "version": 1,
  "alerts": {
    "rpool:health": {
      "pool_name": "rpool",
      "issue_category": "health",
      "first_seen": "2025-11-16T14:30:00Z",
      "last_alerted": "2025-11-16T14:30:00Z",
      "alert_count": 3
    }
  }
}
```

**Architecture Notes**:
- State persists across restarts
- Thread-safe file operations (file locking if needed)
- Graceful handling of corrupt/missing state file
- Platform-specific cache directory (`~/.cache/check_zpools/` on Linux)

### Task 5.2: Implement Email Alerter
**File**: `src/check_zpools/alerting.py` (new)
**Components**:
```python
class EmailAlerter:
    """Send email alerts for pool issues"""

    def __init__(self, email_config: EmailConfig, alert_config: dict):
        self.email_config = email_config
        self.subject_prefix = alert_config.get("subject_prefix", "[ZFS Alert]")
        self.recipients = alert_config.get("alert_recipients", [])

    def send_alert(self, issue: PoolIssue, pool: PoolStatus) -> None:
        """Send email alert for a specific issue"""

    def send_recovery(self, pool_name: str, category: str) -> None:
        """Send email when issue is resolved"""

    def _format_subject(self, severity: Severity, pool_name: str, message: str) -> str:
        """Format email subject line"""

    def _format_body(self, issue: PoolIssue, pool: PoolStatus) -> str:
        """Format plain-text email body"""
```

**Email Template** (Plain Text):
```
ZFS Pool Alert - {SEVERITY}

Pool: {pool_name}
Status: {health}
Timestamp: {timestamp}

Issues:
{formatted_issues}

Pool Details:
  • Capacity: {used_percent}% used ({used_tb} TB / {total_tb} TB)
  • Errors: {read_errors} read, {write_errors} write, {checksum_errors} checksum
  • Last Scrub: {scrub_date} ({days_ago} days ago, {scrub_errors} errors)

Action Required:
  Run 'zpool status {pool_name}' to investigate.

---
Generated by check_zpools v{version}
Hostname: {hostname}
```

### Task 5.3: Add Alerting Tests
**Files**:
- `tests/test_alert_state.py` (new)
- `tests/test_alerting.py` (new)

**Coverage**:
- Test suppression logic (should_alert)
- Test state persistence (save/load)
- Test email formatting
- Mock SMTP sending (use existing `mail.py` test patterns)

## Phase 6: Daemon Implementation (Priority: HIGH)

### Task 6.1: Implement Daemon Loop
**File**: `src/check_zpools/daemon.py` (new)
**Components**:
```python
class ZPoolDaemon:
    """Main daemon for continuous ZFS monitoring"""

    def __init__(
        self,
        zfs_client: ZFSClient,
        monitor: PoolMonitor,
        alerter: EmailAlerter,
        state_manager: AlertStateManager,
        config: dict,
    ):
        self.zfs_client = zfs_client
        self.monitor = monitor
        self.alerter = alerter
        self.state_manager = state_manager
        self.check_interval = config.get("check_interval_seconds", 300)
        self.pools_to_monitor = config.get("pools_to_monitor", [])
        self.shutdown_event = threading.Event()

    def start(self) -> None:
        """Start daemon monitoring loop"""

    def stop(self) -> None:
        """Gracefully stop daemon"""

    def _run_check_cycle(self) -> None:
        """Execute one check cycle"""

    def _handle_check_result(self, result: CheckResult) -> None:
        """Process check result, send alerts, update state"""

    def _setup_signal_handlers(self) -> None:
        """Setup SIGTERM/SIGINT handlers"""
```

**Daemon Behavior**:
1. Load configuration
2. Initialize all components (client, monitor, alerter, state)
3. Setup signal handlers (SIGTERM, SIGINT)
4. Enter main loop:
   - Execute check cycle
   - Process results
   - Send alerts (if needed)
   - Update state
   - Sleep until next interval
5. On shutdown signal:
   - Complete current check
   - Save state
   - Clean exit

**Architecture Notes**:
- Dependency injection for all components (testable)
- Graceful shutdown (complete current check)
- Structured logging for all operations
- Error recovery (log errors, don't crash)

### Task 6.2: Add Daemon Tests
**File**: `tests/test_daemon.py` (new)
**Coverage**:
- Test check cycle execution
- Test signal handling (mock signals)
- Test error recovery (mock failures)
- Test graceful shutdown

## Phase 7: CLI Integration (Priority: HIGH)

### Task 7.1: Update behaviors.py
**File**: `src/check_zpools/behaviors.py`
**Action**: Replace template functions with ZFS behaviors
**New Functions**:
```python
def check_pools_once(config: dict) -> CheckResult:
    """Perform one-shot check of all pools"""

def run_daemon(config: dict, foreground: bool = False) -> None:
    """Start daemon mode"""

def show_pool_status(config: dict, pool_name: str | None = None) -> None:
    """Display current pool status with rich formatting"""
```

**Migration Strategy**:
- Keep existing template functions initially (backward compatibility)
- Mark as deprecated with docstrings
- Remove in future version

### Task 7.2: Update CLI Commands
**File**: `src/check_zpools/cli.py`
**New Commands**:
```python
@click.command()
@click.option("--format", type=click.Choice(["text", "json", "table"]), default="text")
def check(format: str):
    """Perform one-shot check of all ZFS pools"""

@click.command()
@click.option("--foreground", is_flag=True, help="Run in foreground (don't daemonize)")
@click.option("--check-interval", type=int, help="Override check interval (seconds)")
@click.option("--no-email", is_flag=True, help="Disable email alerts")
def daemon(foreground: bool, check_interval: int | None, no_email: bool):
    """Start daemon mode for continuous monitoring"""

@click.command()
@click.option("--format", type=click.Choice(["text", "json", "table"]), default="table")
@click.option("--pool", help="Show specific pool only")
def show_status(format: str, pool: str | None):
    """Display current ZFS pool status"""
```

**Keep Existing Commands**:
- `info`: Package metadata
- `config`: Show configuration
- `config-deploy`: Deploy config files

**Update Help**:
- Update main CLI description
- Add usage examples
- Document exit codes (0=OK, 1=WARNING, 2=CRITICAL)

### Task 7.3: Add CLI Tests
**File**: `tests/test_cli.py` (update existing)
**Coverage**:
- Test all new commands with Click's CliRunner
- Test exit codes
- Test output formats (text, json, table)
- Test option combinations

## Phase 8: Documentation (Priority: MEDIUM)

### Task 8.1: Update README.md
**Sections to Add/Update**:
1. **Overview**: Describe ZFS monitoring purpose
2. **Features**: List key capabilities
3. **Quick Start**: Basic usage examples
4. **Configuration**: Threshold and daemon settings
5. **Commands**: Document all CLI commands
6. **Daemon Mode**: Systemd service example
7. **Email Alerts**: Configuration and testing
8. **Troubleshooting**: Common issues

### Task 8.2: Update DEVELOPMENT.md
**Sections to Update**:
1. Fix stale references to template
2. Add ZFS-specific development notes
3. Document test data generation

### Task 8.3: Update Module Reference
**File**: `docs/systemdesign/module_reference.md`
**Add Modules**:
- `models`: Data structures
- `zfs_client`: Command execution
- `zfs_parser`: JSON parsing
- `monitor`: Threshold checking
- `alert_state`: Alert management
- `alerting`: Email sending
- `daemon`: Main daemon loop

### Task 8.4: Update CHANGELOG.md
**Add v0.1.0 Entry**:
```markdown
## [0.1.0] - 2025-11-XX

### Added
- ZFS pool health monitoring
- Capacity threshold alerts (configurable warning/critical)
- Error monitoring (read/write/checksum errors)
- Scrub status and age monitoring
- Daemon mode with periodic checking
- Email alerts with deduplication/suppression
- Rich console output for pool status
- Comprehensive configuration system
- Complete test suite with sample ZFS data

### Changed
- Repurposed template into ZFS monitoring tool
- Updated all documentation for ZFS context

### Removed
- Template placeholder functions (hello, fail)
```

## Phase 9: Testing & Quality (Priority: HIGH)

### Task 9.1: Create Test Data Files
**Files to Create**:
- `tests/zpool_list_degraded_sample.json`: Pool with DEGRADED health
- `tests/zpool_status_with_errors.json`: Pools with read/write/checksum errors
- `tests/zpool_status_scrub_in_progress.json`: Pool currently scrubbing
- `tests/zpool_status_scrub_old.json`: Pool with scrub > 30 days ago

**Data Source**:
- Use testdata.md content (degraded pool example)
- Generate variations for different scenarios

### Task 9.2: Integration Tests
**File**: `tests/test_integration.py` (new)
**Scenarios**:
- Full check cycle with mocked ZFS commands
- Alert suppression across multiple cycles
- Email sending for various issue types
- State persistence across daemon restarts

### Task 9.3: Run Full Test Suite
**Command**: `make test`
**Expected**:
- All tests pass
- Coverage > 85% (as configured)
- No lint errors (ruff)
- No type errors (pyright)
- No security issues (bandit)
- No dependency vulnerabilities (pip-audit)

### Task 9.4: Manual Testing Checklist
- [ ] One-shot check on system with ZFS
- [ ] Daemon mode startup and shutdown
- [ ] Email sending (test SMTP server)
- [ ] Configuration override via environment variables
- [ ] Alert suppression (trigger same issue twice)
- [ ] Recovery emails (fix degraded pool)
- [ ] Graceful shutdown (SIGTERM)

## Phase 10: Packaging & Deployment (Priority: LOW)

### Task 10.1: Update Package Metadata
**File**: `src/check_zpools/__init__conf__.py`
**Action**: Run `make test` to regenerate from `pyproject.toml`

### Task 10.2: Build Package
**Command**: `make build`
**Validates**:
- Wheel creation succeeds
- Sdist creation succeeds
- Package includes all necessary files

### Task 10.3: Create Systemd Service
**File**: `docs/examples/check_zpools.service` (new)
```ini
[Unit]
Description=ZFS Pool Monitoring Daemon
After=network.target zfs-mount.service

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/check_zpools daemon --foreground
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Task 10.4: Version Bump and Release
**Commands**:
```bash
make bump-patch           # 0.0.1 -> 0.1.0 (or bump-minor)
make test                 # Final validation
make release              # Tag and push
```

**GitHub Actions**:
- CI workflow builds and tests
- Release workflow publishes to PyPI (if configured)

## Implementation Order & Dependencies

### Critical Path
```
Phase 1 (Cleanup)
  ↓
Phase 2 (Models)
  ↓
Phase 3 (ZFS Client & Parser)
  ↓
Phase 4 (Monitor)
  ↓
Phase 5 (Alerting)
  ↓
Phase 6 (Daemon)
  ↓
Phase 7 (CLI)
  ↓
Phase 9 (Testing)
  ↓
Phase 10 (Release)
```

Phase 8 (Documentation) can proceed in parallel with Phases 5-7.

## Estimated Effort

| Phase | Tasks | Estimated Hours | Priority |
|-------|-------|----------------|----------|
| 1. Cleanup | 2 | 0.5 | HIGH |
| 2. Models | 2 | 2 | HIGH |
| 3. ZFS Client | 3 | 6 | HIGH |
| 4. Monitor | 2 | 4 | HIGH |
| 5. Alerting | 3 | 6 | MEDIUM |
| 6. Daemon | 2 | 4 | HIGH |
| 7. CLI | 3 | 3 | HIGH |
| 8. Documentation | 4 | 3 | MEDIUM |
| 9. Testing | 4 | 6 | HIGH |
| 10. Packaging | 4 | 2 | LOW |
| **Total** | **29** | **36.5** | |

## Success Criteria

### Minimum Viable Product (v0.1.0)
- [ ] Execute `zpool list -j` and `zpool status -j` successfully
- [ ] Parse JSON output into PoolStatus objects
- [ ] Check pools against configurable thresholds
- [ ] Send email alerts for CRITICAL/WARNING issues
- [ ] Suppress duplicate alerts (resend after 24h)
- [ ] Run as daemon with configurable interval
- [ ] Graceful shutdown on SIGTERM/SIGINT
- [ ] Test coverage > 85%
- [ ] Complete documentation (README, CHANGELOG)
- [ ] Successful `make test` and `make build`

### Quality Gates
- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] Ruff linting passes (no errors)
- [ ] Pyright type checking passes (strict mode)
- [ ] Bandit security scan passes
- [ ] pip-audit vulnerability scan passes
- [ ] Manual testing checklist complete
- [ ] Code review (if working in team)

## Risk Mitigation

### Technical Risks
| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| ZFS JSON format changes | Low | High | Use OpenZFS version detection, validate schema |
| zpool command not available | Medium | High | Check command availability at startup, clear error message |
| Permission issues (requires root) | High | Medium | Document delegation options, handle gracefully |
| Email delivery failures | Medium | Medium | Log failures, retry with exponential backoff |
| State file corruption | Low | Low | Validate on load, recreate if corrupt |

### Process Risks
| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Scope creep | Medium | Medium | Stick to REQUIREMENTS.md, defer enhancements to v0.2.0 |
| Inadequate testing | Low | High | Maintain >85% coverage, comprehensive integration tests |
| Poor documentation | Low | Medium | Update docs as code is written, not after |

## Future Enhancements (v0.2.0+)

Deferred to future releases:
- Web dashboard for status visualization
- Prometheus metrics export
- Remote ZFS pools (SSH support)
- Dataset-level monitoring
- Snapshot age monitoring
- Automatic scrub scheduling
- Integration with monitoring systems (Nagios, Zabbix, Icinga)
- HTML email templates (currently plain text only)
- Multi-language support
- Windows support (if applicable)

## Notes

- Follow coding guidelines in `CLAUDE.md` and system prompts
- Keep functions small (<20 lines)
- Apply SOLID principles
- Maintain clean architecture (CLI → Behaviors → Domain)
- Use structured logging throughout
- Write self-documenting code (clear names, docstrings)
- Test early and often (`make test` before commits)
