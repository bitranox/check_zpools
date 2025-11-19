# Quality Analysis Summary - check_zpools

**Analysis Date**: 2025-11-19
**Files Analyzed**: 57 Python files
**Output Location**: `/media/srv-main-softdev/projects/tools/check_zpools/LLM-CONTEXT/review-anal/quality/`

---

## Executive Summary

The quality analysis has been completed on the check_zpools codebase. Overall, the codebase shows **good quality** with low average complexity, but there are specific areas that require attention for maintainability and code quality improvements.

### Key Metrics

| Metric | Value |
|--------|-------|
| Total Functions | 885 |
| Total Classes | 144 |
| Total Lines of Code | 14,939 |
| Average Cyclomatic Complexity | 1.86 |
| Maximum Cyclomatic Complexity | 17 |
| Functions with Complexity > 10 | 7 |
| Functions with Complexity > 15 | 1 |
| Duplicate Code Blocks | 131 |
| Estimated Duplicate Lines | 1,350 |
| Functions Needing Refactoring | 62 |

---

## Detailed Findings

### 1. Complexity Analysis

#### Critical Issues (Cyclomatic Complexity > 15)
- **scripts/test.py:_run()** - Complexity: 17, Cognitive: 20
  - 37 lines, 5 parameters, nested depth of 3
  - This is the highest complexity function in the codebase
  - Requires immediate refactoring

#### High Complexity (Cyclomatic Complexity > 10)
1. **scripts/_utils.py:bootstrap_dev()** - Complexity: 14, Cognitive: 17
2. **scripts/test.py:_upload_coverage_report()** - Complexity: 13, Cognitive: 10
3. **scripts/test.py:_pip_audit_guarded()** - Complexity: 12, Cognitive: 17
4. **scripts/test.py:run_tests()** - Complexity: 12, Cognitive: 16
5. **scripts/menu.py:_gather_values()** - Complexity: 11
6. **scripts/push.py:_resolve_commit_message()** - Complexity: 11

#### Good News
- Average complexity of 1.86 is excellent
- Only 7 functions exceed complexity threshold of 10
- Only 1 function exceeds critical threshold of 15

### 2. Code Duplication

**131 duplicate code blocks detected** with approximately **1,350 duplicate lines**

#### Major Duplication Patterns

1. **Test Data Fixtures** (Most Common)
   - PoolStatus object creation appears 10+ times
   - CheckResult initialization duplicated across test files
   - Mock configuration setup repeated in test_cli.py

2. **CLI Argument Patterns**
   - `--to`, `--subject`, `--body` argument definitions duplicated
   - Email configuration mock setup (5+ occurrences)
   - CLI invocation patterns in tests

3. **Parameter Validation**
   - Type checking and default value handling
   - Configuration section extraction (4 occurrences in mail.py)

4. **Error Handling**
   - Try-catch blocks with similar logging patterns
   - Email sending error handling (2 occurrences in alerting.py)

#### Recommended Actions
- Extract test fixtures into conftest.py
- Create shared CLI decorator functions
- Centralize configuration extraction logic
- Create error handling wrapper functions

### 3. Refactoring Opportunities

**62 functions identified** needing refactoring across the following categories:

#### Issue Breakdown

| Issue Type | Count | Priority |
|------------|-------|----------|
| Long function (>50 lines) | 46 | High |
| Too many parameters (>5) | 9 | Medium |
| Too many return statements (>3) | 9 | Medium |
| High cyclomatic complexity (>10) | 7 | Critical |
| High cognitive complexity (>15) | 6 | Critical |
| Deep nesting (>4 levels) | 1 | High |

---

## Top 10 Files Requiring Attention

### 1. scripts/test.py
- **Attention Score**: 52 (Highest)
- **Max Complexity**: 17
- **Refactoring Opportunities**: 5
- **Issues**:
  - `_run()` function has highest complexity in codebase
  - Multiple long functions (run_tests: 238 lines)
  - Too many returns in _upload_coverage_report

### 2. scripts/_utils.py
- **Attention Score**: 43
- **Max Complexity**: 14
- **Refactoring Opportunities**: 4
- **Issues**:
  - `bootstrap_dev()` high complexity
  - Long functions: get_project_metadata (67 lines), _render_metadata_module (78 lines)
  - `run()` has too many parameters (6)

### 3. src/check_zpools/service_install.py
- **Attention Score**: 37
- **Max Complexity**: 9
- **Refactoring Opportunities**: 5
- **Issues**:
  - Multiple long functions (install_service: 103 lines, uninstall_service: 76 lines)
  - _generate_service_file_content: 82 lines

### 4. src/check_zpools/alerting.py
- **Attention Score**: 36
- **Max Complexity**: 8
- **Refactoring Opportunities**: 5
- **Issues**:
  - Constructor with 7 parameters
  - Multiple long functions for formatting
  - Code duplication in error handling

