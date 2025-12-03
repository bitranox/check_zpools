# Changelog

All notable changes to this project will be documented in this file following
the [Keep a Changelog](https://keepachangelog.com/) format.


## [3.6.0] - 2025-12-03

### Changed
- **Logging Setup**: Simplified `attach_std_logging()` call by using library defaults
  - Removed explicit `logger_level="DEBUG"` and `propagate=False` parameters
  - lib_log_rich now handles log level management internally
  - **Why this matters**: Cleaner code with less configuration, letting the library manage defaults

## [3.5.0] - 2025-11-27

### Added
- **System-Wide Alias Support**: `alias-create` and `alias-delete` commands now support `--all-users` flag
  - Creates/removes alias in `/etc/bash.bashrc` instead of user's `~/.bashrc`
  - Allows all users on the system to use the `check_zpools` command
  - Requires root privileges
  - After creation, users need to run `source /etc/bash.bashrc` or open a new terminal
  - **Why this matters**: Simplifies deployment in multi-user environments where all administrators need access to the tool

### Fixed
- **Daemon Alert Resend (Critical Bug)**: Fixed daemon ignoring configured `alert_resend_interval_hours`
  - **Root cause**: Code in `behaviors.py` used wrong config key `alert_resend_hours` instead of `alert_resend_interval_hours`
  - **Impact**: Daemon always used default 24-hour resend interval instead of configured value (default: 2 hours)
  - **Symptom**: Repeat alerts for persistent issues sent after 24 hours instead of configured interval
  - **Solution**: Corrected config key to match `defaultconfig.toml` definition
  - **Why this matters**: Email notifications for ongoing issues are now sent at the configured interval

### Tests
- Added test to verify correct config key is used for alert resend interval
- Added 12 tests for `--all-users` alias functionality

## [3.3.0] - 2025-11-26

### Added
- **Bash Alias Management** (Linux only): New commands to create shell function aliases for venv/uvx installations
  - `alias-create`: Creates a shell function in `~/.bashrc` that forwards calls to the venv-installed executable
  - `alias-delete`: Removes the shell function alias from `~/.bashrc`
  - Both commands support `--user <username>` to manage aliases for specific users
  - Automatically detects installation method (venv, uvx) and configures the correct command path
  - Uses marked blocks (`# [ALIAS FOR check_zpools]`) for safe identification and removal
  - **Why this matters**: CLI tools installed in virtual environments or via uvx are not available system-wide. These commands enable the `check_zpools` command without activating the venv or using the full uvx path.
  - **Example output in ~/.bashrc**:
    ```bash
    # [ALIAS FOR check_zpools]
    check_zpools() {
        /path/to/venv/bin/check_zpools "$@"
    }
    # [/ALIAS FOR check_zpools]
    ```

### Fixed
- **Device-Specific Alert Tracking**: Fixed bug where multiple faulted devices in the same pool shared alert state
  - Previously, all device issues used `pool:device` as the alert key, causing:
    - Only the first device to get alerted
    - Other devices in the same pool to be suppressed as "duplicates"
    - Resend interval to apply incorrectly across all devices
  - Now uses `pool:device:device_name` as the key for device-specific tracking
  - Each faulted device is tracked independently for suppression and resend intervals
  - Recovery detection clears all device issues for a pool when the "device" category recovers
pre-v
### Tests
- Added 54 tests for alias management functionality (marked `linux_only` to skip on macOS CI)
- Added 12 tests for device-specific alert tracking covering:
  - Multiple devices in same pool tracked separately
  - Device-specific resend intervals
  - Clearing all vs. specific device issues
  - Persistence across save/load cycles

## [3.2.2] - 2025-11-26

### Fixed
- **README Documentation**: Corrected configuration examples to match actual defaults
  - Changed from nested structure (`[zfs.capacity]`, `[zfs.errors]`, `[zfs.scrub]`) to flat `[zfs]` section
  - Fixed config key names: `warning_percent` → `capacity_warning_percent`, `alert_resend_hours` → `alert_resend_interval_hours`
  - Corrected default values: error thresholds from `0` to `1`, alert resend from `24h` to `2h`
  - Fixed environment variable format in examples: `CHECK_ZPOOLS_EMAIL_*` → `CHECK_ZPOOLS___EMAIL__*` (triple underscore after slug)

## [3.2.1] - 2025-11-26

### Fixed
- **Service uptime calculation**: Fixed timezone parsing for systemd timestamps
  - Now correctly handles all timezone abbreviations (CET, EST, UTC, etc.)
  - Previously showed "0s" uptime when timezone wasn't UTC
  - Displays timezone in output (e.g., "CET" instead of always "UTC")

## [3.2.0] - 2025-11-26

### Added
- **Enhanced `service-status` Command**: Now displays comprehensive daemon status
  - Service uptime: Shows when the service was started and how long it's been running
  - Daemon configuration: Check interval and alert resend (email silencing) period
  - Current pool status: Number of pools monitored, faulted device count, and active issues
  - Active alert states: For each tracked issue shows alerts sent count and time until next email
  - **Example output**:
    ```
    check_zpools Service Status
    ========================================================
    ✓ Service file installed: /etc/systemd/system/check_zpools.service
      • Running:  ✓ Yes
      • Enabled:  ✓ Yes (starts on boot)
      • Started:  2025-11-26 08:00:00 UTC (uptime: 3h 15m)

    Daemon Configuration:
    --------------------------------------------------------
      • Check interval:     300s (5m)
      • Alert resend:       2h (email silencing period)

    Current Pool Status:
    --------------------------------------------------------
      • Pools monitored:    4
      • Device status:      ✗ 1 FAULTED
      • Active issues:      1
          → rpool: Device wwn-0x5002538f55117008-part3 is FAULTED

    Active Alert States:
    --------------------------------------------------------
      [CRITICAL] rpool:device
          Alerts sent: 3, Next email in: 1h 45m
    ```

### Tests
- Added 33 new tests for enhanced service status functionality covering:
  - Duration formatting (`_format_duration`)
  - Alert state loading (`_load_alert_state`)
  - Service start time parsing (`_get_service_start_time`)
  - Pool status summary (`_get_pool_status_summary`)
  - Full `show_service_status()` output verification

## [3.1.0] - 2025-11-26

### Added
- **Faulted Device Detection**: Detect and report FAULTED/DEGRADED devices even when pool is ONLINE
  - Added `DeviceStatus` model to track individual device state within pools
  - Added `faulted_devices` field to `PoolStatus` containing problematic devices
  - Parser now recursively traverses vdev tree to find FAULTED, DEGRADED, or error-having devices
  - Monitor creates CRITICAL issues for FAULTED devices, WARNING for others with errors
  - CLI table now shows "Devices" column (OK/N FAULTED) for quick visibility
  - **Why this matters**: A pool can be ONLINE with redundancy (mirror/raidz) while containing FAULTED devices that need replacement. Previously this was invisible - now it's properly alerted.

## [3.0.1] - 2025-11-26

### Changed
- **Email Alert Formatting**: Improved size and percentage display in alert emails
  - Sizes now display in appropriate units (GB, TB, PB) based on actual value instead of always showing TB
  - Percentages formatted with max 2 decimal places (e.g., "92.48 %" instead of "92.5%")
  - Added `_format_bytes_human()` helper function for consistent size formatting across email alerts
  - **Why this matters**: Smaller pools now show readable values like "9.48 GB" instead of "0.01 TB"

## [3.0.0] - 2025-11-25

### Breaking Changes
- **Environment variable format changed**: lib_layered_config now requires TRIPLE underscore (`___`) between slug and section
  - Old format: `CHECK_ZPOOLS_EMAIL__SMTP_PASSWORD=value`
  - New format: `CHECK_ZPOOLS___EMAIL__SMTP_PASSWORD=value`
  - Pattern: `<slug>___<section>__<key>=value`
  - Users must update any environment variables they have configured

## [2.5.0] - 2025-11-25

### Changed
- **Systemd service logging**: Added custom console format template to service file
  - Removes emoji icons (`{level_icon}`) from log output for cleaner journald logs
  - Avoids UTF-8 emoji characters (ℹ, ⚠, ✖) appearing as escape sequences in journal
  - Format: `{timestamp} {LEVEL:>8} {logger_name} - {message} {context_fields}`

### Documentation
- **README**: Enhanced systemd logging documentation
  - Explained dual logging mechanism (console capture + direct journald API)
  - Added `-o verbose` journalctl example with real structured field output
  - Documented structured field queries for capacity thresholds and error counts
- **Environment variables**: Fixed all documentation to use correct lib_layered_config format
  - Format: `<slug>___<section>__<key>=value` (TRIPLE underscore after slug, DOUBLE for section/key)
  - Example: `CHECK_ZPOOLS___EMAIL__SMTP_PASSWORD=value`
  - Updated in `defaultconfig.toml`, `config.toml.example`, `.env.example`, `README.md`, and `service_install.py`

## [2.4.0] - 2025-11-24

### Refactored
- **Test Suite Architecture**: Complete refactoring of test suite following clean architecture principles
  - Created shared fixtures in `conftest.py` to eliminate duplication across test files
    - `healthy_pool_status` - Standard healthy pool fixture
    - `ok_check_result` - Successful check result fixture
    - `configurable_pool_status` - Factory pattern fixture for customizable pools
  - Reorganized major test files with focused test classes:
    - `test_alerting.py`: Split into 11 focused classes (31 tests, 91% coverage)
    - `test_daemon.py`: Reorganized into 15 classes (31 tests, 100% coverage)
    - `test_behaviors.py`: Fixed pyright errors, removed duplicates (40 tests, 96% coverage)
    - `test_cli_commands_integration.py`: Updated to use shared fixtures (24 tests)
  - Applied Given-When-Then docstring pattern to all test methods
  - Test names now read like plain English sentences describing exact behavior
  - Each test validates ONE specific behavior (no multi-assert kitchen sinks)
  - **Why this matters**: Tests are now more maintainable, discoverable, and follow clean architecture principles "to the extreme"
- **Code Complexity Reduction**: Eliminated final moderate-complexity function
  - Refactored `uninstall_service()` from complexity 6 to 2 (67% reduction)
  - Created 6 new helper functions, each with complexity ≤2
  - Applied Extract Method pattern for better testability and maintainability
  - **Why this matters**: Service installation code is now more maintainable with smaller, focused functions
- **Code Duplication Elimination**: Removed duplicate code across multiple files
  - Extracted shared `_run_systemctl_with_logging()` helper to eliminate 2 duplicate error handling blocks in `service_install.py`
  - Created shared `validate_smtp_configuration()` function in `cli_email_handlers.py` to eliminate duplicates in `send_email.py` and `send_notification.py`
  - Removed ~66 lines of duplicated code across 3 files
  - Single source of truth for SMTP validation and systemctl error handling
  - **Why this matters**: Easier to maintain, update, and ensure consistency across email commands

### Fixed
- **Type Annotations**: Added proper TYPE_CHECKING imports for forward references
  - Fixed `psutil.Process` type annotations in `service_install.py`
  - Fixed import path for `EmailConfig` in `cli_email_handlers.py` (changed from `..mail` to `.mail`)
  - Fixed pyright reportUnusedExpression errors in test_behaviors.py (removed comma-separated assert messages)
  - Fixed type annotations for fixture factories in test files
  - **Why this matters**: All type checking and linting passes without errors
- **Command Reference**: Corrected incorrect command reference in SMTP validation error message
  - Changed from `bitranox-template-cli-app-config-log-mail config-deploy` to `check_zpools config-deploy`
  - **Why this matters**: Users see correct command in error messages
- **Test Assertions**: Fixed pool name mismatches in CLI integration tests
  - Updated assertions to use "rpool" (from shared fixtures) instead of "testpool"
  - **Why this matters**: Tests now accurately reflect fixture data

### Documentation
- **README Enhancement**: Expanded "Future Enhancements" section with comprehensive roadmap
  - Organized 35+ potential features into 6 categories:
    - Monitoring Enhancements (8 features): Remote SSH monitoring, dataset-level tracking, resilver/scrub progress, device health, fragmentation, SMART integration, I/O stats, snapshot monitoring
    - Alerting & Notification Enhancements (6 features): Multiple channels (Slack, Discord, Teams, PagerDuty), alert grouping, templates, escalation, quiet hours, acknowledgment
    - Reporting & Visualization (7 features): TUI dashboard, historical trending, summaries, capacity prediction, metrics export, web dashboard, Grafana templates
    - Advanced Daemon Features (5 features): Adaptive intervals, self-healing, maintenance windows, pool-specific configs, monitoring system integration
    - CLI & Usability Enhancements (5 features): Historical query, pool comparison, threshold testing, config validation, dry-run mode
    - Security & Compliance (4 features): Audit logging, read-only mode, encrypted state, role-based access
  - Added Contributing subsection to encourage community participation
  - **Why this matters**: Provides clear project roadmap while demonstrating current feature set is production-ready

### Testing
- All 519 tests passing with 77% coverage (exceeds 60% requirement)
- Coverage improvements:
  - `behaviors.py`: 71% → 96% (+25%)
  - `monitor.py`: 100% coverage
  - `mail.py`: 100% coverage
  - `alert_state.py`: 97% coverage
- Zero regressions introduced
- All refactored code fully tested

## [2.3.0] - 2025-11-23

### Added
- **Alert State Change Detection**: Alerts now send immediately when severity changes, bypassing resend interval
  - Added `last_severity` field to `AlertState` dataclass to track previous severity
  - State transitions (e.g., DEGRADED → ONLINE, WARNING → CRITICAL) trigger immediate alerts
  - `alert_resend_interval_hours` now only applies when severity remains unchanged
  - **Why this matters**: Critical state changes are reported immediately, while spam from unchanged states is prevented
- **Alert Severity Filtering**: Implemented `alert_on_severities` configuration setting
  - Filter which severity levels trigger email alerts (CRITICAL, WARNING, INFO)
  - Default: ["CRITICAL", "WARNING"] - only alert on critical and warning issues
  - Recovery emails controlled independently via `daemon.send_recovery_emails`
  - **Why this matters**: Administrators can tune alert noise by filtering severities while ensuring recovery notifications still work
- **Test Coverage**: Added comprehensive test coverage for new features
  - 5 new tests for state change detection (severity changes, recovery, same severity)
  - 6 new tests for severity filtering (filtering behavior, recovery emails independent)
  - All 450 tests passing

### Fixed
- **Configuration Loading (Critical Bug)**: Fixed all ZFS monitoring thresholds being ignored
  - **Root cause**: Code expected nested keys like `zfs.capacity.warning_percent` but config had flat keys like `zfs.capacity_warning_percent`
  - **Impact**: ALL [zfs] section settings were using hardcoded defaults instead of configured values
  - **Symptom**: Custom capacity thresholds, error thresholds, and scrub age limits were ignored
  - **Solution**: Updated `_build_monitor_config()` in `behaviors.py` to read flat keys matching TOML structure
  - **Why this matters**: Users can now actually configure monitoring thresholds via config files
- **Configuration Structure**: Fixed misplaced daemon settings
  - Moved `send_ok_emails` and `send_recovery_emails` from `[alerts]` to `[daemon]` section
  - Code reads from `[daemon]` section, so settings must be defined there
  - **Why this matters**: Recovery email settings now work correctly when configured
- **Test Suite**: Updated 17 tests to match corrected configuration structure
  - Changed nested configuration keys to flat keys in test fixtures
  - Tests now validate actual configuration behavior

### Changed
- **Security**: Suppressed known vulnerability `PYSEC-2022-42969` in `py` package
  - Added to `_DEFAULT_PIP_AUDIT_IGNORES` in `scripts/test.py`
  - Known issue in transitive dependency, not exploitable in this context
  - **Why this matters**: `make test` now passes without false positive security failures

### Documentation
- **Configuration File**: Enhanced `defaultconfig.toml` documentation
  - Updated `alert_resend_interval_hours` documentation to clarify it only applies when severity is unchanged
  - Documented that state changes trigger immediate alerts regardless of interval
  - Added comprehensive documentation for `alert_on_severities` setting
  - Clarified that recovery emails are independent of severity filtering
  - Moved `send_ok_emails` and `send_recovery_emails` to correct `[daemon]` section
- **README**: Updated daemon configuration examples and notes to reflect severity filtering behavior

### Refactored
- **Code Cleanup**: Removed all backwards compatibility code
  - Removed default value from `AlertState.last_severity` field
  - Removed `.get()` fallback in state loading
  - Removed backwards compatibility test
  - **Why this matters**: Cleaner, more maintainable code without unnecessary bloat

## [2.2.0] - 2025-11-20

### Added
- **Pre-commit Hooks**: Automated code quality checks with Ruff, Pyright, and Bandit
  - Runs formatting, linting, type checking, and security scanning on every commit
  - Ensures consistent code quality before changes reach version control
  - Configuration in `.pre-commit-config.yaml`
  - **Why this matters**: Catches quality issues immediately during development, preventing broken builds
- **Security Policy**: Comprehensive security guidelines and vulnerability reporting process
  - Added `SECURITY.md` with responsible disclosure policy (231 lines)
  - Documents supported versions and security update procedures
  - Provides clear vulnerability reporting channels
  - **Why this matters**: Establishes professional security practices for production deployments
- **Architecture Documentation**: Complete system design documentation
  - Added `CODE_ARCHITECTURE.md` with comprehensive Data Models section (217 lines)
  - Documents all domain models, enumerations, and their relationships
  - Includes module organization and Clean Architecture principles
  - **Why this matters**: Enables new contributors to understand system design quickly

### Changed
- **Documentation Enhancements**: Significantly expanded development and user documentation
  - **DEVELOPMENT.md**: Added comprehensive Testing section (171 new lines)
    - Documents test organization, running tests, coverage requirements
    - Explains test categorization and platform-specific testing
    - Provides debugging and contribution guidelines
  - **README.md**: Documented additional CLI commands (112 new lines)
    - `hello` - Installation verification command
    - `fail` - Error handling test command
    - `send-email` - Advanced email testing with HTML and attachments
  - **codecov.yml**: Clarified coverage target differences
    - Local: 60% for rapid development iteration
    - CI: 70% for production quality before merge
  - **Why this matters**: Improved developer onboarding and user experience

### Fixed
- **Code Complexity Reduction**: Eliminated all C-grade (high complexity) functions
  - Extracted helper functions for better testability and maintainability
  - **Why this matters**: Simpler code is easier to maintain, test, and debug
- **Windows CI Build**: Fixed pytest collection error on Windows
  - Added `norecursedirs` to exclude LLM-CONTEXT from pytest collection
  - **Root cause**: LLM-CONTEXT scripts contain UTF-8 characters that fail with Windows cp1252 encoding
  - **Impact**: Windows builds were failing with UnicodeDecodeError during test collection
  - **Why this matters**: Ensures multi-platform CI compatibility (Linux/macOS/Windows)

### Refactored
- **CLI Module**: Extracted error handler from `cli_send_email` (103 lines → 48 lines, 53% reduction)
  - Created reusable `_handle_send_email_error()` helper
  - Applied DRY principle to eliminate code duplication
  - Improved error handling consistency
- **Behaviors Module**: Extracted daemon helpers from `run_daemon` (108 lines → 25 lines, 77% reduction)
  - Created focused helper functions for daemon initialization and monitoring
  - Improved code readability and testability
  - **Why this matters**: Smaller, focused functions are easier to understand and maintain

### Documentation
- **Signal Handler**: Added comprehensive docstring to daemon signal handler
  - Documents shutdown behavior, signal handling, and graceful termination
  - Explains why handlers are registered and their purpose
  - **Why this matters**: Critical daemon behavior is now fully documented

## [2.1.8] - 2025-11-18

### Fixed
- **Logging (Critical Bug)**: Fixed logger_level to use minimum of all output levels
  - **Root cause**: `attach_std_logging()` was using only `console_level` as `logger_level`
  - **Impact**: When `console_level = "WARNING"` but `backend_level = "INFO"`, INFO logs were filtered by Python's logging module BEFORE reaching lib_log_rich
  - **Result**: Journald never received INFO logs even with `backend_level = "INFO"` set
  - **Solution**: Calculate minimum level across all enabled outputs (console, journald, graylog)
  - **Behavior**:
    - If `console_level = "WARNING"` and `backend_level = "INFO"` → logger_level = "INFO"
    - Console handler still filters at WARNING (minimal output)
    - Journald handler receives INFO logs (full logging)
  - **Why this matters**: `console_level` and `backend_level` are now truly independent as documented
  - **Note**: This was a bug in our integration code, not in lib_log_rich itself

## [2.1.7] - 2025-11-18

### Fixed
- **Configuration (Critical Bug)**: Fixed section names in defaultconfig.toml to match what code expects
  - Changed `[check_zpools]` → `[zfs]`
  - Changed `[check_zpools.daemon]` → `[daemon]`
  - Changed `[check_zpools.alerts]` → `[alerts]`
  - **Root cause**: defaultconfig.toml used wrong section names, causing configuration to be ignored
  - **Impact**: ALL configuration was being ignored - daemon used hardcoded defaults instead of config files
  - **Symptom**: SMTP servers and alert recipients configured in `/etc/check_zpools/config.toml` were not loaded
  - **Why this matters**: This was a critical bug preventing any configuration from working since v2.0.0
  - **Note**: After updating to 2.1.7, you may need to regenerate config files or update section names manually

## [2.1.6] - 2025-11-18

### Fixed
- **Service Installation (Configuration Access)**: Fixed systemd service to allow reading configuration files
  - Added `ReadOnlyPaths=/etc/check_zpools /etc/xdg/check_zpools` to service file
  - **Root cause**: `ProtectSystem=strict` makes `/etc` read-only by default
  - Service can now read configuration from both app layer (`/etc/check_zpools/config.toml`) and host layer (`/etc/xdg/check_zpools/config.toml`)
  - **Why this matters**: Configuration files deployed with `config-deploy --target app` or `--target host` are now accessible to the daemon
  - **Symptom**: Config worked in console mode but not when run as systemd service

## [2.1.5] - 2025-11-18

### Added
- **Daemon Logging (Configuration Sources)**: Added INFO-level logging for configuration paths
  - Logs which configuration sections are loaded (email, alerts, monitoring, daemon)
  - Logs all top-level configuration keys found
  - Logs all valid configuration file paths on startup
  - Helps troubleshoot configuration issues and verify layered config is working
  - **Why this matters**: Administrators can see exactly where to place config files

### Documentation
- **Configuration Paths**: Documented layered configuration file locations on Linux
  - **App layer**: `/etc/check_zpools/config.toml` (system-wide application defaults)
  - **Host layer**: `/etc/xdg/check_zpools/config.toml` (system-wide XDG config)
  - **User layer**: `~/.config/check_zpools/config.toml` (user-specific XDG config)
  - Use `check_zpools config-deploy --target [app|host|user]` to create config files
  - Configuration precedence: defaults → app → host → user → dotenv → env
  - **Why this matters**: Understanding the layer precedence helps with configuration management

## [2.1.4] - 2025-11-18

### Added
- **Daemon Logging (Email Configuration)**: Daemon startup now logs email alerting configuration
  - Logs SMTP servers list (or "none" if not configured)
  - Logs alert recipients list (or "none" if not configured)
  - Logs whether recovery emails are enabled
  - **Why this matters**: Administrators can verify email configuration from logs without checking config files

### Fixed
- **Daemon Logging (Configuration Warnings)**: Added ERROR logs if email alerting is misconfigured
  - Logs ERROR if no SMTP servers are configured
  - Logs ERROR if no alert recipients are configured
  - **Why this matters**: Administrators are immediately warned if alerts won't be sent due to missing configuration

### Note
- **Release**: This version contains all fixes from 2.1.3 that were not included in the initial PyPI release
  - The PyPI version 2.1.3 was built before the ZFS dependency fix was committed
  - Version 2.1.4 ensures all fixes are included in the published package
  - **Why this matters**: Users installing from PyPI will now get all the fixes including the ZFS optional dependency

## [2.1.3] - 2025-11-18

### Fixed
- **Service Installation (Executable Detection)**: Fixed service installation to work with absolute paths
  - Previously failed when running with `sudo` because it only searched PATH
  - Now uses `sys.argv[0]` to detect the actual executable being run
  - Falls back to PATH search if sys.argv[0] not available
  - **Why this matters**: Service installation now works from virtualenvs and custom installation locations
- **Service Installation (ZFS Dependency)**: Made ZFS services optional dependencies
  - Changed `Requires=zfs-mount.service` to `Wants=zfs-mount.service`
  - Service now starts even if ZFS kernel modules aren't loaded (e.g., in LXC containers)
  - Still waits for ZFS services if they're available (`After=zfs-mount.service`)
  - **Why this matters**: Service can be installed and tested in environments without ZFS

### Changed
- **Development**: Verified comprehensive daemon logging functionality
  - Confirmed version number displays correctly in startup logs (`version=2.1.3`)
  - Confirmed all context fields are properly formatted and visible in journalctl
  - Confirmed daemon handles ZFS command failures gracefully (continues running, logs errors)
  - Tested on LXC container environment without ZFS pools to verify error handling
  - Verified systemd service installation and journal logging
  - **Why this matters**: Production deployments are validated to show complete logging information

## [2.1.2] - 2025-11-18

### Fixed
- **Logging (Default Console Level)**: Changed default console log level from WARNING to INFO
  - Default was set to WARNING, which prevented INFO-level logs from being visible
  - INFO-level logs include check cycle statistics, pool details, and version information
  - Now matches the documented behavior and systemd service configuration
  - **Why this matters**: Administrators can now see the comprehensive logging added in v2.1.0 without manually configuring log levels
- **Logging (Default Format Preset)**: Changed default console format from "short_loc" to "full_loc"
  - "short_loc" preset only shows timestamp, level, and message (no context fields)
  - "full_loc" preset includes timestamp, level, logger name, message, and context fields
  - Context fields include version, pool details, statistics, and other structured data
  - **Why this matters**: All the rich logging data (version, pool metrics, statistics) is now visible by default
it looks like the daemon mode does not read the environmen 
### Documentation
- **README (Example Log Output)**: Updated example log output to show version field in daemon startup message
  - Startup log now shows: `[version="2.1.1", interval_seconds=300, pools="all"]`
  - Reflects the actual daemon behavior introduced in v2.1.1
  - **Why this matters**: Documentation accurately reflects what administrators will see in their logs

## [2.1.1] - 2025-11-18

### Added
- **Daemon Logging (Version on Startup)**: Daemon now logs its version number on startup
  - Version is included in the startup INFO log message
  - Helps administrators identify which version is running in logs
  - Useful for troubleshooting and verifying deployments
  - **Why this matters**: Makes it easy to confirm daemon version from logs without checking package metadata

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
