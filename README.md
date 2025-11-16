# check_zpools

<!-- Badges -->
[![CI](https://github.com/bitranox/check_zpools/actions/workflows/ci.yml/badge.svg)](https://github.com/bitranox/check_zpools/actions/workflows/ci.yml)
[![CodeQL](https://github.com/bitranox/check_zpools/actions/workflows/codeql.yml/badge.svg)](https://github.com/bitranox/check_zpools/actions/workflows/codeql.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Open in Codespaces](https://img.shields.io/badge/Codespaces-Open-blue?logo=github&logoColor=white&style=flat-square)](https://codespaces.new/bitranox/check_zpools?quickstart=1)
[![PyPI](https://img.shields.io/pypi/v/check_zpools.svg)](https://pypi.org/project/check_zpools/)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/check_zpools.svg)](https://pypi.org/project/check_zpools/)
[![Code Style: Ruff](https://img.shields.io/badge/Code%20Style-Ruff-46A3FF?logo=ruff&labelColor=000)](https://docs.astral.sh/ruff/)
[![codecov](https://codecov.io/gh/bitranox/check_zpools/graph/badge.svg?token=UFBaUDIgRk)](https://codecov.io/gh/bitranox/check_zpools)
[![Maintainability](https://qlty.sh/badges/041ba2c1-37d6-40bb-85a0-ec5a8a0aca0c/maintainability.svg)](https://qlty.sh/gh/bitranox/projects/check_zpools)
[![Known Vulnerabilities](https://snyk.io/test/github/bitranox/check_zpools/badge.svg)](https://snyk.io/test/github/bitranox/check_zpools)

`check_zpools` is a production-ready ZFS pool monitoring tool with intelligent alerting and daemon mode. It provides comprehensive health monitoring with configurable thresholds, email notifications, and alert deduplication.

## Features

- **ZFS Pool Monitoring**: Real-time health, capacity, error, and scrub status tracking
- **Intelligent Alerting**: Email notifications with deduplication and configurable resend intervals
- **Daemon Mode**: Continuous monitoring with graceful shutdown and error recovery
- **Rich CLI**: Beautiful table output and JSON export via rich-click
- **Layered Configuration**: Flexible config system (defaults → app → host → user → .env → env)
- **Structured Logging**: Rich console output with journald, eventlog, and Graylog/GELF support

## Install - recommended via UV
UV - the ultrafast installer - written in Rust (10–20× faster than pip/poetry)

```bash
# recommended Install via uv 
pip install --upgrade uv
# Create and activate a virtual environment (optional but recommended)
uv venv
# macOS/Linux
source .venv/bin/activate
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# install via uv from PyPI
uv pip install check_zpools
```

For alternative install paths (pip, pipx, uv, uvx source builds, etc.), see
[INSTALL.md](INSTALL.md). All supported methods register the `check_zpools` command on your PATH.

### Python 3.13+ Baseline

- The project targets **Python 3.13 and newer only**. 
- Runtime dependencies stay on the current stable releases (`rich-click>=1.9.3`
  and `lib_cli_exit_tools>=2.0.0`) and keeps pytest, ruff, pyright, bandit,
  build, twine, codecov-cli, pip-audit, textual, and import-linter pinned to
  their newest majors.
- CI workflows exercise GitHub's rolling runner images (`ubuntu-latest`,
  `macos-latest`, `windows-latest`) and cover CPython 3.13 alongside the latest
  available 3.x release provided by Actions.


## Usage

The CLI leverages [rich-click](https://github.com/ewels/rich-click) for beautiful help output and Rich-styled tables.

### ZFS Monitoring Commands

```bash
# One-shot pool health check
check_zpools check                # Display issues in text format
check_zpools check --format json  # Export as JSON for scripting

# Display pool status with rich tables
check_zpools status               # Show all pools
check_zpools status rpool         # Show specific pool

# Start continuous monitoring daemon
check_zpools daemon               # Run in foreground (for systemd)

# Systemd service management
sudo check_zpools install-service     # Install as systemd service
sudo check_zpools uninstall-service   # Remove systemd service
check_zpools service-status           # Check service status

# Configuration management
check_zpools config                           # Show current configuration
check_zpools config --format json             # Show as JSON
check_zpools config --section zfs             # Show specific section
check_zpools config-deploy --target user      # Deploy config to user directory

# Package information
check_zpools info                 # Display version and paths
python -m check_zpools --version  # Show version
```

### ZFS Monitoring Configuration

Create a configuration file to customize monitoring thresholds and alert behavior. See [docs/examples/config.toml.example](docs/examples/config.toml.example) for a complete reference.

**Quick Start** - Create `~/.config/check_zpools/config.toml`:

```toml
[zfs.capacity]
warning_percent = 80   # Alert when pool reaches 80% capacity
critical_percent = 90  # Critical alert at 90%

[zfs.errors]
read_errors_warning = 0      # Alert on any read errors
write_errors_warning = 0     # Alert on any write errors
checksum_errors_warning = 0  # Alert on any checksum errors

[zfs.scrub]
max_age_days = 30  # Warn if scrub not run in 30 days

[daemon]
check_interval_seconds = 300  # Check every 5 minutes
alert_resend_hours = 24       # Resend alerts after 24 hours
pools_to_monitor = []         # Empty = monitor all pools

[alerts]
alert_recipients = ["admin@example.com"]
send_recovery_emails = true   # Notify when issues resolve

[email]
smtp_hosts = ["smtp.gmail.com:587"]
from_address = "zfs-monitor@example.com"
smtp_username = "alerts@example.com"
# Set via environment: CHECK_ZPOOLS_EMAIL_SMTP_PASSWORD
use_starttls = true
```

**Exit Codes:**
- `0` - All pools healthy (OK)
- `1` - Warning-level issues detected
- `2` - Critical issues detected

### Email Alert Configuration

The monitoring system sends email alerts via [btx-lib-mail](https://pypi.org/project/btx-lib-mail/) when issues are detected.

#### Email Setup

Configure email settings via environment variables, `.env` file, or configuration files:

**Environment Variables:**
```bash
export CHECK_ZPOOLS_EMAIL_SMTP_HOSTS="smtp.gmail.com:587,smtp.backup.com:587"
export CHECK_ZPOOLS_EMAIL_FROM_ADDRESS="zfs-monitor@example.com"
export CHECK_ZPOOLS_EMAIL_SMTP_USERNAME="your-email@gmail.com"
export CHECK_ZPOOLS_EMAIL_SMTP_PASSWORD="your-app-password"
export CHECK_ZPOOLS_EMAIL_USE_STARTTLS="true"
```

**Configuration File** (`~/.config/check_zpools/config.toml`):
```toml
[email]
smtp_hosts = ["smtp.gmail.com:587", "smtp.backup.com:587"]
from_address = "zfs-monitor@example.com"
smtp_username = "alerts@example.com"
# smtp_password via environment variable: CHECK_ZPOOLS_EMAIL_SMTP_PASSWORD
use_starttls = true
```

**`.env` File:**
```bash
# Email configuration for local testing
CHECK_ZPOOLS_EMAIL_SMTP_HOSTS=smtp.gmail.com:587
CHECK_ZPOOLS_EMAIL_SMTP_PASSWORD=your-app-password
CHECK_ZPOOLS_EMAIL_FROM_ADDRESS=zfs-monitor@example.com
```

#### Gmail Configuration Example

For Gmail, create an [App Password](https://support.google.com/accounts/answer/185833) instead of using your account password:

```bash
CHECK_ZPOOLS_EMAIL_SMTP_HOSTS=smtp.gmail.com:587
CHECK_ZPOOLS_EMAIL_FROM_ADDRESS=your-email@gmail.com
CHECK_ZPOOLS_EMAIL_SMTP_USERNAME=your-email@gmail.com
CHECK_ZPOOLS_EMAIL_SMTP_PASSWORD=your-16-char-app-password
CHECK_ZPOOLS_EMAIL_USE_STARTTLS=true
```

#### Email Troubleshooting

**Connection Failures:**
- Verify SMTP hostname and port are correct
- Check firewall allows outbound connections on SMTP port
- Test connectivity: `telnet smtp.gmail.com 587`

**Authentication Errors:**
- For Gmail: Use App Password, not account password
- Ensure username/password are correct
- Check for 2FA requirements

**Emails Not Arriving:**
- Check recipient's spam folder
- Verify `from_address` is valid and not blacklisted
- Review SMTP server logs for delivery status

### Advanced Configuration

The application uses [lib_layered_config](https://github.com/bitranox/lib_layered_config) for hierarchical configuration with the following precedence (lowest to highest):

**defaults → app → host → user → .env → environment variables**

#### Configuration Locations

Platform-specific paths:
- **Linux (user)**: `~/.config/check_zpools/config.toml`
- **Linux (app)**: `/etc/xdg/check_zpools/config.toml`
- **Linux (host)**: `/etc/check_zpools/hosts/{hostname}.toml`
- **macOS (user)**: `~/Library/Application Support/check_zpools/config.toml`
- **Windows (user)**: `%APPDATA%\check_zpools\config.toml`

#### View Configuration

```bash
# Show merged configuration from all sources
check_zpools config

# Show as JSON for scripting
check_zpools config --format json

# Show specific section only
check_zpools config --section zfs
```

#### Deploy Configuration Files

```bash
# Create user configuration file
check_zpools config-deploy --target user

# Deploy to system-wide location (requires privileges)
sudo check_zpools config-deploy --target app

# Deploy to multiple locations at once
check_zpools config-deploy --target user --target host

# Overwrite existing configuration
check_zpools config-deploy --target user --force
```

#### Environment Variable Overrides

Configuration can be overridden via environment variables:

```bash
# Override ZFS thresholds
CHECK_ZPOOLS_ZFS_CAPACITY_WARNING_PERCENT=85 check_zpools check
CHECK_ZPOOLS_ZFS_CAPACITY_CRITICAL_PERCENT=95 check_zpools check

# Override daemon settings
CHECK_ZPOOLS_DAEMON_CHECK_INTERVAL_SECONDS=600 check_zpools daemon

# Override logging
LOG_CONSOLE_LEVEL=DEBUG check_zpools status
```

#### .env File Support

Create a `.env` file in your project directory for local development:

```bash
# .env
CHECK_ZPOOLS_ZFS_CAPACITY_WARNING_PERCENT=85
CHECK_ZPOOLS_EMAIL_SMTP_PASSWORD=your-app-password
LOG_CONSOLE_LEVEL=INFO
```

The application automatically discovers and loads `.env` files from the current directory or parent directories.

### Library Use

You can import and use check_zpools as a library in your Python code:

```python
from check_zpools.behaviors import check_pools_once, show_pool_status
from check_zpools.config import get_config

# Perform one-shot pool check
result = check_pools_once()
print(f"Overall severity: {result.overall_severity.value}")
print(f"Issues found: {len(result.issues)}")

for issue in result.issues:
    print(f"  {issue.pool_name}: {issue.message}")

# Display pool status programmatically
show_pool_status(output_format="json")

# Access configuration
config = get_config()
print(f"Warning threshold: {config['zfs']['capacity']['warning_percent']}%")
```


## Further Documentation

- [Install Guide](INSTALL.md)
- [Development Handbook](DEVELOPMENT.md)
- [Contributor Guide](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)
- [Module Reference](docs/systemdesign/module_reference.md)
- [License](LICENSE)
