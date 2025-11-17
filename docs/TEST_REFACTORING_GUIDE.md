# Test Suite Refactoring Guide

**Status:** IN PROGRESS
**Created:** 2025-11-17
**Goal:** Refactor entire test suite to extreme clean architecture principles

---

## Overview

This guide documents the systematic refactoring of the check_zpools test suite to achieve:

1. **Maximum test coverage** - Every line, branch, and edge case
2. **Poetic readability** - Tests read like plain English specifications
3. **Single responsibility** - Each test validates exactly one behavior
4. **OS-awareness** - Tests marked for specific platforms (Windows/macOS/Linux/POSIX)
5. **Real behavior over mocks** - Integration tests preferred over stub-only tests
6. **Zero duplication** - DRY with clear helpers, without obscuring intent

---

## Refactoring Principles (The Extreme Standard)

### 1. Poetic Naming - Tests as Literature

**BEFORE** (mechanical):
```python
def test_pool_status_creation():
    """Verify PoolStatus can be created with all fields."""
    pool = PoolStatus(name="rpool", health=PoolHealth.ONLINE, ...)
    assert pool.name == "rpool"
```

**AFTER** (poetic):
```python
@pytest.mark.os_agnostic
def test_a_healthy_pool_status_remembers_its_name_and_health():
    """When we create a pool status with a name,
    it faithfully preserves that name for future inquiries."""

    pool = a_healthy_pool_named("rpool")

    assert pool.name == "rpool"
    assert pool.health == PoolHealth.ONLINE
```

### 2. One Behavior Per Test

**BEFORE** (kitchen sink):
```python
def test_has_errors():
    # Test read errors
    pool1 = PoolStatus(..., read_errors=1, ...)
    assert pool1.has_errors() is True

    # Test write errors
    pool2 = PoolStatus(..., write_errors=1, ...)
    assert pool2.has_errors() is True

    # Test checksum errors
    pool3 = PoolStatus(..., checksum_errors=1, ...)
    assert pool3.has_errors() is True
```

**AFTER** (laser-focused):
```python
@pytest.mark.os_agnostic
def test_a_pool_with_read_errors_knows_it_has_problems():
    pool = a_pool_with(read_errors=1)
    assert pool.has_errors()

@pytest.mark.os_agnostic
def test_a_pool_with_write_errors_knows_it_has_problems():
    pool = a_pool_with(write_errors=1)
    assert pool.has_errors()

@pytest.mark.os_agnostic
def test_a_pool_with_checksum_errors_knows_it_has_problems():
    pool = a_pool_with(checksum_errors=1)
    assert pool.has_errors()
```

### 3. OS-Specific Marking

**Mark EVERY test** with its OS requirements:

```python
@pytest.mark.os_agnostic  # Runs everywhere
def test_severity_comparison_works_on_all_platforms():
    ...

@pytest.mark.posix_only  # Linux, macOS, Unix only
def test_systemd_service_installation_requires_posix():
    ...

@pytest.mark.linux_only  # Linux only
def test_zfs_commands_execute_on_linux():
    ...

@pytest.mark.windows_only  # Windows only
def test_windows_event_log_integration():
    ...

@pytest.mark.macos_only  # macOS only
def test_launchd_service_configuration():
    ...
```

### 4. Real Behavior Over Stubs

**BEFORE** (stub-only, weak):
```python
def test_send_alert():
    """Test that send_alert calls send_email."""
    alerter = EmailAlerter(...)
    with patch("check_zpools.mail.send_email") as mock_send:
        mock_send.return_value = True
        result = alerter.send_alert(issue, pool)
        mock_send.assert_called_once()
```

This ONLY verifies the stub works, not the actual system!

**AFTER** (real behavior):
```python
@pytest.mark.integration
def test_alerter_formats_and_delivers_critical_pool_failure_email():
    """When a pool becomes FAULTED,
    the alerter composes an email with pool details
    and delivers it to the configured recipients."""

    alerter = an_email_alerter_configured_for("admin@example.com")
    failed_pool = a_faulted_pool_named("rpool")
    critical_issue = a_critical_health_issue_for(failed_pool)

    # Use a test SMTP server or in-memory mail collector
    with capturing_sent_emails() as sent_emails:
        alerter.send_alert(critical_issue, failed_pool)

    assert len(sent_emails) == 1
    email = sent_emails[0]
    assert "CRITICAL" in email.subject
    assert "FAULTED" in email.body
    assert failed_pool.name in email.body
```

