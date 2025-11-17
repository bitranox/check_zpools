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

## CLI Command Reference

### Global Options

All commands support these global options:

| Option | Description |
|--------|-------------|
| `--version` | Show version and exit |
| `-h, --help` | Show help message and exit |
| `--traceback` / `--no-traceback` | Show full Python traceback on errors (default: disabled) |

**Example:**
```bash
check_zpools --version
check_zpools --help
check_zpools check --traceback  # Show detailed errors
```

---

### ZFS Monitoring Commands

#### `check` - One-Shot Pool Health Check

Performs a single check of all ZFS pools against configured thresholds and reports any issues found.

**Usage:**
```bash
check_zpools check [OPTIONS]
```

**Options:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--format` | `text` \| `json` | `text` | Output format for results |

**Exit Codes:**
- `0` - All pools healthy (OK)
- `1` - Warning-level issues detected
- `2` - Critical issues detected

**Examples:**
```bash
# Check all pools with text output (default)
check_zpools check

# Check all pools with JSON output for scripting
check_zpools check --format json

# Check in a script and handle exit codes
if check_zpools check --format json > /tmp/zfs_status.json; then
  echo "All pools healthy"
else
  echo "Issues detected - check /tmp/zfs_status.json"
fi
```

**JSON Output Format:**
```json
{
  "timestamp": "2025-11-16T15:30:00.000000",
  "pools": [
    {
      "name": "rpool",
      "health": "ONLINE",
      "capacity_percent": 45.2
    }
  ],
  "issues": [
    {
      "pool_name": "tank",
      "severity": "WARNING",
      "category": "capacity",
      "message": "Pool capacity at 85%",
      "details": {
        "warning_threshold": 80,
        "current_percent": 85
      }
    }
  ],
  "overall_severity": "WARNING"
}
```

---

#### `status` - Display Pool Status

Shows detailed status information for all pools or a specific pool with rich formatting.

**Usage:**
```bash
check_zpools status [OPTIONS] [POOL_NAME]
```

**Options:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--format` | `table` \| `text` \| `json` | `table` | Output format |
| `--pool` | TEXT | None | Show specific pool only |

**Examples:**
```bash
# Show all pools as rich table (default)
check_zpools status

# Show specific pool as table
check_zpools status --pool rpool

# Show all pools as JSON
check_zpools status --format json

# Show specific pool as text
check_zpools status --pool tank --format text
```

**Table Output Example:**
```
┏━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━┓
┃ Pool   ┃ Health  ┃ Capacity ┃ Errors     ┃ Last Scrub   ┃
┡━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━┩
│ rpool  │ ONLINE  │ 45.2%    │ 0/0/0      │ 2 days ago   │
│ tank   │ ONLINE  │ 78.5%    │ 0/0/0      │ 1 week ago   │
└────────┴─────────┴──────────┴────────────┴──────────────┘
```

---

#### `daemon` - Continuous Monitoring

Starts the monitoring daemon which periodically checks pools and sends email alerts.

**Usage:**
```bash
check_zpools daemon [OPTIONS]
```

**Options:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--foreground` | FLAG | `False` | Run in foreground (don't daemonize) |

**Examples:**
```bash
# Start daemon in foreground (for systemd or testing)
check_zpools daemon --foreground

# Start daemon in background (manual mode)
check_zpools daemon

# Run with custom check interval (via environment variable)
CHECK_ZPOOLS_DAEMON_CHECK_INTERVAL_SECONDS=600 check_zpools daemon --foreground
```

**Behavior:**
- Monitors pools at configured intervals (default: 300 seconds / 5 minutes)
- Sends email alerts when issues are detected
- Suppresses duplicate alerts (default: 24 hour interval)
- Sends recovery notifications when issues resolve
- Handles SIGTERM/SIGINT for graceful shutdown
- Logs to journald when run as systemd service

**Systemd Usage:**
```bash
# Use install-service command instead (see below)
sudo check_zpools install-service
sudo systemctl start check_zpools
```

---

### Systemd Service Management

#### `install-service` - Install Systemd Service

Installs check_zpools as a systemd service for automatic monitoring.

**Usage:**
```bash
sudo check_zpools install-service [OPTIONS]
```

**Options:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--no-enable` | FLAG | `False` | Don't enable service to start on boot |
| `--no-start` | FLAG | `False` | Don't start service immediately |

