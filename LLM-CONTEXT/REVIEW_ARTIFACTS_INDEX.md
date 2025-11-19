# Code Review Analysis Artifacts

All analysis outputs generated during the comprehensive code review.

## Analysis Scripts

- `categorize_files.sh` - Categorizes files by type (CODE, TEST, CONFIG, etc.)
- `check_function_lengths.py` - Analyzes line counts for high-complexity functions
- `run_full_analysis.sh` - Runs comprehensive complexity analysis

## Analysis Results

### Complexity Analysis
- `full_complexity_analysis.txt` - Complete radon complexity analysis for all source files
- `function_length_analysis.txt` - Detailed line count analysis for high-complexity functions

### Code Quality
- `full_duplication_report.txt` - Pylint duplication detection results (Score: 10.00/10)

### Security
- `full_security_analysis.txt` - Bandit security scan results (1 low-severity false positive)

### File Organization
- `files_to_review_filtered.txt` - List of all reviewable files (116 total)
- `file_types_breakdown.txt` - Breakdown by file type (61 .py, 21 .md, etc.)
- `directory_breakdown.txt` - Breakdown by directory
- `categorized_files.txt` - Files categorized by purpose (CODE/TEST/CONFIG/DOCS/etc.)
- `prioritized_review_plan.txt` - Files prioritized for review

## Final Report

- `COMPREHENSIVE_REVIEW_FINDINGS.md` - Complete review report with all findings

## Key Findings Summary

### Critical Issues (3 functions)
- `zfs_parser.py::_parse_scrub_time` - C (12), 60 lines
- `config_show.py::display_config` - C (11), 94 lines  
- `service_install.py::_detect_uvx_from_process_tree` - C (15), 81 lines

### High Priority Issues (14 functions with B complexity >50 lines)
See full report for complete list.

### Code Quality Highlights
- ✓ ZERO duplication (10.00/10 score)
- ✓ Average complexity: A (3.08)
- ✓ Only 1 security issue (false positive)

