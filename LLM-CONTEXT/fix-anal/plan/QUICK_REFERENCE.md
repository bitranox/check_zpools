# Fix Plan Quick Reference

**Project:** check_zpools v2.1.8
**Date:** 2025-11-19
**Full Plan:** See FIX_PLAN.md

---

## At a Glance

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| **Overall Grade** | A (95%) | A+ (98%) | ✅ Excellent |
| **Critical Issues** | 0 | 0 | ✅ None |
| **High Priority** | 2 | 0 | 🟡 2 to fix |
| **Test Pass Rate** | 100% | 100% | ✅ Passing |
| **Coverage** | 76.72% | >76% | ✅ Exceeds |
| **Max Complexity** | 17 | <10 | 🟡 Fix needed |
| **Duplicate Blocks** | 131 | <50 | 🟡 Reduce |

---

## Priority Breakdown

### P0 - IMMEDIATE (BLOCKING)
**Must fix before establishing baseline**

| Issue | Description | Effort | Status |
|-------|-------------|--------|--------|
| FIX-0 | Fix Ruff errors in review artifacts | 5 min | ⬜ Not started |

**CRITICAL:** This is blocking `make test`. Fix immediately.

---

### P1 - HIGH PRIORITY (Week 1)
**Recommended for next release**

| Issue | Description | Effort | Impact |
|-------|-------------|--------|--------|
| ISSUE-1 | Reduce _run() complexity from 17 to <10 | 2-3 hrs | Code quality |
| ISSUE-2 | Update system design docs (scaffold → ZFS) | 2-3 hrs | Developer confusion |

**Total:** 4-6 hours

---

### P2 - MEDIUM PRIORITY (Week 2-4)
**Suggested for next sprint**

#### Code Quality (Week 2-3)

| Issue | Description | Effort |
|-------|-------------|--------|
| ISSUE-3 | Reduce duplication (131 → <50 blocks) | 8-12 hrs |
| ISSUE-4 | Break up long functions (46 → 0) | 4-6 hrs |
| ISSUE-10 | Reduce high-complexity (6 functions) | 3-4 hrs |

**Subtotal:** 15-22 hours

#### Documentation & CI/CD (Week 3-4)

| Issue | Description | Effort |
|-------|-------------|--------|
| ISSUE-5 | Expand DEVELOPMENT.md testing docs | 1-2 hrs |
| ISSUE-6 | Add pre-commit hooks | 1 hr |
| ISSUE-7 | Add models.py to architecture docs | 1 hr |
| ISSUE-8 | Enhance GitHub release notes | 2 hrs |
| ISSUE-9 | Align coverage targets (60% vs 70%) | 30 min |

**Subtotal:** 5.5-6.5 hours

**Total P2:** 20.5-28.5 hours

---

### P3 - LOW PRIORITY (Backlog)
**Optional enhancements**

| Count | Category | Total Effort |
|-------|----------|--------------|
| 3 | Security (nosec, SECURITY.md) | 2-3 hrs |
| 4 | CI/CD (templates, OIDC, SBOM) | 4-6 hrs |
| 3 | Code Quality (nesting, params) | 2-3 hrs |

**Total P3:** 8-12 hours

---

## Recommended Execution Order

### Week 1: Foundation
1. **Day 1 Morning:** FIX-0 (5 min) + Establish baseline (30 min)
2. **Day 1-2:** ISSUE-1 (Reduce _run complexity)
3. **Day 3:** ISSUE-2 (Update docs)
4. **Day 4-5:** Begin ISSUE-3 Phase 1 (Extract test fixtures)

### Week 2: Code Quality
5. **Day 1-3:** ISSUE-3 Phases 2-4 (Reduce duplication)
6. **Day 4-5:** ISSUE-4 (Break up long functions)

### Week 3: Polish
7. **Day 1-2:** ISSUE-10 (Reduce high complexity)
8. **Day 3:** ISSUE-5 (Testing docs) + ISSUE-7 (Models docs)
9. **Day 4:** ISSUE-6 (Pre-commit) + ISSUE-9 (Coverage targets)
10. **Day 5:** ISSUE-8 (Release notes)

### Week 4+: Optional
11. **Backlog:** P3 issues as time permits

---

## Key Success Criteria

### Must Have (P0/P1)
- ✅ All tests passing
- ✅ `_run()` complexity < 10
- ✅ System design docs accurate
- ✅ Coverage ≥ 76%

### Should Have (P2)
- ✅ Duplication < 50 blocks
- ✅ All functions < 50 lines (except justified)
- ✅ All functions complexity < 10
- ✅ Testing docs comprehensive
- ✅ Pre-commit hooks active

### Nice to Have (P3)
- ✅ Security reports clean
- ✅ GitHub templates added
- ✅ OIDC publishing enabled

---

## Evidence Requirements

### Before ANY fix:
```bash
# Establish baseline
mkdir -p LLM-CONTEXT/fix-anal/baseline
make test > LLM-CONTEXT/fix-anal/baseline/test_output.txt 2>&1
radon cc -a -s src/ scripts/ > LLM-CONTEXT/fix-anal/baseline/complexity.txt
# ... (see full plan for complete baseline script)
```

### For EACH fix:
```bash
# Before
<measure metrics>
make test

# Apply fix
<make changes>

# After
<measure metrics>
make test

# Validate
diff before after
```

---

## Rollback Triggers

**Immediately rollback if:**
- ❌ Tests fail
- ❌ Coverage decreases
- ❌ New linting/type errors
- ❌ Performance degrades >10%
- ❌ Bugs introduced

**Rollback procedure:**
```bash
git checkout -- <files>
make test
echo "ISSUE-X rolled back: <reason>" >> LLM-CONTEXT/fix-anal/rollback_log.txt
```

---

## Quick Commands

### Run full test suite
```bash
make test
```

### Check complexity
```bash
radon cc -a -s src/ scripts/
```

### Check duplication
```bash
python LLM-CONTEXT/review-anal/quality/check_duplication.py
```

### Security scan
```bash
bandit -r src/ scripts/
```

### Coverage report
```bash
make coverage
```

---

## Progress Tracking

Track progress in: `LLM-CONTEXT/fix-anal/STATUS.md`

Update after each fix:
```markdown
### YYYY-MM-DD
- ✅ Completed ISSUE-X: <description>
- Results: <before → after metrics>
- Evidence: <link to evidence directory>
```

---

## Contact & Questions

- **Full Plan:** LLM-CONTEXT/fix-anal/plan/FIX_PLAN.md
- **Review Report:** LLM-CONTEXT/review-anal/report/REVIEW_REPORT.md
- **Evidence:** LLM-CONTEXT/fix-anal/evidence/
- **Baseline:** LLM-CONTEXT/fix-anal/baseline/

---

## Bottom Line

**Current Status:** Production-ready, A grade (95%)
**Goal:** Exceptional quality, A+ grade (98%)
**Critical Path:** FIX-0 → ISSUE-1 → ISSUE-2
**Total Effort:** 33-46.5 hours (1-2 sprint weeks)
**Risk:** LOW (all fixes are improvements, not bug fixes)

**Recommendation:** Fix high-priority items (P0/P1) this week, medium-priority (P2) next sprint, low-priority (P3) as time permits.