**Examples:**
```bash
# Install, enable, and start service (recommended)
sudo check_zpools install-service

# Install but don't start immediately
sudo check_zpools install-service --no-start

# Install but don't enable for automatic boot
sudo check_zpools install-service --no-enable

# Install without starting or enabling
sudo check_zpools install-service --no-enable --no-start
```

**What it does:**
1. Creates `/etc/systemd/system/check_zpools.service`
2. Enables service to start on boot (unless `--no-enable`)
3. Starts service immediately (unless `--no-start`)
4. Configures automatic restart on failure
5. Sets up journald logging

**Service Configuration:**
The installed service runs as root with the following properties:
- **Type:** Simple
- **Restart:** On failure
- **RestartSec:** 10 seconds
- **After:** network.target, zfs-mount.service

---

#### `uninstall-service` - Remove Systemd Service

Removes the systemd service and optionally stops/disables it.

**Usage:**
```bash
sudo check_zpools uninstall-service [OPTIONS]
```

**Options:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--no-stop` | FLAG | `False` | Don't stop running service |
| `--no-disable` | FLAG | `False` | Don't disable service |

**Examples:**
```bash
# Uninstall completely (stop, disable, remove)
sudo check_zpools uninstall-service

# Uninstall but leave service running
sudo check_zpools uninstall-service --no-stop

# Uninstall but keep enabled
sudo check_zpools uninstall-service --no-disable
```

**Note:** This does not remove cache and state directories:
```bash
# To remove state and cache manually:
sudo rm -rf /var/cache/check_zpools /var/lib/check_zpools
```

---

#### `service-status` - Check Service Status

Displays the current status of the check_zpools systemd service.

**Usage:**
```bash
check_zpools service-status
```

**No options.**

**Example Output:**
```
Service Status:
  Installed: Yes (/etc/systemd/system/check_zpools.service)
  Running:   Yes (active since 2025-11-16 10:30:00)
  Enabled:   Yes (starts on boot)

Systemctl Output:
● check_zpools.service - ZFS Pool Monitoring Daemon
     Loaded: loaded (/etc/systemd/system/check_zpools.service; enabled)
     Active: active (running) since Sat 2025-11-16 10:30:00 CET; 5h ago
   Main PID: 12345 (python3)
      Tasks: 1 (limit: 4915)
     Memory: 28.5M
        CPU: 1.234s
     CGroup: /system.slice/check_zpools.service
             └─12345 /usr/bin/python3 /usr/local/bin/check_zpools daemon --foreground
```

---

### Configuration Management

#### `config` - Display Current Configuration

Shows the merged configuration from all sources (defaults, config files, environment variables).

**Usage:**
```bash
check_zpools config [OPTIONS]
```

**Options:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--format` | `human` \| `json` | `human` | Output format |
| `--section` | TEXT | None | Show only specific section (e.g., `zfs`, `email`, `daemon`) |

**Examples:**
```bash
# Show full configuration (human-readable)
check_zpools config

# Show configuration as JSON
check_zpools config --format json

# Show only ZFS section
check_zpools config --section zfs

# Show only email configuration
check_zpools config --section email

# Export configuration for backup
check_zpools config --format json > backup-config.json
```

**Configuration Precedence:**
```
defaults → app → host → user → .env → environment variables
(lowest)                                      (highest)
```

**Configuration Sources:**
1. **Built-in defaults** (embedded in package)
2. **App config:** `/etc/xdg/check_zpools/config.toml` (Linux)
3. **Host config:** `/etc/check_zpools/hosts/$(hostname).toml` (Linux)
4. **User config:** `~/.config/check_zpools/config.toml` (Linux)
5. **.env files** (project directory or parents)
6. **Environment variables** (`CHECK_ZPOOLS_*`)

---

#### `config-deploy` - Deploy Configuration Files

Creates configuration files in specified locations with default templates.

**Usage:**
```bash
check_zpools config-deploy --target TARGET [OPTIONS]
```

**Options:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--target` | `app` \| `host` \| `user` | *Required* | Target configuration layer (can specify multiple) |
| `--force` | FLAG | `False` | Overwrite existing configuration files |

**Examples:**
```bash
# Deploy to user config directory (recommended for first setup)
check_zpools config-deploy --target user

# Deploy to system-wide app config (requires privileges)
sudo check_zpools config-deploy --target app

# Deploy to host-specific config (requires privileges)
sudo check_zpools config-deploy --target host

