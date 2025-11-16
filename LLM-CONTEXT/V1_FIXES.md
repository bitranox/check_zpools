# check_zpools - v1.0 Critical Fixes

## Overview

This document outlines **critical and high priority issues** that must be resolved before v1.0 release. All issues were identified during comprehensive code review on 2025-11-16.

**Status**: Current implementation is at **v0.1.0** with 215 tests passing (5 daemon tests failing).

---

## Critical Issues (Must Fix for v1.0)

### CRITICAL-1: Daemon Tests Failing (5 tests)

**Severity**: CRITICAL
**Impact**: Cannot verify daemon mode works correctly
**Estimated Effort**: 2-4 hours
**Priority**: P0 (Release Blocker)

#### Problem Description

Five daemon tests in `tests/test_daemon.py` are failing due to mocking strategy issues:

```
FAILED tests/test_daemon.py::test_daemon_check_cycle - AssertionError: assert 0 > 0
FAILED tests/test_daemon.py::test_daemon_handles_new_issues - AssertionError: assert 0 > 0
FAILED tests/test_daemon.py::test_daemon_handles_resolved_issues - AssertionError
FAILED tests/test_daemon.py::test_daemon_sends_alerts_for_issues - AssertionError: assert 1 == 0
FAILED tests/test_daemon.py::test_daemon_suppresses_duplicate_alerts - AssertionError: assert 1 == 0
```

**Root Cause**: Current mocking approach returns empty pool data, preventing the daemon from seeing any pools:

```python
# Current problematic approach:
with patch.object(daemon.zfs_client, "get_pool_list", return_value={}):
    # Returns {} → parser creates empty dict → no pools → warnings logged
```

#### Solution

**Approach**: Mock at parser level with realistic PoolStatus objects instead of mocking ZFS client.

**Implementation Steps**:

1. **Create Realistic Pool Data Fixtures** (30 min)
   ```python
   # tests/test_daemon.py
   from datetime import datetime, timezone
   from check_zpools.models import PoolHealth, PoolStatus

   @pytest.fixture
   def healthy_pool():
       """Fixture for healthy pool."""
       return PoolStatus(
           name="rpool",
           health=PoolHealth.ONLINE,
           capacity_percent=45.2,
           size_bytes=1_000_000_000_000,
           allocated_bytes=452_000_000_000,
           free_bytes=548_000_000_000,
           read_errors=0,
           write_errors=0,
           checksum_errors=0,
           last_scrub=datetime.now(timezone.utc),
           scrub_errors=0,
           scrub_in_progress=False,
       )

   @pytest.fixture
   def degraded_pool():
       """Fixture for degraded pool."""
       return PoolStatus(
           name="rpool",
           health=PoolHealth.DEGRADED,
           capacity_percent=85.0,
           size_bytes=1_000_000_000_000,
           allocated_bytes=850_000_000_000,
           free_bytes=150_000_000_000,
           read_errors=5,
           write_errors=2,
           checksum_errors=1,
           last_scrub=datetime.now(timezone.utc),
           scrub_errors=3,
           scrub_in_progress=False,
       )
   ```

2. **Refactor Mocking Strategy** (1-2 hours)
   ```python
   # Instead of mocking client, mock parser's merge_pool_data method:

   def test_daemon_check_cycle(daemon, healthy_pool):
       """Test that daemon executes check cycle and processes pools."""

       # Mock parser to return realistic pool data
       with patch.object(
           daemon.zfs_client._parser,  # Access parser through client
           "merge_pool_data",
           return_value={"rpool": healthy_pool}
       ):
           daemon._run_check_cycle()

           # Verify monitor was called with pool data
           assert daemon.monitor.check_all_pools.called
           assert len(daemon.monitor.check_all_pools.call_args[0][0]) > 0

   def test_daemon_handles_new_issues(daemon, degraded_pool):
       """Test daemon sends alerts for new issues."""

       # Create mock result with issues
       from check_zpools.models import CheckResult, PoolIssue, Severity

       issue = PoolIssue(
           pool_name="rpool",
           severity=Severity.CRITICAL,
           category="health",
           message="Pool is DEGRADED",
           details={"expected": "ONLINE", "actual": "DEGRADED"}
       )

       result = CheckResult(
           timestamp=datetime.now(timezone.utc),
           pools=[degraded_pool],
           issues=[issue],
           overall_severity=Severity.CRITICAL,
       )

       # Mock monitor to return result with issues
       with patch.object(daemon.monitor, "check_all_pools", return_value=result):
           daemon._run_check_cycle()

           # Verify alert was sent
           assert daemon.alerter.send_alert.call_count > 0
   ```

