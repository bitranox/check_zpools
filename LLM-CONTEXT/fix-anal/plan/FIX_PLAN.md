# Comprehensive Fix Plan - check_zpools

**Project:** check_zpools v2.1.8
**Plan Date:** 2025-11-19
**Based On:** Full codebase review (LLM-CONTEXT/review-anal/report/REVIEW_REPORT.md)
**Planner:** Claude Code (Sonnet 4.5)

---

## Executive Summary

This fix plan addresses all findings from the comprehensive code review. The codebase is **PRODUCTION READY** with an overall grade of **A (95%)**. This plan focuses on elevating quality from excellent to exceptional.

### Key Statistics

- **Total Issues Identified:** 33
- **Critical (Blocking):** 0
- **High Priority (Recommended):** 2
- **Medium Priority (Suggested):** 8
- **Low Priority (Optional):** 23

### Issue Breakdown by Category

| Category | Critical | High | Medium | Low | Total |
|----------|----------|------|--------|-----|-------|
| **Code Quality** | 0 | 1 | 6 | 3 | 10 |
| **Documentation** | 0 | 1 | 2 | 2 | 5 |
| **CI/CD** | 0 | 0 | 2 | 4 | 6 |
| **Security** | 0 | 0 | 0 | 3 | 3 |
| **Testing** | 0 | 0 | 0 | 3 | 3 |
| **Dependencies** | 0 | 0 | 0 | 0 | 0 |
| **Performance** | 0 | 0 | 0 | 0 | 0 |
| **Review Artifacts** | 0 | 0 | 1 | 0 | 1 |

### Estimated Total Effort

- **Critical Issues:** 0 hours (NONE)
- **High Priority:** 4-6 hours
- **Medium Priority:** 16-24 hours
- **Low Priority:** 8-12 hours
- **TOTAL:** 28-42 hours (1-2 sprint weeks)

---

## PREREQUISITE: Fix Review Artifacts (BLOCKING BASELINE)

**ISSUE:** Ruff linting errors in `LLM-CONTEXT/review-anal/quality/run_quality_analysis.py`

**STATUS:** BLOCKING - Must fix before establishing baseline

**Impact:** Cannot run `make test` cleanly to establish baseline for fixes

**Root Cause:** Review analysis scripts have unused imports

**Fix Strategy:**
```bash
# Quick fix - these are analysis artifacts, not production code
cd /media/srv-main-softdev/projects/tools/check_zpools
python -m ruff check --fix LLM-CONTEXT/review-anal/quality/run_quality_analysis.py
```

**Specific Errors:**
1. Remove unused `import os` (line 8)
2. Remove unused `import re` (line 9)
3. Remove unused `typing.Set` (line 14)
4. Remove unused `typing.Tuple` (line 14)

**Evidence Requirements:**
- BEFORE: `ruff check` shows 4 errors
- AFTER: `ruff check` shows 0 errors

**Success Criteria:**
- `make test` completes successfully
- Baseline test results captured

**Rollback Trigger:**
- If fixes break analysis scripts, restore from git

**Effort:** 5 minutes
**Priority:** P0 (IMMEDIATE)

---

## Priority 1: HIGH PRIORITY ISSUES (Recommended)

### ISSUE-1: Reduce Critical Complexity in scripts/test.py:_run()

**Category:** Code Quality
**Severity:** HIGH
**Impact:** Maintenance difficulty, cognitive load for developers
**Current State:** Cyclomatic Complexity: 17, Cognitive Complexity: 20
**Target State:** CC < 10, CogC < 15

**Location:** `/media/srv-main-softdev/projects/tools/check_zpools/scripts/test.py:_run()`

**Root Cause Analysis:**
- Function has too many conditional branches
- Multiple validation paths intertwined
- 5 parameters increase branching
- Nested if-statements create cognitive overhead

**Fix Strategy:**

1. **Extract Validation Helper Functions**
   ```python
   def _validate_format_strict_param(format_strict: str | None) -> bool:
       """Validate and resolve STRICT_RUFF_FORMAT parameter."""
       # Extract 37-line validation logic

   def _validate_verbose_param(verbose: str | None) -> bool:
       """Validate and resolve TEST_VERBOSE parameter."""
       # Extract verbose parameter validation

   def _validate_coverage_param(coverage: str | None) -> str:
       """Validate and resolve coverage mode."""
       # Extract coverage parameter validation
   ```

2. **Refactor Main Function**
   ```python
   def _run(
       format_strict: str | None = None,
       verbose: str | None = None,
       coverage: str | None = None,
       skip_slow: bool = False,
       fail_under: int | None = None,
   ) -> tuple[bool, str]:
       """Run test suite with validated parameters."""
       # Use helper functions
       resolved_format_strict = _validate_format_strict_param(format_strict)
       resolved_verbose = _validate_verbose_param(verbose)
       resolved_coverage = _validate_coverage_param(coverage)

       # Simplified main logic
   ```

**Evidence Requirements:**

**BEFORE:**
```bash
# Run complexity analysis
radon cc scripts/test.py -s -a
# Expected: _run() shows CC=17, CogC=20

# Run tests to establish baseline
make test
# Expected: All tests pass
```

**AFTER:**
```bash
# Verify reduced complexity
radon cc scripts/test.py -s -a
# Expected: All functions CC < 10

# Verify functionality preserved
make test
# Expected: All tests pass, same results as baseline

# Verify no behavior changes
git diff scripts/test.py | grep -E "^\+.*if|^\+.*else|^\+.*elif"
# Expected: No new conditionals in main code path
```

**Success Criteria:**
1. ✅ `_run()` complexity reduced from CC=17 to CC < 10
2. ✅ Cognitive complexity reduced from 20 to < 15
3. ✅ All existing tests pass unchanged
4. ✅ No behavior changes (output identical)
5. ✅ Helper functions have clear single responsibilities
6. ✅ Code coverage maintained or improved

**Rollback Triggers:**
- If test results differ from baseline
- If test execution time increases >10%
- If any test starts failing
- If cognitive complexity increases

**Dependencies:**
- Must establish baseline test results first (PREREQUISITE)
- No dependencies on other fixes

**Effort:** 2-3 hours
**Priority:** P1 (High)
**Owner:** Development Team

---

### ISSUE-2: Update Outdated System Design Documentation

**Category:** Documentation
**Severity:** HIGH
**Impact:** Developer confusion, misleading architecture reference
**Current State:** `docs/systemdesign/module_reference.md` describes scaffold/template instead of ZFS monitoring
**Target State:** Accurate documentation of current ZFS monitoring architecture

**Location:** `/media/srv-main-softdev/projects/tools/check_zpools/docs/systemdesign/module_reference.md`

**Root Cause Analysis:**
- Documentation was not updated during refactoring from scaffold to ZFS monitoring
- Template/scaffold content still present from project initialization
- No process to validate docs against actual implementation

**Fix Strategy:**

**Option 1: Replace with Current Architecture (RECOMMENDED)**

Create new comprehensive module reference:

```markdown
# ZFS Monitoring System - Module Reference

## Core Modules

### zfs_client.py
**Purpose:** Interface to ZFS command-line tools
**Responsibilities:**
- Execute `zpool` commands
- Parse command output
- Handle ZFS-specific errors
**Dependencies:** subprocess, typing
**Tests:** test_zfs_client.py (25% coverage - requires ZFS)

### zfs_parser.py
**Purpose:** Parse ZFS JSON output into typed models
**Responsibilities:**
- Parse `zpool list -j` output
- Parse `zpool status -j` output
- Convert sizes to bytes (with LRU caching)
- Parse health states (with LRU caching)
**Dependencies:** models, typing, functools
**Tests:** test_zfs_parser.py (97% coverage)

### monitor.py
**Purpose:** Pool health monitoring and threshold checking
**Responsibilities:**
- Check pool capacity thresholds
- Check pool health states
- Check scrub age/status
- Check vdev errors
- Generate CheckResult objects
**Dependencies:** models, zfs_parser
**Tests:** test_monitor.py (100% coverage)

### alerting.py
**Purpose:** Alert generation and notification
**Responsibilities:**
- Format alert messages (plain text, HTML)
- Send email notifications
- Integrate with alert state tracking
- Support multiple email backends
**Dependencies:** models, mail, alert_state
**Tests:** test_alerting.py (91% coverage)

### daemon.py
**Purpose:** Background monitoring service
**Responsibilities:**
- Periodic pool checking
- Signal handling (SIGTERM, SIGINT)
- State persistence between runs
- Alert deduplication
**Dependencies:** behaviors, alert_state, threading
**Tests:** test_daemon.py (77% coverage)

### models.py
**Purpose:** Type-safe data structures
**Responsibilities:**
- Define PoolStatus (frozen dataclass)
- Define CheckResult (frozen dataclass)
- Define Enum vocabularies (PoolHealth, Severity)
- Ensure immutability and serializability
**Design Patterns:**
- Frozen dataclasses for immutability
- Enums for type-safe vocabularies
- LRU-cached enum methods
**Tests:** test_models.py (85% coverage)

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                         CLI Layer                        │
│                  (cli.py, __main__.py)                   │
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
         ┌───────────┼───────────┐
         │           │           │
         ▼           ▼           ▼
┌─────────────┐ ┌──────────┐ ┌────────────┐
│   Daemon    │ │ Monitor  │ │ Alerting   │
│ (daemon.py) │ │(monitor) │ │(alerting)  │
└─────────────┘ └──────────┘ └────────────┘
         │           │           │
         │           ▼           ▼
         │     ┌──────────┐ ┌──────────┐
         │     │ZFS Parser│ │   Mail   │
         │     │(parser)  │ │  (mail)  │
         │     └──────────┘ └──────────┘
         │           │
         ▼           ▼
    ┌──────────┐ ┌──────────┐
    │  State   │ │  Models  │
    │(alert_   │ │(models)  │
    │ state)   │ │          │
    └──────────┘ └──────────┘
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
```

