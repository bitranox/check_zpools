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
[![security: bandit](https://img.shields.io/badge/security-bandit-yellow.svg)](https://github.com/PyCQA/bandit)

`check_zpools` is a production-ready ZFS pool monitoring tool with intelligent alerting and daemon mode. It provides comprehensive health monitoring with configurable thresholds, email notifications, and alert deduplication.

## Features

- **ZFS Pool Monitoring**: Real-time health, capacity, error, and scrub status tracking
- **Intelligent Alerting**: Email notifications with deduplication and configurable resend intervals
- **Daemon Mode**: Continuous monitoring with graceful shutdown and error recovery
- **Rich CLI**: Beautiful table output and JSON export via rich-click
- **Layered Configuration**: Flexible config system (defaults → app → host → user → .env → env)
- **Structured Logging**: Rich console output with journald, eventlog, and Graylog/GELF support

## Platform Support

**Current Status:**
- **Linux/FreeBSD/macOS:** Full support with local ZFS pools
- **Windows:** Limited support - ZFS pools are not natively available on Windows
  - CLI commands work but require ZFS to be present (e.g., via WSL)
  - **Future:** Remote ZFS monitoring via SSH is planned, which will enable Windows users to monitor remote ZFS servers

**Note:** The tool is primarily designed for systems running ZFS. Windows support is currently a preparation for future remote monitoring capabilities.

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
- **Comprehensive logging:** Each check cycle logs:
  - Check cycle number and daemon uptime (e.g., "Check #42, uptime: 2d 5h 30m")
  - Overall statistics (pools checked, issues found, severity)
  - Detailed metrics for each pool (health, capacity, size, errors, scrub status)

**Systemd Usage:**
```bash
# Use service-install command instead (see below)
sudo check_zpools service-install
sudo systemctl start check_zpools
```

---

### Systemd Service Management

> **Note:** Systemd service installation is only available on Linux systems with systemd. Not supported on Windows or macOS.

#### `service-install` - Install Systemd Service

Installs check_zpools as a systemd service for automatic monitoring.

**Usage:**
```bash
sudo check_zpools service-install [OPTIONS]
```

**Options:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--no-enable` | FLAG | `False` | Don't enable service to start on boot |
| `--no-start` | FLAG | `False` | Don't start service immediately |
| `--uvx-version` | TEXT | `None` | Version specifier for uvx installations (e.g., `@latest`, `@1.0.0`) |

**Examples:**
```bash
# Install, enable, and start service (recommended)
sudo check_zpools service-install

# Install but don't start immediately
sudo check_zpools service-install --no-start

# Install but don't enable for automatic boot
sudo check_zpools service-install --no-enable

# Install without starting or enabling
sudo check_zpools service-install --no-enable --no-start

# Install with uvx using @latest (auto-updates to latest version)
sudo uvx check_zpools@latest service-install --uvx-version @latest

# Install with uvx pinned to specific version
sudo uvx check_zpools@1.0.0 service-install --uvx-version @1.0.0
```

**What it does:**
1. Creates `/etc/systemd/system/check_zpools.service`
2. Detects installation method (pip, venv, uv, uvx) and configures ExecStart accordingly
3. Enables service to start on boot (unless `--no-enable`)
4. Starts service immediately (unless `--no-start`)
5. Configures automatic restart on failure
6. Sets up journald logging

**Installation Method Detection:**
The service installer automatically detects how check_zpools was installed:
- **pip/pipx:** Uses absolute path to executable
- **Virtual environment:** Uses venv path with proper PATH configuration
- **uv project:** Uses `uv run check_zpools`
- **uvx:** Uses `uvx check_zpools` (works with temporary cache installations)

**Service Configuration:**
The installed service runs as root with the following properties:
- **Type:** Simple
- **Restart:** On failure
- **RestartSec:** 10 seconds
- **After:** network.target, zfs-mount.service

---

#### `service-uninstall` - Remove Systemd Service

Removes the systemd service and optionally stops/disables it.

**Usage:**
```bash
sudo check_zpools service-uninstall [OPTIONS]
```

**Options:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--no-stop` | FLAG | `False` | Don't stop running service |
| `--no-disable` | FLAG | `False` | Don't disable service |

**Examples:**
```bash
# Uninstall completely (stop, disable, remove)
sudo check_zpools service-uninstall

# Uninstall but leave service running
sudo check_zpools service-uninstall --no-stop

# Uninstall but keep enabled
sudo check_zpools service-uninstall --no-disable
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

### Testing & Utilities

#### `hello` - Verify Installation

Prints "Hello World" to verify the package is properly installed and executable.

**Usage:**
```bash
check_zpools hello
```

**Output:**
```
Hello World
```

**Use Cases:**
- Verify package installation succeeded
- Test CLI entry point is working
- Quick smoke test after deployment
- Validate PATH configuration for installed command

---

#### `fail` - Test Error Handling

Intentionally raises a RuntimeError to test error handling and logging.

**Usage:**
```bash
check_zpools fail
```

**Behavior:**
- Logs intentional failure at WARNING level
- Raises RuntimeError with "Intentional failure for testing"
- Exits with non-zero status code
- Demonstrates error logging and traceback handling

**Use Cases:**
- Test error logging configuration
- Verify exception handling is working
- Test monitoring/alerting for failed commands
- Validate log aggregation captures errors

**Note:** This is a development/testing command. Use `--traceback` flag to see full stack trace.

---

#### `send-email` - Advanced Email Testing

Sends a custom email using configured SMTP settings with full control over message content and attachments.

**Usage:**
```bash
check_zpools send-email --to EMAIL --subject SUBJECT [OPTIONS]
```

**Options:**

| Option | Type | Required | Description |
|--------|------|----------|-------------|
| `--to` | TEXT | Yes | Recipient email address (can specify multiple times) |
| `--subject` | TEXT | Yes | Email subject line |
| `--body` | TEXT | No | Plain-text email body |
| `--body-html` | TEXT | No | HTML email body (sent as multipart with plain text) |
| `--from` | TEXT | No | Override sender address (uses config default if not specified) |
| `--attachment` | PATH | No | File to attach (can specify multiple times) |

**Examples:**
```bash
# Send simple text email
check_zpools send-email \
  --to recipient@example.com \
  --subject "Test Email" \
  --body "Hello from check_zpools CLI"

# Send HTML email with plain text fallback
check_zpools send-email \
  --to admin@example.com \
  --subject "HTML Test" \
  --body "Plain text version" \
  --body-html "<h1>HTML Version</h1><p>Rich formatting</p>"

# Send email with attachments
check_zpools send-email \
  --to ops@example.com \
  --subject "System Report" \
  --body "Please review attached logs" \
  --attachment /var/log/zpool.log \
  --attachment /tmp/report.pdf

# Send to multiple recipients with custom sender
check_zpools send-email \
  --to user1@example.com \
  --to user2@example.com \
  --from "zfs-monitor@example.com" \
  --subject "Alert" \
  --body "Multi-recipient test"
```

**Use Cases:**
- Test SMTP configuration with custom message content
- Verify HTML email rendering in mail clients
- Test attachment handling and size limits
- Validate multi-recipient delivery
- Test custom sender address override

**Comparison with `send-notification`:**
- `send-notification`: Simplified interface, notification-style messages
- `send-email`: Full-featured, supports HTML, attachments, custom sender

---

#### `send-notification` - Test Email Configuration

Sends a test notification email to verify SMTP settings are working correctly.

**Usage:**
```bash
check_zpools send-notification --to EMAIL --subject SUBJECT --message MESSAGE
```

**Options:**

| Option | Type | Required | Description |
|--------|------|----------|-------------|
| `--to` | TEXT | Yes | Recipient email address (can specify multiple times) |
| `--subject` | TEXT | Yes | Notification subject line |
| `--message` | TEXT | Yes | Notification message (plain text) |

**Examples:**
```bash
# Send simple test notification
check_zpools send-notification \
  --to admin@example.com \
  --subject "Test Alert" \
  --message "Testing check_zpools email configuration"

# Send to multiple recipients
check_zpools send-notification \
  --to ops@example.com \
  --to dev@example.com \
  --subject "Service Status" \
  --message "All services operational"

# Use environment variable for SMTP password
CHECK_ZPOOLS_EMAIL_SMTP_PASSWORD="app-password" \
check_zpools send-notification \
  --to test@example.com \
  --subject "Test" \
  --message "Testing SMTP authentication"
```

**Use Cases:**
- Verify SMTP configuration before deploying daemon
- Test email delivery to alert recipients
- Troubleshoot email authentication issues
- Confirm firewall allows SMTP connections

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
from check_zpools.behaviors import check_pools_once
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
sudo check_zpools service-install
```

#### Email delivery failures
```bash
# Test SMTP connectivity
telnet smtp.gmail.com 587

# Verify configuration
check_zpools config --section email

# Check logs for detailed error
LOG_CONSOLE_LEVEL=DEBUG check_zpools daemon --foreground

# Test email configuration (see send-notification command above)
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

## Daemon Logging

The daemon mode provides comprehensive logging to help monitor system health and troubleshoot issues. All logs are structured with additional metadata for easy filtering and analysis.

### Log Levels

Set the log level using the `LOG_CONSOLE_LEVEL` environment variable:

```bash
# Available levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_CONSOLE_LEVEL=INFO check_zpools daemon --foreground
LOG_CONSOLE_LEVEL=DEBUG check_zpools daemon --foreground  # Detailed debugging
```

### Check Cycle Statistics

On each check cycle, the daemon logs overall statistics at INFO level:

```
INFO: Check cycle completed [check_number=42, uptime="2d 5h 30m", pools_checked=3, issues_found=0, severity="OK"]
```

**Logged fields:**
- `check_number` - Sequential check counter since daemon start
- `uptime` - Human-readable daemon uptime (days, hours, minutes)
- `pools_checked` - Number of pools monitored this cycle
- `issues_found` - Total issues detected
- `severity` - Overall severity level (OK, INFO, WARNING, CRITICAL)

### Per-Pool Details

For each pool, the daemon logs detailed metrics at INFO level:

```
INFO: Pool: rpool [health="ONLINE", capacity_percent="45.2%", size="1.00 TB", allocated="452.00 GB", free="548.00 GB", read_errors=0, write_errors=0, checksum_errors=0, last_scrub="2025-11-18 14:30:00", scrub_errors=0, scrub_in_progress=False]
```

**Logged fields per pool:**
- `pool_name` - Name of the pool
- `health` - Health status (ONLINE, DEGRADED, FAULTED, etc.)
- `capacity_percent` - Used capacity percentage
- `size` - Total pool size (human-readable)
- `allocated` - Allocated/used space (human-readable)
- `free` - Free space available (human-readable)
- `read_errors` - Read I/O error count
- `write_errors` - Write I/O error count
- `checksum_errors` - Checksum error count (data corruption)
- `last_scrub` - Timestamp of last scrub or "Never"
- `scrub_errors` - Errors found during last scrub
- `scrub_in_progress` - Whether scrub is currently running

### Viewing Logs

#### Systemd Service Logs

When running as a systemd service, logs are sent to journald:

```bash
# Follow logs in real-time
sudo journalctl -u check_zpools -f

# View last 50 entries
sudo journalctl -u check_zpools -n 50

# View last 100 entries
sudo journalctl -u check_zpools -n 100

# View logs since boot
sudo journalctl -u check_zpools -b

# View logs for specific time range
sudo journalctl -u check_zpools --since "2025-11-18 00:00:00" --until "2025-11-18 23:59:59"

# Filter by log level
sudo journalctl -u check_zpools -p info     # INFO and above
sudo journalctl -u check_zpools -p warning  # WARNING and above
sudo journalctl -u check_zpools -p err      # ERROR and above

# Search for specific pool
sudo journalctl -u check_zpools | grep "Pool: rpool"

# Export logs to file
sudo journalctl -u check_zpools > /tmp/check_zpools.log
```

#### Foreground Mode Logs

When running in foreground, logs go to stdout:

```bash
# Run with default INFO level
check_zpools daemon --foreground

# Run with DEBUG level for troubleshooting
LOG_CONSOLE_LEVEL=DEBUG check_zpools daemon --foreground

# Redirect to file
check_zpools daemon --foreground > /var/log/check_zpools.log 2>&1

# Follow logs with tail
check_zpools daemon --foreground 2>&1 | tee -a /var/log/check_zpools.log
```

### Example Log Output

Here's what a typical check cycle looks like in the logs:

```
[2025-11-18 14:35:00] INFO: Starting ZFS pool monitoring daemon [version="2.1.1", interval_seconds=300, pools="all"]
[2025-11-18 14:35:00] INFO: PoolMonitor initialized [capacity_warning=80, capacity_critical=90, scrub_max_age_days=30]
[2025-11-18 14:35:05] INFO: Check cycle completed [check_number=1, uptime="0m", pools_checked=2, issues_found=0, severity="OK"]
[2025-11-18 14:35:05] INFO: Pool: rpool [health="ONLINE", capacity_percent="45.2%", size="1.00 TB", allocated="452.00 GB", free="548.00 GB", read_errors=0, write_errors=0, checksum_errors=0, last_scrub="2025-11-18 02:00:00", scrub_errors=0, scrub_in_progress=False]
[2025-11-18 14:35:05] INFO: Pool: backup [health="ONLINE", capacity_percent="62.5%", size="2.00 TB", allocated="1.25 TB", free="750.00 GB", read_errors=0, write_errors=0, checksum_errors=0, last_scrub="2025-11-17 02:00:00", scrub_errors=0, scrub_in_progress=False]
[2025-11-18 14:40:05] INFO: Check cycle completed [check_number=2, uptime="5m", pools_checked=2, issues_found=0, severity="OK"]
[2025-11-18 14:40:05] INFO: Pool: rpool [health="ONLINE", capacity_percent="45.2%", ...]
[2025-11-18 14:40:05] INFO: Pool: backup [health="ONLINE", capacity_percent="62.5%", ...]
```

### Log Analysis Tips

#### Monitor Daemon Health

```bash
# Check daemon uptime
sudo journalctl -u check_zpools | grep "uptime=" | tail -1

# Count total checks performed
sudo journalctl -u check_zpools | grep "Check cycle completed" | wc -l

# View last check statistics
sudo journalctl -u check_zpools | grep "Check cycle completed" | tail -1
```

#### Track Pool Capacity Over Time

```bash
# Extract capacity percentages for specific pool
sudo journalctl -u check_zpools | grep 'Pool: rpool' | grep -o 'capacity_percent="[^"]*"'

# Monitor capacity growth
sudo journalctl -u check_zpools --since "1 week ago" | grep 'Pool: rpool' | grep -o 'capacity_percent="[^"]*"'
```

#### Find Issues

```bash
# Find all warnings
sudo journalctl -u check_zpools -p warning

# Find cycles with issues
sudo journalctl -u check_zpools | grep 'issues_found=[1-9]'

# Find error events
sudo journalctl -u check_zpools | grep -E '(read_errors=[1-9]|write_errors=[1-9]|checksum_errors=[1-9])'
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

## Future Enhancements

We're always looking to improve `check_zpools`! Here are some planned features and enhancement requests for future versions:

- **Web dashboard** for status visualization
- **Metrics export** in Prometheus format
- **Remote ZFS pools** monitoring via SSH
- **Integration** with monitoring systems (Nagios, Zabbix, etc.)
- **Snapshot monitoring** and management capabilities
- **Dataset-level monitoring** (in addition to pools)

Have an idea or feature request? Please open an issue on GitHub!

---

## Support

- **Issues:** https://github.com/bitranox/check_zpools/issues
- **Discussions:** https://github.com/bitranox/check_zpools/discussions
- **Documentation:** https://github.com/bitranox/check_zpools/tree/main/docs