### 5. Extreme Clarity - Obvious Helpers

Extract common patterns into **obviously named** helper functions:

```python
# Builders (factory functions)
def a_healthy_pool_named(name: str) -> PoolStatus:
    """Create a healthy pool with sensible defaults."""
    return PoolStatus(
        name=name,
        health=PoolHealth.ONLINE,
        capacity_percent=45.0,
        size_bytes=1_000_000_000_000,
        allocated_bytes=450_000_000_000,
        free_bytes=550_000_000_000,
        read_errors=0,
        write_errors=0,
        checksum_errors=0,
        last_scrub=datetime.now(timezone.utc),
        scrub_errors=0,
        scrub_in_progress=False,
    )

def a_pool_with(**overrides) -> PoolStatus:
    """Create a pool with specific attributes overridden."""
    defaults = {
        "name": "test-pool",
        "health": PoolHealth.ONLINE,
        "capacity_percent": 50.0,
        "size_bytes": 1000,
        "allocated_bytes": 500,
        "free_bytes": 500,
        "read_errors": 0,
        "write_errors": 0,
        "checksum_errors": 0,
        "last_scrub": None,
        "scrub_errors": 0,
        "scrub_in_progress": False,
    }
    return PoolStatus(**{**defaults, **overrides})

def a_faulted_pool_named(name: str) -> PoolStatus:
    """Create a critically failed pool."""
    return a_pool_with(name=name, health=PoolHealth.FAULTED)
```

---

## OS-Specific Testing Strategy

### Available Markers

```python
@pytest.mark.os_agnostic     # Runs on all platforms (default assumption)
@pytest.mark.windows_only    # Windows-specific (file paths, registry, services)
@pytest.mark.macos_only      # macOS-specific (launchd, specific paths)
@pytest.mark.linux_only      # Linux-specific (systemd, ZFS commands)
@pytest.mark.posix_only      # POSIX systems (Linux, macOS, Unix)
```

### When to Use Each Marker

**@pytest.mark.os_agnostic** (Default):
- Pure Python logic (models, enums, algorithms)
- Configuration parsing (TOML, environment variables)
- Data transformations
- Business rules

**@pytest.mark.posix_only**:
- File permission tests (chmod, ownership)
- Signal handling (SIGTERM, SIGHUP)
- Process forking
- Unix socket operations

**@pytest.mark.linux_only**:
- systemd service installation/management
- ZFS command execution (if ZFS only tested on Linux CI)
- Linux-specific paths (/etc/systemd, /var/run)

**@pytest.mark.windows_only**:
- Windows Event Log integration
- Windows service management
- Windows-specific path handling (C:\, backslashes)
- Registry operations

**@pytest.mark.macos_only**:
- launchd configuration
- macOS-specific paths (/Library/LaunchDaemons)

### Testing OS-Specific Code on All Platforms

For code that has OS-specific behavior, create variants:

```python
@pytest.mark.posix_only
def test_config_path_uses_xdg_on_posix():
    """On POSIX systems, configuration follows XDG Base Directory spec."""
    # Real test on POSIX CI runners
    path = get_default_config_path()
    assert str(path).startswith(os.path.expanduser("~/.config"))

@pytest.mark.windows_only
def test_config_path_uses_appdata_on_windows():
    """On Windows, configuration uses APPDATA directory."""
    # Real test on Windows CI runners
    path = get_default_config_path()
    assert "AppData" in str(path)
```

---

## File-by-File Refactoring Checklist

### Priority 1: Foundation (Domain Models)

- [ ] **test_models.py** - Pure domain objects, OS-agnostic
  - Mark all tests as `@pytest.mark.os_agnostic`
  - Use builder helpers (a_healthy_pool, a_pool_with, etc.)
  - One assertion per test
  - Poetic naming

### Priority 2: Core Logic

- [ ] **test_monitor.py** - Business rules for pool monitoring
  - Mark as `@pytest.mark.os_agnostic`
  - Test each threshold independently
  - Test each health check independently
  - Use fixtures for MonitorConfig variants

