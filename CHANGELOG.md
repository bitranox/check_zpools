# Changelog

All notable changes to this project will be documented in this file following
the [Keep a Changelog](https://keepachangelog.com/) format.

## [2.1.1] - 2025-11-18

### Documentation
- **README (Daemon Logging Section)**: Added comprehensive documentation for daemon logging features
  - New "Daemon Logging" section with complete guide to log levels, formats, and fields
  - Examples of check cycle statistics and per-pool detail logs
  - Systemd journald query examples (view last 50 entries, filter by level, time ranges)
  - Foreground mode logging examples with DEBUG level and file redirection
  - Real-world example log output showing multiple check cycles
  - Log analysis tips for monitoring daemon health, tracking capacity, and finding issues
  - **Why this matters**: Administrators now have clear documentation on how to monitor and troubleshoot the daemon using logs

## [2.1.0] - 2025-11-18

### Added
- **Daemon Logging (Statistics Tracking)**: Enhanced daemon mode with comprehensive statistics logging
  - Logs check cycle number and daemon uptime on each check (e.g., "Check #42, uptime: 2d 5h 30m")
  - Tracks total number of checks performed since daemon start
  - Displays human-readable uptime in days, hours, and minutes format
  - **Why this matters**: Administrators can monitor daemon health and track monitoring activity in logs
- **Daemon Logging (Pool Details)**: Added detailed INFO-level logging for each pool on every check cycle
  - Logs all key pool metrics: health, capacity, size, allocated, free, errors, scrub status
  - Human-readable size formatting (e.g., "1.00 TB", "464.00 GB")
  - Formatted scrub timestamps (e.g., "2025-11-18 14:30:00") or "Never" if never scrubbed
  - Error counts for read/write/checksum errors
  - **Why this matters**: Complete pool state is logged for troubleshooting and audit trail without running manual commands

## [2.0.6] - 2025-11-18

### Fixed
- **Service Installation (ProtectHome security setting)**: Removed `ProtectHome` directive from systemd service file
  - `ProtectHome=true` completely blocks access to `/root`, preventing uvx from accessing `/root/.cache/uv`
  - Even `ProtectHome=read-only` can cause issues with cache access
  - Service still runs as root with `ProtectSystem=strict` and `NoNewPrivileges=true` for security
  - **Why this matters**: The service needs access to `/root/.cache/uv` for uvx installations, and ProtectHome interferes with this requirement
- **Service Installation (Warning Message)**: Updated version number in example to reflect current version
  - Now correctly states: Use explicit version for production (e.g., `@2.0.6`)
  - Clarifies that `@latest` is for auto-updates but not recommended for production

## [2.0.5] - 2025-11-18
### Changed
- **Service Installation (Code Refactoring)**: Significantly simplified service installation module
  - Reduced code from 852 lines to 605 lines (29% reduction, 247 lines removed)
  - Merged 3 redundant functions into single `_detect_uvx_from_process_tree()` function
  - Removed support for unused installation methods (venv, uv project)
  - Now only supports 2 installation methods: "uvx" and "direct"
  - Simplified service file generation (removed 4 conditional branches)
  - Improved code clarity and maintainability
  - **Why this matters**: The previous code was over-engineered for edge cases that don't occur in practice. The simplified code is easier to understand, debug, and extend.

## [2.0.4] - 2025-11-18
### Fixed
- **Service Installation (uvx cache directory access)**: Fixed "Read-only file system" error when running daemon via uvx
  - Added `/root/.cache/uv` to `ReadWritePaths` in systemd service file for uvx installations
  - uvx needs write access to its cache directory even with `ProtectSystem=strict`
  - **Why this matters**: uvx creates temporary venvs in `/root/.cache/uv/` on every invocation, which was blocked by systemd's filesystem protection
- **Service Installation (MemoryLimit deprecation)**: Changed `MemoryLimit` to `MemoryMax` in systemd service file
  - Follows systemd best practices and eliminates deprecation warning
- **Service Installation (Enhanced logging for version detection)**: Improved logging to help diagnose uvx version detection issues
  - Added detailed debug logging showing each ancestor process checked
  - Added warnings when version specifier not found in process tree
  - Provides helpful error message with example command when auto-detection fails

### Documentation
- **Important**: When installing service via uvx, include a version specifier for best results:
  - ✅ Recommended for production: `uvx check_zpools@2.0.4 service-install`
  - ✅ Acceptable for auto-updates: `uvx check_zpools@latest service-install`
  - ⚠️  Works but may use unexpected version: `uvx check_zpools service-install`
- Version specifier is auto-detected from the invocation command and included in the service file

## [2.0.3] - 2025-11-17
### Fixed
- **Service Installation (uvx detection via 'uv tool uvx')**: Fixed uvx detection when uvx is invoked as a wrapper around `uv tool uvx`
  - Detects `uv tool uvx` pattern in process tree and locates uvx sibling binary in same directory as uv
  - Walks up to 10 ancestor processes (increased from 5) to find uvx/uv
  - Checks both cmdline[0] and cmdline[1] for Python script invocations
  - Continues searching even if individual ancestors fail (improved error handling)
  - Resolves relative paths to absolute paths for accurate matching
  - **Why this matters**: Modern uvx implementations exec to `uv tool uvx`, so the parent process is `uv` not `uvx`. We must detect this pattern and find the actual uvx binary in the same directory as uv.

### Added
- **Service Installation (Auto-detect uvx version)**: Automatically detects version specifier when invoked via uvx
  - Scans process tree for `check_zpools@version` pattern (e.g., `check_zpools@latest`, `check_zpools@1.0.0`)
  - Automatically includes version specifier in systemd service file ExecStart
  - No need to manually specify `--uvx-version` parameter - it's extracted from invocation
  - **Why this matters**: When user runs `uvx check_zpools@latest service-install`, the service file will use `uvx check_zpools@latest daemon` instead of just `uvx check_zpools daemon`, ensuring the service runs the correct version

## [2.0.0] - 2025-11-17
### Changed - BREAKING CHANGES
- **CLI Command Naming**: Renamed service management commands for better consistency
  - `install-service` → `service-install`
  - `uninstall-service` → `service-uninstall`
  - **Migration**: Update scripts and documentation to use new command names
- **Size Display Format**: Changed pool size display in `check` command output from compact format (e.g., "1.0T", "464.0G") to explicit unit format (e.g., "1.00 TB", "464.00 GB") for better readability
- **Error Column Consolidation**: Combined three error columns into single "Errors (R/W/C)" column
  - Previous: Separate columns for "Read Errors", "Write Errors", "Checksum Errors"
  - New: Single column showing "0/0/0" format (Read/Write/Checksum)
  - Benefit: More compact table display, easier to scan

### Removed - BREAKING CHANGES
- **status command**: Removed redundant `status` command - use `check` command instead
  - The `status` command only displayed pool information without threshold evaluation
  - The `check` command provides the same pool status display PLUS issue detection and monitoring
  - **Migration**: Replace `check_zpools status` with `check_zpools check`

### Fixed
- **Service Installation (uvx detection priority)**: Fixed critical design flaw where system PATH uvx was used instead of user's explicitly chosen uvx
  - **Search priority order** (respects user intent):
    1. Parent process (uvx that actually launched check_zpools) - PRIMARY
    2. Current working directory (`./uvx`)
    3. Same bin directory as check_zpools
    4. System PATH - LAST RESORT ONLY
  - Uses `psutil` to examine parent process command line and executable path
  - Handles all invocation methods: `./uvx`, `/path/to/uvx`, `uvx` in PATH
  - Resolves relative paths to absolute paths for parent process detection
  - Falls back to parent process executable path if cmdline path resolution fails
  - **Why this matters**: If user runs `/opt/venv/bin/uvx`, we must use THAT uvx, not a different one from PATH

### Added
- **Last Scrub Column**: Added "Last Scrub" column to `check` command table output showing when each pool was last scrubbed
  - Displays relative time (e.g., "Today", "Yesterday", "2d ago", "3w ago", "2mo ago")
  - Color-coded: green for recent scrubs (<30 days), yellow for aging (30-60 days), red for old (>60 days)
  - Shows "Never" in yellow if pool has never been scrubbed
  - Comprehensive test coverage: 16 tests covering all time ranges, boundaries, and edge cases
- `psutil>=6.1.0` dependency for robust parent process detection during service installation

### Testing
- Added 16 comprehensive unit tests for `_format_last_scrub()` helper function
- Tests cover: None handling, all time ranges (today, yesterday, days, weeks, months), color coding, timezone handling (naive/aware), and boundary conditions
- Total test count: 439 tests (all passing)


## [1.1.6] - 2025-11-17
### Changed
- **CLI Command Naming**: Renamed `install-service` to `service-install` and `uninstall-service` to `service-uninstall` for better consistency with other service commands
### Fixed
- **Service Installation (uvx not in PATH)**: Fixed installation failure when uvx is invoked with relative/absolute path (e.g., `./uvx check_zpools service-install` or `/path/to/uvx check_zpools service-install`) - now uses psutil to examine parent process command line to locate uvx executable, with fallbacks to current working directory and check_zpools bin directory
### Added
- `psutil>=7.1.3` dependency for robust parent process detection during service installation

## [1.1.2] - 2025-11-17
### Fixed
- **Service Installation (uvx detection)**: Fixed uvx detection being incorrectly identified as venv installation - reordered detection checks to check for uvx cache paths (`cache/uv/`) BEFORE checking for virtual environments, since uvx creates temporary venvs. Service file now correctly uses `uvx check_zpools` instead of ephemeral cache paths like `/root/.cache/uv/archive-v0/.../bin/check_zpools`

## [1.1.1] - 2025-11-17
### Added
- **Service Installation (uvx version control)**: Added `--uvx-version` option to `install-service` command, allowing users to specify version for uvx installations (e.g., `@latest` for auto-updates or `@1.0.0` for pinned versions)
### Fixed
- **CLI Output Rendering**: Fixed ANSI escape codes displaying literally after running TUIs like Midnight Commander - refactored to print directly to console instead of using intermediate StringIO buffer, preventing double-encoding issues
- **Service Installation (uvx)**: Fixed service installation when using uvx - now correctly detects uvx cache paths (`cache/uv/`) and generates service file with `uvx check_zpools` instead of invalid cache path, preventing "code=exited, status=203/EXEC" errors

## [1.1.0] - 2025-11-17
### Changed
- **Config Display Enhancement**: `config` command now shows the source layer and file path for each configuration value, making it easier to understand where settings are coming from (e.g., `[defaults: /path/to/defaultconfig.toml]`, `[user: ~/.config/...]`, `[env]`)
- **Email Configuration**: Added `[email]` section to defaultconfig.toml with all SMTP settings and secure defaults (empty password, localhost defaults)
- **Environment Variable Names**: Corrected all environment variable prefixes to `CHECK_ZPOOLS_*` format throughot documentation
### Fixed
- **Service Installation**: Fixed installation failure when invoked with relative/absolute path (e.g., `./check_zpools install-service`) - now uses `sys.argv[0]` to detect invocation path instead of only searching PATH
- **Email Configuration Documentation**: Added comprehensive security warnings and best practices for SMTP password configuration, emphasizing environment variables over config files

## [1.0.3] - 2025-11-17
### Changed
- **CLI Output Enhancement**: `check` command now displays pool status in a Rich table format with color-coded health, capacity, and error counts, providing better visibility and readability
- **Config Display Enhancement**: `config` command now shows the source layer and file path for each configuration value, making it easier to understand where settings are coming from (e.g., `[defaults: /path/to/defaultconfig.toml]`, `[user: ~/.config/...]`, `[env]`)

## [1.0.2] - 2025-11-17
### Fixed
- **Error Monitoring Logic**: Fixed false positives where pools with 0 errors were triggering warnings - now only warns when errors are actually present (> 0)

## [1.0.1] - 2025-11-17
### Fixed
- **ZFS Parser Compatibility**: Fixed parsing for newer ZFS JSON output format
  - Capacity parsing now handles "%" suffix in capacity values (e.g., "2%" → 2.0)
  - Error count extraction supports both `vdevs` (newer) and `vdev_tree` (older) structures
  - Scrub detection handles both `scan_stats` (newer) and `scan` (older) field names
  - Scrub timestamp parsing supports Unix timestamps and human-readable datetime strings
  - Convert `scrub_errors` string values to integers to prevent type comparison errors
- **CLI Output**: Fixed color rendering in `check` command - now properly displays colored output using Rich Console instead of showing markup tags
### Added
- `python-dateutil>=2.8.2` dependency for robust datetime string parsing
- **Smart Service Installation**: Automatic detection of installation method for systemd service
  - Detects virtual environment installations and configures PATH appropriately
  - Detects UV project installations (`uv run check_zpools`)
  - Detects uvx installations (`uvx check_zpools`)
  - Detects direct pip installations (system/user)
  - Generates systemd service files tailored to the detected installation method

## [1.0.0] - 2025-11-17
### Added - ZFS Pool Monitoring
- **ZFS Data Models** (`models.py`): Comprehensive data structures for pool status and issues
  - `PoolHealth`, `Severity` enumerations
  - `PoolStatus`, `PoolIssue`, `CheckResult` dataclasses
- **ZFS Command Integration** (`zfs_client.py`, `zfs_parser.py`):
  - Execute `zpool list -j` and `zpool status -j` commands
  - Parse JSON output into typed data structures
  - Error handling for command failures and timeouts
- **Pool Monitoring** (`monitor.py`):
  - Configurable capacity thresholds (warning/critical)
  - Error monitoring (read/write/checksum errors)
  - Scrub status and age monitoring
  - Multi-pool health checking with severity aggregation
- **Alert Management** (`alert_state.py`, `alerting.py`):
  - Persistent alert state with JSON storage
  - Alert deduplication and resend throttling
  - Email notifications with rich formatting
  - Recovery notifications when issues resolve
  - Secure state file permissions (0o600)
- **Daemon Mode** (`daemon.py`):
  - Continuous monitoring with configurable intervals
  - Graceful shutdown via SIGTERM/SIGINT
  - Error recovery (continues after failures)
  - State persistence across restarts
- **CLI Commands**:
  - `check`: One-shot pool health check (text/JSON output)
  - `daemon`: Start continuous monitoring service
  - `status`: Display pool status with rich tables
  - `install-service`: Install as systemd service
  - `uninstall-service`: Remove systemd service
  - `service-status`: Show service status
- **Systemd Integration** (`service_install.py`):
  - Automated service file generation
  - Service installation/uninstallation
  - Status checking and management
- **Configuration**:
  - Example configuration file (`docs/examples/config.toml.example`)
  - Layered configuration system (app/host/user/env)
  - Configuration validation with clear error messages
- **Testing** (204 total tests, all passing):
  - 42 tests for alert state management and email alerting
  - 70 tests for ZFS parser, monitor, and models
  - Comprehensive edge case and error scenario coverage
### Security
- State files created with 0o600 permissions (owner-only read/write)
- State directories created with 0o750 permissions
- SMTP passwords via environment variables (not config files)
- No hardcoded credentials
### Dependencies
- CLI framework via `rich-click>=1.9.4`
- CLI Exit Code Handling via `lib_cli_exit_tools>=2.1.0`
- config via `lib_layered_config>=1.1.1`
- logging via `lib_log_rich>=5.2.0`
- Email sending via `btx-lib-mail>=1.0.1`
- Rich output via `rich>=13.0.0`
