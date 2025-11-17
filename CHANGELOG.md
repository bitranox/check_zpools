# Changelog

All notable changes to this project will be documented in this file following
the [Keep a Changelog](https://keepachangelog.com/) format.

## [1.0.1] - 2025-11-17

### Fixed
- **ZFS Parser Compatibility**: Fixed parsing for newer ZFS JSON output format
  - Capacity parsing now handles "%" suffix in capacity values (e.g., "2%" → 2.0)
  - Error count extraction supports both `vdevs` (newer) and `vdev_tree` (older) structures
  - Scrub detection handles both `scan_stats` (newer) and `scan` (older) field names
  - Scrub timestamp parsing supports Unix timestamps and human-readable datetime strings
  - Convert `scrub_errors` string values to integers to prevent type comparison errors

### Added
- `python-dateutil>=2.8.2` dependency for robust datetime string parsing

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