**Option 2: Archive and Create New**

```bash
# Rename old file
mv docs/systemdesign/module_reference.md \
   docs/systemdesign/module_reference.SCAFFOLD_ARCHIVE.md

# Create new file
touch docs/systemdesign/module_reference.md
# Add content from Option 1
```

**Evidence Requirements:**

**BEFORE:**
```bash
# Capture current state
grep -n "scaffold\|template\|hello" docs/systemdesign/module_reference.md
# Expected: Multiple matches to scaffold/template content

# Check what modules are mentioned
grep -n "zfs_client\|zfs_parser\|monitor\|alerting\|daemon" docs/systemdesign/module_reference.md
# Expected: Few or no matches
```

**AFTER:**
```bash
# Verify new content
grep -n "zfs_client\|zfs_parser\|monitor\|alerting\|daemon" docs/systemdesign/module_reference.md
# Expected: All core modules documented

# Verify no scaffold references
grep -n "scaffold\|template\|hello" docs/systemdesign/module_reference.md
# Expected: Zero matches

# Verify completeness
ls src/check_zpools/*.py | wc -l
grep -c "^### " docs/systemdesign/module_reference.md
# Expected: Count should match (all modules documented)
```

**Success Criteria:**
1. ✅ All 7 core modules documented (zfs_client, zfs_parser, monitor, alerting, daemon, models, behaviors)
2. ✅ Zero references to scaffold/template/hello
3. ✅ Architecture diagram present and accurate
4. ✅ Responsibilities clearly defined for each module
5. ✅ Dependencies documented
6. ✅ Test coverage mentioned
7. ✅ Design patterns explained (frozen dataclasses, LRU caching)

**Rollback Triggers:**
- If documentation is factually incorrect
- If missing critical modules

**Dependencies:**
- None

**Effort:** 2-3 hours
**Priority:** P1 (High)
**Owner:** Development Team

---

## Priority 2: MEDIUM PRIORITY ISSUES (Suggested)

### ISSUE-3: Reduce Code Duplication (131 blocks, ~1,350 lines)

**Category:** Code Quality
**Severity:** MEDIUM
**Impact:** Maintenance overhead, inconsistent patterns, tech debt
**Current State:** 131 duplicate blocks, ~1,350 duplicate lines
**Target State:** <50 duplicate blocks, <500 duplicate lines

**Root Cause Analysis:**
- Test fixtures duplicated across test files
- CLI argument patterns repeated
- Configuration extraction logic duplicated
- Error handling patterns repeated

**Fix Strategy:**

**Phase 1: Extract Test Fixtures to conftest.py**

```python
# tests/conftest.py

@pytest.fixture
def sample_pool_status() -> PoolStatus:
    """Standard PoolStatus for testing."""
    return PoolStatus(
        name="tank",
        health=PoolHealth.ONLINE,
        size=1000000000000,
        allocated=500000000000,
        free=500000000000,
        capacity=50,
        fragmentation=5,
        # ... etc
    )

@pytest.fixture
def sample_check_result_ok() -> CheckResult:
    """CheckResult with OK status."""
    return CheckResult(
        severity=Severity.OK,
        message="All checks passed",
        details={},
    )

@pytest.fixture
def sample_check_result_warning() -> CheckResult:
    """CheckResult with WARNING status."""
    return CheckResult(
        severity=Severity.WARNING,
        message="Capacity above threshold",
        details={"capacity": 85},
    )

@pytest.fixture
def mock_email_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock email configuration environment variables."""
    monkeypatch.setenv("CHECK_ZPOOLS_EMAIL_SMTP_HOSTS", "localhost:1025")
    monkeypatch.setenv("CHECK_ZPOOLS_EMAIL_FROM_ADDRESS", "test@example.com")
    # ... etc
```

**Phase 2: Create Shared CLI Decorators**

```python
# src/check_zpools/cli_decorators.py

def email_options(func):
    """Common email CLI options."""
    func = click.option("--to", multiple=True, help="Recipient email")(func)
    func = click.option("--subject", help="Email subject")(func)
    func = click.option("--body", help="Email body")(func)
    return func

# Usage in cli.py:
@cli.command()
@email_options
def send_email(to, subject, body):
    ...
```

**Phase 3: Centralize Configuration Extraction**

```python
# src/check_zpools/config_utils.py

def extract_email_config(config: dict) -> dict:
    """Extract email configuration with validation."""
    email_section = config.get("email", {})
    # Common extraction logic
    return {
        "smtp_hosts": email_section.get("smtp_hosts"),
        "from_address": email_section.get("from_address"),
        # ... etc
    }
```

**Phase 4: Create Error Handling Wrappers**

```python
# src/check_zpools/error_handlers.py

def with_email_error_handling(func):
    """Decorator for consistent email error handling."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except EmailConfigurationError as e:
            logger.error(f"Email configuration error: {e}")
            raise
        except SMTPError as e:
            logger.error(f"SMTP error: {e}")
            raise
    return wrapper
```

**Evidence Requirements:**

**BEFORE:**
```bash
# Run duplication analysis
python LLM-CONTEXT/review-anal/quality/check_duplication.py

# Expected output:
# Duplicate blocks: 131
# Estimated duplicate lines: ~1,350

# Count PoolStatus creations in tests
grep -r "PoolStatus(" tests/ | wc -l
# Expected: 10+ duplicates

# Count config extraction patterns
grep -rn "config.get.*email" src/ | wc -l
# Expected: 4+ duplicates
```

**AFTER:**
```bash
# Verify reduced duplication
python LLM-CONTEXT/review-anal/quality/check_duplication.py

# Expected:
# Duplicate blocks: <50 (reduction of >60%)
# Estimated duplicate lines: <500

# Verify fixture usage
grep -r "sample_pool_status" tests/ | wc -l
# Expected: Multiple uses of shared fixture

# Verify centralized config
grep -rn "extract_email_config" src/ | wc -l
# Expected: Single definition, multiple usages

# Verify all tests still pass
make test
# Expected: All tests pass
```

**Success Criteria:**
1. ✅ Duplicate blocks reduced from 131 to <50 (>60% reduction)
2. ✅ Duplicate lines reduced from ~1,350 to <500 (>60% reduction)
3. ✅ All test fixtures centralized in conftest.py
4. ✅ All tests pass with same coverage
5. ✅ No new pylint/ruff warnings
6. ✅ Code more maintainable (single source of truth)

**Rollback Triggers:**
- If test coverage decreases
- If any tests fail
- If new linting errors appear
- If refactoring introduces bugs

**Dependencies:**
- None (can be done incrementally)

**Effort:** 8-12 hours (can split across phases)
**Priority:** P2 (Medium)
**Owner:** Development Team

---

### ISSUE-4: Break Up Long Functions (46 functions >50 lines)

**Category:** Code Quality
**Severity:** MEDIUM
**Impact:** Code comprehension, maintainability
**Current State:** 46 functions exceed 50 lines, longest is 238 lines
**Target State:** All functions <50 lines (except well-justified cases)

**Top Functions to Refactor:**

1. **scripts/test.py:run_tests()** - 238 lines
2. **src/check_zpools/mail.py:send_email()** - 119 lines
3. **src/check_zpools/behaviors.py:run_daemon()** - 108 lines
4. **src/check_zpools/service_install.py:install_service()** - 103 lines
5. **src/check_zpools/cli.py:cli_send_email()** - 103 lines

**Fix Strategy (Example: scripts/test.py:run_tests())**