3. **Update All Failing Tests** (1-2 hours)
   - Apply new mocking pattern to all 5 failing tests
   - Ensure realistic pool data flows through entire call chain
   - Verify alerts are sent/suppressed correctly

4. **Verify Test Coverage** (30 min)
   ```bash
   make test
   # Expect: All 220 tests passing (including daemon tests)
   # Expect: test_daemon.py coverage > 90%
   ```

#### Success Criteria

- [ ] All 5 daemon tests pass
- [ ] No new warnings in test output
- [ ] Test coverage for daemon.py remains > 90%
- [ ] Realistic pool data flows through entire daemon cycle
- [ ] Alert sending and suppression logic verified

#### Files Modified

- `tests/test_daemon.py` (refactor mocking strategy)

---

### CRITICAL-2: Incomplete Size Parsing Implementation

**Severity**: CRITICAL
**Impact**: Cannot parse ZFS sizes with suffixes (K/M/G/T/P)
**Estimated Effort**: 2-4 hours
**Priority**: P0 (Release Blocker)

#### Problem Description

Current implementation in `src/check_zpools/zfs_parser.py:376-403` is a placeholder:

```python
@lru_cache(maxsize=32)
def _parse_size_to_bytes(self, size_str: str) -> int:
    """Convert size string to bytes."""
    try:
        # If it's already a number, return it
        return int(float(size_str))
    except ValueError:
        # Try to parse with suffix (K, M, G, T, P)
        # This is a simplified version; ZFS may use different formats
        logger.debug(f"Parsing size string: {size_str}")
        return int(float(size_str))  # ⚠️ PLACEHOLDER - just tries again!
```

**Issue**: When parsing fails, code just tries the same conversion again (which will fail again). Doesn't actually handle suffixes.

#### Solution

**Approach**: Implement regex-based parsing with binary multipliers (1K = 1024 bytes).

**Implementation Steps**:

1. **Implement Suffix Parsing** (1 hour)
   ```python
   # src/check_zpools/zfs_parser.py

   import re
   from functools import lru_cache

   @lru_cache(maxsize=32)
   def _parse_size_to_bytes(self, size_str: str) -> int:
       """Convert size string to bytes.

       Why Cached
       ----------
       Same size values appear repeatedly across multiple pools (e.g., "1000000").
       Caching eliminates redundant string-to-float-to-int conversions.
       maxsize=32 covers typical ZFS size variations without excessive memory.

       Parameters
       ----------
       size_str:
           Size as string. May be numeric ("1000000") or with suffix ("1.5T").
           Supports binary suffixes: K (1024), M (1024^2), G (1024^3),
           T (1024^4), P (1024^5).

       Returns
       -------
       int:
           Size in bytes

       Raises
       ------
       ValueError:
           If size_str cannot be parsed as number or number+suffix

       Examples
       --------
       >>> parser = ZFSParser()
       >>> parser._parse_size_to_bytes("1000000")
       1000000
       >>> parser._parse_size_to_bytes("1.5T")
       1649267441664
       >>> parser._parse_size_to_bytes("500G")
       536870912000
       """
       # Try parsing as plain number first (most common case)
       try:
           return int(float(size_str))
       except ValueError:
           pass

       # Parse with suffix (e.g., "1.5T", "500G", "10M")
       pattern = r'^([0-9.]+)\s*([KMGTP])$'
       match = re.match(pattern, size_str.strip().upper())

       if not match:
           raise ValueError(
               f"Cannot parse size string '{size_str}' - "
               f"expected number or number+suffix (K/M/G/T/P)"
           )

       value_str, suffix = match.groups()

       try:
           value = float(value_str)
       except ValueError as exc:
           raise ValueError(f"Invalid numeric value in size string '{size_str}'") from exc

       # Binary multipliers (1K = 1024 bytes, not 1000)
       multipliers = {
           'K': 1024,
           'M': 1024 ** 2,
           'G': 1024 ** 3,
           'T': 1024 ** 4,
           'P': 1024 ** 5,
       }

       multiplier = multipliers[suffix]
       result = int(value * multiplier)

       logger.debug(
           f"Parsed size string: '{size_str}' → {result} bytes",
           extra={"size_str": size_str, "value": value, "suffix": suffix, "bytes": result}
       )

       return result
   ```

