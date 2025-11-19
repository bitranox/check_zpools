# Review Findings: src/check_zpools/zfs_client.py

## CRITICAL ISSUE #1: Significant Code Duplication

### Location
- `_execute_json_command()` (lines 302-389): 88 lines
- `_execute_text_command()` (lines 391-462): 72 lines

### Problem
**45+ lines of IDENTICAL code** between these two methods:
- Lines 331-351 in `_execute_json_command()` are identical to lines 418-438 in `_execute_text_command()`
- Lines 353-363 in `_execute_json_command()` are identical to lines 440-450 in `_execute_text_command()`
- Lines 381-389 in `_execute_json_command()` are identical to lines 454-462 in `_execute_text_command()`

### Duplicated Code Blocks

**Block 1: subprocess.run() execution (lines 334-340 vs 421-427)**
```python
result = subprocess.run(  # nosec B603
    command,
    capture_output=True,
    text=True,
    timeout=actual_timeout,
    check=False,
)
```

**Block 2: Logging (lines 342-351 vs 429-438)**
```python
logger.debug(
    "Command completed",
    extra={
        "command": " ".join(command),
        "exit_code": result.returncode,
        "stdout_length": len(result.stdout),
        "stderr_length": len(result.stderr),
    },
)
```

**Block 3: Error checking (lines 353-363 vs 440-450)**
```python
if result.returncode != 0:
    logger.error(
        "ZFS command failed",
        extra={
            "command": " ".join(command),
            "exit_code": result.returncode,
            "stderr": result.stderr,
        },
    )
    raise ZFSCommandError(command, result.returncode, result.stderr)
```

**Block 4: Timeout handling (lines 381-389 vs 454-462)**
```python
except subprocess.TimeoutExpired:
    logger.error(
        "ZFS command timed out",
        extra={
            "command": " ".join(command),
            "timeout": actual_timeout,
        },
    )
    raise
```

### Impact
- **Maintainability:** Changes must be duplicated in both methods
- **Bug Risk:** Easy to fix a bug in one method but not the other
- **Code Size:** 45+ unnecessary lines
- **Violation:** DRY principle violated

### Recommended Refactoring

Extract common code into a shared helper:

```python
def _execute_command(
    self,
    command: list[str],
    *,
    timeout: int | None = None,
) -> subprocess.CompletedProcess:
    """Execute command and return result.
    
    Common implementation for both JSON and text commands.
    """
    actual_timeout = timeout if timeout is not None else self.default_timeout
    
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=actual_timeout,
            check=False,
        )
        
        # Log command execution
        logger.debug(
            "Command completed",
            extra={
                "command": " ".join(command),
                "exit_code": result.returncode,
                "stdout_length": len(result.stdout),
                "stderr_length": len(result.stderr),
            },
        )
        
        # Check for command failure
        if result.returncode != 0:
            logger.error(
                "ZFS command failed",
                extra={
                    "command": " ".join(command),
                    "exit_code": result.returncode,
                    "stderr": result.stderr,
                },
            )
            raise ZFSCommandError(command, result.returncode, result.stderr)
        
        return result
        
    except subprocess.TimeoutExpired:
        logger.error(
            "ZFS command timed out",
            extra={
                "command": " ".join(command),
                "timeout": actual_timeout,
            },
        )
        raise

def _execute_json_command(
    self,
    command: list[str],
    *,
    timeout: int | None = None,
) -> dict[str, Any]:
    """Execute command and parse JSON output."""
    result = self._execute_command(command, timeout=timeout)
    
    try:
        data = json.loads(result.stdout)
        logger.debug(f"Parsed JSON successfully, top-level keys: {list(data.keys())}")
        return data
    except json.JSONDecodeError as exc:
        logger.error(
            "Failed to parse JSON output",
            extra={
                "command": " ".join(command),
                "stdout_preview": result.stdout[:500],
                "error": str(exc),
            },
        )
        raise

def _execute_text_command(
    self,
    command: list[str],
    *,
    timeout: int | None = None,
) -> str:
    """Execute command and return text output."""
    result = self._execute_command(command, timeout=timeout)
    return result.stdout
```

**Benefits:**
- Reduces code by ~50 lines
- Single place to fix bugs
- Clearer separation of concerns
- Easier to test

## Other Observations

### Security
✓ Proper use of subprocess with list arguments (no shell=True)
✓ Correct # nosec annotation with justification
✓ Timeout handling in place

### Documentation
✓ Comprehensive docstrings
✓ Examples provided
✓ Return types and exceptions documented

### API Design
✓ Consistent with existing methods (get_pool_list, get_pool_status)
✓ Proper keyword-only arguments
✓ Optional timeout parameter

## Verdict for zfs_client.py

**Status:** ⚠️ CHANGES REQUIRED

**Required Actions:**
1. **CRITICAL:** Refactor to eliminate code duplication between _execute_json_command() and _execute_text_command()
2. Extract common command execution into _execute_command() helper
3. Verify all tests still pass after refactoring

**Estimated Effort:** 30 minutes
**Risk Level:** Low (well-tested code, straightforward refactoring)