**Current Structure (238 lines):**
```python
def run_tests(...):
    # 1. Metadata sync (10 lines)
    # 2. Format check (15 lines)
    # 3. Lint check (10 lines)
    # 4. Import linter (10 lines)
    # 5. Type check (15 lines)
    # 6. Security scan (20 lines)
    # 7. pip-audit (40 lines)
    # 8. pytest (50 lines)
    # 9. Coverage upload (30 lines)
    # 10. Summary (20 lines)
```

**Proposed Structure:**
```python
def run_tests(...) -> None:
    """Run full test suite - orchestrator function."""
    # Each step becomes a function call (10-20 lines total)
    _sync_metadata()
    _run_format_checks(format_strict)
    _run_lint_checks()
    _run_import_linter()
    _run_type_checks()
    _run_security_scans()
    _run_vulnerability_audit(pip_audit_ignore)
    test_results = _run_pytest_with_coverage(verbose, coverage, fail_under)
    _upload_coverage_if_applicable(test_results, coverage)
    _print_summary(test_results)

def _sync_metadata() -> None:
    """Synchronize metadata module before testing."""
    # 10 lines

def _run_format_checks(strict: bool) -> None:
    """Run Ruff format checks."""
    # 15 lines

# ... etc for each step
```

**Evidence Requirements:**

**BEFORE:**
```bash
# Measure function lengths
grep -n "^def " scripts/test.py | while read line; do
    echo "$line"
done

# Count lines in run_tests
sed -n '/^def run_tests/,/^def /p' scripts/test.py | wc -l
# Expected: 238 lines

# Run baseline tests
make test
# Expected: All pass
```

**AFTER:**
```bash
# Verify no functions >50 lines in test.py
python -c "
import ast
with open('scripts/test.py') as f:
    tree = ast.parse(f.read())
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef):
        length = node.end_lineno - node.lineno
        if length > 50:
            print(f'{node.name}: {length} lines')
"
# Expected: No output (all functions <50 lines)

# Verify tests still pass
make test
# Expected: All pass, identical results to baseline

# Verify no complexity increase
radon cc scripts/test.py -a
# Expected: Average complexity same or lower
```

**Success Criteria:**
1. ✅ scripts/test.py:run_tests() reduced from 238 to <50 lines
2. ✅ All extracted functions have single responsibility
3. ✅ All tests pass unchanged
4. ✅ Test execution time unchanged (±5%)
5. ✅ No increase in cyclomatic complexity
6. ✅ Code more readable and maintainable

**Rollback Triggers:**
- If tests fail
- If execution time increases >10%
- If complexity increases
- If bugs introduced

**Dependencies:**
- ISSUE-1 (complexity reduction in _run) can be done in parallel

**Effort:** 4-6 hours
**Priority:** P2 (Medium)
**Owner:** Development Team

---

### ISSUE-5: Expand DEVELOPMENT.md Testing Documentation

**Category:** Documentation
**Severity:** MEDIUM
**Impact:** New contributor onboarding difficulty
**Current State:** Testing section is minimal, scattered
**Target State:** Comprehensive testing guide

**Fix Strategy:**

Add dedicated "## Testing" section to DEVELOPMENT.md:

```markdown
## Testing

### Quick Start

```bash
# Run full test suite
make test

# Run tests only (skip linting/type checking)
pytest

# Run specific test file
pytest tests/test_monitor.py

# Run specific test
pytest tests/test_monitor.py::test_check_capacity_ok

# Run with verbose output
TEST_VERBOSE=1 make test
```

### Test Organization

```
tests/
├── conftest.py              # Shared fixtures and configuration
├── test_alerting.py         # Alert generation and notification
├── test_behaviors.py        # High-level behavior tests
├── test_cli.py              # CLI command tests
├── test_config.py           # Configuration loading tests
├── test_daemon.py           # Daemon mode tests
├── test_formatters.py       # Output formatting tests
├── test_mail.py             # Email functionality tests
├── test_models.py           # Data model tests
├── test_monitor.py          # Pool monitoring logic tests
├── test_zfs_client.py       # ZFS command execution tests
└── test_zfs_parser.py       # ZFS output parsing tests
```

### Test Categories

#### Unit Tests
Focus on individual functions/classes in isolation.

Example:
```python
def test_check_capacity_ok(sample_pool_status):
    """Test capacity check when under threshold."""
    config = MonitorConfig(capacity_threshold=80)
    result = check_capacity(sample_pool_status, config)
    assert result.severity == Severity.OK
```

#### Integration Tests
Test interactions between components.

Example:
```python
def test_email_alert_end_to_end(mock_smtp_server, sample_pool_status):
    """Test full alert flow from check to email."""
    # Setup
    config = load_config()
    # Execute
    result = check_pools([sample_pool_status], config)
    send_alert(result, config)
    # Verify
    assert mock_smtp_server.messages_sent == 1
```

#### CLI Tests
Test command-line interface.

Example:
```python
def test_cli_check_command(runner, monkeypatch):
    """Test 'check' command."""
    monkeypatch.setenv("CHECK_ZPOOLS_CONFIG", "/tmp/test.toml")
    result = runner.invoke(cli, ["check"])
    assert result.exit_code == 0
```

### Fixtures

Shared test fixtures are defined in `tests/conftest.py`:

- `sample_pool_status`: Standard PoolStatus for testing
- `sample_check_result_ok`: CheckResult with OK status
- `sample_check_result_warning`: CheckResult with WARNING
- `mock_email_config`: Mocked email configuration
- `mock_smtp_server`: Fake SMTP server for testing

Usage:
```python
def test_something(sample_pool_status):
    # Use fixture
    assert sample_pool_status.health == PoolHealth.ONLINE
```

### Mocking Patterns

#### Mock ZFS Commands
```python
def test_zfs_parsing(monkeypatch):
    mock_output = '{"pool": "tank", "health": "ONLINE"}'
    monkeypatch.setattr(
        "check_zpools.zfs_client.run_zpool_command",
        lambda *args: mock_output
    )
```

#### Mock Configuration
```python
def test_with_config(monkeypatch):
    monkeypatch.setenv("CHECK_ZPOOLS_EMAIL_SMTP_HOSTS", "localhost:1025")
    config = get_config()
    assert config.email.smtp_hosts == "localhost:1025"
```

### Coverage Requirements

- **Minimum:** 60% (enforced by `make test`)
- **Target:** 70% (Codecov PR checks)
- **Current:** 76.72%

Check coverage:
```bash
make coverage
# Opens HTML report in browser
```

### Running Specific Test Types

```bash
# Run only unit tests
pytest tests/ -m "not integration"

# Run only integration tests
pytest tests/ -m integration

# Skip slow tests
pytest tests/ -m "not slow"
```

### Debugging Tests

```bash
# Run with debugger on failure
pytest --pdb

# Show print statements
pytest -s

# Verbose output
pytest -vv

# Show all test output
pytest -vv -s
```

### Writing New Tests

1. **Follow naming convention:** `test_<function>_<scenario>.py`
2. **Use descriptive test names:** `test_check_capacity_exceeds_threshold_returns_warning`
3. **Arrange-Act-Assert pattern:**
   ```python
   def test_something():
       # Arrange - setup
       config = MonitorConfig(capacity_threshold=80)

       # Act - execute
       result = check_capacity(pool, config)

       # Assert - verify
       assert result.severity == Severity.WARNING
   ```
4. **Use fixtures for setup:** Prefer fixtures over setup code in tests
5. **Test one thing:** Each test should verify one behavior
6. **Add docstrings:** Explain what the test verifies

### Continuous Integration

Tests run automatically on:
- Every push to GitHub
- Every pull request
- Daily at 3:17 AM UTC
- Multiple platforms (Linux, macOS, Windows)
- Multiple Python versions (3.13, 3.x)

See `.github/workflows/ci.yml` for details.
```

**Evidence Requirements:**

**BEFORE:**
```bash
# Check current testing documentation
grep -n "^## Test" DEVELOPMENT.md
# Expected: Minimal or no testing section

# Count testing examples
grep -c "pytest" DEVELOPMENT.md
# Expected: Few or zero examples
```

**AFTER:**
```bash
# Verify comprehensive testing section
grep -n "^## Testing" DEVELOPMENT.md
# Expected: Section found

# Count testing examples
grep -c "pytest\|```python" DEVELOPMENT.md
# Expected: 10+ examples

# Verify coverage requirements mentioned
grep "60%\|70%" DEVELOPMENT.md
# Expected: Both thresholds documented