# Deploy to multiple locations at once
check_zpools config-deploy --target user --target host

# Overwrite existing configuration
check_zpools config-deploy --target user --force

# Deploy app and user configs (app needs sudo)
sudo check_zpools config-deploy --target app --target user
```

**Deployment Paths:**

| Target | Linux Path | macOS Path | Windows Path |
|--------|------------|------------|--------------|
| `app` | `/etc/xdg/check_zpools/config.toml` | `/Library/Application Support/check_zpools/config.toml` | `C:\ProgramData\check_zpools\config.toml` |
| `host` | `/etc/check_zpools/hosts/$(hostname).toml` | `/Library/Application Support/check_zpools/hosts/$(hostname).toml` | `C:\ProgramData\check_zpools\hosts\$(hostname).toml` |
| `user` | `~/.config/check_zpools/config.toml` | `~/Library/Application Support/check_zpools/config.toml` | `%APPDATA%\check_zpools\config.toml` |

---

### Package Information

#### `info` - Display Package Information

Shows package version, installation paths, and metadata.

**Usage:**
```bash
check_zpools info
```

**No options.**

**Example Output:**
```
check_zpools v0.1.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Package Information:
  Name:        check_zpools
  Version:     0.1.0
  Command:     check_zpools
  Description: Zpool Monitoring Daemon

Paths:
  Package:     /usr/local/lib/python3.13/site-packages/check_zpools
  Config:      /etc/xdg/check_zpools/config.toml
  Cache:       ~/.cache/check_zpools

Project URLs:
  Homepage:    https://github.com/bitranox/check_zpools
  Repository:  https://github.com/bitranox/check_zpools.git
  Issues:      https://github.com/bitranox/check_zpools/issues

Authors:
  bitranox <bitranox@gmail.com>
```

---

## Configuration

### Quick Start Configuration

Create `~/.config/check_zpools/config.toml` with the following content:

```toml
# ZFS Monitoring Thresholds
[zfs.capacity]
warning_percent = 80   # Alert when pool reaches 80% capacity
critical_percent = 90  # Critical alert at 90%

[zfs.errors]
read_errors_warning = 0      # Alert on any read errors
write_errors_warning = 0     # Alert on any write errors
checksum_errors_warning = 0  # Alert on any checksum errors

[zfs.scrub]
max_age_days = 30  # Warn if scrub not run in 30 days

# Daemon Settings
[daemon]
check_interval_seconds = 300  # Check every 5 minutes
alert_resend_hours = 24       # Resend alerts after 24 hours
pools_to_monitor = []         # Empty = monitor all pools
send_ok_emails = false        # Don't send emails for OK status
send_recovery_emails = true   # Notify when issues resolve

# Email Alert Recipients
[alerts]
alert_recipients = ["admin@example.com", "ops@example.com"]

