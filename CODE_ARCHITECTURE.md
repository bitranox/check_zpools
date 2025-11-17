# Code Architecture Documentation

## Email Alerting Module (`alerting.py`)

### Design Principles

The email alerting system follows clean code principles with:
- **Single Responsibility Principle**: Each method handles one specific formatting concern
- **DRY (Don't Repeat Yourself)**: Shared logic extracted into reusable helper methods
- **Self-Documenting Code**: Named constants instead of magic numbers

### Module-Level Constants

```python
# Binary unit multipliers (powers of 1024)
_BYTES_PER_KB = 1024
_BYTES_PER_MB = 1024 ** 2
_BYTES_PER_GB = 1024 ** 3
_BYTES_PER_TB = 1024 ** 4
_BYTES_PER_PB = 1024 ** 5
```

These constants provide self-documenting byte conversions and eliminate magic numbers throughout the codebase.

### Email Formatting Architecture

#### Return Pattern

All email formatting helper methods follow a consistent pattern:
- **Helper methods** return `list[str]` (individual lines)
- **Parent methods** perform single `"\n".join()` operation
- This prevents double-joining and ensures correct spacing

#### Alert Email Structure

**Main method:** `_format_body(issue, pool) -> str`

Delegates to specialized formatters:
1. `_format_alert_header()` → Alert header with issue details
2. `_format_pool_details_section()` → Pool capacity and scrub summary
3. `_format_recommended_actions_section()` → Context-specific actions
4. `_format_alert_footer()` → Version and hostname
5. `_format_complete_pool_status()` → Full pool status details

#### Pool Status Formatting

**Main method:** `_format_complete_pool_status(pool) -> str`

Delegates to specialized formatters:
1. `_format_capacity_section()` → Capacity in TB/GB/bytes
2. `_format_error_statistics_section()` → Error counts
3. `_format_scrub_status_section()` → Scrub timing and results
4. `_format_health_assessment_section()` → Health status
5. `_format_notes_section()` → Warnings (empty list if none)

### Helper Methods

#### `_calculate_scrub_age_days(pool) -> int | None`

Calculates days since last scrub. Returns `None` if pool has never been scrubbed.

**Used by:**
- `_format_pool_details_section()` - For alert email summary
- `_format_scrub_status_section()` - For detailed scrub status
- `_format_notes_section()` - For scrub age warnings

This eliminates code duplication across three locations.

### Binary Unit Conversions

All capacity calculations use named constants:

```python
used_tb = pool.allocated_bytes / _BYTES_PER_TB
used_gb = pool.allocated_bytes / _BYTES_PER_GB
```

This provides:
- Clear intent (what unit we're converting to)
- Easy maintenance (change definition in one place)
- Consistency across all calculations

## Daemon Module (`daemon.py`)

### Alert Processing Architecture

**Main method:** `_handle_check_result(result, pools) -> dict[str, set[str]]`

Delegates to specialized methods:
1. `_should_send_alert(issue)` → Filtering logic
2. `_send_alert_for_issue(issue, pool)` → Alert delivery

#### `_should_send_alert(issue) -> bool`

Determines if an alert should be sent based on:
- Severity filtering (skip OK issues if configured)
- Alert state management (prevent duplicates within resend interval)

#### `_send_alert_for_issue(issue, pool) -> None`

Handles alert delivery and state recording:
- Sends email via alerter
- Records successful delivery in state manager
- Logs result for monitoring

### Benefits

- **Testability**: Each concern can be tested independently
- **Maintainability**: Clear boundaries between filtering, sending, and recording
- **Readability**: Method names clearly describe intent

## Parser Module (`zfs_parser.py`)

### Regex Optimization

Pre-compiled regex pattern for performance:

```python
# Module-level constant
_SIZE_PATTERN = re.compile(r'^([0-9.]+)\s*([KMGTP])$')
```

**Used in:** `_parse_size_to_bytes(size_str) -> int`

Benefits:
- Pattern compiled once at module import
- Eliminates repeated compilation overhead
- Critical for daemon mode (continuous parsing)

### Helper Methods

#### `_parse_health_state(health_value, pool_name) -> PoolHealth`

Parses health state strings into enum values with fallback to OFFLINE for unknown states.

#### `_extract_capacity_metrics(props) -> dict`

Extracts and converts capacity metrics from pool properties:
- `capacity_percent` (float)
- `size_bytes`, `allocated_bytes`, `free_bytes` (int)

#### `_extract_scrub_info(pool_data) -> dict`

Extracts scrub information from pool status data:
- `last_scrub` (datetime | None)
- `scrub_errors` (int)
- `scrub_in_progress` (bool)

These helpers eliminate duplication between `_parse_pool_from_list()` and `_parse_pool_from_status()`.

## Code Quality Standards

### Type Hints

All methods include complete type hints:
- Parameter types
- Return types
- Union types where applicable (`int | None`)

### Documentation

Methods include structured docstrings:
- Purpose statement (Why)
- Implementation details (What)
- Parameter descriptions
- Return value descriptions

### Testing Recommendations

1. **Snapshot tests** for email formatting to catch spacing regressions
2. **Unit tests** for helper methods (scrub age, capacity calculations)
3. **Integration tests** for complete alert flow

### Performance Considerations

1. **Pre-compiled regex** for size parsing (daemon mode optimization)
2. **LRU cache** on size parsing method (existing optimization)
3. **Single join operation** for string formatting (memory efficiency)

## Future Enhancements

Potential improvements to consider:
1. Pass timestamp as parameter to eliminate multiple `datetime.now()` calls
2. Add examples in docstrings showing expected output
3. Implement snapshot/golden file tests for email formatting