# Verify test categories documented
grep -E "Unit Tests|Integration Tests|CLI Tests" DEVELOPMENT.md
# Expected: All three categories present
```

**Success Criteria:**
1. ✅ Dedicated "## Testing" section added
2. ✅ Quick start commands documented
3. ✅ Test organization explained
4. ✅ Test categories defined (unit, integration, CLI)
5. ✅ Fixture usage explained with examples
6. ✅ Mocking patterns documented
7. ✅ Coverage requirements stated
8. ✅ Debugging tips provided
9. ✅ Writing new tests guide included
10. ✅ CI integration mentioned

**Rollback Triggers:**
- If documentation is factually incorrect
- If examples don't work

**Dependencies:**
- ISSUE-3 (if fixtures are refactored, update docs accordingly)

**Effort:** 1-2 hours
**Priority:** P2 (Medium)
**Owner:** Development Team

---

### ISSUE-6: Add Pre-Commit Hooks

**Category:** CI/CD
**Severity:** MEDIUM
**Impact:** Developers can commit without local validation
**Current State:** No `.pre-commit-config.yaml`
**Target State:** Active pre-commit hooks running Ruff, basic checks

**Fix Strategy:**

Create `.pre-commit-config.yaml`:

```yaml
# .pre-commit-config.yaml
default_install_hook_types: [pre-commit, commit-msg]
default_stages: [pre-commit]

repos:
  # Ruff - Fast Python linter and formatter
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.14.5
    hooks:
      - id: ruff
        args: [--fix]
        name: Ruff linter (auto-fix)
      - id: ruff-format
        name: Ruff formatter

  # Pre-commit hooks for basic checks
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
        name: Trim trailing whitespace
      - id: end-of-file-fixer
        name: Fix end of files
      - id: check-yaml
        name: Check YAML syntax
      - id: check-toml
        name: Check TOML syntax
      - id: check-added-large-files
        args: [--maxkb=1000]
        name: Check for large files
      - id: check-merge-conflict
        name: Check for merge conflicts
      - id: check-case-conflict
        name: Check for case conflicts
      - id: mixed-line-ending
        args: [--fix=lf]
        name: Fix line endings

  # Optional: Commit message format checking
  - repo: https://github.com/compilerla/conventional-pre-commit
    rev: v3.2.0
    hooks:
      - id: conventional-pre-commit
        stages: [commit-msg]
        name: Check commit message format
```

Update `pyproject.toml` to include pre-commit in dev dependencies:

```toml
[project.optional-dependencies]
dev = [
    # ... existing deps ...
    "pre-commit>=3.6.0",
]
```

Update `DEVELOPMENT.md`:

```markdown
## Git Hooks

This project uses pre-commit hooks to ensure code quality before committing.

### Setup

```bash
# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install --install-hooks

# Install commit-msg hook (for conventional commits)
pre-commit install --hook-type commit-msg
```

### Usage

Hooks run automatically on `git commit`. To run manually:

```bash
# Run on all files
pre-commit run --all-files

# Run specific hook
pre-commit run ruff --all-files

# Skip hooks (not recommended)
git commit --no-verify
```

### Hooks Enabled

- **Ruff linter:** Auto-fixes common issues
- **Ruff formatter:** Ensures consistent code style
- **Trailing whitespace:** Removes trailing spaces
- **End of file fixer:** Ensures files end with newline
- **YAML/TOML check:** Validates config files
- **Large file check:** Prevents accidental large file commits
- **Merge conflict check:** Detects unresolved merge conflicts
- **Conventional commits:** Validates commit message format
```

**Evidence Requirements:**

**BEFORE:**
```bash
# Check for pre-commit config
ls -la .pre-commit-config.yaml
# Expected: File not found

# Check if hooks are installed
ls -la .git/hooks/pre-commit
# Expected: Only sample file or not found

# Check dev dependencies
grep "pre-commit" pyproject.toml
# Expected: Not found
```

**AFTER:**
```bash
# Verify config exists
ls -la .pre-commit-config.yaml
# Expected: File exists

# Verify hooks installed
pre-commit install
ls -la .git/hooks/pre-commit
# Expected: Executable hook installed

# Test hooks
pre-commit run --all-files
# Expected: All hooks pass on current code

# Test commit with issues
echo "trailing space  " >> test_file.py
git add test_file.py
git commit -m "test"
# Expected: Hook removes trailing space, commit succeeds

# Verify documented
grep "pre-commit" DEVELOPMENT.md
# Expected: Setup instructions present
```

**Success Criteria:**
1. ✅ `.pre-commit-config.yaml` created
2. ✅ Ruff hooks configured (lint + format)
3. ✅ Basic checks configured (whitespace, YAML, etc.)
4. ✅ Documented in DEVELOPMENT.md
5. ✅ Added to dev dependencies
6. ✅ All hooks pass on current codebase
7. ✅ Hooks run automatically on commit

**Rollback Triggers:**
- If hooks break existing workflow
- If hooks are too slow (>5 seconds)
- If false positives occur

**Dependencies:**
- None

**Effort:** 1 hour
**Priority:** P2 (Medium)
**Owner:** Development Team

---

### ISSUE-7: Add models.py to CODE_ARCHITECTURE.md

**Category:** Documentation
**Severity:** MEDIUM
**Impact:** Developers may not understand immutability patterns
**Current State:** models.py not documented in architecture guide
**Target State:** Comprehensive models.py section

**Fix Strategy:**

Add section to `CODE_ARCHITECTURE.md`:

```markdown
## Module: models.py

### Purpose
Defines immutable, type-safe data structures for ZFS pool information and check results.

### Location
`src/check_zpools/models.py`

### Responsibilities
1. Define `PoolStatus` frozen dataclass
2. Define `CheckResult` frozen dataclass
3. Define `PoolHealth` enum vocabulary
4. Define `Severity` enum vocabulary
5. Provide LRU-cached enum comparison methods

### Design Patterns

#### Frozen Dataclasses
All dataclasses use `frozen=True` to ensure immutability:

```python
@dataclass(frozen=True)
class PoolStatus:
    """Immutable representation of ZFS pool status."""
    name: str
    health: PoolHealth
    size: int
    allocated: int
    free: int
    # ...
```

**Benefits:**
- Thread-safe by default
- Hashable (can use as dict keys)
- Prevents accidental mutation
- Signals intent: "this is data, not behavior"

#### Type-Safe Enums
Enums provide controlled vocabularies:

```python
class PoolHealth(Enum):
    """Valid ZFS pool health states."""
    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    FAULTED = "FAULTED"
    OFFLINE = "OFFLINE"
    UNAVAIL = "UNAVAIL"
    REMOVED = "REMOVED"
```

**Benefits:**
- Compile-time type checking
- Auto-completion in IDEs
- Prevents invalid values
- Self-documenting

#### LRU-Cached Comparisons
Enum comparison methods use `@lru_cache` for performance:

```python
class PoolHealth(Enum):
    @lru_cache(maxsize=4)
    def is_healthy(self) -> bool:
        """Check if pool is healthy (ONLINE only)."""
        return self == PoolHealth.ONLINE

    @lru_cache(maxsize=6)
    def is_degraded_or_worse(self) -> bool:
        """Check if pool is degraded or worse."""
        return self in (
            PoolHealth.DEGRADED,
            PoolHealth.FAULTED,
            PoolHealth.UNAVAIL,
        )
```

**Rationale:**
- These methods are called repeatedly in monitoring loops
- Results are deterministic (same input → same output)
- Cache size matches number of enum values
- 16-28x speedup measured in profiling

### Type Safety

All fields have explicit type hints:

```python
@dataclass(frozen=True)
class CheckResult:
    severity: Severity           # Enum type
    message: str                 # Built-in type
    details: dict[str, Any]      # Generic type
    timestamp: str | None = None # Union type with default
```

**Enforced by:**
- Pyright strict mode (CI)
- 100% type hint coverage
- PEP 561 py.typed marker

### Serializability

Dataclasses are easily serializable:

```python
# To dict
result_dict = asdict(check_result)

# To JSON
json.dumps(asdict(check_result))

# From dict
check_result = CheckResult(**result_dict)
```

**Used for:**
- State persistence (daemon mode)
- Logging structured data
- API responses (future)

### Testing

Tests: `tests/test_models.py` (85% coverage)

**Covered:**
- Dataclass immutability
- Enum comparison methods
- Type validation
- Serialization/deserialization
- Edge cases (None values, empty dicts)

**Not covered:**
- Some enum combinations (acceptable - exhaustive testing not needed)

### Usage Examples

#### Creating Pool Status

```python
from check_zpools.models import PoolStatus, PoolHealth

pool = PoolStatus(
    name="tank",
    health=PoolHealth.ONLINE,
    size=1000000000000,
    allocated=500000000000,
    free=500000000000,
    capacity=50,
    fragmentation=5,
)
```

#### Checking Pool Health

```python
if pool.health.is_healthy():
    print("Pool is healthy!")
elif pool.health.is_degraded_or_worse():
    send_alert(f"Pool {pool.name} is {pool.health.value}")
```

#### Creating Check Results