2. **Add Comprehensive Tests** (1-2 hours)
   ```python
   # tests/test_zfs_parser.py

   import pytest
   from check_zpools.zfs_parser import ZFSParser

   class TestParseSizeToBytes:
       """Test size string parsing with various formats."""

       def setup_method(self):
           self.parser = ZFSParser()

       @pytest.mark.parametrize("size_str,expected_bytes", [
           # Plain numbers
           ("0", 0),
           ("1", 1),
           ("1000", 1000),
           ("1000000", 1000000),
           ("1234567890", 1234567890),

           # Decimal numbers
           ("1.5", 1),
           ("10.5", 10),
           ("100.9", 100),

           # Kilobytes (1K = 1024 bytes)
           ("1K", 1024),
           ("10K", 10240),
           ("1.5K", 1536),

           # Megabytes (1M = 1024^2 bytes)
           ("1M", 1048576),
           ("10M", 10485760),
           ("1.5M", 1572864),

           # Gigabytes (1G = 1024^3 bytes)
           ("1G", 1073741824),
           ("10G", 10737418240),
           ("1.5G", 1610612736),

           # Terabytes (1T = 1024^4 bytes)
           ("1T", 1099511627776),
           ("2T", 2199023255552),
           ("1.5T", 1649267441664),

           # Petabytes (1P = 1024^5 bytes)
           ("1P", 1125899906842624),
           ("2P", 2251799813685248),

           # Case insensitivity
           ("1k", 1024),
           ("1m", 1048576),
           ("1g", 1073741824),
           ("1t", 1099511627776),

           # Whitespace handling
           ("1 K", 1024),
           (" 1K ", 1024),
           ("1K ", 1024),
           (" 1K", 1024),
       ])
       def test_valid_sizes(self, size_str, expected_bytes):
           """Test parsing valid size strings."""
           result = self.parser._parse_size_to_bytes(size_str)
           assert result == expected_bytes

       @pytest.mark.parametrize("invalid_str", [
           "",                # Empty
           "   ",             # Whitespace only
           "abc",             # No number
           "K",               # Suffix only
           "1X",              # Invalid suffix
           "1 2 K",           # Multiple numbers
           "K1",              # Suffix before number
           "1KK",             # Multiple suffixes
           "-1K",             # Negative (invalid in ZFS context)
       ])
       def test_invalid_sizes(self, invalid_str):
           """Test parsing invalid size strings raises ValueError."""
           with pytest.raises(ValueError, match="Cannot parse size string"):
               self.parser._parse_size_to_bytes(invalid_str)

       def test_caching(self):
           """Test that lru_cache improves performance."""
           # First call
           result1 = self.parser._parse_size_to_bytes("1.5T")

           # Second call (should hit cache)
           result2 = self.parser._parse_size_to_bytes("1.5T")

           # Results should be identical
           assert result1 == result2

           # Cache info should show hits
           cache_info = self.parser._parse_size_to_bytes.cache_info()
           assert cache_info.hits >= 1
   ```

