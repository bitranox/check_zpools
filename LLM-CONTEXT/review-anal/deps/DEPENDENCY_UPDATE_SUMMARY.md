# Dependency Update Report
**Project:** check_zpools v2.1.8  
**Date:** 2025-11-19  
**Command:** /bx_review_anal_sub_deps

---

## Executive Summary

✅ **Status:** Dependency updates completed successfully  
📦 **Packages Updated:** 18 transitive dependencies  
🧪 **Test Results:** All tests passing (505 passed, 11 skipped)  
📊 **Test Coverage:** 76.72% (exceeds requirement of 60%)

---

## Direct Dependencies Status

All **7 runtime dependencies** and **11 dev dependencies** specified in `pyproject.toml` are already at their latest compatible versions:

### Runtime Dependencies (All Current)
- ✅ rich-click>=1.9.4
- ✅ lib_cli_exit_tools>=2.1.0
- ✅ lib_log_rich>=5.3.1
- ✅ lib_layered_config>=1.1.1
- ✅ btx-lib-mail>=1.0.1
- ✅ python-dateutil>=2.8.2
- ✅ psutil>=7.1.3

### Dev Dependencies (All Current)
- ✅ pytest>=9.0.1
- ✅ pytest-cov>=7.0.0
- ✅ ruff>=0.14.5
- ✅ pyright>=1.1.407
- ✅ bandit>=1.9.1
- ✅ build>=1.3.0
- ✅ twine>=6.2.0
- ✅ codecov-cli>=11.2.5
- ✅ pip-audit>=2.9.0
- ✅ textual>=6.6.0
- ✅ import-linter>=2.7

---

## Transitive Dependencies Updated

Successfully updated **18 transitive dependencies** to their latest compatible versions:

| Package | Previous Version | Updated Version | Type |
|---------|-----------------|-----------------|------|
| CacheControl | 0.14.3 | 0.14.4 | Minor |
| cachetools | 6.2.1 | 6.2.2 | Patch |
| certifi | 2025.10.5 | 2025.11.12 | Security certificates |
| coverage | 7.11.0 | 7.12.0 | Minor |
| docutils | 0.22.2 | 0.22.3 | Patch |
| hypothesis | 6.142.5 | 6.148.2 | Patch |
| keyring | 25.6.0 | 25.7.0 | Minor |
| pydantic | 2.12.3 | 2.12.4 | Patch |
| pydantic_core | 2.41.4 | 2.41.5 | Patch |
| PyNaCl | 1.6.0 | 1.6.1 | Patch |
| pytest-asyncio | 1.2.0 | 1.3.0 | Minor |
| redis | 7.0.1 | 7.1.0 | Minor |
| rpds-py | 0.28.0 | 0.29.0 | Minor |
| SecretStorage | 3.4.0 | 3.4.1 | Patch |
| sentry-sdk | 2.43.0 | 2.45.0 | Patch |
| trove-classifiers | 2025.9.11.17 | 2025.11.14.15 | Data update |
| uv | 0.9.7 | 0.9.10 | Patch |
| wrapt | 2.0.0 | 2.0.1 | Patch |

---

## Dependency Conflicts Resolved

During the update process, version conflicts were detected and resolved:

### Conflicts Identified
1. **codecov-cli** required older versions of:
   - click <8.3.0 (latest was 8.3.1)
   - responses ==0.21.* (latest was 0.25.8)
   - test-results-parser ==0.6.0 (latest was 0.6.1)

2. **pip-audit** required:
   - cyclonedx-python-lib <10 (latest was 11.5.0)

3. **radon** required:
   - mando <0.8 (latest was 0.8.2)

### Resolution Strategy
**Downgraded conflicting packages** to maintain compatibility with dev tools:
- ⬇️ click: 8.3.1 → 8.2.1
- ⬇️ responses: 0.25.8 → 0.21.0
- ⬇️ test-results-parser: 0.6.1 → 0.6.0
- ⬇️ cyclonedx-python-lib: 11.5.0 → 9.1.0
- ⬇️ mando: 0.8.2 → 0.7.1

