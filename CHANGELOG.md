# Changelog

All notable changes to this project will be documented in this file following
the [Keep a Changelog](https://keepachangelog.com/) format.

## [Unreleased]

## [0.1.0] - 2025-11-16

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

### Changed
- Repurposed template into ZFS monitoring tool
- Updated behaviors.py with ZFS monitoring functions
- Enhanced datetime handling for timezone-aware comparisons
- Improved error handling throughout codebase

### Fixed
- Configuration validation prevents invalid threshold values
- Datetime comparison handles both aware and naive datetimes
- State file permissions restricted to owner-only access
- ZFS command error handling prevents daemon crashes

### Security
- State files created with 0o600 permissions (owner-only read/write)
- State directories created with 0o750 permissions
- SMTP passwords via environment variables (not config files)
- No hardcoded credentials

### Dependencies
- Email sending via `btx-lib-mail>=1.0.1`
- Rich output via `rich>=13.0.0`
- CLI framework via `rich-click>=1.7.0`

## [0.0.1] - 2025-11-11
- Bootstrap 