3. **Test with Real ZFS Data** (30 min)
   - Use sample JSON from `LLM-CONTEXT/testdata.md`
   - Verify parsing works with actual ZFS output format
   - Check edge cases (0 bytes, very large sizes)

4. **Update Docstring** (30 min)
   - Document supported formats
   - Add examples
   - Note binary vs decimal multipliers

#### Success Criteria

- [ ] Parses plain numbers correctly
- [ ] Parses K/M/G/T/P suffixes correctly
- [ ] Uses binary multipliers (1K = 1024, not 1000)
- [ ] Handles decimal values (1.5T)
- [ ] Case insensitive parsing
- [ ] Handles whitespace gracefully
- [ ] Raises ValueError for invalid formats
- [ ] All parametrized tests pass
- [ ] Cache hit rate > 50% in real usage
- [ ] Works with actual ZFS JSON output

#### Files Modified

- `src/check_zpools/zfs_parser.py` (implement parsing logic)
- `tests/test_zfs_parser.py` (add comprehensive parametrized tests)

---

## High Priority Issues (Should Fix for v1.0)

### HIGH-1: Missing Configuration Validation Tests

**Severity**: HIGH
**Impact**: Invalid configuration could cause runtime errors
**Estimated Effort**: 2-3 hours
**Priority**: P1

#### Problem Description

No tests exist for `_build_monitor_config()` in `behaviors.py:475-533`, which validates configuration thresholds.

**Risk**: Invalid config (e.g., warning > critical, negative values) could cause runtime errors or incorrect monitoring.

#### Solution

**Implementation Steps**:

1. **Create Test File** (2-3 hours)
   ```python
   # tests/test_behaviors.py (new file)

   import pytest
   from check_zpools.behaviors import _build_monitor_config
   from check_zpools.monitor import MonitorConfig

   class TestBuildMonitorConfig:
       """Test configuration building and validation."""

       def test_default_values(self):
           """Test defaults when config sections missing."""
           config = {}
           result = _build_monitor_config(config)

           assert result.capacity_warning_percent == 80
           assert result.capacity_critical_percent == 90
           assert result.scrub_max_age_days == 30
           assert result.read_errors_warning == 0
           assert result.write_errors_warning == 0
           assert result.checksum_errors_warning == 0

       def test_custom_values(self):
           """Test custom threshold values."""
           config = {
               "zfs": {
                   "capacity": {
                       "warning_percent": 70,
                       "critical_percent": 85,
                   },
                   "scrub": {
                       "max_age_days": 14,
                   },
                   "errors": {
                       "read_errors_warning": 5,
                       "write_errors_warning": 3,
                       "checksum_errors_warning": 1,
                   }
               }
           }

           result = _build_monitor_config(config)

           assert result.capacity_warning_percent == 70
           assert result.capacity_critical_percent == 85
           assert result.scrub_max_age_days == 14
           assert result.read_errors_warning == 5
           assert result.write_errors_warning == 3
           assert result.checksum_errors_warning == 1

       @pytest.mark.parametrize("warning,critical,error_msg", [
           (90, 80, "must be less than critical_percent"),  # Warning > critical
           (80, 80, "must be less than critical_percent"),  # Warning == critical
           (0, 90, "must be between 0 and 100"),            # Warning at boundary
           (80, 101, "must be between 0 and 100"),          # Critical > 100
           (-10, 90, "must be between 0 and 100"),          # Negative warning
       ])
       def test_invalid_capacity_thresholds(self, warning, critical, error_msg):
           """Test validation rejects invalid capacity thresholds."""
           config = {
               "zfs": {
                   "capacity": {
                       "warning_percent": warning,
                       "critical_percent": critical,
                   }
               }
           }

           with pytest.raises(ValueError, match=error_msg):
               _build_monitor_config(config)

       @pytest.mark.parametrize("scrub_age", [
           -1,    # Negative
           -100,  # Large negative
       ])
       def test_invalid_scrub_age(self, scrub_age):
           """Test validation rejects negative scrub age."""
           config = {
               "zfs": {
                   "scrub": {
                       "max_age_days": scrub_age,
                   }
               }
           }

           with pytest.raises(ValueError, match="must be non-negative"):
               _build_monitor_config(config)

       @pytest.mark.parametrize("error_type,value", [
           ("read_errors_warning", -1),
           ("write_errors_warning", -5),
           ("checksum_errors_warning", -10),
       ])
       def test_invalid_error_thresholds(self, error_type, value):
           """Test validation rejects negative error thresholds."""
           config = {
               "zfs": {
                   "errors": {
                       error_type: value,
                   }
               }
           }

           with pytest.raises(ValueError, match="must be non-negative"):
               _build_monitor_config(config)

       def test_edge_case_thresholds(self):
           """Test edge case values that should be valid."""
           config = {
               "zfs": {
                   "capacity": {
                       "warning_percent": 1,    # Minimum valid
                       "critical_percent": 100,  # Maximum valid
                   },
                   "scrub": {
                       "max_age_days": 0,        # 0 = disabled
                   },
                   "errors": {
                       "read_errors_warning": 0,      # 0 = any error triggers
                       "write_errors_warning": 1000,  # Large threshold
                       "checksum_errors_warning": 0,
                   }
               }
           }

           result = _build_monitor_config(config)

           assert result.capacity_warning_percent == 1
           assert result.capacity_critical_percent == 100
           assert result.scrub_max_age_days == 0
   ```

