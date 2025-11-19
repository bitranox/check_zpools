# Review Findings: tests/test_alerting.py

## Changes Summary

### Change 1: Updated test_format_subject_includes_severity_and_pool (lines 205-214)

**Before:** Test checked for severity, pool name, and message
**After:** Test also checks for hostname in brackets

**Added lines 210-211:**
```python
assert "[" in subject  # Hostname should be in brackets
assert "]" in subject
```

**Updated docstring (line 206):**
```python
"""Subject should include hostname, severity, pool name, and message."""
```

### Change 2: Updated test_format_recovery_subject (lines 346-356)

**Before:** Test checked for recovery indication
**After:** Test also checks for hostname in brackets

**Added lines 351-352:**
```python
assert "[" in subject  # Hostname should be in brackets
assert "]" in subject
```

**Updated docstring (line 347):**
```python
"""Recovery subject should include hostname and indicate issue resolved."""
```

## Analysis

### Test Quality

#### Positive Aspects
✓ **Tests verify actual functionality:** Checking that brackets exist verifies hostname is included
✓ **Docstrings updated:** Clearly state hostname is being tested
✓ **Comments explain intent:** Inline comment clarifies what the brackets mean

#### Issues Found

**ISSUE #1: Tests are too generic**

The tests check for `[` and `]` but don't verify:
1. That the hostname is actually present
2. That the hostname is in the correct position (after prefix, before severity)
3. That the brackets contain actual content

**Current test:**
```python
assert "[" in subject  # Hostname should be in brackets
assert "]" in subject
```

**Problems:**
- Will pass if subject is: `"[ZFS Test] WARNING - pool"`  (no hostname!)
- Will pass if brackets are anywhere in the string
- Doesn't verify bracket contents

**Better test would be:**
```python
import socket

# Verify hostname is actually in the subject
hostname = socket.gethostname()
assert f"[{hostname}]" in subject, f"Expected hostname [{hostname}] in subject"

# Or at minimum, verify brackets have content between them
import re
hostname_match = re.search(r'\[([^\]]+)\].*\[([^\]]+)\]', subject)
assert hostname_match is not None, "Subject should have two bracketed sections"
assert len(hostname_match.group(2)) > 0, "Hostname brackets should not be empty"
```

**ISSUE #2: No verification of subject format**

The test doesn't verify the **order** or **format** of elements. 

**Expected format:**
```
[ZFS Alert] [hostname] SEVERITY - pool_name: message
```

**Current test would pass for:**
```
[ZFS Alert] SEVERITY [hostname] - pool_name: message  # Wrong order!
[hostname] [ZFS Alert] SEVERITY - pool_name: message  # Wrong order!
```

**Better test:**
```python
import socket

subject = alerter._format_subject(Severity.WARNING, "rpool", "High capacity")
hostname = socket.gethostname()

# Test the actual format
expected_start = f"[ZFS Test] [{hostname}] WARNING"
assert subject.startswith(expected_start), \
    f"Subject should start with '{expected_start}', got: {subject}"

assert "rpool" in subject
assert "High capacity" in subject
```

### Test Coverage

**What's tested:**
- ✓ Brackets exist in subject
- ✓ Other elements still present (severity, pool name, message, prefix)

**What's NOT tested:**
- ✗ Actual hostname value is included
- ✗ Hostname is in correct position
- ✗ Brackets contain non-empty content
- ✗ Subject format/structure

### Comparison with Actual Implementation

Let me verify what the actual implementation does:

**From alerting.py line 232:**
```python
hostname = socket.gethostname()
return f"{self.subject_prefix} [{hostname}] {severity.value.upper()} - {pool_name}: {message}"
```

So the implementation:
1. Gets actual hostname
2. Puts it in brackets
3. Positions it between prefix and severity

**The test doesn't verify any of this!**

## Verdict for test_alerting.py

**Status:** ⚠️ CHANGES RECOMMENDED (but not critical)

**Issues:**
1. **Tests are too weak** - Don't verify actual hostname presence
2. **Tests don't verify format** - Just check for bracket characters
3. **Easy to break implementation** without failing tests

**Recommended Changes:**

```python
def test_format_subject_includes_severity_and_pool(self, alerter: EmailAlerter) -> None:
    """Subject should include hostname, severity, pool name, and message."""
    import socket
    
    subject = alerter._format_subject(Severity.WARNING, "rpool", "High capacity")
    hostname = socket.gethostname()

    # Verify exact format
    assert subject.startswith(f"[ZFS Test] [{hostname}]"), \
        f"Subject should start with '[ZFS Test] [{hostname}]', got: {subject}"
    
    assert "WARNING" in subject
    assert "rpool" in subject
    assert "High capacity" in subject
    
    # Verify format structure
    assert subject.count("[") >= 2, "Subject should have at least 2 opening brackets"
    assert subject.count("]") >= 2, "Subject should have at least 2 closing brackets"

def test_format_recovery_subject(self, alerter: EmailAlerter) -> None:
    """Recovery subject should include hostname and indicate issue resolved."""
    import socket
    
    subject = alerter._format_recovery_subject("rpool", "capacity")
    hostname = socket.gethostname()

    # Verify exact format
    assert subject.startswith(f"[ZFS Test] [{hostname}]"), \
        f"Subject should start with '[ZFS Test] [{hostname}]', got: {subject}"
    
    assert "RECOVERY" in subject
    assert "rpool" in subject
    assert "capacity" in subject
```

**Estimated Effort:** 15 minutes
**Risk Level:** Very Low (strengthening existing tests)
**Priority:** Medium (tests pass but could be stronger)
