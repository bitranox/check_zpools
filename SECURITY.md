# Security Policy

## Supported Versions

We release patches for security vulnerabilities for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 1.x.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

We take the security of check_zpools seriously. If you discover a security vulnerability, please follow these steps:

### 1. Do Not Open a Public Issue

**Please do not report security vulnerabilities through public GitHub issues.**

### 2. Report Privately

Send an email to the project maintainers with:
- A description of the vulnerability
- Steps to reproduce the issue
- Potential impact
- Suggested fix (if available)

**Contact:** Create a private security advisory on GitHub or contact the repository owner directly.

### 3. What to Expect

- **Acknowledgment:** Within 48 hours
- **Initial Assessment:** Within 1 week
- **Status Updates:** Every 1-2 weeks
- **Fix Timeline:** Varies by severity
  - **Critical:** 1-7 days
  - **High:** 1-2 weeks
  - **Medium:** 2-4 weeks
  - **Low:** Next regular release

### 4. Disclosure Policy

- We follow **coordinated disclosure**
- Fixes will be released before public disclosure
- We will credit researchers in release notes (unless you prefer to remain anonymous)
- Public disclosure will occur after a fix is available

## Security Considerations

### SMTP Credentials

**Risk:** SMTP passwords stored in configuration files or environment variables could be exposed.

**Mitigations:**
- Store passwords in environment variables, not config files
- Use restrictive file permissions (0600) for config files containing credentials
- Consider using app-specific passwords (Gmail, Office 365)
- Rotate credentials regularly
- Use encrypted connections (TLS/STARTTLS)

### ZFS Command Execution

**Risk:** The application executes `zpool` commands with subprocess.

**Mitigations:**
- Commands use argument lists, not shell=True (prevents command injection)
- Commands are hardcoded (`zpool list`, `zpool status`)
- No user input is passed to ZFS commands
- Requires appropriate privileges (typically root or sudoers)

### Email Content Injection

**Risk:** Pool data could contain malicious content injected via ZFS pool names.

**Mitigations:**
- Pool names are validated by ZFS itself
- Email formatting escapes special characters
- HTML email uses proper escaping
- Subject lines are constructed from trusted templates

### Configuration File Security

**Best Practices:**
```bash
# Application config (may contain SMTP credentials)
chmod 600 /etc/check_zpools/config.toml
chown root:root /etc/check_zpools/config.toml

# User config
chmod 600 ~/.config/check_zpools/config.toml

# Systemd service runs as root (required for ZFS access)
# Ensure service file permissions prevent tampering
chmod 644 /etc/systemd/system/check-zpools.service
chown root:root /etc/systemd/system/check-zpools.service
```

### Daemon Mode Security

**Considerations:**
- Daemon runs continuously with elevated privileges
- Alert state files may contain pool information
- Logs may contain pool names and health details

**Best Practices:**
- Run daemon under dedicated service account (if possible)
- Secure log destinations (journald, syslog)
- Rotate state files with appropriate permissions
- Monitor daemon process for unexpected behavior

### Network Security

**Email Transmission:**
- Always use TLS/STARTTLS for SMTP connections
- Verify SMTP server certificates (set `verify_ssl: true`)
- Use authentication for SMTP servers
- Avoid plain text credentials in network captures

**Firewall Rules:**
- Allow outbound SMTP (port 587 for STARTTLS, 465 for SMTPS)
- Block inbound connections (daemon doesn't listen on network)

## Dependency Security

### Automated Scanning

We use multiple tools to monitor dependencies:

- **pip-audit:** Checks for known vulnerabilities in Python packages
- **Bandit:** Static analysis for security issues in code
- **Snyk:** GitHub integration for dependency monitoring
- **Dependabot:** Automatic dependency update PRs

### Audit Results

Run local security audit:
```bash
# Full test suite includes security scans
make test

# Run only security scans
bandit -r src/check_zpools
pip-audit --skip-editable
```

### Known Exceptions

Check `pyproject.toml` for `[tool.bandit]` exclusions with justification comments.

## Security Updates

### Update Notifications

- Security releases are tagged with `SECURITY` in release notes
- Critical vulnerabilities are announced in README
- GitHub Security Advisories used for severe issues

### Staying Updated

```bash
# Check current version
check_zpools info

# Update to latest version
pip install --upgrade check-zpools

# Or with pipx
pipx upgrade check-zpools

# Or with uv
uv tool upgrade check-zpools
```

## Security Best Practices for Users

1. **Keep check_zpools updated** to the latest version
2. **Use environment variables** for sensitive configuration (SMTP passwords)
3. **Restrict configuration file permissions** to prevent unauthorized access
4. **Enable TLS/STARTTLS** for all SMTP connections
5. **Rotate credentials regularly** (SMTP passwords, app-specific passwords)
6. **Monitor daemon logs** for unexpected errors or behavior
7. **Review alert recipients** to ensure emails go to authorized personnel only
8. **Use app-specific passwords** for Gmail and Office 365 (not account passwords)
9. **Audit dependencies** periodically with `pip-audit`
10. **Review systemd service configuration** to ensure it runs with minimal necessary privileges

## Secure Configuration Example

```toml
# /etc/check_zpools/config.toml
# chmod 600, owner root:root

[email]
# Use environment variable for password (recommended)
# smtp_password is NOT set here
smtp_hosts = ["smtp.gmail.com:587"]
smtp_username = "zfs-monitor@example.com"
from_address = "zfs-monitor@example.com"
use_tls = false
use_starttls = true
verify_ssl = true
timeout = 30

[alerts]
recipients = ["ops-team@example.com"]

[daemon]
check_interval_seconds = 300
pools_to_monitor = []  # Empty = monitor all pools
send_recovery_emails = true
```

```bash
# Environment variable (recommended for secrets)
export CHECK_ZPOOLS_EMAIL_SMTP_PASSWORD="your-app-specific-password"

# Start daemon
check_zpools daemon --foreground
```

## Additional Resources

- [Python Security Best Practices](https://python.readthedocs.io/en/latest/library/security_warnings.html)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [CWE Common Weakness Enumeration](https://cwe.mitre.org/)

## Acknowledgments

We appreciate the security research community's efforts to improve software security. Responsible disclosure helps keep all users safe.

Thank you for helping make check_zpools more secure!