# Email SMTP Configuration
[email]
smtp_hosts = ["smtp.gmail.com:587"]
from_address = "zfs-monitor@example.com"
smtp_username = "alerts@example.com"
# IMPORTANT: Set password via environment variable:
# CHECK_ZPOOLS_EMAIL_SMTP_PASSWORD=your-app-password
use_starttls = true
timeout = 30.0
```

### Configuration Sections

#### `[zfs.capacity]` - Capacity Monitoring

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `warning_percent` | int | 80 | Capacity percentage that triggers WARNING alert |
| `critical_percent` | int | 90 | Capacity percentage that triggers CRITICAL alert |

**Constraints:**
- `0 < warning_percent < critical_percent <= 100`
- Defaults are appropriate for most systems

---

#### `[zfs.errors]` - Error Monitoring

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `read_errors_warning` | int | 0 | Threshold for read error alerts (0 = any error triggers alert) |
| `write_errors_warning` | int | 0 | Threshold for write error alerts |
| `checksum_errors_warning` | int | 0 | Threshold for checksum error alerts |

**Note:** Default of `0` means ANY error triggers an alert. Set higher thresholds only if you understand the implications.

---

#### `[zfs.scrub]` - Scrub Monitoring

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `max_age_days` | int | 30 | Maximum days since last scrub before alerting (0 = disabled) |

**Recommendation:** Monthly scrubs (30 days) are appropriate for most systems. High-value data may require weekly scrubs (7 days).

---

#### `[daemon]` - Daemon Behavior

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `check_interval_seconds` | int | 300 | Seconds between pool checks (300 = 5 minutes) |
| `alert_resend_hours` | int | 24 | Hours before resending duplicate alerts |
| `pools_to_monitor` | list | `[]` | Specific pools to monitor (empty = all pools) |
| `send_ok_emails` | bool | `false` | Send email when pools are OK |
| `send_recovery_emails` | bool | `true` | Send email when issues resolve |

**Notes:**
- `check_interval_seconds`: Lower values increase system load
- `alert_resend_hours`: Prevents alert fatigue from persistent issues
- `pools_to_monitor`: Example: `["rpool", "tank"]`

---

#### `[alerts]` - Alert Recipients

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `alert_recipients` | list | `[]` | Email addresses to receive alerts |

**Example:**
```toml
[alerts]
alert_recipients = [
  "admin@example.com",
  "ops-team@example.com",
  "monitoring@pagerduty.example.com"
]
```

---

#### `[email]` - SMTP Configuration

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `smtp_hosts` | list | `[]` | SMTP servers in `host:port` format (tried in order) |
| `from_address` | str | `"noreply@localhost"` | Sender email address |
| `smtp_username` | str | `None` | SMTP authentication username |
| `smtp_password` | str | `None` | SMTP authentication password (use env var!) |
| `use_starttls` | bool | `true` | Enable STARTTLS encryption |
| `timeout` | float | `30.0` | SMTP connection timeout in seconds |

**Security Best Practices:**
```bash
# NEVER put passwords in config files!
# Use environment variables instead:
export CHECK_ZPOOLS_EMAIL_SMTP_PASSWORD="your-app-password"

# Or use .env file:
echo "CHECK_ZPOOLS_EMAIL_SMTP_PASSWORD=your-app-password" > .env
```

---

### Environment Variable Overrides

All configuration can be overridden via environment variables using the prefix `CHECK_ZPOOLS_`:

**Format:**
```
CHECK_ZPOOLS_<SECTION>_<SUBSECTION>_<KEY>=value
```

**Examples:**
```bash
# Override ZFS capacity thresholds
export CHECK_ZPOOLS_ZFS_CAPACITY_WARNING_PERCENT=85
export CHECK_ZPOOLS_ZFS_CAPACITY_CRITICAL_PERCENT=95

# Override daemon check interval
export CHECK_ZPOOLS_DAEMON_CHECK_INTERVAL_SECONDS=600

# Override email SMTP settings
export CHECK_ZPOOLS_EMAIL_SMTP_HOSTS="smtp.gmail.com:587"
export CHECK_ZPOOLS_EMAIL_FROM_ADDRESS="alerts@example.com"
export CHECK_ZPOOLS_EMAIL_SMTP_PASSWORD="app-password"

# Override logging
export LOG_CONSOLE_LEVEL=DEBUG
export LOG_FILE=/var/log/check_zpools.log

# Run with overrides
CHECK_ZPOOLS_ZFS_CAPACITY_WARNING_PERCENT=85 check_zpools check
```

---

### Email Configuration Examples

#### Gmail with App Password

```toml
[email]
smtp_hosts = ["smtp.gmail.com:587"]
from_address = "your-email@gmail.com"
smtp_username = "your-email@gmail.com"
use_starttls = true
```

```bash
# Set password via environment variable
export CHECK_ZPOOLS_EMAIL_SMTP_PASSWORD="xxxx-xxxx-xxxx-xxxx"
```

**Setup Gmail App Password:**
1. Go to https://myaccount.google.com/security
2. Enable 2-Step Verification
3. Go to App Passwords: https://myaccount.google.com/apppasswords
4. Generate new app password
5. Use the 16-character password

---

#### Office 365 / Outlook

```toml
[email]
smtp_hosts = ["smtp.office365.com:587"]
from_address = "alerts@yourdomain.com"
smtp_username = "alerts@yourdomain.com"
use_starttls = true
```

---

#### Multiple SMTP Servers (Failover)

```toml
[email]
smtp_hosts = [
  "smtp.primary.com:587",
  "smtp.backup.com:587",
  "smtp.fallback.com:25"
]
from_address = "monitoring@example.com"
smtp_username = "monitoring@example.com"
use_starttls = true
```

The system will try each server in order until one succeeds.

---

## Library Usage

You can use check_zpools as a Python library:

```python
from check_zpools.behaviors import check_pools_once, show_pool_status
from check_zpools.config import get_config
from check_zpools.models import Severity