- [ ] **test_zfs_parser.py** - JSON parsing logic
  - Mark most as `@pytest.mark.os_agnostic`
  - **REPLACE stub tests** with real JSON fixtures
  - Test actual ZFS JSON output samples
  - Comprehensive edge case coverage

- [ ] **test_alert_state.py** - Alert deduplication logic
  - Mark as `@pytest.mark.os_agnostic`
  - Add edge cases for time boundaries
  - Test concurrent access scenarios

### Priority 3: Integration

- [ ] **test_daemon.py** - Orchestration layer
  - Mark as `@pytest.mark.integration`
  - **REPLACE mocks with real components** where possible
  - Use in-memory adapters instead of stubs
  - Test real signal handling on appropriate platforms

- [ ] **test_alerting.py** - Email composition & delivery
  - Mark as `@pytest.mark.integration`
  - Use test SMTP server or memory collector
  - **REPLACE mock.send_email with real delivery**
  - Test actual email formatting

### Priority 4: Platform-Specific

- [ ] **test_cli.py** - Command-line interface
  - Mark appropriately (mostly `@pytest.mark.os_agnostic`)
  - Service commands: `@pytest.mark.linux_only` (systemd)
  - Test real CLI invocation, not just click.testing mocks

- [ ] **test_behaviors.py** - Application layer
  - Mark config path tests as OS-specific
  - Mark display tests as `@pytest.mark.os_agnostic`

- [ ] **test_config_deploy.py** - Configuration deployment
  - Mark path-related tests by OS
  - Test real file creation (use tmp_path)

### Priority 5: Utilities

- [ ] **test_formatters.py** - Output formatting
  - Mark as `@pytest.mark.os_agnostic`
  - Test all output modes
  - Test color codes independently

- [ ] **test_cli_errors.py** - Error handling
  - Mark as `@pytest.mark.os_agnostic`
  - Test all exception paths

- [ ] **test_mail.py** - Email configuration & sending
  - Integration tests for real SMTP (if credentials available)
  - Mark SMTP tests as `@pytest.mark.slow`

- [ ] **test_metadata.py** - Package metadata
  - Mark as `@pytest.mark.os_agnostic`

---

## Coverage Maximization Strategy

### 1. Branch Coverage

For every `if` statement, create tests for:
- Condition true
- Condition false
- Edge cases at boundaries

Example:
```python
# Code:
if capacity_percent >= critical_threshold:
    severity = Severity.CRITICAL
elif capacity_percent >= warning_threshold:
    severity = Severity.WARNING
else:
    severity = Severity.OK

# Tests needed:
test_capacity_at_exact_critical_threshold()      # == critical
test_capacity_just_above_critical_threshold()    # > critical
test_capacity_just_below_critical_threshold()    # < critical
test_capacity_at_exact_warning_threshold()       # == warning
test_capacity_between_warning_and_critical()     # between
test_capacity_below_warning_threshold()          # < warning
test_capacity_at_zero_percent()                  # edge: 0
test_capacity_at_maximum_percent()               # edge: 100
```

### 2. Exception Coverage

Test every exception path:
```python
# Code:
try:
    value = float(capacity_str)
except ValueError:
    logger.warning(...)
    value = 0.0

# Tests needed:
test_valid_capacity_string_converts_to_float()
test_invalid_capacity_string_defaults_to_zero()
test_empty_capacity_string_defaults_to_zero()
test_non_numeric_capacity_string_logs_warning()
```

### 3. State Transition Coverage

For state machines, test all transitions:
```python
# Code: AlertState lifecycle
# NEW -> SENT -> RESENT -> CLEARED

# Tests needed:
test_new_issue_transitions_to_sent_on_first_alert()
test_sent_issue_stays_sent_within_resend_interval()
test_sent_issue_transitions_to_resent_after_interval()
test_any_state_transitions_to_cleared_when_resolved()
```

### 4. Boundary Value Analysis

Test at exact boundaries, just below, and just above:
```python
test_threshold_at_79_percent_is_ok()           # Just below warning (80)
test_threshold_at_80_percent_triggers_warning()  # Exact boundary
test_threshold_at_81_percent_triggers_warning()  # Just above boundary
test_threshold_at_89_percent_is_warning()      # Just below critical (90)
test_threshold_at_90_percent_triggers_critical() # Exact boundary
test_threshold_at_91_percent_triggers_critical() # Just above
```