### 5. src/check_zpools/mail.py
- **Attention Score**: 34
- **Max Complexity**: 9
- **Refactoring Opportunities**: 4
- **Issues**:
  - send_email: 119 lines, 7 parameters
  - High cognitive complexity in __post_init__
  - Configuration extraction duplication

### 6. src/check_zpools/daemon.py
- **Attention Score**: 30
- **Max Complexity**: 7
- **Refactoring Opportunities**: 4
- **Issues**:
  - Constructor with 6 parameters
  - Multiple long functions (start: 58 lines)

### 7. src/check_zpools/monitor.py
- **Attention Score**: 30
- **Max Complexity**: 7
- **Refactoring Opportunities**: 4
- **Issues**:
  - Multiple 60+ line functions
  - Similar checking logic could be extracted

### 8. src/check_zpools/zfs_parser.py
- **Attention Score**: 29
- **Max Complexity**: 7
- **Refactoring Opportunities**: 4
- **Issues**:
  - Long parsing functions
  - _parse_size_to_bytes: 71 lines

### 9. src/check_zpools/behaviors.py
- **Attention Score**: 28
- **Max Complexity**: 8
- **Refactoring Opportunities**: 3
- **Issues**:
  - run_daemon: 108 lines
  - check_pools_once: 79 lines

### 10. src/check_zpools/cli.py
- **Attention Score**: 27
- **Max Complexity**: 7
- **Refactoring Opportunities**: 3
- **Issues**:
  - cli_send_email: 103 lines, 6 parameters
  - Argument definition duplication

---

## Critical Functions Requiring Immediate Attention

### Priority 1: Critical Complexity
1. **scripts/test.py:_run()** - CC: 17, CogC: 20
   - Break into smaller validation functions
   - Extract conditional logic into helper methods

2. **scripts/_utils.py:bootstrap_dev()** - CC: 14, CogC: 17
   - Extract environment setup steps
   - Separate validation from execution

3. **scripts/test.py:_pip_audit_guarded()** - CC: 12, CogC: 17
   - Simplify nested error handling
   - Extract ignore resolution logic

### Priority 2: Long Functions
1. **scripts/test.py:run_tests()** - 238 lines
   - Break into stages: setup, execute, report
   - Extract each test type into separate functions

2. **src/check_zpools/mail.py:send_email()** - 119 lines
   - Extract SMTP connection logic
   - Separate message building from sending

3. **src/check_zpools/behaviors.py:run_daemon()** - 108 lines
   - Extract signal handling
   - Separate initialization from main loop

### Priority 3: Deep Nesting
1. **src/check_zpools/formatters.py:_format_last_scrub()** - 5 levels
   - Use early returns
   - Extract nested logic into helper functions

---

## Recommendations

### Immediate Actions (Critical)
1. Refactor `scripts/test.py:_run()` to reduce complexity from 17 to <10
2. Break up long functions in test.py (especially run_tests: 238 lines)
3. Address deep nesting in formatters.py:_format_last_scrub()

### Short-term Actions (High Priority)
1. Extract duplicate test fixtures to conftest.py
2. Create shared CLI decorators for common arguments
3. Refactor functions with >7 parameters using configuration objects
4. Break functions >100 lines into smaller, focused functions

### Medium-term Actions
1. Reduce code duplication from 131 blocks to <50
2. Centralize error handling patterns
3. Extract configuration validation logic
4. Create builder patterns for complex object construction

### Long-term Improvements
1. Maintain cyclomatic complexity <10 for all new functions
2. Keep function length <50 lines
3. Limit parameters to 4-5 maximum
4. Regular duplication analysis and cleanup

---

## Analysis Outputs

All detailed reports are available in:
`/media/srv-main-softdev/projects/tools/check_zpools/LLM-CONTEXT/review-anal/quality/`

- **complexity_analysis.txt** - Full complexity metrics for all files and functions
- **duplication_analysis.txt** - Complete list of all 131 duplicate code blocks
- **refactoring_opportunities.txt** - Detailed refactoring suggestions for 62 functions
- **quality_summary.txt** - Statistical summary and top files ranking
- **run_quality_analysis.py** - The analysis tool (reusable for future runs)

---

## Conclusion

The check_zpools codebase demonstrates **good overall quality** with:
- ✅ Excellent average complexity (1.86)
- ✅ Only 7 high-complexity functions
- ✅ Well-structured test coverage
- ✅ Clear separation of concerns

Areas for improvement:
- ⚠️ Reduce duplication (1,350 duplicate lines)
- ⚠️ Refactor 7 high-complexity functions
- ⚠️ Break up 46 long functions
- ⚠️ Simplify parameter lists in 9 functions

The codebase is maintainable in its current state, but addressing the identified refactoring opportunities will significantly improve long-term maintainability and reduce technical debt.
