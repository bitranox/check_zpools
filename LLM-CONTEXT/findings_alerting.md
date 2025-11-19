# Review Findings: src/check_zpools/alerting.py

## CRITICAL ISSUE #1: Code Duplication - zpool status fetching

### Location
- `_format_body()` lines 296-319
- `_format_recovery_body()` lines 757-780

### Problem
**24 lines of IDENTICAL code** duplicated between alert and recovery email formatting:

```python
# Add zpool status output if ZFS client is available
if self.zfs_client is not None:
    try:
        zpool_status_output = self.zfs_client.get_pool_status_text(pool_name=pool.name)
        lines.extend(
            [
                "",
                "=" * 70,
                "ZPOOL STATUS OUTPUT",
                "=" * 70,
                zpool_status_output.rstrip(),
            ]
        )
    except Exception as exc:
        logger.warning(
            "Failed to fetch zpool status output for [email/recovery email]",
            extra={
                "pool": pool.name,
                "error": str(exc),
                "error_type": type(exc).__name__,
            },
        )
        # Continue without zpool status - don't fail the entire email
```

**Only difference:** Log message says "for email" vs "for recovery email"

### Impact
- **Maintainability:** Bug fixes must be applied twice
- **Code Size:** 24 unnecessary lines
- **DRY Violation:** Same logic duplicated

### Recommended Refactoring

Extract into a helper method:

```python
def _append_zpool_status(
    self,
    lines: list[str],
    pool_name: str,
    email_type: str = "email",
) -> None:
    """Append zpool status output to email lines.
    
    Parameters
    ----------
    lines:
        List to append status output to (modified in place).
    pool_name:
        Name of the pool to get status for.
    email_type:
        Type of email for logging ("email" or "recovery email").
    """
    if self.zfs_client is None:
        return
    
    try:
        zpool_status_output = self.zfs_client.get_pool_status_text(pool_name=pool_name)
        lines.extend(
            [
                "",
                "=" * 70,
                "ZPOOL STATUS OUTPUT",
                "=" * 70,
                zpool_status_output.rstrip(),
            ]
        )
    except Exception as exc:
        logger.warning(
            f"Failed to fetch zpool status output for {email_type}",
            extra={
                "pool": pool_name,
                "error": str(exc),
                "error_type": type(exc).__name__,
            },
        )
        # Continue without zpool status - don't fail the entire email

# Then in _format_body():
self._append_zpool_status(lines, pool.name, "email")

# And in _format_recovery_body():
self._append_zpool_status(lines, pool.name, "recovery email")
```

## CRITICAL ISSUE #2: Overly Long Functions

### Functions Exceeding 50 Lines

1. **`_format_recovery_body()` - 74 lines** (lines 708-781)
   - Already too long BEFORE the zpool status addition
   - Now even longer with new code
   - Should be broken down

2. **`send_recovery()` - 66 lines** (lines 154-219)
   - Mixes: configuration checks, email formatting, sending, error handling
   - Should separate concerns

3. **`_format_body()` - 64 lines** (lines 258-320)
   - Already too long BEFORE the zpool status addition
   - Now even longer with new code
   - Should be broken down

4. **`send_alert()` - 61 lines** (lines 93-153)
   - Similar to send_recovery() - too many concerns

5. **`_format_recommended_actions_section()` - 52 lines** (lines 403-454)
   - Barely over threshold
   - Could benefit from extraction

### Recommended Refactoring Strategy

The `_format_body()` and `_format_recovery_body()` are already well-structured with helper methods for each section. The issue is they're **orchestration functions** that could benefit from extraction:

**Option 1: Extract zpool status appending (already recommended above)**

**Option 2: Further break down into smaller orchestrators**
```python
def _format_body(self, issue: PoolIssue, pool: PoolStatus) -> str:
    """Format plain-text email body with issue details and pool stats."""
    lines: list[str] = []
    
    # Delegate to section builders
    self._append_alert_sections(lines, issue, pool)
    self._append_pool_status_sections(lines, pool)
    self._append_zpool_status(lines, pool.name, "email")
    
    return "\n".join(lines)

def _append_alert_sections(
    self,
    lines: list[str],
    issue: PoolIssue,
    pool: PoolStatus,
) -> None:
    """Append alert-specific sections to email lines."""
    hostname = socket.gethostname()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z")
    
    lines.extend(self._format_alert_header(issue, pool, hostname, timestamp))
    lines.extend(self._format_pool_details_section(pool))
    lines.extend(self._format_recommended_actions_section(issue, pool))
    lines.extend(self._format_alert_footer(hostname))

def _append_pool_status_sections(
    self,
    lines: list[str],
    pool: PoolStatus,
) -> None:
    """Append complete pool status section to email lines."""
    lines.extend(
        [
            "",
            "=" * 70,
            "COMPLETE POOL STATUS",
            "=" * 70,
        ]
    )
    lines.append(self._format_complete_pool_status(pool))
```

## ISSUE #3: Exception Handling Too Broad

### Location
Lines 309, 770

### Problem
```python
except Exception as exc:
```

This catches **ALL** exceptions, including:
- `KeyboardInterrupt` (although not likely here)
- `SystemExit`
- Programming errors (AttributeError, TypeError, etc.)

### Recommended Fix
Be more specific about what can fail:

```python
except (ZFSCommandError, subprocess.TimeoutExpired, RuntimeError) as exc:
```

Or at minimum:
```python
except Exception as exc:
    if isinstance(exc, (KeyboardInterrupt, SystemExit)):
        raise
    # ... rest of handling
```

## ISSUE #4: TYPE_CHECKING Import Pattern

### Location
Lines 27-34

```python
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .zfs_client import ZFSClient
```

### Observation
✓ **GOOD:** Proper use of TYPE_CHECKING to avoid circular imports
✓ **GOOD:** zfs_client parameter is properly type-hinted as `ZFSClient | None`

This is correct implementation.

## ISSUE #5: Memory Considerations

### Concern
`zpool status` output could be quite large for pools with many vdevs. Each email will fetch and store this in memory.

### Analysis
For a pool with 100 vdevs, output might be 10-20KB. Even for 1000 concurrent emails (unlikely), that's only 10-20MB.

**Verdict:** ✓ Not a practical concern for this use case.

## ISSUE #6: Error Logging Message Consistency

### Problem
Two slightly different messages for the same operation:
- Line 311: "Failed to fetch zpool status output for email"
- Line 772: "Failed to fetch zpool status output for recovery email"

### Recommended Fix
Use f-string with email_type parameter (as shown in refactoring suggestion).

## Other Observations

### Error Handling
✓ Graceful degradation - email still sends if zpool status fails
✓ Proper logging of failures
⚠️ Exception catching too broad (see Issue #3)

### Code Organization
✓ Consistent with existing patterns
✓ Good use of helper methods
⚠️ Functions too long (see Issue #2)

### Documentation
✓ No new documentation needed (implementation detail)

## Verdict for alerting.py

**Status:** ⚠️⚠️ CHANGES STRONGLY RECOMMENDED

**Required Actions:**
1. **HIGH PRIORITY:** Extract zpool status fetching into `_append_zpool_status()` helper
2. **MEDIUM PRIORITY:** Make exception handling more specific
3. **LOW PRIORITY:** Consider further breaking down long orchestration functions

**Estimated Effort:** 1-2 hours
**Risk Level:** Low-Medium (need to ensure error paths still work correctly)
