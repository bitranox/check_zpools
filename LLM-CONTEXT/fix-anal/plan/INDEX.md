# Fix Plan Index - check_zpools

**Location:** `/media/srv-main-softdev/projects/tools/check_zpools/LLM-CONTEXT/fix-anal/plan/`
**Generated:** 2025-11-19
**Based On:** Comprehensive code review (review-anal)

---

## Quick Navigation

### Start Here
- 📋 **[QUICK_REFERENCE.md](./QUICK_REFERENCE.md)** - One-page summary, recommended execution order
- 📖 **[FIX_PLAN.md](./FIX_PLAN.md)** - Complete fix plan with detailed strategies

### Source Material
- 📊 **[../../../LLM-CONTEXT/review-anal/report/REVIEW_REPORT.md](../../review-anal/report/REVIEW_REPORT.md)** - Full review report

---

## Document Overview

### QUICK_REFERENCE.md (2 pages)
**Purpose:** Fast orientation and daily reference
**Use when:** You need to quickly check status or next steps
**Contents:**
- At-a-glance metrics
- Priority breakdown
- Execution timeline
- Quick commands
- Success criteria

### FIX_PLAN.md (60+ pages)
**Purpose:** Comprehensive fix specifications
**Use when:** Planning or executing a specific fix
**Contents:**
- Executive summary
- PREREQUISITE: Fix review artifacts (P0)
- 2 High-priority issues (P1)
- 8 Medium-priority issues (P2)
- 23 Low-priority issues (P3)
- Evidence collection framework
- Rollback procedures
- Progress tracking

---

## Issue Categories

### By Priority

| Priority | Count | Effort | Timeline |
|----------|-------|--------|----------|
| P0 (PREREQUISITE) | 1 | 5 min | Immediate |
| P1 (HIGH) | 2 | 4-6 hrs | Week 1 |
| P2 (MEDIUM) | 8 | 20.5-28.5 hrs | Week 2-4 |
| P3 (LOW) | 22 | 8-12 hrs | Backlog |
| **TOTAL** | **33** | **33-46.5 hrs** | **1-2 sprints** |

### By Category

| Category | P0 | P1 | P2 | P3 | Total |
|----------|----|----|----|----|-------|
| Code Quality | 0 | 1 | 3 | 3 | 7 |
| Documentation | 0 | 1 | 3 | 1 | 5 |
| CI/CD | 0 | 0 | 2 | 8 | 10 |
| Security | 0 | 0 | 0 | 3 | 3 |
| Testing | 0 | 0 | 0 | 3 | 3 |
| Review Artifacts | 1 | 0 | 0 | 0 | 1 |
| Dependencies | 0 | 0 | 0 | 0 | 0 |
| Performance | 0 | 0 | 0 | 0 | 0 |

---

## Issue List

### P0 - PREREQUISITE (BLOCKING)

| ID | Title | Effort | Page |
|----|-------|--------|------|
| FIX-0 | Fix Ruff errors in review artifacts | 5 min | FIX_PLAN.md:L125 |

### P1 - HIGH PRIORITY

| ID | Title | Effort | Page |
|----|-------|--------|------|
| ISSUE-1 | Reduce critical complexity in scripts/test.py:_run() | 2-3 hrs | FIX_PLAN.md:L200 |
| ISSUE-2 | Update system design documentation | 2-3 hrs | FIX_PLAN.md:L350 |

### P2 - MEDIUM PRIORITY (Code Quality)

| ID | Title | Effort | Page |
|----|-------|--------|------|
| ISSUE-3 | Reduce code duplication (131 blocks) | 8-12 hrs | FIX_PLAN.md:L550 |
| ISSUE-4 | Break up long functions (46 functions) | 4-6 hrs | FIX_PLAN.md:L750 |
| ISSUE-10 | Reduce high-complexity functions (6 functions) | 3-4 hrs | FIX_PLAN.md:L1450 |

### P2 - MEDIUM PRIORITY (Documentation & CI/CD)

