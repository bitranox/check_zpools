# Test Refactoring Guide - Clean Architecture Principles

This guide demonstrates how to refactor the entire test suite according to clean architecture principles, using `test_cli_commands_integration.py` as the exemplar.

## Table of Contents
1. [Refactoring Principles](#refactoring-principles)
2. [Before & After Examples](#before--after-examples)
3. [OS-Specific Test Markers](#os-specific-test-markers)
4. [Test Naming Patterns](#test-naming-patterns)
5. [Fixture Design](#fixture-design)
6. [Coverage Maximization](#coverage-maximization)
7. [File-by-File Refactoring Plan](#file-by-file-refactoring-plan)

---

## Refactoring Principles

### 1. Test Names Read Like Plain English

**Bad:**
```python
def test_check_cmd():
    """Test check."""
```

**Good:**
```python
def test_displays_pool_status_in_human_readable_text():
    """When checking pools with default text format, it shows readable status.

    Given: A healthy pool named 'testpool' with ONLINE status
    When: Running 'check_zpools check' with default (text) format
    Then: Output contains pool name and health status in text
    """
```

**Pattern:** `test_<action>_<condition>_<outcome>`
- Action: What the system does (displays, reports, exits, sends)
- Condition: Under what circumstances (when healthy, with errors, without config)
- Outcome: What the result is (in text, with code, successfully)

### 2. Each Test Checks ONE Behavior

**Bad - Kitchen Sink Test:**
```python
def test_check_command(self, sample_result):
    """Test check command."""
    result = run_cli(["check"])
    assert result.exit_code == 0
    assert "testpool" in result.output
    assert "ONLINE" in result.output

    # Also test JSON format
    json_result = run_cli(["check", "--format", "json"])
    assert json_result.exit_code == 0
    data = json.loads(json_result.output)
    assert data["pools"][0]["name"] == "testpool"

    # Also test error handling
    with patch(...) as mock:
        mock.side_effect = RuntimeError()
        error_result = run_cli(["check"])
        assert error_result.exit_code == 1
```

**Good - Focused Tests:**
```python
def test_displays_pool_status_in_human_readable_text(self, cli_runner, ok_result):
    """When checking pools with default text format, it shows readable status."""
    # Single behavior: text output format

def test_displays_pool_status_as_parseable_json(self, cli_runner, ok_result):
    """When checking pools with JSON format, it outputs valid structured data."""
    # Single behavior: JSON output format

def test_reports_unexpected_errors_with_helpful_message(self, cli_runner):
    """When unexpected errors occur, show error message to user."""
    # Single behavior: error handling
```

### 3. Given-When-Then Structure

Every test follows this pattern in docstring and code:

```python
def test_exits_with_code_one_when_pools_have_warnings(
    self,
    cli_runner: CliRunner,
    warning_check_result: CheckResult,
) -> None:
    """When pools have warnings, exit with code 1 for monitoring tools.

    Given: Pools with WARNING severity issues
    When: Running 'check_zpools check'
    Then: Process exits with code 1 (standard monitoring WARNING)
    """
    # Given - setup is done by fixtures
    with patch("...check_pools_once") as mock_check:
        mock_check.return_value = warning_check_result

        # When - execute one action
        result = cli_runner.invoke(cli, ["check"])

        # Then - assert one outcome
        assert result.exit_code == 1, "WARNING severity must exit with code 1"
```

### 4. Descriptive Class Names

Group related behaviors with descriptive class names:

```python
class TestCheckCommandSucceedsWithHealthyPools:
    """When pools are healthy, the check command reports success."""
    # All tests here validate success scenarios

class TestCheckCommandExitsWithMonitoringStatusCodes:
    """The check command exits with standard monitoring tool codes."""
    # All tests here validate exit code behavior

class TestCheckCommandHandlesExpectedErrors:
    """The check command handles error conditions gracefully."""
    # All tests here validate error handling
```

### 5. Real Behavior Over Mocks

**When to Mock:**
- ✅ External dependencies (SMTP servers, file system, network)
- ✅ System calls that require special privileges
- ✅ Slow operations (database, network I/O)

**When NOT to Mock:**
- ❌ Internal business logic
- ❌ Data transformations
- ❌ Simple calculations
- ❌ Pure functions

**Example - Too Much Mocking:**
```python
def test_monitor_checks_capacity(self):
    with patch("monitor.get_capacity") as mock_cap:
        with patch("monitor.calculate_percent") as mock_calc:
            with patch("monitor.compare_threshold") as mock_cmp:
                mock_cap.return_value = 90000
                mock_calc.return_value = 90.0
                mock_cmp.return_value = True
                # We're only testing that mocks were called!
```

**Example - Real Behavior:**
```python
def test_monitor_detects_when_capacity_exceeds_warning_threshold(self):
    """When pool capacity reaches 80%, monitor issues WARNING."""
    pool = PoolStatus(capacity_percent=85.0, ...)
    monitor = PoolMonitor(capacity_warning=80.0)

    issues = monitor.check_pool(pool)

    assert len(issues) == 1
    assert issues[0].severity == Severity.WARNING
    # Tests actual business logic, not mocks
```

---

## Before & After Examples

### Example 1: test_models.py

**Before:**
```python
def test_pool_status_creation(self):
    pool = PoolStatus(
        name="tank",
        health=PoolHealth.ONLINE,
        capacity_percent=50.0,
        # ... many fields
    )
    assert pool.name == "tank"
    assert pool.health == PoolHealth.ONLINE
    assert pool.capacity_percent == 50.0
```

**After:**
```python
# At top of file - OS marker
pytestmark = pytest.mark.skipif(False, reason="OS-agnostic model tests")

class TestPoolStatusRemembersItsProperties:
    """A pool status object remembers all the properties given to it."""

    def test_remembers_its_name(self, healthy_pool: PoolStatus):
        """When creating a pool status, it remembers the pool name.

        Given: Pool created with name 'testpool'
        When: Accessing the name property
        Then: Returns the name that was set
        """
        assert healthy_pool.name == "testpool"

    def test_remembers_its_health_state(self, healthy_pool: PoolStatus):
        """When creating a pool status, it remembers the health state.

        Given: Pool created with ONLINE health
        When: Accessing the health property
        Then: Returns ONLINE health state
        """
        assert healthy_pool.health == PoolHealth.ONLINE
```

### Example 2: test_monitor.py

**Before:**
```python
def test_capacity_warning(self):
    config = MonitorConfig(capacity_warning=80, capacity_critical=90)
    monitor = PoolMonitor(config)
    pool = PoolStatus(capacity_percent=85, ...)
    issues = monitor.check_pool(pool)
    assert len(issues) > 0
    assert any(i.severity == Severity.WARNING for i in issues)
```

**After:**
```python
pytestmark = pytest.mark.skipif(False, reason="OS-agnostic monitoring logic tests")

class TestMonitorDetectsCapacityProblems:
    """The monitor detects when pool capacity exceeds thresholds."""

    def test_issues_warning_when_capacity_reaches_eighty_percent(
        self,
        monitor_with_default_thresholds: PoolMonitor,
    ):
        """When pool capacity reaches 80%, the monitor issues a WARNING.

        Given: Monitor configured with 80% warning threshold
        When: Checking a pool at 85% capacity
        Then: Issues a WARNING severity alert about capacity
        """
        pool_at_85_percent = PoolStatus(capacity_percent=85.0, ...)

        issues = monitor_with_default_thresholds.check_pool(pool_at_85_percent)

        capacity_issues = [i for i in issues if "capacity" in i.message.lower()]
        assert len(capacity_issues) == 1, "Should detect one capacity issue"
        assert capacity_issues[0].severity == Severity.WARNING
```

---

## OS-Specific Test Markers

### Marking Tests by Platform

```python
# At top of file or on specific test
import sys
import pytest

# OS-agnostic tests (work everywhere)
pytestmark = pytest.mark.skipif(False, reason="OS-agnostic tests")

# Windows-only tests
pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Windows-specific service installation tests"
)

# macOS-only tests
pytestmark = pytest.mark.skipif(
    sys.platform != "darwin",
    reason="macOS-specific launchd tests"
)

# POSIX-only tests (Linux, macOS, BSD)
pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX-specific systemd tests"
)

# Linux-only tests
pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="Linux-specific systemd tests"
)
```

### Example: test_service_install.py

```python
"""Service installation tests - OS-specific behaviors.

Service installation works differently on each platform:
- Linux: systemd unit files in /etc/systemd/system/
- macOS: launchd plist files in ~/Library/LaunchAgents/
- Windows: Windows Service via pywin32
"""

import sys
import pytest

class TestServiceInstallationOnLinux:
    """On Linux systems, services are installed via systemd."""

    pytestmark = pytest.mark.skipif(
        not sys.platform.startswith("linux"),
        reason="Linux-specific systemd tests - run on Linux CI"
    )

    def test_creates_systemd_unit_file_in_system_directory(self):
        """When installing service on Linux, creates systemd unit file."""
        # Real test that runs on Linux CI runners

class TestServiceInstallationOnMacOS:
    """On macOS systems, services are installed via launchd."""

    pytestmark = pytest.mark.skipif(
        sys.platform != "darwin",
        reason="macOS-specific launchd tests - run on macOS CI"
    )

    def test_creates_launchd_plist_in_launch_agents(self):
        """When installing service on macOS, creates launchd plist file."""
        # Real test that runs on macOS CI runners

class TestServiceInstallationOnWindows:
    """On Windows systems, services are installed via Windows Service API."""

    pytestmark = pytest.mark.skipif(
        sys.platform != "win32",
        reason="Windows-specific service tests - run on Windows CI"
    )

    def test_registers_windows_service_with_scm(self):
        """When installing service on Windows, registers with Service Control Manager."""
        # Real test that runs on Windows CI runners
```

---

## Test Naming Patterns

### Pattern Library

| Pattern | Example | Use When |
|---------|---------|----------|
| `test_<action>_<object>_<context>` | `test_displays_pool_status_in_text_format` | Testing output/display |
| `test_<object>_<state>_<outcome>` | `test_pool_with_errors_reports_warning` | Testing state transitions |
| `test_<verb>s_when_<condition>` | `test_exits_with_code_one_when_pools_have_warnings` | Testing conditional behavior |
| `test_<action>_<object>_<location>` | `test_creates_config_file_in_user_directory` | Testing file operations |
| `test_remembers_<property>` | `test_remembers_its_capacity_percentage` | Testing data retention |
| `test_detects_when_<condition>` | `test_detects_when_capacity_exceeds_threshold` | Testing detection logic |
| `test_reports_<condition>_with_<format>` | `test_reports_errors_with_helpful_message` | Testing error reporting |

### Anti-Patterns to Avoid

❌ **Vague names:**
```python
def test_check():           # What does it check?
def test_email():          # What about email?
def test_monitor_1():      # Why "1"?
def test_it_works():       # What works?
```

✅ **Specific names:**
```python
def test_displays_pool_status_in_human_readable_text():
def test_sends_email_when_smtp_is_configured():
def test_monitor_detects_capacity_warnings_at_eighty_percent():
def test_configuration_deploys_to_user_directory_without_sudo():
```

---

## Fixture Design

### Fixture Hierarchy

```python
# conftest.py - Shared fixtures across all tests
@pytest.fixture
def temp_config_dir(tmp_path):
    """Temporary configuration directory for tests."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return config_dir

# test_module.py - Module-specific fixtures
@pytest.fixture
def cli_runner():
    """CLI test runner for this module."""
    return CliRunner()

@pytest.fixture
def healthy_pool():
    """Standard healthy pool for happy-path tests."""
    return PoolStatus(health=PoolHealth.ONLINE, ...)

@pytest.fixture
def degraded_pool():
    """Degraded pool for error testing."""
    return PoolStatus(health=PoolHealth.DEGRADED, ...)

@pytest.fixture
def monitor_with_strict_thresholds():
    """Monitor configured with strict (low) thresholds for testing edge cases."""
    return PoolMonitor(MonitorConfig(capacity_warning=60, capacity_critical=75))
```

### Fixture Naming Conventions

| Prefix | Meaning | Example |
|--------|---------|---------|
| `empty_*` | Container with no items | `empty_pool_list` |
| `valid_*` | Object with all required fields | `valid_email_config` |
| `invalid_*` | Object missing required fields | `invalid_smtp_config` |
| `*_with_*` | Object configured with specific property | `pool_with_errors` |
| `*_without_*` | Object lacking specific property | `config_without_smtp` |
| `*_at_*` | Object at specific state | `pool_at_ninety_percent_capacity` |

---

## Coverage Maximization

### Identify Coverage Gaps

```bash
# Run with coverage report
python3 -m pytest --cov=src/check_zpools --cov-report=term-missing

# Focus on specific module
python3 -m pytest --cov=src/check_zpools/monitor --cov-report=term-missing tests/test_monitor.py
```

### Coverage Targets by Module Type

| Module Type | Target Coverage | Focus Areas |
|-------------|----------------|-------------|
| Models (dataclasses) | 100% | Property access, validation, immutability |
| Business Logic | 95-100% | All branches, edge cases, error paths |
| CLI Commands | 90-95% | Happy paths, error handling, exit codes |
| I/O Adapters | 70-85% | Mock external systems, test error handling |
| Configuration | 100% | Loading, merging, validation |

### Systematic Coverage Approach

1. **Line Coverage** - Every line executed
2. **Branch Coverage** - Every if/else path taken
3. **Edge Cases** - Boundary values (0, empty, max, None)
4. **Error Paths** - Every exception handler triggered
5. **Integration Paths** - End-to-end flows

**Example - Systematic Monitor Testing:**

```python
class TestMonitorCapacityDetection:
    """Systematically test all capacity thresholds."""

    # Below warning threshold
    def test_no_alert_when_capacity_below_warning_threshold(self):
        """When capacity is 79%, no alert is issued (threshold is 80%)."""

    # At warning threshold
    def test_warning_alert_when_capacity_exactly_at_warning_threshold(self):
        """When capacity is exactly 80%, WARNING alert is issued."""

    # Between thresholds
    def test_warning_alert_when_capacity_between_warning_and_critical(self):
        """When capacity is 85%, WARNING alert is issued (before CRITICAL at 90%)."""

    # At critical threshold
    def test_critical_alert_when_capacity_exactly_at_critical_threshold(self):
        """When capacity is exactly 90%, CRITICAL alert is issued."""

    # Above critical threshold
    def test_critical_alert_when_capacity_above_critical_threshold(self):
        """When capacity is 95%, CRITICAL alert is issued."""

    # At maximum
    def test_critical_alert_when_capacity_is_one_hundred_percent(self):
        """When capacity is 100% (full), CRITICAL alert is issued."""

    # Edge case: Zero
    def test_no_alert_when_capacity_is_zero_percent(self):
        """When capacity is 0% (empty pool), no alert is issued."""
```

---

## File-by-File Refactoring Plan

### Priority 1: High-Impact, Low-Coverage Files

1. **test_daemon.py** (77% coverage)
   - Add tests for daemon shutdown paths
   - Test alert delivery timing
   - Test state persistence
   - OS markers: POSIX vs Windows

2. **test_behaviors.py** (71% coverage)
   - Cover error paths in `check_pools_once`
   - Test daemon lifecycle
   - Test greeting behavior edge cases
   - OS markers: OS-agnostic

3. **test_alerting.py** (91% coverage)
   - Cover edge cases in alert suppression
   - Test recovery email paths
   - Test concurrent alert scenarios
   - OS markers: OS-agnostic (logic), POSIX (file I/O)

### Priority 2: Existing Tests Needing Refactoring

4. **test_monitor.py** (100% coverage, needs refactoring)
   - ✅ Already has good coverage
   - Refactor test names to be more descriptive
   - Split kitchen-sink tests into focused ones
   - Add OS markers
   - Group related tests into descriptive classes

5. **test_models.py** (85% coverage)
   - Cover missing edge cases
   - Refactor to one-behavior-per-test
   - Better test names
   - OS markers: OS-agnostic

6. **test_formatters.py** (96% coverage)
   - Cover edge cases in JSON formatting
   - Test error formatting paths
   - Refactor test names
   - OS markers: OS-agnostic

### Priority 3: Low-Coverage, OS-Specific Files

7. **test_service_install.py** (low coverage)
   - ⚠️ Requires real OS environments
   - Split into OS-specific test classes
   - Mark with appropriate OS markers
   - Document which tests run on which CI platform
   - Focus on integration tests in CI, not local mocks

### Test Refactoring Checklist

For each test file:

- [ ] Add OS markers at file or class level
- [ ] Rename all tests to descriptive English sentences
- [ ] Split multi-assertion tests into focused single-behavior tests
- [ ] Extract common setup into well-named fixtures
- [ ] Add Given-When-Then docstrings
- [ ] Group related tests into descriptive classes
- [ ] Replace stub-only tests with real behavior tests
- [ ] Add tests for all uncovered branches
- [ ] Verify tests are deterministic (no randomness/timing)
- [ ] Run tests and verify they pass
- [ ] Check coverage improved

---

## Summary

**Key Principles:**
1. Test names are sentences describing behavior
2. Each test checks ONE thing
3. Given-When-Then structure throughout
4. Real behavior over mocks when possible
5. OS-specific markers for platform-dependent code
6. Fixtures create reusable, well-named test data
7. Coverage pushed to the extreme systematically
8. Tests read like executable specifications

**The refactored `test_cli_commands_integration.py` demonstrates all these principles and serves as the template for refactoring the remaining 478 tests.**