#### Success Criteria

- [ ] Tests for default values
- [ ] Tests for custom values
- [ ] Tests for invalid thresholds (parametrized)
- [ ] Tests for edge cases (boundary values)
- [ ] All tests pass
- [ ] Coverage for `_build_monitor_config()` > 95%

#### Files Modified

- `tests/test_behaviors.py` (new file)

---

### HIGH-2: Missing CLI Error Handling Tests

**Severity**: HIGH
**Impact**: CLI may not handle errors gracefully
**Estimated Effort**: 2-3 hours
**Priority**: P1

#### Problem Description

Insufficient tests for CLI error scenarios:
- Permission denied (requires root)
- Corrupt state file
- SMTP timeout
- ZFS not available

#### Solution

**Implementation Steps**:

1. **Add Error Scenario Tests** (2-3 hours)
   ```python
   # tests/test_cli.py (add to existing file)

   from click.testing import CliRunner
   import pytest
   from unittest.mock import patch
   from check_zpools.cli import cli
   from check_zpools.zfs_client import ZFSNotAvailableError

   class TestCLIErrorHandling:
       """Test CLI error handling scenarios."""

       def test_check_zfs_not_available(self):
           """Test check command when ZFS not available."""
           runner = CliRunner()

           with patch("check_zpools.behaviors.ZFSClient") as mock_client:
               mock_client.return_value.check_zpool_available.return_value = False
               mock_client.return_value.get_pool_list.side_effect = ZFSNotAvailableError(
                   "zpool command not found"
               )

               result = runner.invoke(cli, ["check"])

               assert result.exit_code != 0
               assert "zpool" in result.output.lower() or "not available" in result.output.lower()

       def test_daemon_permission_denied(self):
           """Test daemon fails gracefully when lacking permissions."""
           runner = CliRunner()

           with patch("check_zpools.behaviors.ZFSClient") as mock_client:
               mock_client.return_value.get_pool_list.side_effect = PermissionError(
                   "Permission denied - requires root"
               )

               result = runner.invoke(cli, ["daemon", "--foreground"])

               assert result.exit_code != 0
               assert "permission" in result.output.lower() or "root" in result.output.lower()

       def test_daemon_corrupt_state_file(self):
           """Test daemon handles corrupt state file gracefully."""
           runner = CliRunner()

           with runner.isolated_filesystem():
               # Create corrupt state file
               with open("alert_state.json", "w") as f:
                   f.write("{invalid json")

               with patch("check_zpools.behaviors._get_state_file_path") as mock_path:
                   mock_path.return_value = Path("alert_state.json")

                   result = runner.invoke(cli, ["daemon", "--foreground"])

                   # Should log warning but continue (recreate state)
                   # Don't crash
                   assert "corrupt" in result.output.lower() or "recreat" in result.output.lower()

       def test_show_status_timeout(self):
           """Test show-status handles command timeout."""
           runner = CliRunner()

           with patch("check_zpools.behaviors.ZFSClient") as mock_client:
               import subprocess
               mock_client.return_value.get_pool_list.side_effect = subprocess.TimeoutExpired(
                   cmd="zpool list", timeout=30
               )

               result = runner.invoke(cli, ["show-status"])

               assert result.exit_code != 0
               assert "timeout" in result.output.lower()
   ```