# Perform one-shot pool check
result = check_pools_once()

print(f"Overall severity: {result.overall_severity.value}")
print(f"Pools checked: {len(result.pools)}")
print(f"Issues found: {len(result.issues)}")

# Display issues
for issue in result.issues:
    print(f"  [{issue.severity.value}] {issue.pool_name}: {issue.message}")

# Check severity and exit accordingly
if result.overall_severity == Severity.CRITICAL:
    print("CRITICAL issues detected!")
    exit(2)
elif result.overall_severity == Severity.WARNING:
    print("WARNING issues detected")
    exit(1)
else:
    print("All pools healthy")
    exit(0)

# Display pool status programmatically
show_pool_status(output_format="table")

# Access configuration
config = get_config()
capacity_config = config['zfs']['capacity']
print(f"Warning threshold: {capacity_config['warning_percent']}%")
print(f"Critical threshold: {capacity_config['critical_percent']}%")
```

**Advanced Example - Custom Monitoring Script:**
```python
#!/usr/bin/env python3
"""Custom ZFS monitoring with Slack notifications."""

import requests
from check_zpools.behaviors import check_pools_once
from check_zpools.models import Severity

def send_slack_alert(message: str, severity: Severity):
    """Send alert to Slack webhook."""
    webhook_url = "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"

    color = {
        Severity.CRITICAL: "danger",
        Severity.WARNING: "warning",
        Severity.INFO: "good",
        Severity.OK: "good"
    }[severity]

    payload = {
        "attachments": [{
            "color": color,
            "text": message,
            "footer": "ZFS Pool Monitor"
        }]
    }

    requests.post(webhook_url, json=payload)

# Check pools
result = check_pools_once()

# Send alerts if issues found
if result.issues:
    message = f"ZFS Issues Detected ({result.overall_severity.value}):\n"
    for issue in result.issues:
        message += f"• {issue.pool_name}: {issue.message}\n"

    send_slack_alert(message, result.overall_severity)
```

---

## Troubleshooting

### Common Issues

#### "ZFS command not available"
```bash
# Verify ZFS is installed
which zpool
zpool list

# If not installed (Ubuntu/Debian):
sudo apt install zfsutils-linux

# If installed but not in PATH:
export PATH="$PATH:/usr/sbin:/sbin"
check_zpools check
```

#### "Permission denied" errors
```bash
# ZFS commands require root privileges
sudo check_zpools check

# Or run daemon as root
sudo check_zpools daemon --foreground

# For systemd service (recommended):
sudo check_zpools install-service
```

#### Email delivery failures
```bash
# Test SMTP connectivity
telnet smtp.gmail.com 587

# Verify configuration
check_zpools config --section email

# Check logs for detailed error
LOG_CONSOLE_LEVEL=DEBUG check_zpools daemon --foreground

# Test email directly
check_zpools send-notification \
  --to test@example.com \
  --subject "Test" \
  --message "Testing email configuration"
```

#### Systemd service not starting
```bash
# Check service status
check_zpools service-status

# View detailed logs
sudo journalctl -u check_zpools -f

# Check for configuration errors
check_zpools config

# Verify ZFS access as root
sudo zpool list
```

#### Daemon not sending alerts
```bash
# Check alert recipients are configured
check_zpools config --section alerts

# Check email configuration
check_zpools config --section email

# Verify SMTP password is set
echo $CHECK_ZPOOLS_EMAIL_SMTP_PASSWORD

# Check alert state (may be suppressed)
cat ~/.cache/check_zpools/alert_state.json

# Force new alerts by clearing state
rm ~/.cache/check_zpools/alert_state.json
```

---

## Further Documentation

- [Install Guide](INSTALL.md) - Detailed installation instructions
- [Development Handbook](DEVELOPMENT.md) - Contributing and development setup
- [Contributor Guide](CONTRIBUTING.md) - How to contribute
- [Changelog](CHANGELOG.md) - Version history
- [Module Reference](docs/systemdesign/module_reference.md) - API documentation
- [License](LICENSE) - MIT License

---

## Support

- **Issues:** https://github.com/bitranox/check_zpools/issues
- **Discussions:** https://github.com/bitranox/check_zpools/discussions
- **Documentation:** https://github.com/bitranox/check_zpools/tree/main/docs
