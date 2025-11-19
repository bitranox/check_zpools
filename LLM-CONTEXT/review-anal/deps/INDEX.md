# Dependency Update - File Index

## Generated Files

All dependency update artifacts are stored in:
`/media/srv-main-softdev/projects/tools/check_zpools/LLM-CONTEXT/review-anal/deps/`

### Summary Reports
- **DEPENDENCY_UPDATE_SUMMARY.md** - Human-readable comprehensive summary report
- **update_summary.json** - Machine-readable summary with statistics

### Analysis Files
- **categorized_updates.json** - Categorized list of direct vs transitive dependencies
- **update_analysis.txt** - Initial dependency analysis

### Package Lists
- **outdated_packages_initial.json** - Initial scan of outdated packages
- **outdated_packages_final.json** - Remaining outdated packages after updates
- **current_packages.txt** - Complete package list before updates

### Update Logs
- **update_log.txt** - Complete pip update output
- **conflict_resolution.txt** - Dependency conflict resolution log
- **dependency_conflicts.txt** - Detected conflicts and resolution strategy

### Verification
- **pip_check_result.txt** - Final dependency integrity check
- **test_results.txt** - Complete test suite output (505 tests)

### This Index
- **INDEX.md** - This file

## Quick Reference

```bash
# View summary report
cat DEPENDENCY_UPDATE_SUMMARY.md

# View test results
tail -100 test_results.txt

# View machine-readable summary
cat update_summary.json | jq

# Check for conflicts
cat pip_check_result.txt

# View outdated packages
cat outdated_packages_final.json | jq
```