```python
from check_zpools.models import CheckResult, Severity

result = CheckResult(
    severity=Severity.WARNING,
    message=f"Pool capacity at {pool.capacity}%",
    details={"pool": pool.name, "capacity": pool.capacity},
)
```

### Dependencies

**Imports:**
- `dataclasses`: Standard library (frozen dataclasses)
- `enum`: Standard library (Enum base class)
- `functools`: Standard library (lru_cache)
- `typing`: Standard library (type hints)

**Used by:**
- `zfs_parser.py`: Constructs PoolStatus from ZFS output
- `monitor.py`: Creates CheckResult objects
- `alerting.py`: Formats CheckResult for alerts
- `daemon.py`: Serializes state for persistence
- All test files: Test data construction

### Design Decisions

#### Why Frozen Dataclasses?

**Alternative 1: Regular Dataclasses**
- ❌ Mutable by default
- ❌ Not hashable
- ❌ Risk of accidental mutation

**Alternative 2: NamedTuples**
- ✅ Immutable
- ✅ Hashable
- ❌ Less readable syntax
- ❌ No default values
- ❌ Limited type checking

**Alternative 3: Pydantic Models**
- ✅ Immutable (with frozen=True)
- ✅ Strong validation
- ❌ Heavier dependency
- ❌ Slower performance
- ❌ Overkill for simple models

**Chosen: Frozen Dataclasses**
- ✅ Immutable
- ✅ Hashable
- ✅ Readable syntax
- ✅ Standard library (no deps)
- ✅ Full type checking
- ✅ Fast performance

#### Why LRU Cache on Enums?

Profiling showed enum methods called 1000s of times per monitoring cycle:

```
Without cache:   is_healthy() called 1,200 times → 0.012ms
With cache:      is_healthy() called 1,200 times → 0.0007ms (16x faster)
```

Cache size matches enum cardinality:
- `PoolHealth`: 6 values → maxsize=6
- `Severity`: 4 values → maxsize=4

### Future Enhancements

**Potential additions:**
1. Validation in `__post_init__`:
   ```python
   def __post_init__(self):
       if self.capacity < 0 or self.capacity > 100:
           raise ValueError(f"Invalid capacity: {self.capacity}")
   ```

2. Computed properties:
   ```python
   @property
   def capacity_percentage(self) -> str:
       return f"{self.capacity}%"
   ```

3. JSON schema generation for API documentation

**Current stance:**
- Keep models simple (data, not behavior)
- Validation belongs in parsing layer (zfs_parser.py)
- Computed properties only if widely used

### Maintenance

**When adding new fields:**
1. Add to dataclass definition with type hint
2. Add to parser (zfs_parser.py)
3. Add tests for new field
4. Update this documentation

**When adding new enums:**
1. Define enum class with all values
2. Add LRU-cached comparison methods if needed
3. Add tests for enum methods
4. Update parser to use new enum
5. Document in this section
```

**Evidence Requirements:**

**BEFORE:**
```bash
# Check if models.py is documented
grep -n "models.py" CODE_ARCHITECTURE.md
# Expected: Not found or minimal mention