#### Success Criteria

- [ ] Test ZFS not available error
- [ ] Test permission denied error
- [ ] Test corrupt state file recovery
- [ ] Test command timeout
- [ ] All error messages are user-friendly
- [ ] Exit codes are appropriate (non-zero for errors)

#### Files Modified

- `tests/test_cli.py` (add error handling tests)

---

### HIGH-3: Missing Security Tests

**Severity**: HIGH
**Impact**: Security vulnerabilities in state file handling
**Estimated Effort**: 1-2 hours
**Priority**: P1

#### Problem Description

No tests verify that:
- State file has secure permissions (0o600)
- State directory has appropriate permissions (0o750)
- No secrets leaked in logs

#### Solution

**Implementation Steps**:

1. **Add Security Tests** (1-2 hours)
   ```python
   # tests/test_security.py (new file)

   import pytest
   import os
   import stat
   from pathlib import Path
   from check_zpools.alert_state import AlertStateManager

   class TestSecurityFilePermissions:
       """Test file and directory permission security."""

       def test_state_file_permissions(self, tmp_path):
           """Test state file created with secure permissions."""
           state_file = tmp_path / "alert_state.json"
           manager = AlertStateManager(state_file, resend_interval_hours=24)

           # Trigger state file creation
           manager.save_state()

           # Verify file exists
           assert state_file.exists()

           # Get file permissions
           file_stat = state_file.stat()
           file_perms = stat.filemode(file_stat.st_mode)

           # Should be -rw------- (0o600)
           # Owner: read+write, Group: none, Other: none
           assert file_stat.st_mode & 0o777 == 0o600, \
               f"State file has insecure permissions: {file_perms}"

       def test_state_directory_permissions(self, tmp_path):
           """Test state directory created with appropriate permissions."""
           state_dir = tmp_path / "cache"
           state_file = state_dir / "alert_state.json"

           # Ensure directory doesn't exist
           assert not state_dir.exists()

           manager = AlertStateManager(state_file, resend_interval_hours=24)
           manager.save_state()

           # Verify directory was created
           assert state_dir.exists()
           assert state_dir.is_dir()

           # Get directory permissions
           dir_stat = state_dir.stat()
           dir_perms = stat.filemode(dir_stat.st_mode)

           # Should be drwxr-x--- (0o750)
           # Owner: full access, Group: read+execute, Other: none
           assert dir_stat.st_mode & 0o777 == 0o750, \
               f"State directory has incorrect permissions: {dir_perms}"

       @pytest.mark.parametrize("sensitive_field", [
           "smtp_password",
           "smtp_username",
       ])
       def test_no_secrets_in_logs(self, caplog, sensitive_field):
           """Test that sensitive config fields not logged."""
           # This would require actual log inspection during config loading
           # Implementation depends on logging setup
           pass  # Placeholder - implement when logging finalized
   ```

#### Success Criteria

- [ ] State file created with 0o600 permissions
- [ ] State directory created with 0o750 permissions
- [ ] No SMTP passwords in logs
- [ ] Tests pass on Linux and macOS (skip on Windows if needed)

#### Files Modified