---

## Test Organization Pattern

### File Structure

```python
"""Module docstring explaining what's tested."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from check_zpools.models import ...

# ============================================================================
# Test Fixtures & Helpers
# ============================================================================

@pytest.fixture
def healthy_pool() -> PoolStatus:
    """Provide a healthy pool for tests."""
    return a_healthy_pool_named("test-pool")


def a_healthy_pool_named(name: str) -> PoolStatus:
    """Create a healthy pool with sensible defaults."""
    ...


# ============================================================================
# Tests: PoolHealth Enumeration
# ============================================================================

class TestPoolHealthStates:
    """All health states are recognized and behave correctly."""

    @pytest.mark.os_agnostic
    def test_all_six_health_states_exist(self):
        """ZFS defines exactly six health states:
        ONLINE, DEGRADED, FAULTED, OFFLINE, UNAVAIL, REMOVED."""
        ...

    @pytest.mark.os_agnostic
    def test_online_is_the_only_healthy_state(self):
        """Among all states, only ONLINE represents a healthy pool."""
        ...


# ============================================================================
# Tests: PoolStatus Immutability
# ============================================================================

class TestPoolStatusImmutability:
    """Pool status objects are frozen and cannot be modified."""

    @pytest.mark.os_agnostic
    def test_pool_name_cannot_be_changed_after_creation(self):
        """Once created, a pool's name is locked forever."""
        ...


# ============================================================================
# Tests: Error Detection
# ============================================================================

class TestErrorDetection:
    """Pools accurately report whether they have I/O errors."""

    @pytest.mark.os_agnostic
    def test_a_pool_with_read_errors_knows_it_has_problems(self):
        ...
```

---

## Refactoring Progress

### Completed ✅

- [x] Created OS-specific markers in conftest.py
- [x] Documented refactoring principles
- [x] Created builder helper pattern examples

### In Progress 🔄

- [ ] test_models.py refactoring (example file)

### Pending 📋

- [ ] test_zfs_parser.py (replace stubs with real behavior)
- [ ] test_monitor.py
- [ ] test_daemon.py (real integration tests)
- [ ] test_alerting.py (real email delivery)
- [ ] test_cli.py
- [ ] test_behaviors.py
- [ ] test_config_deploy.py
- [ ] test_formatters.py
- [ ] test_cli_errors.py
- [ ] test_mail.py
- [ ] test_alert_state.py
- [ ] test_metadata.py
- [ ] test_module_entry.py
- [ ] test_scripts.py (excluded from refactoring)

---

## Definition of Done Checklist

The refactoring is complete when:

- [ ] Every test is marked with an OS marker (or explicitly `@pytest.mark.os_agnostic`)
- [ ] Every test name reads like plain English (subject-verb-object)
- [ ] Every test validates exactly one behavior
- [ ] No test contains more than one assertion (except for closely related attributes)
- [ ] All tests use builder helpers instead of repeating PoolStatus(...) creation
- [ ] Stub-only tests are replaced with real behavioral tests
- [ ] Coverage is at maximum (every branch, every edge case)
- [ ] Running tests on each OS yields only relevant results (correct skips)
- [ ] Reading the test suite feels like reading a specification document
- [ ] All tests pass: `make test` shows 362+ tests, 0 failures
- [ ] Coverage report shows ≥90% (approaching 100%)

---

## Quick Reference Commands

```bash
# Run all tests
make test

# Run only OS-agnostic tests (portable)
pytest -m os_agnostic

# Run only POSIX-specific tests
pytest -m posix_only

# Run only integration tests
pytest -m integration

# Check coverage
pytest --cov=src/check_zpools --cov-report=html
open htmlcov/index.html

# Run specific test file with verbose output
pytest tests/test_models.py -vv

# Run only tests matching a pattern
pytest -k "test_severity" -vv
```

---

**Next Steps:**

1. Complete test_models.py refactoring as exemplar
2. Use test_models.py as template for other domain tests
3. Tackle integration tests (daemon, alerting) next
4. Add missing edge case tests for maximum coverage
5. Final verification: all tests pass, coverage maximized