**Result:** ✅ No broken requirements (`pip check` passed)

---

## Remaining Outdated Packages

**5 packages** remain at older versions due to compatibility constraints:

| Package | Current | Latest | Reason |
|---------|---------|--------|--------|
| click | 8.2.1 | 8.3.1 | codecov-cli constraint |
| cyclonedx-python-lib | 9.1.0 | 11.5.0 | pip-audit constraint |
| mando | 0.7.1 | 0.8.2 | radon constraint |
| responses | 0.21.0 | 0.25.8 | codecov-cli constraint |
| test-results-parser | 0.6.0 | 0.6.1 | codecov-cli constraint |

These packages will be automatically updated when the constraining dev tools release new versions.

---

## Test Results

Full test suite executed successfully after dependency updates:

```
✅ 505 tests passed
⏭️  11 tests skipped
⏱️  Test duration: 7.31 seconds
📊 Code coverage: 76.72% (requirement: 60%)
```

### Test Suite Breakdown
- Ruff format (apply): ✅ 58 files unchanged
- Ruff format check: ✅ All files formatted
- Ruff lint: ✅ All checks passed
- Import-linter contracts: ✅ Layer architecture verified
- Pyright type-check: ✅ 0 errors, 0 warnings
- Bandit security scan: ✅ No security issues
- pip-audit: ✅ No known vulnerabilities
- pytest with coverage: ✅ 505 passed, 11 skipped

### Coverage by Module
- formatters.py: 100%
- mail.py: 100%
- monitor.py: 100%
- config.py: 100%
- __init__conf__.py: 100%
- zfs_parser.py: 97%
- config_show.py: 97%
- __main__.py: 96%
- alert_state.py: 94%
- alerting.py: 91%
- models.py: 85%
- daemon.py: 77%
- behaviors.py: 74%
- cli.py: 69%
- zfs_client.py: 25% (intentionally low - requires ZFS)
- service_install.py: 10% (intentionally low - requires systemd)

---

## Breaking Changes

**None detected.** All updates were minor/patch versions of transitive dependencies with no breaking changes to the project's API or functionality.

---

## Security Impact

Updated `certifi` package from 2025.10.5 to 2025.11.12, ensuring the latest SSL/TLS certificate bundle for secure HTTPS connections.

No security vulnerabilities detected by:
- pip-audit ✅
- bandit security scanner ✅

---

## Recommendations

1. ✅ **No immediate action required** - All updates applied successfully
2. 📌 **Monitor dev tool updates** - Watch for new releases of:
   - codecov-cli (to allow click 8.3+, responses 0.25+)
   - pip-audit (to allow cyclonedx-python-lib 11+)
   - radon (to allow mando 0.8+)
3. 🔄 **Regular updates** - Run dependency updates quarterly to stay current
4. 📊 **Coverage monitoring** - Codecov upload successful, continue monitoring

---

## Update Logs

All detailed logs saved to:
- `/media/srv-main-softdev/projects/tools/check_zpools/LLM-CONTEXT/review-anal/deps/`

### Log Files Created
- `outdated_packages_initial.json` - Initial outdated packages scan
- `current_packages.txt` - Full package list before updates
- `categorized_updates.json` - Categorized dependency analysis
- `update_log.txt` - Full pip update output
- `dependency_conflicts.txt` - Conflict detection details
- `conflict_resolution.txt` - Conflict resolution log
- `pip_check_result.txt` - Final dependency check
- `outdated_packages_final.json` - Remaining outdated packages
- `test_results.txt` - Complete test suite output
- `DEPENDENCY_UPDATE_SUMMARY.md` - This summary report

---

## Conclusion

The dependency update process completed successfully with:
- ✅ 18 packages updated to latest compatible versions
- ✅ All dependency conflicts resolved
- ✅ All 505 tests passing
- ✅ 76.72% code coverage maintained
- ✅ No security vulnerabilities
- ✅ No breaking changes

The project is now running on the latest stable versions of all dependencies within compatibility constraints.
