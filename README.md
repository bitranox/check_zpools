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

`check_zpools` is a template CLI application demonstrating configuration management and structured logging. It showcases rich-click for ergonomics and lib_cli_exit_tools for exits, providing a solid foundation for building CLI applications.
- CLI entry point styled with rich-click (rich output + click ergonomics).
- Layered configuration system with lib_layered_config (defaults → app → host → user → .env → env).
- Rich structured logging with lib_log_rich (console, journald, eventlog, Graylog/GELF).
- Exit-code and messaging helpers powered by lib_cli_exit_tools.
- Metadata helpers ready for packaging, testing, and release automation.

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
[INSTALL.md](INSTALL.md). All supported methods register both the
`check_zpools` and `bitranox-template-cli-app-config-log-mail` commands on your PATH.

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

The CLI leverages [rich-click](https://github.com/ewels/rich-click) so help output, validation errors, and prompts render with Rich styling while keeping the familiar click ergonomics.

### Available Commands

```bash
# Display package information
bitranox-template-cli-app-config-log info

# Test commands for development
bitranox-template-cli-app-config-log hello
bitranox-template-cli-app-config-log fail
bitranox-template-cli-app-config-log --traceback fail

# Configuration management
bitranox-template-cli-app-config-log config                    # Show current configuration
bitranox-template-cli-app-config-log config --format json      # Show as JSON
bitranox-template-cli-app-config-log config --section lib_log_rich  # Show specific section
bitranox-template-cli-app-config-log config-deploy --target user    # Deploy config to user directory
bitranox-template-cli-app-config-log config-deploy --target user --target host  # Deploy to multiple locations

# All commands work with any entry point
python -m check_zpools info
uvx check_zpools info
```

### Email Sending

The application includes email sending capabilities via [btx-lib-mail](https://pypi.org/project/btx-lib-mail/), supporting both simple notifications and rich HTML emails with attachments.

#### Email Configuration

Configure email settings via environment variables, `.env` file, or configuration files:

**Environment Variables:**
```bash
export BITRANOX_TEMPLATE_CLI_APP_CONFIG_LOG_MAIL_EMAIL_SMTP_HOSTS="smtp.gmail.com:587,smtp.backup.com:587"
export BITRANOX_TEMPLATE_CLI_APP_CONFIG_LOG_MAIL_EMAIL_FROM_ADDRESS="alerts@myapp.com"
export BITRANOX_TEMPLATE_CLI_APP_CONFIG_LOG_MAIL_EMAIL_SMTP_USERNAME="your-email@gmail.com"
export BITRANOX_TEMPLATE_CLI_APP_CONFIG_LOG_MAIL_EMAIL_SMTP_PASSWORD="your-app-password"
export BITRANOX_TEMPLATE_CLI_APP_CONFIG_LOG_MAIL_EMAIL_USE_STARTTLS="true"
export BITRANOX_TEMPLATE_CLI_APP_CONFIG_LOG_MAIL_EMAIL_TIMEOUT="60.0"
```

**Configuration File** (`~/.config/bitranox-template-cli-app-config-log/config.toml`):
```toml
[email]
smtp_hosts = ["smtp.gmail.com:587", "smtp.backup.com:587"]  # Fallback to backup if primary fails
from_address = "alerts@myapp.com"
smtp_username = "myuser@gmail.com"
smtp_password = "secret_password"  # Consider using environment variables for sensitive data
use_starttls = true
timeout = 60.0
```

**`.env` File:**
```bash
# Email configuration for local testing
BITRANOX_TEMPLATE_CLI_APP_CONFIG_LOG_MAIL_EMAIL_SMTP_HOSTS=smtp.gmail.com:587
BITRANOX_TEMPLATE_CLI_APP_CONFIG_LOG_MAIL_EMAIL_FROM_ADDRESS=noreply@example.com
```

#### Gmail Configuration Example

For Gmail, create an [App Password](https://support.google.com/accounts/answer/185833) instead of using your account password:

```bash
BITRANOX_TEMPLATE_CLI_APP_CONFIG_LOG_MAIL_EMAIL_SMTP_HOSTS=smtp.gmail.com:587
BITRANOX_TEMPLATE_CLI_APP_CONFIG_LOG_MAIL_EMAIL_FROM_ADDRESS=your-email@gmail.com
BITRANOX_TEMPLATE_CLI_APP_CONFIG_LOG_MAIL_EMAIL_SMTP_USERNAME=your-email@gmail.com
BITRANOX_TEMPLATE_CLI_APP_CONFIG_LOG_MAIL_EMAIL_SMTP_PASSWORD=your-16-char-app-password
```

#### Send Simple Email

```bash
# Send basic email to one recipient
bitranox-template-cli-app-config-log send-email \
    --to recipient@example.com \
    --subject "Test Email" \
    --body "Hello from bitranox!"

# Send to multiple recipients
bitranox-template-cli-app-config-log send-email \
    --to user1@example.com \
    --to user2@example.com \
    --subject "Team Update" \
    --body "Please review the latest changes"
```

#### Send HTML Email with Attachments

```bash
bitranox-template-cli-app-config-log send-email \
    --to recipient@example.com \
    --subject "Monthly Report" \
    --body "Please find the monthly report attached." \
    --body-html "<h1>Monthly Report</h1><p>See attached PDF for details.</p>" \
    --attachment report.pdf \
    --attachment data.csv
```

#### Send Notifications

For simple plain-text notifications, use the convenience command:

```bash
# Single recipient
bitranox-template-cli-app-config-log send-notification \
    --to ops@example.com \
    --subject "Deployment Success" \
    --message "Application deployed successfully to production at $(date)"

# Multiple recipients
bitranox-template-cli-app-config-log send-notification \
    --to admin1@example.com \
    --to admin2@example.com \
    --subject "System Alert" \
    --message "Database backup completed successfully"
```

#### Programmatic Email Usage

```python
from check_zpools.mail import EmailConfig, send_email, send_notification

# Configure email
config = EmailConfig(
    smtp_hosts=["smtp.gmail.com:587"],
    from_address="alerts@myapp.com",
    smtp_username="myuser@gmail.com",
    smtp_password="app-password",
    timeout=60.0,
)

# Send simple email
send_email(
    config=config,
    recipients="recipient@example.com",
    subject="Test Email",
    body="Hello from Python!",
)

# Send email with HTML and attachments
from pathlib import Path
send_email(
    config=config,
    recipients=["user1@example.com", "user2@example.com"],
    subject="Report",
    body="See attached report",
    body_html="<h1>Report</h1><p>Details in attachment</p>",
    attachments=[Path("report.pdf")],
)

# Send notification
send_notification(
    config=config,
    recipients="ops@example.com",
    subject="Deployment Complete",
    message="Production deployment finished successfully",
)
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

### Configuration Management

The application uses [lib_layered_config](https://github.com/bitranox/lib_layered_config) for hierarchical configuration with the following precedence (lowest to highest):

**defaults → app → host → user → .env → environment variables**

#### Configuration Locations

Platform-specific paths:
- **Linux (user)**: `~/.config/bitranox-template-cli-app-config-log/config.toml`
- **Linux (app)**: `/etc/xdg/bitranox-template-cli-app-config-log/config.toml`
- **Linux (host)**: `/etc/bitranox-template-cli-app-config-log/hosts/{hostname}.toml`
- **macOS (user)**: `~/Library/Application Support/bitranox/Bitranox Template CLI App Config Log/config.toml`
- **Windows (user)**: `%APPDATA%\bitranox\Bitranox Template CLI App Config Log\config.toml`

#### View Configuration

```bash
# Show merged configuration from all sources
bitranox-template-cli-app-config-log config

# Show as JSON for scripting
bitranox-template-cli-app-config-log config --format json

# Show specific section only
bitranox-template-cli-app-config-log config --section lib_log_rich
```

#### Deploy Configuration Files

```bash
# Create user configuration file
bitranox-template-cli-app-config-log config-deploy --target user

# Deploy to system-wide location (requires privileges)
sudo bitranox-template-cli-app-config-log config-deploy --target app

# Deploy to multiple locations at once
bitranox-template-cli-app-config-log config-deploy --target user --target host

# Overwrite existing configuration
bitranox-template-cli-app-config-log config-deploy --target user --force
```

#### Environment Variable Overrides

Configuration can be overridden via environment variables using two methods:

**Method 1: Native lib_log_rich variables (highest precedence)**
```bash
LOG_CONSOLE_LEVEL=DEBUG bitranox-template-cli-app-config-log hello
LOG_ENABLE_GRAYLOG=true LOG_GRAYLOG_ENDPOINT="logs.example.com:12201" bitranox-template-cli-app-config-log hello
```

**Method 2: Application-prefixed variables**
```bash
BITRANOX_TEMPLATE_CLI_APP_CONFIG_LOG_LIB_LOG_RICH_CONSOLE_LEVEL=DEBUG bitranox-template-cli-app-config-log hello
```

#### .env File Support

Create a `.env` file in your project directory for local development:

```bash
# .env
LOG_CONSOLE_LEVEL=DEBUG
LOG_CONSOLE_FORMAT_PRESET=short
LOG_ENABLE_GRAYLOG=false
```

The application automatically discovers and loads `.env` files from the current directory or parent directories.

### Library Use

You can import the documented helpers directly:

```python
import check_zpools as btcacl

btcacl.emit_greeting()
try:
    btcacl.raise_intentional_failure()
except RuntimeError as exc:
    print(f"caught expected failure: {exc}")

btcacl.print_info()
```


## Further Documentation

- [Install Guide](INSTALL.md)
- [Development Handbook](DEVELOPMENT.md)
- [Contributor Guide](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)
- [Module Reference](docs/systemdesign/module_reference.md)
- [License](LICENSE)