| ID | Title | Effort | Page |
|----|-------|--------|------|
| ISSUE-5 | Expand DEVELOPMENT.md testing docs | 1-2 hrs | FIX_PLAN.md:L900 |
| ISSUE-6 | Add pre-commit hooks | 1 hr | FIX_PLAN.md:L1050 |
| ISSUE-7 | Add models.py to CODE_ARCHITECTURE.md | 1 hr | FIX_PLAN.md:L1200 |
| ISSUE-8 | Enhance GitHub release notes | 2 hrs | FIX_PLAN.md:L1350 |
| ISSUE-9 | Align coverage targets | 30 min | FIX_PLAN.md:L1400 |

### P3 - LOW PRIORITY

| ID | Title | Effort | Page |
|----|-------|--------|------|
| ISSUE-11 | Add signal_handler docstring | 10 min | FIX_PLAN.md:L1600 |
| ISSUE-12 | Document or hide template commands | 30 min | FIX_PLAN.md:L1700 |
| ISSUE-13 | Add nosec comments for security false positives | 1 hr | FIX_PLAN.md:L1800 |
| ISSUE-14-33 | Various enhancements | 7-11 hrs | FIX_PLAN.md:L1900 |

---

## Key Metrics

### Baseline (Before Fixes)
- **Test Pass Rate:** 100% (505 passed, 11 skipped)
- **Coverage:** 76.72%
- **Avg Complexity:** 1.86
- **Max Complexity:** 17 (scripts/test.py:_run)
- **Duplicate Blocks:** 131 (~1,350 lines)
- **Long Functions:** 46 (>50 lines)
- **High Complexity:** 7 (CC >10)
- **Security Issues:** 20 (1 HIGH, 19 LOW - mostly false positives)

### Target (After Fixes)
- **Test Pass Rate:** 100% (maintained)
- **Coverage:** ≥76.72% (maintained or improved)
- **Avg Complexity:** <2 (maintained)
- **Max Complexity:** <10 (all functions)
- **Duplicate Blocks:** <50 (>60% reduction)
- **Long Functions:** <10 (well-justified cases only)
- **High Complexity:** 0 (all CC <10)
- **Security Issues:** 0 (acknowledged with nosec)

### Grade Progression
- **Current:** A (95%)
- **After P0/P1:** A (96%)
- **After P0/P1/P2:** A+ (98%)
- **After All:** A+ (99%)

---

## Execution Workflow

### Step 1: Preparation
1. Read QUICK_REFERENCE.md (5 min)
2. Review baseline metrics (see above)
3. Set up evidence collection (see FIX_PLAN.md:L2100)

### Step 2: Execute P0 (IMMEDIATE)
1. Fix Ruff errors in review artifacts (5 min)
2. Establish baseline (30 min)
3. Verify `make test` passes

### Step 3: Execute P1 (Week 1)
1. ISSUE-1: Reduce _run() complexity (2-3 hrs)
2. ISSUE-2: Update system design docs (2-3 hrs)
3. Collect evidence for each fix
4. Update progress in STATUS.md

### Step 4: Execute P2 (Week 2-4)
1. Code Quality issues (ISSUE-3, 4, 10) - 15-22 hrs
2. Documentation & CI/CD (ISSUE-5, 6, 7, 8, 9) - 5.5-6.5 hrs
3. Validate all changes
4. Update metrics

### Step 5: Execute P3 (Backlog)
1. Optional enhancements (ISSUE-11 through 33)
2. As time permits
3. Low risk, nice-to-have improvements

---

## Evidence Collection

### Baseline (Before ANY fixes)
```bash
mkdir -p LLM-CONTEXT/fix-anal/baseline
make test > LLM-CONTEXT/fix-anal/baseline/test_output.txt 2>&1
radon cc -a -s src/ scripts/ > LLM-CONTEXT/fix-anal/baseline/complexity.txt
# ... (see FIX_PLAN.md for complete script)
```

### Per-Fix Evidence
```bash
mkdir -p LLM-CONTEXT/fix-anal/evidence/ISSUE-X
# Before: capture metrics
# Apply fix
# After: capture metrics
# Compare: verify improvement
```

See FIX_PLAN.md:L2100 for complete evidence collection framework.