# Check coverage of architecture doc
ls src/check_zpools/*.py | wc -l
grep -c "^## Module:" CODE_ARCHITECTURE.md
# Expected: 6/7 modules documented (models missing)
```

**AFTER:**
```bash
# Verify models.py section exists
grep -n "^## Module: models.py" CODE_ARCHITECTURE.md
# Expected: Section found

# Verify key concepts documented
grep -E "frozen dataclass|LRU cache|immutability" CODE_ARCHITECTURE.md
# Expected: All concepts mentioned

# Verify examples provided
grep -c "```python" CODE_ARCHITECTURE.md | awk '{print $1 + 0}'
# Expected: Increased from before (14 → 20+)

# Verify all modules documented
ls src/check_zpools/*.py | wc -l
grep -c "^## Module:" CODE_ARCHITECTURE.md
# Expected: Equal (7/7 modules documented)
```

**Success Criteria:**
1. ✅ models.py section added to CODE_ARCHITECTURE.md
2. ✅ Frozen dataclass pattern explained
3. ✅ Enum vocabulary pattern explained
4. ✅ LRU caching rationale documented
5. ✅ Type safety benefits explained
6. ✅ Serializability covered
7. ✅ Usage examples provided (3+)
8. ✅ Design decisions justified
9. ✅ Dependencies listed
10. ✅ Testing coverage mentioned

**Rollback Triggers:**
- If documentation is factually incorrect
- If examples don't compile

**Dependencies:**
- None

**Effort:** 1 hour
**Priority:** P2 (Medium)
**Owner:** Development Team

---

### ISSUE-8: Enhance GitHub Release Notes

**Category:** CI/CD
**Severity:** MEDIUM
**Impact:** Release notes lack detail, user experience
**Current State:** Basic release notes ("Release vX.Y.Z")
**Target State:** Release notes extracted from CHANGELOG.md

**Fix Strategy:**

Update `scripts/_utils.py` to extract CHANGELOG entries:

```python
def extract_changelog_entry(version: str) -> str:
    """
    Extract CHANGELOG.md entry for specified version.

    Args:
        version: Semver version (e.g., "2.1.8")

    Returns:
        Changelog entry for version, or generic message if not found

    Example:
        >>> extract_changelog_entry("2.1.8")
        '### Fixed\\n- Bug fix in parser\\n### Added\\n- New feature'
    """
    changelog = Path("CHANGELOG.md")
    if not changelog.exists():
        return f"Release {version}"

    text = changelog.read_text(encoding="utf-8")

    # Match section: ## [version] - date
    # Capture until next ## [ or end of file
    pattern = rf"## \[{re.escape(version)}\][^\n]*\n(.*?)(?=## \[|$)"
    match = re.search(pattern, text, re.DOTALL)

    if match:
        entry = match.group(1).strip()
        # Clean up entry
        entry = entry.replace("### ", "## ")  # Adjust heading levels for GitHub
        return entry

    return f"Release {version}"
```

Update `scripts/release.py` to use extracted entries:

```python
def _create_github_release(tag: str, version: str) -> None:
    """Create GitHub release with CHANGELOG entry."""
    from ._utils import gh_release_create, extract_changelog_entry

    # Extract CHANGELOG entry
    body = extract_changelog_entry(version)

    # Add footer
    body += "\n\n---\n\n"
    body += f"**Full Changelog**: {get_compare_url(version)}\n"
    body += f"**Package**: [PyPI]({get_pypi_url(version)})\n"

    # Create release
    gh_release_create(
        tag=tag,
        title=f"Release {tag}",
        body=body,
        draft=False,
        prerelease=False,
    )

def get_compare_url(version: str) -> str:
    """Get GitHub compare URL for version."""
    # Parse repository URL from pyproject.toml
    metadata = get_project_metadata()
    repo_url = metadata.urls.get("Repository", "")
    if not repo_url:
        return ""
    return f"{repo_url}/compare/v{get_previous_version(version)}...v{version}"

def get_pypi_url(version: str) -> str:
    """Get PyPI package URL."""
    metadata = get_project_metadata()
    name = metadata.name
    return f"https://pypi.org/project/{name}/{version}/"

def get_previous_version(version: str) -> str:
    """Get previous git tag version."""
    result = run(["git", "describe", "--abbrev=0", "--tags", f"v{version}^"])
    if result.success and result.stdout:
        return result.stdout.strip().lstrip("v")
    return "0.0.0"
```

**Evidence Requirements:**

**BEFORE:**
```bash
# Check current release script
grep -A5 "gh_release_create" scripts/release.py
# Expected: Basic call with simple message

# Check for changelog extraction function
grep "extract_changelog" scripts/_utils.py
# Expected: Not found

# Check latest release on GitHub
gh release view --json body --jq .body
# Expected: Simple "Release vX.Y.Z" message
```

**AFTER:**
```bash
# Verify changelog extraction function
grep -A20 "def extract_changelog_entry" scripts/_utils.py
# Expected: Function found with regex matching

# Test function
python -c "
from scripts._utils import extract_changelog_entry
print(extract_changelog_entry('2.1.8'))
"
# Expected: Actual changelog content printed

# Create test release
make bump-patch
make release
gh release view --json body --jq .body
# Expected: CHANGELOG entry + footer with links

# Verify links work
gh release view --json body --jq .body | grep -E "Full Changelog|PyPI"
# Expected: Both links present and valid
```

**Success Criteria:**
1. ✅ `extract_changelog_entry()` function created
2. ✅ Release script uses CHANGELOG content
3. ✅ Release notes include version-specific changes
4. ✅ Release notes include comparison link
5. ✅ Release notes include PyPI link
6. ✅ Handles missing CHANGELOG.md gracefully
7. ✅ Handles missing version entry gracefully

**Rollback Triggers:**
- If release creation fails
- If changelog extraction errors
- If links are broken

**Dependencies:**
- None

**Effort:** 2 hours
**Priority:** P2 (Medium)
**Owner:** Development Team

---

### ISSUE-9: Align Coverage Targets

**Category:** CI/CD
**Severity:** MEDIUM
**Impact:** Confusion between 60% minimum and 70% target
**Current State:** pyproject.toml has 60%, codecov.yml has 70%
**Target State:** Documented difference or aligned values

**Fix Strategy:**

**Option 1: Document the Difference (RECOMMENDED)**

Update `pyproject.toml`:

```toml
[tool.coverage.report]
omit = ["tests/*"]
fail_under = 60  # Local minimum (failing threshold)
show_missing = true

# Note: Codecov target is 70% (aspirational goal)
# Local 60% allows some flexibility for rapid iteration
# CI enforces higher 70% standard for PR approval
```

Update `DEVELOPMENT.md`:

```markdown
### Coverage Requirements

The project has two coverage thresholds:

1. **Local Minimum (60%)**: Enforced by `make test`
   - Prevents commits with very low coverage
   - Allows flexibility for rapid development
   - Failing threshold for local testing

2. **CI Target (70%)**: Enforced by Codecov
   - Higher standard for production code
   - Required for PR approval
   - Aspirational goal for the project

**Current coverage:** 76.72% (exceeds both thresholds)

**Why two thresholds?**
- Local 60% allows developers to iterate quickly
- CI 70% ensures production code meets higher quality bar
- Gap provides room for experimental code locally
```

**Option 2: Raise Local Minimum to 70%**

```toml
[tool.coverage.report]
fail_under = 70  # Match Codecov target
```

**Pros:**
- Simpler (one threshold)
- Higher quality enforcement

**Cons:**
- Stricter local requirements
- May slow down development

**Option 3: Lower Codecov Target to 60%**

```yaml
# codecov.yml
coverage:
  status:
    project:
      default:
        target: 60%  # Match local minimum
```

**Pros:**
- Simpler (one threshold)
- More flexible

**Cons:**
- Lower quality bar
- Current coverage is 76.72%, so this is unnecessary

**Evidence Requirements:**

**BEFORE:**
```bash
# Check local threshold
grep "fail_under" pyproject.toml
# Expected: fail_under = 60

# Check CI threshold
grep "target:" codecov.yml
# Expected: target: 70%

# Check documentation
grep -E "60%|70%" DEVELOPMENT.md
# Expected: Not explained
```

**AFTER (Option 1):**
```bash
# Verify documented
grep -A10 "Coverage Requirements" DEVELOPMENT.md
# Expected: Both thresholds explained

# Verify still works
make test
# Expected: Passes (coverage above 60%)

# Verify Codecov still checks
grep "target: 70%" codecov.yml
# Expected: Still 70%
```

**Success Criteria:**
1. ✅ Coverage thresholds documented in DEVELOPMENT.md
2. ✅ Rationale for two thresholds explained
3. ✅ Current coverage mentioned
4. ✅ Both thresholds clearly stated
5. ✅ No confusion for new contributors

**Rollback Triggers:**
- If documentation is confusing
- If decision is changed to single threshold

**Dependencies:**
- None

**Effort:** 30 minutes
**Priority:** P2 (Medium)
**Owner:** Development Team

---

### ISSUE-10: Reduce High-Complexity Functions (6 functions)

**Category:** Code Quality
**Severity:** MEDIUM
**Impact:** Maintenance difficulty
**Current State:** 6 functions with CC >10 (in addition to _run with CC=17)
**Target State:** All functions with CC <10

**Functions to Refactor:**

1. **scripts/_utils.py:bootstrap_dev()** - CC: 14, CogC: 17
2. **scripts/test.py:_upload_coverage_report()** - CC: 13
3. **scripts/test.py:_pip_audit_guarded()** - CC: 12, CogC: 17
4. **scripts/test.py:run_tests()** - CC: 12
5. **scripts/menu.py:_gather_values()** - CC: 11
6. **scripts/push.py:_resolve_commit_message()** - CC: 11

**Fix Strategy (Example: _pip_audit_guarded)**

**Current Structure (CC=12, CogC=17):**
```python
def _pip_audit_guarded(ignore_list: tuple[str, ...]) -> None:
    """Run pip-audit with known ignores."""
    # 1. Prepare command (3 branches)
    # 2. Run audit (2 branches)
    # 3. Parse JSON (4 branches)
    # 4. Check for new vulns (3 branches)
    # Total: 12 branches
```

**Proposed Structure:**
```python
def _pip_audit_guarded(ignore_list: tuple[str, ...]) -> None:
    """Run pip-audit with known ignores."""
    # Orchestrate (2-3 branches total)
    _run_pip_audit_scan(ignore_list)
    vulnerabilities = _parse_audit_results()
    _validate_vulnerabilities(vulnerabilities, ignore_list)

def _run_pip_audit_scan(ignore_list: tuple[str, ...]) -> None:
    """Execute pip-audit command."""
    # 2-3 branches

def _parse_audit_results() -> list[dict]:
    """Parse pip-audit JSON output."""
    # 2-3 branches

def _validate_vulnerabilities(
    vulns: list[dict],
    ignore_list: tuple[str, ...]
) -> None:
    """Check for unexpected vulnerabilities."""
    # 3-4 branches
```

**Evidence Requirements:**

**BEFORE:**
```bash
# Measure complexity
radon cc scripts/test.py -s | grep "_pip_audit_guarded"
# Expected: CC=12, CogC=17

# Baseline tests
make test
# Expected: All pass
```

**AFTER:**
```bash
# Verify reduced complexity
radon cc scripts/test.py -s | grep -E "_pip_audit|_run_pip_audit|_parse_audit|_validate"
# Expected: All functions CC < 10

# Verify functionality
make test
# Expected: All pass, identical behavior
```

**Success Criteria:**
1. ✅ All 6 functions reduced to CC < 10
2. ✅ Cognitive complexity reduced
3. ✅ All tests pass unchanged
4. ✅ No new bugs introduced
5. ✅ Code more maintainable

**Rollback Triggers:**
- If tests fail
- If bugs introduced
- If complexity increases overall

**Dependencies:**
- ISSUE-1 (_run complexity) should be done first
- ISSUE-4 (long functions) can be done in parallel

**Effort:** 3-4 hours
**Priority:** P2 (Medium)
**Owner:** Development Team

---

## Priority 3: LOW PRIORITY ISSUES (Optional)

### ISSUE-11: Add signal_handler Docstring

**Category:** Documentation
**Severity:** LOW
**Impact:** Minor API documentation incompleteness
**Current State:** signal_handler missing docstring (daemon.py:196)
**Target State:** 100% function docstring coverage

**Fix Strategy:**

Add docstring to `src/check_zpools/daemon.py`:

```python
def signal_handler(signum: int, frame: Any) -> None:
    """
    Handle SIGTERM and SIGINT for graceful daemon shutdown.

    Sets the daemon's stop flag to trigger cleanup and exit on next check cycle.

    Args:
        signum: Signal number (SIGTERM=15, SIGINT=2)
        frame: Current stack frame (unused)

    Side Effects:
        Sets self._stop_flag.set() to signal shutdown
        Logs the received signal

    Example:
        >>> signal.signal(signal.SIGTERM, daemon.signal_handler)
        >>> # On SIGTERM, daemon will finish current cycle and exit
    """
    logger.info(f"Received signal {signum}, initiating graceful shutdown")
    self._stop_flag.set()
```

**Evidence Requirements:**

**BEFORE:**
```bash
# Check current state
grep -A5 "def signal_handler" src/check_zpools/daemon.py
# Expected: No docstring

# Check docstring coverage
python -c "
import ast
with open('src/check_zpools/daemon.py') as f:
    tree = ast.parse(f.read())
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef):
        if node.name == 'signal_handler':
            print(f'Has docstring: {ast.get_docstring(node) is not None}')
"
# Expected: Has docstring: False
```

**AFTER:**
```bash
# Verify docstring added
grep -A10 "def signal_handler" src/check_zpools/daemon.py
# Expected: Docstring present

# Verify coverage
python -c "
import ast
with open('src/check_zpools/daemon.py') as f:
    tree = ast.parse(f.read())
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef):
        if node.name == 'signal_handler':
            print(f'Has docstring: {ast.get_docstring(node) is not None}')
"
# Expected: Has docstring: True

# Verify no syntax errors
python -m py_compile src/check_zpools/daemon.py
# Expected: No errors
```

**Success Criteria:**
1. ✅ Docstring added to signal_handler
2. ✅ Docstring follows project conventions
3. ✅ Args documented (signum, frame)
4. ✅ Side effects documented
5. ✅ 100% function docstring coverage achieved

**Effort:** 10 minutes
**Priority:** P3 (Low)
**Owner:** Any contributor

---

### ISSUE-12: Document or Hide Template Commands

**Category:** Documentation
**Severity:** LOW
**Impact:** User confusion if they discover undocumented commands
**Current State:** 3 CLI commands not in README (hello, fail, send-email)
**Target State:** Commands documented or marked hidden

**Fix Strategy:**

**Option 1: Hide Development Commands (RECOMMENDED)**

```python
# src/check_zpools/cli.py

@cli.command(hidden=True)
def hello() -> None:
    """Development test command (hidden from help)."""
    ...

@cli.command(hidden=True)
def fail() -> None:
    """Development test command (hidden from help)."""
    ...
```

**Option 2: Document as Development Commands**

Add to README.md:

```markdown
### Development/Debug Commands

The following commands are available for development and debugging:

#### `hello`
Test command that prints a greeting.

```bash
check-zpools hello
```

#### `fail`
Test command that intentionally fails (for testing error handling).

```bash
check-zpools fail
```

#### `send-email`
Low-level email sending (use `check --email` instead in production).

```bash
check-zpools send-email --to user@example.com --subject "Test" --body "Test message"
```

**Note:** These commands are for development only. For production email alerts, use `check --email`.
```

**Option 3: Remove Development Commands**

If no longer needed, remove from codebase.

**Evidence Requirements:**

**BEFORE:**
```bash
# List all CLI commands
check-zpools --help | grep "^  "
# Expected: Shows hello, fail, send-email

# Check README
grep -E "hello|fail|send-email" README.md
# Expected: Not documented
```

**AFTER (Option 1):**
```bash
# Verify hidden
check-zpools --help | grep "^  "
# Expected: hello, fail not shown

# Verify still accessible
check-zpools hello
# Expected: Still works (just hidden)

# Verify code marked hidden
grep "hidden=True" src/check_zpools/cli.py
# Expected: Found for hello, fail
```

**Success Criteria:**
1. ✅ Development commands hidden from help
2. ✅ Commands still functional (for testing)
3. ✅ Or documented in README if kept visible
4. ✅ No user confusion

**Effort:** 30 minutes
**Priority:** P3 (Low)
**Owner:** Development Team

---

### ISSUE-13: Add nosec Comments for Security False Positives

**Category:** Security
**Severity:** LOW
**Impact:** Clean security reports, reduce noise
**Current State:** Bandit reports 1 HIGH + 19 LOW (mostly false positives)
**Target State:** Acknowledged false positives with # nosec comments

**Fix Strategy:**

Add `# nosec` comments to acknowledged safe code:

```python
# scripts/_utils.py:166

def run(..., shell: bool = False, ...) -> Result:
    """Execute subprocess command."""
    result = subprocess.run(
        args,
        shell=shell,  # nosec B602 - Internal build script, controlled input only
        cwd=cwd,
        env=env,
        text=True,
        capture_output=capture,
    )
```

For other false positives:

```python
# scripts/test.py:229
elif token in _FALSY or token == "":  # nosec B105 - Empty string check, not a password
    resolved_format_strict = False
```

**Evidence Requirements:**

**BEFORE:**
```bash
# Run Bandit
bandit -r scripts/ src/ -f json > security_before.json

# Count issues
jq '.results | length' security_before.json
# Expected: 20 issues (1 HIGH + 19 LOW)
```

**AFTER:**
```bash
# Run Bandit
bandit -r scripts/ src/ -f json > security_after.json

# Count issues
jq '.results | length' security_after.json
# Expected: 0 issues (all acknowledged)

# Verify nosec comments
grep -rn "nosec" scripts/ src/
# Expected: Comments for all false positives

# Verify tests still pass
make test
# Expected: All pass
```

**Success Criteria:**
1. ✅ All false positives have # nosec comments
2. ✅ Comments explain why safe (not just "nosec")
3. ✅ Bandit report clean
4. ✅ No real security issues masked
5. ✅ Tests pass

**Effort:** 1 hour
**Priority:** P3 (Low)
**Owner:** Development Team

---

### ISSUE-14 through ISSUE-33: Additional Low Priority Items

Due to space constraints, the remaining low-priority issues are summarized here. Full details can be provided on request.

**Remaining Issues:**

- ISSUE-14: Add SECURITY.md (Security)
- ISSUE-15: Add PR templates (CI/CD)
- ISSUE-16: Add Issue templates (CI/CD)
- ISSUE-17: Add CODEOWNERS (CI/CD)
- ISSUE-18: Migrate to OIDC publishing (CI/CD)
- ISSUE-19: Generate SBOM (CI/CD)
- ISSUE-20: Add multi-platform notebook testing (CI/CD)
- ISSUE-21: Reduce deep nesting in formatters.py:_format_last_scrub (Code Quality)
- ISSUE-22: Simplify parameter lists (9 functions with >5 params) (Code Quality)
- ISSUE-23: Add benchmark tracking (CI/CD)
- ISSUE-24-33: Various minor enhancements (all P3)

**Total Effort for P3:** 8-12 hours

---

## Fixing Order & Dependencies

### Phase 0: Prerequisites (IMMEDIATE)
**Must complete before anything else**

1. **FIX-0:** Fix review artifacts Ruff errors
   - **Blocking:** Yes (prevents baseline establishment)
   - **Effort:** 5 minutes
   - **Dependencies:** None

### Phase 1: High Priority (Week 1)
**Recommended for next release**

2. **ISSUE-1:** Reduce critical complexity in scripts/test.py:_run()
   - **Depends on:** FIX-0
   - **Effort:** 2-3 hours
   - **Blocks:** None

3. **ISSUE-2:** Update system design documentation
   - **Depends on:** None
   - **Effort:** 2-3 hours
   - **Blocks:** None

**Phase 1 Total:** 4-6 hours

### Phase 2: Medium Priority Code Quality (Week 2-3)
**Suggested for next sprint**

4. **ISSUE-3:** Reduce code duplication
   - **Depends on:** None
   - **Effort:** 8-12 hours (can split across multiple PRs)
   - **Blocks:** None

5. **ISSUE-4:** Break up long functions
   - **Depends on:** ISSUE-1 (recommended, not required)
   - **Effort:** 4-6 hours
   - **Blocks:** None

6. **ISSUE-10:** Reduce high-complexity functions
   - **Depends on:** ISSUE-1
   - **Effort:** 3-4 hours
   - **Blocks:** None

**Phase 2 Total:** 15-22 hours

### Phase 3: Medium Priority Documentation & CI/CD (Week 3-4)
**Suggested for next sprint**

7. **ISSUE-5:** Expand DEVELOPMENT.md testing docs
   - **Depends on:** ISSUE-3 (if fixtures refactored)
   - **Effort:** 1-2 hours
   - **Blocks:** None

8. **ISSUE-6:** Add pre-commit hooks
   - **Depends on:** ISSUE-1, ISSUE-4, ISSUE-10 (recommended)
   - **Effort:** 1 hour
   - **Blocks:** None

9. **ISSUE-7:** Add models.py to CODE_ARCHITECTURE.md
   - **Depends on:** None
   - **Effort:** 1 hour
   - **Blocks:** None

10. **ISSUE-8:** Enhance GitHub release notes
    - **Depends on:** None
    - **Effort:** 2 hours
    - **Blocks:** None

11. **ISSUE-9:** Align coverage targets
    - **Depends on:** None
    - **Effort:** 30 minutes
    - **Blocks:** None

**Phase 3 Total:** 5.5-6.5 hours

### Phase 4: Low Priority (Backlog)
**Optional enhancements**

12-33. **ISSUE-11 through ISSUE-33:** Various low-priority items
    - **Depends on:** Various (see individual issues)
    - **Effort:** 8-12 hours total
    - **Blocks:** None

**Phase 4 Total:** 8-12 hours

### Total Effort Summary

| Phase | Priority | Effort | Timeline |
|-------|----------|--------|----------|
| Phase 0 | P0 (Prerequisite) | 5 minutes | Immediate |
| Phase 1 | P1 (High) | 4-6 hours | Week 1 |
| Phase 2 | P2 (Medium - Code) | 15-22 hours | Week 2-3 |
| Phase 3 | P2 (Medium - Docs/CI) | 5.5-6.5 hours | Week 3-4 |
| Phase 4 | P3 (Low) | 8-12 hours | Backlog |
| **TOTAL** | | **33-46.5 hours** | **1-2 sprints** |

---

## Evidence Collection Framework

### Baseline Establishment

**Before ANY fixes:**

```bash
# Create baseline directory
mkdir -p LLM-CONTEXT/fix-anal/baseline

# 1. Run full test suite
make test > LLM-CONTEXT/fix-anal/baseline/test_output.txt 2>&1

# 2. Capture test results
pytest --tb=short --no-header -q > LLM-CONTEXT/fix-anal/baseline/pytest_results.txt 2>&1

# 3. Measure complexity
radon cc -a -s src/ scripts/ > LLM-CONTEXT/fix-anal/baseline/complexity.txt

# 4. Measure duplication
python LLM-CONTEXT/review-anal/quality/check_duplication.py > LLM-CONTEXT/fix-anal/baseline/duplication.txt

# 5. Count long functions
python -c "
import ast
from pathlib import Path

long_funcs = []
for pyfile in Path('src').rglob('*.py'):
    with open(pyfile) as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            length = node.end_lineno - node.lineno
            if length > 50:
                long_funcs.append(f'{pyfile}:{node.name}:{length}')

with open('LLM-CONTEXT/fix-anal/baseline/long_functions.txt', 'w') as f:
    f.write('\n'.join(long_funcs))
    f.write(f'\n\nTotal: {len(long_funcs)} functions >50 lines\n')
"

# 6. Security scan baseline
bandit -r src/ scripts/ -f json > LLM-CONTEXT/fix-anal/baseline/security.json

# 7. Current coverage
coverage report > LLM-CONTEXT/fix-anal/baseline/coverage.txt

# 8. Git status
git status --porcelain > LLM-CONTEXT/fix-anal/baseline/git_status.txt
git rev-parse HEAD > LLM-CONTEXT/fix-anal/baseline/git_commit.txt
```

### Per-Fix Evidence Collection

For each fix, create a subdirectory and collect:

```bash
# Example for ISSUE-1
mkdir -p LLM-CONTEXT/fix-anal/evidence/ISSUE-1

# Before fix
radon cc scripts/test.py -s | grep "_run" > LLM-CONTEXT/fix-anal/evidence/ISSUE-1/before_complexity.txt
make test > LLM-CONTEXT/fix-anal/evidence/ISSUE-1/before_tests.txt 2>&1

# Apply fix
# ... make changes ...

# After fix
radon cc scripts/test.py -s | grep "_run" > LLM-CONTEXT/fix-anal/evidence/ISSUE-1/after_complexity.txt
make test > LLM-CONTEXT/fix-anal/evidence/ISSUE-1/after_tests.txt 2>&1

# Compare
diff -u LLM-CONTEXT/fix-anal/evidence/ISSUE-1/before_tests.txt \
        LLM-CONTEXT/fix-anal/evidence/ISSUE-1/after_tests.txt \
        > LLM-CONTEXT/fix-anal/evidence/ISSUE-1/test_diff.txt
```

### Success Criteria Validation

Each fix must pass ALL criteria:

```bash
# Automated validation script
# LLM-CONTEXT/fix-anal/scripts/validate_fix.sh

#!/bin/bash
ISSUE=$1

echo "Validating ISSUE-$ISSUE..."

# 1. Tests must pass
make test || { echo "FAIL: Tests failed"; exit 1; }

# 2. Coverage must not decrease
old_coverage=$(grep "TOTAL" LLM-CONTEXT/fix-anal/baseline/coverage.txt | awk '{print $4}' | tr -d '%')
new_coverage=$(coverage report | grep "TOTAL" | awk '{print $4}' | tr -d '%')
if (( $(echo "$new_coverage < $old_coverage" | bc -l) )); then
    echo "FAIL: Coverage decreased from $old_coverage% to $new_coverage%"
    exit 1
fi

# 3. No new linting errors
ruff check src/ scripts/ || { echo "FAIL: Linting errors"; exit 1; }

# 4. No new type errors
pyright src/ || { echo "FAIL: Type errors"; exit 1; }

echo "SUCCESS: All validation checks passed for ISSUE-$ISSUE"
```

---

## Rollback Procedures

### Individual Fix Rollback

```bash
# If a fix breaks tests or introduces issues:

# 1. Revert changes
git checkout -- <modified files>

# 2. Verify baseline restored
make test

# 3. Document rollback
echo "ISSUE-X rolled back: <reason>" >> LLM-CONTEXT/fix-anal/rollback_log.txt

# 4. Investigate root cause
# ... analyze what went wrong ...

# 5. Update fix strategy
# ... revise approach ...
```

### Full Rollback (Emergency)

```bash
# If multiple fixes cause issues:

# 1. Restore from git
git reset --hard <baseline-commit-sha>

# 2. Verify clean state
make test

# 3. Document event
echo "Full rollback to $(git rev-parse HEAD)" >> LLM-CONTEXT/fix-anal/rollback_log.txt

# 4. Review fix plan
# ... assess what went wrong ...
```

---

## Progress Tracking

### Status Dashboard

Create `LLM-CONTEXT/fix-anal/STATUS.md`:

```markdown
# Fix Plan Progress

**Last Updated:** YYYY-MM-DD
**Current Phase:** Phase X

## Summary

| Phase | Issues | Completed | In Progress | Blocked | Total Effort |
|-------|--------|-----------|-------------|---------|--------------|
| Phase 0 | 1 | 0 | 0 | 0 | 5 min |
| Phase 1 | 2 | 0 | 0 | 0 | 4-6 hrs |
| Phase 2 | 3 | 0 | 0 | 0 | 15-22 hrs |
| Phase 3 | 5 | 0 | 0 | 0 | 5.5-6.5 hrs |
| Phase 4 | 22 | 0 | 0 | 0 | 8-12 hrs |
| **TOTAL** | **33** | **0** | **0** | **0** | **33-46.5 hrs** |

## Issue Status

### Phase 0: Prerequisites
- [ ] FIX-0: Fix review artifacts Ruff errors (5 min)

### Phase 1: High Priority
- [ ] ISSUE-1: Reduce critical complexity in _run() (2-3 hrs)
- [ ] ISSUE-2: Update system design docs (2-3 hrs)

### Phase 2: Medium Priority - Code Quality
- [ ] ISSUE-3: Reduce code duplication (8-12 hrs)
- [ ] ISSUE-4: Break up long functions (4-6 hrs)
- [ ] ISSUE-10: Reduce high-complexity functions (3-4 hrs)

### Phase 3: Medium Priority - Docs & CI/CD
- [ ] ISSUE-5: Expand testing docs (1-2 hrs)
- [ ] ISSUE-6: Add pre-commit hooks (1 hr)
- [ ] ISSUE-7: Add models.py to architecture (1 hr)
- [ ] ISSUE-8: Enhance release notes (2 hrs)
- [ ] ISSUE-9: Align coverage targets (30 min)

### Phase 4: Low Priority
- [ ] ISSUE-11 through ISSUE-33 (8-12 hrs total)

## Metrics

### Baseline (2025-11-19)
- Test Pass Rate: 100% (505 passed, 11 skipped)
- Coverage: 76.72%
- Complexity (avg): 1.86
- Complexity (max): 17
- Duplicate Blocks: 131
- Duplicate Lines: ~1,350
- Long Functions (>50 lines): 46
- Security Issues: 20 (1 HIGH, 19 LOW - mostly false positives)

### Current
- Test Pass Rate: TBD
- Coverage: TBD
- Complexity (avg): TBD
- Complexity (max): TBD
- Duplicate Blocks: TBD
- Duplicate Lines: TBD
- Long Functions (>50 lines): TBD
- Security Issues: TBD

## Recent Activity

### YYYY-MM-DD
- Started FIX-0: Review artifacts cleanup
- [Log entries as work progresses]
```

---

## Conclusion

This fix plan provides a comprehensive, prioritized approach to addressing all review findings. The plan is:

1. **Actionable**: Each issue has clear fix strategies
2. **Evidence-Based**: Before/after measurements required
3. **Safe**: Success criteria and rollback triggers defined
4. **Prioritized**: Critical → High → Medium → Low
5. **Incremental**: Can be executed in phases
6. **Trackable**: Progress dashboard and evidence collection

### Immediate Next Steps

1. **FIX-0 (5 minutes):** Fix Ruff errors in review artifacts
2. **Establish Baseline (30 minutes):** Run evidence collection scripts
3. **Begin Phase 1 (4-6 hours):** Start ISSUE-1 and ISSUE-2
4. **Track Progress:** Update STATUS.md daily

### Success Metrics

**Project will be considered EXCEPTIONAL (A+) when:**
- ✅ All P0/P1 issues resolved (2 issues)
- ✅ 80%+ of P2 issues resolved (7/8 issues)
- ✅ Complexity: All functions CC <10
- ✅ Duplication: <50 blocks
- ✅ Documentation: 100% coverage
- ✅ Tests: 100% pass rate maintained
- ✅ Coverage: >76% maintained

**Current Grade:** A (95%)
**Target Grade:** A+ (98%)
**Estimated Effort:** 33-46.5 hours (1-2 sprint weeks)

---

**END OF FIX PLAN**