- `tests/test_security.py` (new file)
- `src/check_zpools/alert_state.py` (ensure secure permissions)

---

## Execution Checklist

### Phase 1: Critical Fixes (4-8 hours)

- [ ] **CRITICAL-1**: Fix daemon tests
  - [ ] Create realistic pool data fixtures
  - [ ] Refactor mocking strategy
  - [ ] Update all 5 failing tests
  - [ ] Verify 100% test pass rate

- [ ] **CRITICAL-2**: Implement size parsing
  - [ ] Implement regex-based parsing
  - [ ] Add binary multiplier support
  - [ ] Add comprehensive parametrized tests
  - [ ] Test with real ZFS data

- [ ] Run `make test` - expect all tests passing
- [ ] Commit: `fix: resolve daemon test failures and implement size parsing`

### Phase 2: High Priority Tests (6-10 hours)

- [ ] **HIGH-1**: Add configuration validation tests
  - [ ] Create `tests/test_behaviors.py`
  - [ ] Add default value tests
  - [ ] Add invalid threshold tests (parametrized)
  - [ ] Add edge case tests

- [ ] **HIGH-2**: Add CLI error handling tests
  - [ ] Add ZFS not available test
  - [ ] Add permission denied test
  - [ ] Add corrupt state file test
  - [ ] Add timeout test

- [ ] **HIGH-3**: Add security tests
  - [ ] Create `tests/test_security.py`
  - [ ] Add file permission tests
  - [ ] Add directory permission tests
  - [ ] Implement secure permission creation

- [ ] Run `make test` - expect all tests passing
- [ ] Verify coverage > 85% overall
- [ ] Commit: `test: add comprehensive validation, error handling, and security tests`

### Phase 3: Documentation & Release (2 hours)

- [ ] Update `CHANGELOG.md` with v0.1.0 entry
- [ ] Update `README.md` if needed
- [ ] Run final `make test`
- [ ] Version bump: `make bump-minor` (0.0.1 → 0.1.0)
- [ ] Create release: `make release`

---

## Estimated Total Effort

| Phase | Tasks | Hours (Min-Max) |
|-------|-------|-----------------|
| Phase 1: Critical Fixes | 2 | 4-8 |
| Phase 2: High Priority Tests | 3 | 6-10 |
| Phase 3: Documentation & Release | - | 2 |
| **Total** | **5** | **12-20** |

**Realistic Estimate**: 12-16 hours for complete v1.0 readiness.

---

## Risk Mitigation

### Critical Risks

| Risk | Mitigation |
|------|------------|
| Daemon tests still fail after refactor | Start with simplest test first, verify mocking pattern works before applying to all tests |
| Size parsing breaks existing functionality | Add tests for current behavior first (plain numbers), then add suffix support |
| Security tests fail on Windows | Use `pytest.mark.skipif(sys.platform == "win32")` for Unix-specific tests |

### Quality Gates

Before proceeding to next phase:
- [ ] All tests must pass (`make test` exit code 0)
- [ ] No pyright type errors
- [ ] No ruff linting errors
- [ ] Coverage > 85% overall
- [ ] No manual testing failures

---

## Success Criteria for v1.0 Release

- [x] Execute ZFS commands and parse JSON (Phase 3 complete)
- [x] Monitor pools against thresholds (Phase 4 complete)
- [x] Send email alerts (Phase 5 complete)
- [x] Run daemon mode (Phase 6 complete)
- [x] CLI integration (Phase 7 complete)
- [ ] **All tests pass (220/220)** ← Current blocker
- [ ] **Size parsing handles suffixes** ← Current blocker
- [ ] Test coverage > 85%
- [ ] Complete documentation
- [ ] Successful release build

---

## Notes

- Follow coding guidelines in `CLAUDE.md`
- Run `make test` before each commit
- Keep functions small (<20 lines)
- Use parametrized tests for multiple scenarios
- Add structured logging for all operations
- Write self-documenting code with clear docstrings