---

## Success Validation

### Automated Checks
```bash
# Run validation script
bash LLM-CONTEXT/fix-anal/scripts/validate_fix.sh ISSUE-X
```

### Manual Verification
For each fix, verify:
- ✅ All tests pass (same or better)
- ✅ Coverage maintained (≥76.72%)
- ✅ No new lint/type errors
- ✅ Metrics improved (complexity, duplication, etc.)
- ✅ Documentation updated
- ✅ Evidence collected

---

## Rollback Procedures

### Individual Fix Rollback
```bash
git checkout -- <files>
make test
echo "ISSUE-X rolled back: <reason>" >> LLM-CONTEXT/fix-anal/rollback_log.txt
```

### Emergency Full Rollback
```bash
git reset --hard <baseline-commit>
make test
# Document and reassess
```

See FIX_PLAN.md:L2400 for complete rollback procedures.

---

## Progress Tracking

### Status Document
- **Location:** `LLM-CONTEXT/fix-anal/STATUS.md`
- **Update:** After each fix
- **Contents:** Metrics, issue status, recent activity

### Evidence Directory
- **Location:** `LLM-CONTEXT/fix-anal/evidence/`
- **Structure:** One subdirectory per issue
- **Contents:** Before/after measurements, diffs, validation results

### Baseline Directory
- **Location:** `LLM-CONTEXT/fix-anal/baseline/`
- **Purpose:** Reference metrics before any fixes
- **Created:** Before starting FIX-0

---

## Related Documentation

### Review Analysis
- **Main Report:** `LLM-CONTEXT/review-anal/report/REVIEW_REPORT.md`
- **Quality Analysis:** `LLM-CONTEXT/review-anal/quality/ANALYSIS_SUMMARY.md`
- **Security Analysis:** `LLM-CONTEXT/review-anal/security/SECURITY_FINDINGS_SUMMARY.md`
- **Performance:** `LLM-CONTEXT/review-anal/perf/EXECUTIVE_SUMMARY.txt`
- **Documentation:** `LLM-CONTEXT/review-anal/docs/SUMMARY.md`
- **CI/CD:** `LLM-CONTEXT/review-anal/cicd/CICD_ANALYSIS_SUMMARY.md`

### Project Documentation
- **README:** `README.md`
- **Architecture:** `CODE_ARCHITECTURE.md`
- **Development:** `DEVELOPMENT.md`
- **Contributing:** `CONTRIBUTING.md`
- **Claude Guidelines:** `CLAUDE.md`

---

## FAQ

### Q: Where do I start?
**A:** Read QUICK_REFERENCE.md, then execute FIX-0 (5 min) to fix review artifacts.

### Q: What's the critical path?
**A:** FIX-0 → ISSUE-1 → ISSUE-2 (total: 5 hrs)

### Q: Can I skip P2/P3 issues?
**A:** Yes. P1 issues are recommended for next release, P2/P3 are enhancements.

### Q: How do I track progress?
**A:** Update `LLM-CONTEXT/fix-anal/STATUS.md` after each fix.

### Q: What if a fix breaks something?
**A:** Immediately rollback (see FIX_PLAN.md:L2400) and reassess.

### Q: How long will this take?
**A:** P0/P1: 5 hours, P0/P1/P2: 25-33 hours, All: 33-46.5 hours

### Q: Is this safe to do incrementally?
**A:** Yes. Each fix is independent (except noted dependencies) and can be done separately.

### Q: What's the expected grade improvement?
**A:** Current A (95%) → P1: A (96%) → P2: A+ (98%) → All: A+ (99%)

---

## Support & Contact

- **Full Plan:** FIX_PLAN.md
- **Quick Ref:** QUICK_REFERENCE.md
- **Review Report:** ../../review-anal/report/REVIEW_REPORT.md
- **Project Issues:** GitHub Issues (if available)

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-11-19 | Initial fix plan creation |

---

**Last Updated:** 2025-11-19
**Plan Author:** Claude Code (Sonnet 4.5)
**Review Basis:** /bx_review_anal comprehensive review
